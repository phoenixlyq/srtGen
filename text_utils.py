# -*- coding: utf-8 -*-
import gzip
import io
import re
from typing import List, Tuple

from app_models import Segment


def is_repetitive_text(
    text: str,
    repeat_sentence_count: int,
    ngram_min_unique_ratio: float,
    gzip_ratio_threshold: float,
) -> bool:
    if not text:
        return False
    normalized = re.sub(r"\s+", "", text).strip()
    if len(normalized) < 12:
        return False

    sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]", text) if s.strip()]
    counts = {}
    max_repeat = 0
    for sent in sentences:
        sent_norm = re.sub(r"\s+", "", sent)
        if len(sent_norm) < 4:
            continue
        counts[sent_norm] = counts.get(sent_norm, 0) + 1
        if counts[sent_norm] > max_repeat:
            max_repeat = counts[sent_norm]
    if max_repeat >= repeat_sentence_count:
        return True

    unique_ratio = ngram_unique_ratio(normalized, 3)
    if unique_ratio < ngram_min_unique_ratio:
        return True

    if gzip_ratio(normalized) > gzip_ratio_threshold:
        return True

    return False


def ngram_unique_ratio(text: str, n: int) -> float:
    if len(text) < n:
        return 1.0
    total = len(text) - n + 1
    grams = {text[i : i + n] for i in range(total)}
    return len(grams) / float(total or 1)


def gzip_ratio(text: str) -> float:
    raw = text.encode("utf-8", errors="ignore")
    if not raw:
        return 0.0
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as handle:
        handle.write(raw)
    compressed = len(buffer.getvalue())
    if compressed == 0:
        return 0.0
    return len(raw) / float(compressed)


def dedupe_repetitive_segments(seg_items: List[Segment]) -> List[Segment]:
    if not seg_items:
        return []
    seen = set()
    filtered: List[Segment] = []
    for seg in seg_items:
        norm = re.sub(r"\s+", "", seg.text)
        if len(norm) < 2:
            filtered.append(seg)
            continue
        if norm in seen:
            continue
        seen.add(norm)
        filtered.append(seg)
    return filtered


def trim_overlap_prefix(prev_text: str, curr_text: str, min_match: int, max_match: int) -> str:
    if not prev_text or not curr_text:
        return curr_text
    prev_norm, _ = normalize_with_map(prev_text)
    curr_norm, curr_map = normalize_with_map(curr_text)
    if not prev_norm or not curr_norm:
        return curr_text
    max_len = min(max_match, len(prev_norm), len(curr_norm))
    for size in range(max_len, min_match - 1, -1):
        if prev_norm[-size:] == curr_norm[:size]:
            if size - 1 < len(curr_map):
                cut = curr_map[size - 1] + 1
                return curr_text[cut:].lstrip()
    return curr_text


def normalize_with_map(text: str) -> Tuple[str, List[int]]:
    normalized = []
    mapping: List[int] = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        normalized.append(ch)
        mapping.append(idx)
    return "".join(normalized), mapping
