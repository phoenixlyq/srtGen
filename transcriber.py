# -*- coding: utf-8 -*-
import ctypes
import os
import shutil
import sys
from dataclasses import dataclass
from typing import List, Tuple

from app_models import Segment
from audio_utils import build_audio_segments
from text_utils import dedupe_repetitive_segments, is_repetitive_text, trim_overlap_prefix

SEGMENT_OVERLAP_SEC = 0.6
VAD_FRAME_MS = 30
VAD_THRESHOLD_DB = -35.0
VAD_MIN_SPEECH_SEC = 0.4
VAD_MIN_SILENCE_SEC = 0.5
VAD_PAD_SEC = 0.3
MIN_SEGMENT_SEC = 0.6
REPEAT_SENTENCE_COUNT = 3
REPEAT_NGRAM_MIN_UNIQUE_RATIO = 0.2
REPEAT_GZIP_RATIO_THRESHOLD = 2.4
MERGE_MIN_MATCH = 6
MERGE_MAX_MATCH = 20


@dataclass
class TranscribeConfig:
    model_path: str
    language: str
    no_context: bool
    no_speech_threshold: float
    logprob_threshold: float
    segment_enable: bool
    segment_len: float
    vad_enable: bool


class WhisperTranscriber:
    def __init__(self, base_dir: str, clr_module, log, log_error, set_progress, format_ts) -> None:
        self.base_dir = base_dir
        self.clr = clr_module
        self._log = log
        self._log_error = log_error
        self._set_progress = set_progress
        self._format_ts = format_ts
        self.dll_dir_handles: list = []

    def extract_audio(self, video_path: str, wav_path: str, trim_silence: bool) -> float:
        from moviepy import VideoFileClip

        with VideoFileClip(video_path) as clip:
            if clip.audio is None:
                raise RuntimeError("视频中未检测到音频轨道。")
            duration = float(clip.duration or 0)
            ffmpeg_params = ["-ac", "1"]
            if trim_silence:
                self._log("启用静音过滤（首尾）。")
                ffmpeg_params += [
                    "-af",
                    "silenceremove=start_periods=1:start_duration=0.3:start_threshold=-40dB:"
                    "stop_periods=1:stop_duration=0.5:stop_threshold=-40dB",
                ]
            clip.audio.write_audiofile(
                wav_path,
                fps=16000,
                nbytes=2,
                codec="pcm_s16le",
                ffmpeg_params=ffmpeg_params,
                logger=None,
            )
        self._log("音频提取完成。")
        return duration

    def transcribe(self, wav_path: str, duration: float, config: TranscribeConfig, temp_root: str) -> List[Segment]:
        factory_cls, _event_args_type = self._load_whisper_factory()
        factory = None
        try:
            from Whisper.net import WhisperFactoryOptions  # type: ignore

            options = WhisperFactoryOptions()
            options.UseGpu = True
            options.GpuDevice = 0
            options.DelayInitialization = False
            factory = factory_cls.FromPath(config.model_path, options)
        except Exception:
            factory = factory_cls.FromPath(config.model_path)

        segments: List[Segment] = []
        try:
            audio_segments = build_audio_segments(
                wav_path=wav_path,
                duration=duration,
                temp_root=temp_root,
                segment_len=max(10.0, float(config.segment_len)),
                use_segment=bool(config.segment_enable),
                use_vad=bool(config.vad_enable),
                vad_frame_ms=VAD_FRAME_MS,
                vad_threshold_db=VAD_THRESHOLD_DB,
                vad_min_speech_sec=VAD_MIN_SPEECH_SEC,
                vad_min_silence_sec=VAD_MIN_SILENCE_SEC,
                vad_pad_sec=VAD_PAD_SEC,
                min_segment_sec=MIN_SEGMENT_SEC,
                overlap_sec=SEGMENT_OVERLAP_SEC,
                logger=self._log,
            )
            if not audio_segments:
                self._log("未找到有效语音分段。")
                return []

            self._log(f"分段数量：{len(audio_segments)}")
            for idx, audio_seg in enumerate(audio_segments, 1):
                seg_len = max(0.0, audio_seg.end - audio_seg.start)
                self._log(
                    f"[{idx}/{len(audio_segments)}] "
                    f"{self._format_ts(audio_seg.start)} --> {self._format_ts(audio_seg.end)}"
                    f"  ({seg_len:.1f}s)"
                )

                seg_items = self._process_segment(
                    factory=factory,
                    audio_seg=audio_seg,
                    language=config.language,
                    duration=duration,
                    no_context=config.no_context,
                    no_speech_threshold=config.no_speech_threshold,
                    logprob_threshold=config.logprob_threshold,
                    safe_mode=False,
                )
                merged_text = "".join(seg.text for seg in seg_items)

                if is_repetitive_text(
                    merged_text,
                    REPEAT_SENTENCE_COUNT,
                    REPEAT_NGRAM_MIN_UNIQUE_RATIO,
                    REPEAT_GZIP_RATIO_THRESHOLD,
                ):
                    self._log("检测到异常重复，正在使用保守参数重跑该段...")
                    seg_items = self._process_segment(
                        factory=factory,
                        audio_seg=audio_seg,
                        language=config.language,
                        duration=duration,
                        no_context=True,
                        no_speech_threshold=config.no_speech_threshold,
                        logprob_threshold=config.logprob_threshold,
                        safe_mode=True,
                    )
                    merged_text = "".join(seg.text for seg in seg_items)
                    if is_repetitive_text(
                        merged_text,
                        REPEAT_SENTENCE_COUNT,
                        REPEAT_NGRAM_MIN_UNIQUE_RATIO,
                        REPEAT_GZIP_RATIO_THRESHOLD,
                    ):
                        self._log("重跑后仍异常，仅保留重复内容的第一条。")
                        seg_items = dedupe_repetitive_segments(seg_items)
                        if not seg_items:
                            continue

                for seg in seg_items:
                    if segments:
                        if seg.text == segments[-1].text and seg.start <= (segments[-1].end + 0.05):
                            continue
                        merged_text = trim_overlap_prefix(
                            segments[-1].text, seg.text, MERGE_MIN_MATCH, MERGE_MAX_MATCH
                        )
                        if not merged_text.strip():
                            continue
                        if merged_text != seg.text:
                            seg = Segment(start=seg.start, end=seg.end, text=merged_text)
                    segments.append(seg)
        finally:
            try:
                factory.Dispose()
            except Exception:
                pass

        return segments

    def _process_segment(
        self,
        factory,
        audio_seg,
        language: str,
        duration: float,
        no_context: bool,
        no_speech_threshold: float,
        logprob_threshold: float,
        safe_mode: bool,
    ) -> List[Segment]:
        seg_items: List[Segment] = []
        last_text = ""
        repeat_count = 0

        def on_segment(segment) -> None:
            nonlocal last_text, repeat_count
            start = self._timespan_to_seconds(getattr(segment, "Start", 0)) + audio_seg.start
            end = self._timespan_to_seconds(getattr(segment, "End", 0)) + audio_seg.start
            text = str(getattr(segment, "Text", "")).strip()
            if not text:
                return
            if text == last_text:
                repeat_count += 1
                if repeat_count in (10, 50, 200):
                    self._log(f"重复片段已忽略（{repeat_count} 次）：{text}")
                if repeat_count >= 3:
                    return
            else:
                repeat_count = 0
            last_text = text
            seg_items.append(Segment(start=start, end=end, text=text))
            percent = min(100, int((end / duration) * 100))
            self._set_progress(percent)
            self._log(f"{self._format_ts(start)} --> {self._format_ts(end)}  {text}")

        builder = factory.CreateBuilder()
        if language == "auto":
            builder = builder.WithLanguageDetection()
        elif language:
            builder = builder.WithLanguage(language)

        if no_context or safe_mode:
            builder = builder.WithNoContext()

        builder = builder.WithNoSpeechThreshold(float(no_speech_threshold))
        builder = builder.WithLogProbThreshold(float(logprob_threshold))
        builder = self._apply_builder_option(builder, "WithTemperature", 0.0)
        if safe_mode:
            builder = self._apply_builder_option(builder, "WithBeamSize", 5)
            builder = self._apply_builder_option(builder, "WithBestOf", 1)

        try:
            from Whisper.net import OnSegmentEventHandler, SegmentData  # type: ignore

            try:
                handler = OnSegmentEventHandler(on_segment)  # type: ignore
            except Exception:
                from System import Action  # type: ignore

                handler = Action[SegmentData](on_segment)  # type: ignore
            builder = builder.WithSegmentEventHandler(handler)
        except Exception as exc:
            self._log_error(f"绑定分段回调失败：{exc}")
            raise

        processor = builder.Build()
        try:
            from System import IO  # type: ignore

            stream = IO.File.OpenRead(audio_seg.path)
            try:
                processor.Process(stream)
            finally:
                try:
                    stream.Dispose()
                except Exception:
                    pass
        finally:
            try:
                processor.Dispose()
            except Exception:
                pass

        if not seg_items:
            percent = min(100, int((audio_seg.end / duration) * 100))
            self._set_progress(percent)
        return seg_items

    def _apply_builder_option(self, builder, name: str, *args):
        method = getattr(builder, name, None)
        if method is None:
            return builder
        try:
            result = method(*args)
            return result if result is not None else builder
        except Exception:
            return builder

    def _timespan_to_seconds(self, value) -> float:
        try:
            return float(value.TotalSeconds)
        except Exception:
            try:
                return float(value)
            except Exception:
                return 0.0

    def _add_dll_search_dir(self, path: str) -> None:
        if not os.path.isdir(path):
            return
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            handle = os.add_dll_directory(path)
            self.dll_dir_handles.append(handle)

    def _preload_native_library(self, search_dirs: List[str]) -> None:
        if not sys.platform.startswith("win"):
            return
        loaded = []
        for folder in search_dirs:
            # 按顺序加载：whisper.dll 是 Whisper.net 查找的主要 DLL
            for name in ("whisper.dll", "ggml-whisper.dll", "ggml-base-whisper.dll", "ggml-cpu-whisper.dll", "ggml-vulkan-whisper.dll"):
                lib_path = os.path.join(folder, name)
                if os.path.isfile(lib_path) and lib_path not in loaded:
                    try:
                        ctypes.WinDLL(lib_path)
                        loaded.append(lib_path)
                        self._log(f"已加载 native 库：{lib_path}")
                    except OSError as exc:
                        self._log_error(f"加载 {lib_path} 失败：{exc}")
        if not loaded:
            raise FileNotFoundError("未找到 ggml/whisper DLL，请确认 native 运行时文件已复制到 deps 目录。")

    def _ensure_native_aliases(self, folder: str) -> None:
        if not folder or not os.path.isdir(folder):
            return
        alias_map = {
            "whisper.dll": "libwhisper.dll",
            "ggml-whisper.dll": "libggml-whisper.dll",
            "ggml-vulkan-whisper.dll": "libggml-vulkan-whisper.dll",
            "ggml-cpu-whisper.dll": "libggml-cpu-whisper.dll",
            "ggml-base-whisper.dll": "libggml-base-whisper.dll",
        }
        for src_name, alias_name in alias_map.items():
            src_path = os.path.join(folder, src_name)
            alias_path = os.path.join(folder, alias_name)
            if os.path.isfile(src_path) and not os.path.isfile(alias_path):
                try:
                    shutil.copy2(src_path, alias_path)
                    self._log(f"已创建 DLL 别名：{alias_name}")
                except Exception:
                    pass

    def _load_whisper_factory(self):
        if self.clr is None:
            raise RuntimeError("pythonnet 未初始化。")

        deps_dir = os.path.join(self.base_dir, "deps")
        whisper_dll = os.path.join(deps_dir, "Whisper.net.dll")
        native_dir = os.path.join(deps_dir, "native")

        if not os.path.isfile(whisper_dll):
            raise FileNotFoundError("未找到 deps/Whisper.net.dll。")

        if not os.path.isdir(native_dir):
            raise FileNotFoundError("未找到 deps/native 目录。")

        self._log("native 目录：")
        self._log(f"  - {native_dir}")
        names = [n for n in os.listdir(native_dir) if n.lower().endswith(".dll")]
        self._log(f"    DLLs: {', '.join(names) if names else '无'}")

        self._ensure_native_aliases(native_dir)
        self._add_dll_search_dir(native_dir)
        self._preload_native_library([native_dir])

        managed_deps = [
            os.path.join(deps_dir, "Microsoft.Extensions.AI.Abstractions.dll"),
            os.path.join(deps_dir, "Microsoft.Bcl.AsyncInterfaces.dll"),
            os.path.join(deps_dir, "System.Memory.dll"),
            os.path.join(deps_dir, "System.Buffers.dll"),
            os.path.join(deps_dir, "System.Runtime.CompilerServices.Unsafe.dll"),
            os.path.join(deps_dir, "System.Numerics.Vectors.dll"),
        ]
        for dll in managed_deps:
            if os.path.isfile(dll):
                try:
                    self.clr.AddReference(dll)
                    self._log(f"已加载托管依赖：{os.path.basename(dll)}")
                except Exception:
                    pass

        # 在加载 Whisper.net.dll 之前先设置 RuntimeOptions
        try:
            self.clr.AddReference(whisper_dll)
            from Whisper.net.LibraryLoader import RuntimeOptions, RuntimeLibrary  # type: ignore
            from System.Collections.Generic import List  # type: ignore

            options = RuntimeOptions
            if hasattr(RuntimeOptions, "Instance"):
                try:
                    options = RuntimeOptions.Instance
                except Exception:
                    options = RuntimeOptions

            # 设置 BypassLoading（因为已经用 ctypes 预加载了）
            if hasattr(options, "SetBypassLoading"):
                try:
                    options.SetBypassLoading(True)
                    self._log("已启用 BypassLoading")
                except Exception:
                    pass
            if hasattr(options, "BypassLoading"):
                try:
                    options.BypassLoading = True
                except Exception:
                    pass

            # 设置原生库路径
            if hasattr(options, "SetLibraryPath"):
                try:
                    options.SetLibraryPath(native_dir)
                    self._log(f"已设置 LibraryPath: {native_dir}")
                except Exception as exc:
                    self._log_error(f"SetLibraryPath 失败：{exc}")
            if hasattr(options, "LibraryPath"):
                try:
                    options.LibraryPath = native_dir
                except Exception:
                    pass

            order = List[RuntimeLibrary]()
            order.Add(RuntimeLibrary.Vulkan)
            order.Add(RuntimeLibrary.Cpu)
            if hasattr(options, "SetRuntimeLibraryOrder"):
                try:
                    options.SetRuntimeLibraryOrder(order)
                except Exception:
                    pass
            if hasattr(options, "RuntimeLibraryOrder"):
                try:
                    options.RuntimeLibraryOrder = order
                except Exception:
                    pass

            if hasattr(options, "SetLoadedLibrary"):
                try:
                    options.SetLoadedLibrary(RuntimeLibrary.Vulkan)
                except Exception:
                    pass
            if hasattr(options, "LoadedLibrary"):
                try:
                    options.LoadedLibrary = RuntimeLibrary.Vulkan
                except Exception:
                    pass

            if hasattr(options, "SetUseGpu"):
                try:
                    options.SetUseGpu(True)
                except Exception:
                    pass
            if hasattr(options, "UseGpu"):
                try:
                    options.UseGpu = True
                except Exception:
                    pass
            if hasattr(options, "SetGpuDevice"):
                try:
                    options.SetGpuDevice(0)
                except Exception:
                    pass
            if hasattr(options, "GpuDevice"):
                try:
                    options.GpuDevice = 0
                except Exception:
                    pass

            try:
                lib_path = getattr(options, "LibraryPath", None)
                loaded_lib = getattr(options, "LoadedLibrary", None)
                self._log(f"RuntimeOptions.LibraryPath={lib_path}")
                if loaded_lib is not None:
                    self._log(f"RuntimeOptions.LoadedLibrary={loaded_lib}")
            except Exception:
                pass
        except Exception as exc:
            self._log_error(f"配置 Whisper.NET 失败：{exc}")
            raise

        try:
            from Whisper.net import WhisperFactory  # type: ignore

            try:
                from Whisper.net import OnSegmentEventArgs  # type: ignore

                return WhisperFactory, OnSegmentEventArgs
            except Exception:
                return WhisperFactory, None
        except Exception:
            try:
                import Whisper  # type: ignore

                try:
                    return Whisper.net.WhisperFactory, Whisper.net.OnSegmentEventArgs  # type: ignore
                except Exception:
                    return Whisper.net.WhisperFactory, None  # type: ignore
            except Exception as exc:
                raise RuntimeError("载入 Whisper.NET 失败，请检查 deps 下的 DLL。") from exc
