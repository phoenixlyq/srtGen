# -*- coding: utf-8 -*-
import audioop
import math
import os
import wave
from typing import Callable, List, Tuple

from app_models import AudioSegment


def build_audio_segments(
    wav_path: str,
    duration: float,
    temp_root: str,
    segment_len: float,
    use_segment: bool,
    use_vad: bool,
    vad_frame_ms: int,
    vad_threshold_db: float,
    vad_min_speech_sec: float,
    vad_min_silence_sec: float,
    vad_pad_sec: float,
    min_segment_sec: float,
    overlap_sec: float,
    logger: Callable[[str], None],
) -> List[AudioSegment]:
    logger(
        f"分段：{'ON' if use_segment else 'OFF'}，时长={segment_len:.0f}s；"
        f"VAD：{'ON' if use_vad else 'OFF'} (th={vad_threshold_db}dB)"
    )

    if not use_segment and not use_vad:
        return [AudioSegment(start=0.0, end=duration, path=wav_path)]

    if use_vad:
        regions = detect_speech_regions(
            wav_path=wav_path,
            duration=duration,
            vad_frame_ms=vad_frame_ms,
            vad_threshold_db=vad_threshold_db,
            vad_min_speech_sec=vad_min_speech_sec,
            vad_min_silence_sec=vad_min_silence_sec,
            logger=logger,
        )
        if not regions:
            if use_segment:
                logger("VAD 未检测到语音，回退到固定分段。")
                bounds = fixed_segments(duration, segment_len, min_segment_sec, overlap_sec)
            else:
                return []
        elif use_segment:
            bounds = pack_regions_to_segments(
                regions=regions,
                duration=duration,
                max_len=segment_len,
                pad_sec=vad_pad_sec,
                min_segment_sec=min_segment_sec,
                overlap_sec=overlap_sec,
            )
        else:
            bounds = [
                (max(0.0, start - vad_pad_sec), min(duration, end + vad_pad_sec))
                for start, end in regions
            ]
    else:
        bounds = fixed_segments(duration, segment_len, min_segment_sec, overlap_sec)

    if not bounds:
        return []

    if len(bounds) == 1:
        start, end = bounds[0]
        if start <= 0.01 and end >= (duration - 0.01):
            return [AudioSegment(start=start, end=end, path=wav_path)]

    seg_dir = os.path.join(temp_root, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    audio_segments: List[AudioSegment] = []
    for idx, (start, end) in enumerate(bounds, 1):
        if end - start < min_segment_sec:
            continue
        seg_path = os.path.join(seg_dir, f"seg_{idx:04d}.wav")
        write_wav_segment(wav_path, start, end, seg_path)
        audio_segments.append(AudioSegment(start=start, end=end, path=seg_path))

    return audio_segments


def detect_speech_regions(
    wav_path: str,
    duration: float,
    vad_frame_ms: int,
    vad_threshold_db: float,
    vad_min_speech_sec: float,
    vad_min_silence_sec: float,
    logger: Callable[[str], None],
) -> List[Tuple[float, float]]:
    try:
        with wave.open(wav_path, "rb") as reader:
            rate = reader.getframerate()
            channels = reader.getnchannels()
            sampwidth = reader.getsampwidth()
            if channels != 1:
                logger("检测到非单声道，VAD 可能不稳定。")
            frame_samples = max(1, int(rate * vad_frame_ms / 1000.0))
            frame_bytes = frame_samples * sampwidth * channels
            max_val = float(2 ** (8 * sampwidth - 1))
            is_speech_flags: List[bool] = []
            while True:
                data = reader.readframes(frame_samples)
                if not data:
                    break
                if len(data) < frame_bytes:
                    data = data.ljust(frame_bytes, b"\x00")
                rms = audioop.rms(data, sampwidth)
                db = 20.0 * math.log10((rms / max_val) + 1e-10)
                is_speech_flags.append(db >= vad_threshold_db)
    except Exception as exc:
        logger(f"VAD 处理失败，将使用固定分段：{exc}")
        return []

    frame_sec = vad_frame_ms / 1000.0
    regions: List[Tuple[float, float]] = []
    idx = 0
    total_flags = len(is_speech_flags)
    while idx < total_flags:
        if not is_speech_flags[idx]:
            idx += 1
            continue
        start_idx = idx
        while idx < total_flags and is_speech_flags[idx]:
            idx += 1
        end_idx = idx
        start_sec = start_idx * frame_sec
        end_sec = end_idx * frame_sec
        if end_sec - start_sec >= vad_min_speech_sec:
            regions.append((start_sec, min(end_sec, duration)))

    merged: List[Tuple[float, float]] = []
    for start, end in regions:
        if not merged:
            merged.append((start, end))
            continue
        prev_start, prev_end = merged[-1]
        if start - prev_end <= vad_min_silence_sec:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    if merged:
        total_speech = sum(max(0.0, end - start) for start, end in merged)
        logger(f"VAD 语音区间数：{len(merged)}，总语音时长：{total_speech:.1f}s")
    else:
        logger("VAD 未检测到有效语音区间。")

    return merged


def pack_regions_to_segments(
    regions: List[Tuple[float, float]],
    duration: float,
    max_len: float,
    pad_sec: float,
    min_segment_sec: float,
    overlap_sec: float,
) -> List[Tuple[float, float]]:
    segments: List[Tuple[float, float]] = []
    cur_start = None
    cur_end = None
    for start, end in regions:
        start = max(0.0, start - pad_sec)
        end = min(duration, end + pad_sec)
        if end - start >= max_len:
            if cur_start is not None:
                segments.append((cur_start, cur_end))
                cur_start, cur_end = None, None
            seg_start = start
            while seg_start < end:
                seg_end = min(end, seg_start + max_len)
                if seg_end - seg_start >= min_segment_sec:
                    segments.append((seg_start, seg_end))
                if seg_end >= end:
                    break
                seg_start = max(start, seg_end - overlap_sec)
            continue

        if cur_start is None:
            cur_start, cur_end = start, end
        elif end - cur_start <= max_len:
            cur_end = end
        else:
            segments.append((cur_start, cur_end))
            cur_start, cur_end = start, end

    if cur_start is not None:
        segments.append((cur_start, cur_end))

    return segments


def fixed_segments(
    duration: float, segment_len: float, min_segment_sec: float, overlap_sec: float
) -> List[Tuple[float, float]]:
    segments: List[Tuple[float, float]] = []
    if duration <= 0:
        return segments
    overlap = overlap_sec if segment_len > overlap_sec else 0.0
    start = 0.0
    while start < duration:
        end = min(duration, start + segment_len)
        if end - start >= min_segment_sec:
            segments.append((start, end))
        if end >= duration:
            break
        start = max(0.0, end - overlap)
    return segments


def write_wav_segment(wav_path: str, start: float, end: float, out_path: str) -> None:
    with wave.open(wav_path, "rb") as reader:
        rate = reader.getframerate()
        channels = reader.getnchannels()
        sampwidth = reader.getsampwidth()
        total_frames = reader.getnframes()
        total_duration = total_frames / float(rate or 1)
        start = max(0.0, min(start, total_duration))
        end = max(start, min(end, total_duration))
        start_frame = int(start * rate)
        end_frame = int(end * rate)
        reader.setpos(max(0, min(start_frame, total_frames)))
        frames = reader.readframes(max(0, end_frame - start_frame))

    with wave.open(out_path, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sampwidth)
        writer.setframerate(rate)
        writer.writeframes(frames)
