# -*- coding: utf-8 -*-
import json
import re
import threading
from typing import Callable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

SEP_TOKEN = "<<<LINE>>>"
HEARTBEAT_INTERVAL = 12.0
SYSTEM_TRANSLATE_PROMPT = (
    "You are a translation engine. Follow the user's instructions exactly. "
    "Reply with only the translated text lines and no extra commentary or tags."
)

DEFAULT_TRANSLATE_PROMPT = (
    "You are a professional subtitle translator. Target language: {target}.\n"
    "Translate the following subtitle lines. Keep the line count and order exactly the same.\n"
    "Output only the translated text lines with no numbering or extra text.\n"
    "Separate each line with the token {sep} and do not add extra lines.\n"
    "Keep the token [[LB]] unchanged.\n"
    "Do NOT output any tags such as <think>, <INPUT>, <TRANSLATE_TEXT>.\n"
    "Lines:\n"
    "{text}"
)


class OllamaTranslator:
    def __init__(
        self,
        base_url: str,
        model: str,
        log: Callable[[str], None],
        log_error: Callable[[str], None],
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._log = log
        self._log_error = log_error
        self.timeout = timeout

    def translate_texts(
        self,
        texts: List[str],
        target_lang: str,
        prompt_template: str,
        batch_size: int,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        if not texts:
            return []
        if not target_lang:
            return texts[:]
        if not prompt_template.strip():
            prompt_template = DEFAULT_TRANSLATE_PROMPT

        batch_size = max(1, int(batch_size or 1))
        results: List[str] = []
        total = len(texts)
        index = 0
        stop_heartbeat = threading.Event()
        progress_state = {"done": 0}

        def heartbeat() -> None:
            while not stop_heartbeat.wait(HEARTBEAT_INTERVAL):
                done = progress_state["done"]
                self._log(f"Translating... {done}/{total}")

        if total > 0:
            threading.Thread(target=heartbeat, daemon=True).start()

        try:
            while index < total:
                batch = texts[index : index + batch_size]
                translated = self._translate_batch(batch, target_lang, prompt_template)
                if translated is None:
                    self._log("批次翻译行数不匹配，尝试逐行翻译。")
                    translated = []
                    for item in batch:
                        translated.append(self._translate_single(item, target_lang, prompt_template))
                results.extend(translated)
                index += batch_size
                progress_state["done"] = min(index, total)
                if progress:
                    progress(min(index, total), total)
        finally:
            stop_heartbeat.set()
        return results

    def _translate_single(self, text: str, target_lang: str, prompt_template: str) -> str:
        translated = self._translate_batch([text], target_lang, prompt_template)
        if translated and len(translated) == 1:
            return translated[0]
        self._log("逐行翻译失败，已回退原文。")
        return text

    def _translate_batch(self, texts: List[str], target_lang: str, prompt_template: str) -> Optional[List[str]]:
        safe_lines = [self._escape_line(t) for t in texts]
        joined = "\n".join(f"{idx + 1}\t{line}" for idx, line in enumerate(safe_lines))
        prompt = (
            prompt_template.replace("{target}", target_lang)
            .replace("{lang}", target_lang)
            .replace("{text}", joined)
            .replace("{batch_input}", joined)
        )
        if "{sep}" in prompt:
            prompt = prompt.replace("{sep}", SEP_TOKEN)
        else:
            prompt = f"{prompt.rstrip()}\nUse the separator token: {SEP_TOKEN}"

        try:
            content = self._call_ollama(prompt)
        except URLError as exc:
            self._log_error(f"Ollama 连接失败：{exc}")
            return None
        except Exception as exc:
            self._log_error(f"Ollama 调用失败：{exc}")
            return None

        content = self._sanitize_response(content)
        content = self._normalize_separator(content)

        lines = self._split_by_separator(content, len(texts))
        if lines is None:
            lines = self._extract_numbered_lines(content, len(texts))
        if lines is None:
            lines = self._parse_lines(content, len(texts))
        if lines is None or len(lines) != len(texts):
            if len(texts) == 1:
                single = self._extract_single_line(content)
                if single:
                    return [single]
            snippet = content.strip().replace("\n", " ")[:200]
            self._log_error(f"翻译解析失败，输出片段：{snippet}")
            return None
        return [self._restore_line(line) for line in lines]

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_TRANSLATE_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "stream": False,
        }
        url = f"{self.base_url}/chat/completions"
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]

    def _sanitize_response(self, content: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.S | re.I)
        cleaned = re.sub(r"<analysis>.*?</analysis>", "", cleaned, flags=re.S | re.I)
        cleaned = re.sub(r"^```.*?$", "", cleaned, flags=re.M)
        return cleaned.strip()

    def _normalize_separator(self, content: str) -> str:
        return re.sub(r"<+\s*LINE\s*>+", SEP_TOKEN, content, flags=re.I)

    def _extract_numbered_lines(self, content: str, expected: int) -> Optional[List[str]]:
        if expected <= 0:
            return []
        raw_lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        found: dict[int, str] = {}
        for line in raw_lines:
            match = re.match(r"^\s*(\d+)\s*[\t\.\-\)\:]\s*(.*)$", line)
            if not match:
                continue
            idx = int(match.group(1))
            text = self._clean_line(match.group(2))
            if idx not in found and text != "":
                found[idx] = text
        if len(found) < expected:
            return None
        return [found.get(i, "") for i in range(1, expected + 1)]

    def _split_by_separator(self, content: str, expected: int) -> Optional[List[str]]:
        if SEP_TOKEN not in content:
            return None
        parts = [self._clean_line(p.strip()) for p in content.split(SEP_TOKEN)]
        parts = self._trim_to_expected(parts, expected)
        if parts is None:
            return None
        return parts

    def _parse_lines(self, content: str, expected: int) -> Optional[List[str]]:
        raw_lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        lines: List[str] = []
        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                continue
            lines.append(self._clean_line(stripped))
        lines = self._trim_to_expected(lines, expected)
        if lines is None:
            return None
        return lines

    def _trim_to_expected(self, lines: List[str], expected: int) -> Optional[List[str]]:
        if expected <= 0:
            return []
        if len(lines) == expected:
            return lines
        if len(lines) > expected:
            return lines[-expected:]
        while lines and len(lines) > expected and lines[0] == "":
            lines.pop(0)
        while lines and len(lines) > expected and lines[-1] == "":
            lines.pop()
        if len(lines) == expected:
            return lines
        return None

    def _escape_line(self, text: str) -> str:
        return text.replace("\n", " [[LB]] ").strip()

    def _restore_line(self, text: str) -> str:
        return text.replace("[[LB]]", "\n").strip()

    def _clean_line(self, text: str) -> str:
        cleaned = re.sub(r"^\s*\d+[\.\-\)\:]\s*", "", text.strip())
        if "\t" in cleaned:
            cleaned = cleaned.split("\t", 1)[-1].strip()
        cleaned = cleaned.replace(SEP_TOKEN, " ")
        cleaned = re.sub(r"<+\s*LINE\s*>+", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"^[-•]\s*", "", cleaned)
        return cleaned.strip()

    def _extract_single_line(self, content: str) -> str:
        cleaned = self._sanitize_response(content)
        cleaned = self._normalize_separator(cleaned)
        cleaned = cleaned.replace(SEP_TOKEN, " ").strip()
        if not cleaned:
            return ""
        lines = [self._clean_line(l) for l in cleaned.replace("\r\n", "\n").split("\n") if l.strip()]
        if not lines:
            return ""
        if len(lines) == 1:
            return self._restore_line(lines[0])
        return self._restore_line(lines[-1])
