# -*- coding: utf-8 -*-
from typing import Callable, List, Tuple

from translator import OllamaTranslator


def translate_srt_file(
    input_path: str,
    output_path: str,
    target_lang: str,
    translator: OllamaTranslator,
    prompt_template: str,
    batch_size: int,
    log: Callable[[str], None],
    progress: Callable[[int, int], None] | None = None,
) -> str:
    content, encoding = _read_text(input_path)
    log(f"读取字幕：{input_path} (encoding={encoding})")
    blocks = _parse_srt(content)
    if not blocks:
        raise RuntimeError("未解析到有效字幕块。")

    texts = ["\n".join(lines).strip() for _, _, lines in blocks]
    translated = translator.translate_texts(
        texts,
        target_lang=target_lang,
        prompt_template=prompt_template,
        batch_size=batch_size,
        progress=progress,
    )

    if len(translated) != len(blocks):
        log("翻译行数不匹配，已使用原文输出。")
        translated = texts

    new_blocks: List[Tuple[str, str, List[str]]] = []
    for (idx_line, time_line, _lines), text in zip(blocks, translated):
        cleaned = text.strip()
        if cleaned:
            lines = cleaned.splitlines()
        else:
            lines = [""]
        new_blocks.append((idx_line, time_line, lines))

    output = _compose_srt(new_blocks)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(output)
    log(f"翻译完成：{output_path}")
    return output_path


def _read_text(path: str) -> Tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read(), encoding
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read(), "utf-8"


def _parse_srt(content: str) -> List[Tuple[str, str, List[str]]]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Tuple[str, str, List[str]]] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        index_line = lines[i].strip()
        i += 1
        if i >= len(lines):
            break
        time_line = lines[i].strip()
        i += 1
        text_lines: List[str] = []
        while i < len(lines) and lines[i].strip() != "":
            text_lines.append(lines[i])
            i += 1
        blocks.append((index_line, time_line, text_lines))
        while i < len(lines) and not lines[i].strip():
            i += 1
    return blocks


def _compose_srt(blocks: List[Tuple[str, str, List[str]]]) -> str:
    out_lines: List[str] = []
    for index_line, time_line, text_lines in blocks:
        out_lines.append(str(index_line))
        out_lines.append(time_line)
        if text_lines:
            out_lines.extend(text_lines)
        else:
            out_lines.append("")
        out_lines.append("")
    return "\n".join(out_lines).rstrip() + "\n"
