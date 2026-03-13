# -*- coding: utf-8 -*-
import os
import sys
import queue
import threading
import tempfile
import traceback
from typing import List, Tuple

import ttkbootstrap as tb
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from ttkbootstrap.dialogs import Messagebox

from app_models import Segment
from transcriber import TranscribeConfig, WhisperTranscriber
from translator import DEFAULT_TRANSLATE_PROMPT, OllamaTranslator
from srt_translate import translate_srt_file

try:
    import pythonnet

    try:
        pythonnet.load("coreclr")
    except Exception:
        pass
    import clr  # type: ignore
except Exception:
    clr = None


VIDEO_TYPES = (
    ("\u89c6\u9891\u6587\u4ef6", "*.mp4 *.mkv *.avi *.mov *.flv *.webm"),
    ("\u6240\u6709\u6587\u4ef6", "*.*"),
)

LANG_OPTIONS = [
    ("\u4e2d\u6587", "zh"),
    ("\u65e5\u8bed", "ja"),
    ("\u82f1\u8bed", "en"),
    ("\u97e9\u8bed", "ko"),
    ("\u6cd5\u8bed", "fr"),
    ("\u5fb7\u8bed", "de"),
    ("\u897f\u73ed\u7259\u8bed", "es"),
    ("\u4fc4\u8bed", "ru"),
    ("\u81ea\u52a8\u8bc6\u522b", "auto"),
]

MODEL_OPTIONS = [
    "ggml-base.bin",
    "ggml-small.bin",
    "ggml-medium.bin",
    "ggml-large-v2.bin",
    "ggml-large-v3.bin",
    "ggml-large-v3-turbo.bin",
    "ggml-kotoba-whisper-bilingual-v1.0.bin",
]

TRANSLATE_LANG_OPTIONS = [(name, code) for name, code in LANG_OPTIONS if code != "auto"]


class WhisperApp:
    def __init__(self) -> None:
        self.app = tb.Window(themename="litera")
        self.app.title("\u89c6\u9891\u8f6c\u5b57\u5e55\uff08Whisper.NET\uff09")
        self.app.geometry("960x960")

        self.video_var = tb.StringVar()
        self.model_var = tb.StringVar(value="ggml-large-v3-turbo.bin")
        self.lang_var = tb.StringVar(value="\u65e5\u8bed")
        self.model_status_var = tb.StringVar(value="\u6a21\u578b\uff1a\u672a\u68c0\u67e5")
        self.status_var = tb.StringVar(value="\u5c31\u7eea")
        self.trim_silence_var = tb.BooleanVar(value=False)
        self.no_speech_var = tb.DoubleVar(value=0.6)
        self.logprob_var = tb.DoubleVar(value=-1.2)
        self.no_speech_text = tb.StringVar(value="0.60")
        self.logprob_text = tb.StringVar(value="-1.20")
        self.no_context_var = tb.BooleanVar(value=True)
        self.segment_enable_var = tb.BooleanVar(value=True)
        self.segment_len_var = tb.DoubleVar(value=45.0)
        self.segment_len_text = tb.StringVar(value="45")
        self.vad_enable_var = tb.BooleanVar(value=True)
        self.translate_enable_var = tb.BooleanVar(value=False)
        self.translate_lang_var = tb.StringVar(value="\u4e2d\u6587")
        self.translate_model_var = tb.StringVar(value="Qwen3-8B-Trans")
        self.translate_batch_var = tb.IntVar(value=30)

        self.log_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self._build_ui()
        self._refresh_model_status()
        self.app.after(120, self._flush_log_queue)

    def _build_ui(self) -> None:
        self.app.columnconfigure(1, weight=1)
        self.app.rowconfigure(9, weight=1)

        ttk.Label(self.app, text="\u89c6\u9891\u6587\u4ef6").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.video_entry = ttk.Entry(self.app, textvariable=self.video_var, state="readonly")
        self.video_entry.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        self.video_btn = ttk.Button(self.app, text="\u9009\u62e9\u6587\u4ef6", command=self._choose_video)
        self.video_btn.grid(row=0, column=2, padx=10, pady=8)

        ttk.Label(self.app, text="\u8bc6\u522b\u8bed\u8a00").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.lang_combo = ttk.Combobox(
            self.app,
            textvariable=self.lang_var,
            values=[item[0] for item in LANG_OPTIONS],
            state="readonly",
            width=12,
        )
        self.lang_combo.grid(row=1, column=1, padx=6, pady=8, sticky="w")

        ttk.Label(self.app, text="\u6a21\u578b").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.model_combo = ttk.Combobox(
            self.app,
            textvariable=self.model_var,
            values=MODEL_OPTIONS,
            state="readonly",
            width=18,
        )
        self.model_combo.grid(row=2, column=1, padx=6, pady=8, sticky="w")
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_model_status())

        self.silence_check = ttk.Checkbutton(
            self.app,
            text="\u53bb\u9664\u9996\u5c3e\u9759\u97f3",
            variable=self.trim_silence_var,
            bootstyle="round-toggle",
        )
        self.silence_check.grid(row=2, column=2, padx=10, pady=8, sticky="w")

        self.model_status = ttk.Label(self.app, textvariable=self.model_status_var, bootstyle="secondary")
        self.model_status.grid(row=3, column=0, columnspan=3, padx=10, pady=6, sticky="w")

        settings_frame = ttk.Frame(self.app)
        settings_frame.grid(row=4, column=0, columnspan=3, padx=10, pady=6, sticky="ew")
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="\u9759\u97f3\u9608\u503c").grid(row=0, column=0, padx=(0, 6), pady=4, sticky="w")
        self.no_speech_scale = ttk.Scale(
            settings_frame,
            from_=0.0,
            to=1.0,
            orient="horizontal",
            variable=self.no_speech_var,
            command=lambda v: self.no_speech_text.set(f"{float(v):.2f}"),
        )
        self.no_speech_scale.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        ttk.Label(settings_frame, textvariable=self.no_speech_text, width=6).grid(
            row=0, column=2, padx=(6, 0), pady=4, sticky="w"
        )

        ttk.Label(settings_frame, text="\u7f6e\u4fe1\u5ea6\u9608\u503c").grid(row=1, column=0, padx=(0, 6), pady=4, sticky="w")
        self.logprob_scale = ttk.Scale(
            settings_frame,
            from_=-3.0,
            to=0.0,
            orient="horizontal",
            variable=self.logprob_var,
            command=lambda v: self.logprob_text.set(f"{float(v):.2f}"),
        )
        self.logprob_scale.grid(row=1, column=1, padx=6, pady=4, sticky="ew")
        ttk.Label(settings_frame, textvariable=self.logprob_text, width=6).grid(
            row=1, column=2, padx=(6, 0), pady=4, sticky="w"
        )

        self.no_context_check = ttk.Checkbutton(
            settings_frame,
            text="\u4e0d\u53c2\u8003\u4e0a\u4e0b\u6587",
            variable=self.no_context_var,
            bootstyle="round-toggle",
        )
        self.no_context_check.grid(row=2, column=0, columnspan=3, padx=6, pady=(4, 0), sticky="w")

        ttk.Label(settings_frame, text="\u5206\u6bb5\u65f6\u957f(\u79d2)").grid(
            row=3, column=0, padx=(0, 6), pady=4, sticky="w"
        )
        self.segment_len_scale = ttk.Scale(
            settings_frame,
            from_=10.0,
            to=180.0,
            orient="horizontal",
            variable=self.segment_len_var,
            command=lambda v: self.segment_len_text.set(f"{float(v):.0f}"),
        )
        self.segment_len_scale.grid(row=3, column=1, padx=6, pady=4, sticky="ew")
        ttk.Label(settings_frame, textvariable=self.segment_len_text, width=6).grid(
            row=3, column=2, padx=(6, 0), pady=4, sticky="w"
        )

        self.segment_check = ttk.Checkbutton(
            settings_frame,
            text="\u542f\u7528\u5206\u6bb5",
            variable=self.segment_enable_var,
            bootstyle="round-toggle",
        )
        self.segment_check.grid(row=4, column=0, padx=6, pady=(4, 0), sticky="w")

        self.vad_check = ttk.Checkbutton(
            settings_frame,
            text="VAD \u8fc7\u6ee4\u65e0\u8bed\u97f3",
            variable=self.vad_enable_var,
            bootstyle="round-toggle",
        )
        self.vad_check.grid(row=4, column=1, columnspan=2, padx=6, pady=(4, 0), sticky="w")

        translate_frame = ttk.Frame(self.app)
        translate_frame.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="ew")
        translate_frame.columnconfigure(2, weight=1)

        self.translate_check = ttk.Checkbutton(
            translate_frame,
            text="\u542f\u7528\u7ffb\u8bd1\uff08Ollama\uff09",
            variable=self.translate_enable_var,
            bootstyle="round-toggle",
        )
        self.translate_check.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        ttk.Label(translate_frame, text="\u76ee\u6807\u8bed\u8a00").grid(row=0, column=1, padx=(0, 6), pady=4, sticky="w")
        self.translate_lang_combo = ttk.Combobox(
            translate_frame,
            textvariable=self.translate_lang_var,
            values=[item[0] for item in TRANSLATE_LANG_OPTIONS],
            state="readonly",
            width=10,
        )
        self.translate_lang_combo.grid(row=0, column=2, padx=6, pady=4, sticky="w")

        ttk.Label(translate_frame, text="\u6bcf\u6279\u6761\u6570").grid(row=0, column=3, padx=(8, 6), pady=4, sticky="w")
        self.translate_batch_spin = ttk.Spinbox(
            translate_frame,
            from_=1,
            to=200,
            textvariable=self.translate_batch_var,
            width=6,
        )
        self.translate_batch_spin.grid(row=0, column=4, padx=(0, 6), pady=4, sticky="w")

        ttk.Label(translate_frame, text="Ollama \u6a21\u578b").grid(row=1, column=0, padx=(0, 6), pady=4, sticky="w")
        self.translate_model_entry = ttk.Entry(translate_frame, textvariable=self.translate_model_var, width=20)
        self.translate_model_entry.grid(row=1, column=1, columnspan=2, padx=6, pady=4, sticky="w")

        ttk.Label(translate_frame, text="\u63d0\u793a\u8bcd\uff08\u652f\u6301 {target} \u548c {text}\uff09").grid(
            row=2, column=0, columnspan=5, padx=(0, 6), pady=(6, 2), sticky="w"
        )
        self.translate_prompt_text = ScrolledText(translate_frame, height=6, wrap="word")
        self.translate_prompt_text.grid(row=3, column=0, columnspan=5, padx=0, pady=(0, 4), sticky="ew")
        self.translate_prompt_text.insert("1.0", DEFAULT_TRANSLATE_PROMPT)

        action_frame = ttk.Frame(self.app)
        action_frame.grid(row=6, column=0, columnspan=3, padx=10, pady=8, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        self.start_btn = ttk.Button(
            action_frame,
            text="\u5f00\u59cb\u8f6c\u5199",
            bootstyle="primary",
            command=self._start_job,
            width=18,
        )
        self.start_btn.grid(row=0, column=0, padx=6, pady=4, sticky="w")

        self.translate_btn = ttk.Button(
            action_frame,
            text="\u7ffb\u8bd1\u5b57\u5e55",
            bootstyle="secondary",
            command=self._open_translate_window,
            width=12,
        )
        self.translate_btn.grid(row=0, column=1, padx=6, pady=4, sticky="w")

        self.progress = ttk.Progressbar(self.app, orient="horizontal", mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=3, padx=10, pady=(8, 4), sticky="ew")

        ttk.Label(self.app, text="\u65e5\u5fd7").grid(row=8, column=0, padx=10, pady=(8, 2), sticky="w")
        self.log_text = ScrolledText(self.app, height=16, wrap="word", state="disabled")
        self.log_text.grid(row=9, column=0, columnspan=3, padx=10, pady=4, sticky="nsew")
        self.log_text.tag_config("error", foreground="#c0392b")

        status_frame = ttk.Frame(self.app)
        status_frame.grid(row=10, column=0, columnspan=3, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").grid(
            row=0, column=0, padx=10, pady=6, sticky="ew"
        )

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(title="\u9009\u62e9\u89c6\u9891\u6587\u4ef6", filetypes=VIDEO_TYPES)
        if not path:
            return
        self.video_var.set(os.path.abspath(path))
        self._refresh_model_status()

    def _open_translate_window(self) -> None:
        if hasattr(self, "translate_window") and self.translate_window.winfo_exists():
            self.translate_window.focus_set()
            return

        win = tb.Toplevel(self.app)
        win.title("\u5b57\u5e55\u7ffb\u8bd1\uff08Ollama\uff09")
        win.geometry("760x560")
        win.columnconfigure(1, weight=1)
        win.rowconfigure(5, weight=1)
        win.rowconfigure(6, weight=1)
        self.translate_window = win

        input_var = tb.StringVar()
        output_var = tb.StringVar()
        lang_var = tb.StringVar(value=self.translate_lang_var.get())
        model_var = tb.StringVar(value=self.translate_model_var.get())
        batch_var = tb.IntVar(value=self.translate_batch_var.get())
        status_var = tb.StringVar(value="\u5c31\u7eea")

        def append_log(message: str, level: str = "info") -> None:
            def apply() -> None:
                log_text.configure(state="normal")
                if level == "error":
                    log_text.insert("end", message + "\n", "error")
                else:
                    log_text.insert("end", message + "\n")
                log_text.configure(state="disabled")
                log_text.see("end")

            self.app.after(0, apply)

        def set_status(message: str) -> None:
            self.app.after(0, lambda: status_var.set(message))

        def set_progress(value: int) -> None:
            self.app.after(0, lambda: progress.configure(value=value))

        def suggest_output(path: str) -> None:
            if not path:
                return
            base, _ext = os.path.splitext(path)
            code = self._translate_language_code_from_label(lang_var.get())
            suffix = code if code else "translated"
            output_var.set(f"{base}.{suffix}.srt")

        def choose_input() -> None:
            path = filedialog.askopenfilename(
                title="\u9009\u62e9 SRT \u6587\u4ef6",
                filetypes=(("\u5b57\u5e55\u6587\u4ef6", "*.srt"), ("\u6240\u6709\u6587\u4ef6", "*.*")),
            )
            if not path:
                return
            input_var.set(os.path.abspath(path))
            suggest_output(path)

        def choose_output() -> None:
            path = filedialog.asksaveasfilename(
                title="\u4fdd\u5b58 SRT",
                defaultextension=".srt",
                filetypes=(("\u5b57\u5e55\u6587\u4ef6", "*.srt"), ("\u6240\u6709\u6587\u4ef6", "*.*")),
            )
            if not path:
                return
            output_var.set(os.path.abspath(path))

        ttk.Label(win, text="\u8f93\u5165 SRT").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        input_entry = ttk.Entry(win, textvariable=input_var, state="readonly")
        input_entry.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        ttk.Button(win, text="\u9009\u62e9\u6587\u4ef6", command=choose_input).grid(
            row=0, column=2, padx=10, pady=8
        )

        ttk.Label(win, text="\u8f93\u51fa SRT").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        output_entry = ttk.Entry(win, textvariable=output_var)
        output_entry.grid(row=1, column=1, padx=6, pady=6, sticky="ew")
        ttk.Button(win, text="\u53e6\u5b58\u4e3a", command=choose_output).grid(row=1, column=2, padx=10, pady=6)

        ttk.Label(win, text="\u76ee\u6807\u8bed\u8a00").grid(row=2, column=0, padx=10, pady=6, sticky="w")
        lang_combo = ttk.Combobox(
            win,
            textvariable=lang_var,
            values=[item[0] for item in TRANSLATE_LANG_OPTIONS],
            state="readonly",
            width=10,
        )
        lang_combo.grid(row=2, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(win, text="\u6bcf\u6279\u6761\u6570").grid(row=2, column=2, padx=6, pady=6, sticky="e")
        batch_spin = ttk.Spinbox(win, from_=1, to=200, textvariable=batch_var, width=6)
        batch_spin.grid(row=2, column=3, padx=(0, 10), pady=6, sticky="w")

        ttk.Label(win, text="Ollama \u6a21\u578b").grid(row=3, column=0, padx=10, pady=6, sticky="w")
        model_entry = ttk.Entry(win, textvariable=model_var, width=18)
        model_entry.grid(row=3, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(win, text="\u63d0\u793a\u8bcd\uff08\u652f\u6301 {target} \u548c {text}\uff09").grid(
            row=4, column=0, columnspan=4, padx=10, pady=(8, 4), sticky="w"
        )
        prompt_text = ScrolledText(win, height=6, wrap="word")
        prompt_text.grid(row=5, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="nsew")
        prompt_text.insert("1.0", self.translate_prompt_text.get("1.0", "end").strip() or DEFAULT_TRANSLATE_PROMPT)

        log_text = ScrolledText(win, height=8, wrap="word", state="disabled")
        log_text.grid(row=6, column=0, columnspan=4, padx=10, pady=(4, 6), sticky="nsew")
        log_text.tag_config("error", foreground="#c0392b")

        progress = ttk.Progressbar(win, orient="horizontal", mode="determinate", maximum=100)
        progress.grid(row=7, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="ew")

        status_label = ttk.Label(win, textvariable=status_var, anchor="w")
        status_label.grid(row=8, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="ew")

        def run_translate() -> None:
            input_path = input_var.get().strip()
            output_path = output_var.get().strip()
            target_label = lang_var.get().strip()
            model_name = model_var.get().strip()
            if not input_path or not os.path.isfile(input_path):
                append_log("\u8bf7\u9009\u62e9\u6709\u6548\u7684 SRT \u6587\u4ef6\u3002", "error")
                return
            if not output_path:
                append_log("\u8bf7\u8bbe\u7f6e\u8f93\u51fa\u8def\u5f84\u3002", "error")
                return
            if not model_name:
                append_log("\u8bf7\u586b\u5199 Ollama \u6a21\u578b\u540d\u3002", "error")
                return
            if not target_label:
                append_log("\u8bf7\u9009\u62e9\u76ee\u6807\u8bed\u8a00\u3002", "error")
                return

            prompt = prompt_text.get("1.0", "end").strip() or DEFAULT_TRANSLATE_PROMPT
            batch_size = max(1, int(batch_var.get() or 1))

            def progress_cb(done: int, total: int) -> None:
                if total > 0:
                    set_progress(int(done / total * 100))

            def task() -> None:
                set_status("\u7ffb\u8bd1\u4e2d...")
                set_progress(0)
                try:
                    translator = OllamaTranslator(
                        base_url="http://localhost:11434/v1",
                        model=model_name,
                        log=append_log,
                        log_error=lambda m: append_log(m, "error"),
                    )
                    translate_srt_file(
                        input_path=input_path,
                        output_path=output_path,
                        target_lang=target_label,
                        translator=translator,
                        prompt_template=prompt,
                        batch_size=batch_size,
                        log=append_log,
                        progress=progress_cb,
                    )
                    set_progress(100)
                    set_status("\u5b8c\u6210")
                    self._open_output_dir(os.path.dirname(output_path))
                except Exception as exc:
                    append_log(f"\u7ffb\u8bd1\u5931\u8d25\uff1a{exc}", "error")
                    set_status("\u9519\u8bef")

            threading.Thread(target=task, daemon=True).start()

        def on_start() -> None:
            self.translate_lang_var.set(lang_var.get())
            self.translate_model_var.set(model_var.get())
            self.translate_batch_var.set(batch_var.get())
            self.translate_prompt_text.delete("1.0", "end")
            self.translate_prompt_text.insert("1.0", prompt_text.get("1.0", "end").strip())
            run_translate()

        ttk.Button(win, text="\u5f00\u59cb\u7ffb\u8bd1", bootstyle="primary", command=on_start).grid(
            row=9, column=2, padx=10, pady=8, sticky="e"
        )
        ttk.Button(win, text="\u5173\u95ed", command=win.destroy).grid(row=9, column=3, padx=10, pady=8, sticky="e")

    def _refresh_model_status(self) -> None:
        model_path = self._model_path()
        if os.path.isfile(model_path):
            self.model_status_var.set(f"\u6a21\u578b\uff1a\u5df2\u627e\u5230 ({os.path.basename(model_path)})")
            self.model_status.configure(bootstyle="success")
        else:
            self.model_status_var.set(
                f"\u6a21\u578b\uff1a\u7f3a\u5931\uff0c\u8bf7\u4e0b\u8f7d {os.path.basename(model_path)} \u5e76\u653e\u5230 ./models/"
            )
            self.model_status.configure(bootstyle="danger")

    def _start_job(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        video_path = self.video_var.get().strip()
        if not video_path:
            Messagebox.show_warning("\u8bf7\u5148\u9009\u62e9\u89c6\u9891\u6587\u4ef6\u3002", "\u63d0\u793a")
            return
        if not os.path.isfile(video_path):
            Messagebox.show_error("\u89c6\u9891\u6587\u4ef6\u4e0d\u5b58\u5728\u3002", "\u9519\u8bef")
            return
        if not os.path.isfile(self._model_path()):
            Messagebox.show_error(
                f"\u6a21\u578b\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u8bf7\u4e0b\u8f7d {os.path.basename(self._model_path())}\u3002",
                "\u9519\u8bef",
            )
            return
        if clr is None:
            Messagebox.show_error("\u53d1\u73b0 pythonnet \u672a\u5b89\u88c5\u6216\u521d\u59cb\u5316\u5931\u8d25\u3002", "\u9519\u8bef")
            return
        if self.translate_enable_var.get():
            if not self.translate_model_var.get().strip():
                Messagebox.show_warning("\u8bf7\u586b\u5199 Ollama \u6a21\u578b\u540d\u3002", "\u63d0\u793a")
                return
            if not self._translate_language_label():
                Messagebox.show_warning("\u8bf7\u9009\u62e9\u7ffb\u8bd1\u76ee\u6807\u8bed\u8a00\u3002", "\u63d0\u793a")
                return

        self._set_running(True)
        self._set_progress(0)
        self._log("\u5f00\u59cb\u4efb\u52a1\uff1a\u63d0\u53d6\u97f3\u9891\u5e76\u8fdb\u884c\u8bc6\u522b")

        language_code = self._language_code()
        self.worker = threading.Thread(
            target=self._worker_entry,
            args=(os.path.abspath(video_path), language_code),
            daemon=True,
        )
        self.worker.start()

    def _worker_entry(self, video_path: str, language: str) -> None:
        tmp_dir = None
        try:
            self._set_status("\u6b63\u5728\u63d0\u53d6\u97f3\u9891...")
            tmp_dir = tempfile.TemporaryDirectory()
            wav_path = os.path.abspath(os.path.join(tmp_dir.name, "audio.wav"))

            transcriber = WhisperTranscriber(
                base_dir=self._base_dir(),
                clr_module=clr,
                log=self._log,
                log_error=self._log_error,
                set_progress=self._set_progress,
                format_ts=self._format_ts,
            )

            duration = transcriber.extract_audio(video_path, wav_path, self.trim_silence_var.get())
            if duration <= 0:
                raise RuntimeError("\u65e0\u6cd5\u83b7\u53d6\u89c6\u9891\u65f6\u957f\u3002")

            self._set_status("\u6b63\u5728\u8bc6\u522b...")
            config = TranscribeConfig(
                model_path=self._model_path(),
                language=language,
                no_context=bool(self.no_context_var.get()),
                no_speech_threshold=float(self.no_speech_var.get()),
                logprob_threshold=float(self.logprob_var.get()),
                segment_enable=bool(self.segment_enable_var.get()),
                segment_len=float(self.segment_len_var.get()),
                vad_enable=bool(self.vad_enable_var.get()),
            )
            segments = transcriber.transcribe(wav_path, duration, config, tmp_dir.name)

            if not segments:
                raise RuntimeError("\u672a\u8bc6\u522b\u5230\u6709\u6548\u5b57\u5e55\u5185\u5bb9\u3002")

            if self.translate_enable_var.get():
                self._set_status("\u6b63\u5728\u7ffb\u8bd1...")
                try:
                    prompt_template = self.translate_prompt_text.get("1.0", "end").strip() or DEFAULT_TRANSLATE_PROMPT
                    target_lang = self._translate_language_label()
                    batch_size = max(1, int(self.translate_batch_var.get() or 1))
                    model_name = self.translate_model_var.get().strip()
                    translator = OllamaTranslator(
                        base_url="http://localhost:11434/v1",
                        model=model_name,
                        log=self._log,
                        log_error=self._log_error,
                    )
                    original_texts = [seg.text for seg in segments]
                    translated = translator.translate_texts(
                        original_texts,
                        target_lang=target_lang,
                        prompt_template=prompt_template,
                        batch_size=batch_size,
                    )
                    if len(translated) == len(segments):
                        for seg, text in zip(segments, translated):
                            seg.text = text
                    else:
                        self._log_error(
                            "\u7ffb\u8bd1\u8fd4\u56de\u884c\u6570\u4e0d\u5339\u914d\uff0c\u5df2\u4f7f\u7528\u539f\u6587\u8f93\u51fa\u3002"
                        )
                except Exception as exc:
                    self._log_error(f"\u7ffb\u8bd1\u5931\u8d25\uff0c\u5df2\u4f7f\u7528\u539f\u6587\u8f93\u51fa\uff1a{exc}")

            srt_path = self._write_srt(video_path, segments)
            self._set_progress(100)
            self._set_status("\u5b8c\u6210")
            self._log(f"SRT \u5df2\u751f\u6210\uff1a{srt_path}")
            self._open_output_dir(os.path.dirname(srt_path))
            self._ui_call(lambda: Messagebox.show_info(f"SRT \u5df2\u751f\u6210\uff1a\n{srt_path}", "\u5b8c\u6210"))
        except Exception as exc:
            message = str(exc)
            self._log_error(message)
            self._log_error(traceback.format_exc())
            self._set_status("\u9519\u8bef")
            self._ui_call(lambda m=message: Messagebox.show_error(m, "\u9519\u8bef"))
        finally:
            if tmp_dir is not None:
                tmp_dir.cleanup()
            self._set_running(False)

    def _write_srt(self, video_path: str, segments: List[Segment]) -> str:
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        srt_path = os.path.join(os.path.dirname(video_path), f"{base_name}.srt")
        with open(srt_path, "w", encoding="utf-8") as handle:
            for idx, seg in enumerate(segments, 1):
                handle.write(f"{idx}\n")
                handle.write(f"{self._format_ts(seg.start)} --> {self._format_ts(seg.end)}\n")
                handle.write(seg.text.strip() + "\n\n")
        return srt_path

    def _format_ts(self, seconds: float) -> str:
        ms_total = max(0, int(round(seconds * 1000)))
        hours = ms_total // 3600000
        minutes = (ms_total % 3600000) // 60000
        secs = (ms_total % 60000) // 1000
        ms = ms_total % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    def _set_running(self, running: bool) -> None:
        def apply_state() -> None:
            state = "disabled" if running else "normal"
            self.video_btn.configure(state=state)
            self.start_btn.configure(state=state)
            self.translate_btn.configure(state=state)
            self.lang_combo.configure(state="disabled" if running else "readonly")
            self.model_combo.configure(state="disabled" if running else "readonly")
            self.silence_check.configure(state=state)
            self.no_speech_scale.configure(state=state)
            self.logprob_scale.configure(state=state)
            self.no_context_check.configure(state=state)
            self.segment_len_scale.configure(state=state)
            self.segment_check.configure(state=state)
            self.vad_check.configure(state=state)
            self.translate_check.configure(state=state)
            self.translate_lang_combo.configure(state="disabled" if running else "readonly")
            self.translate_batch_spin.configure(state=state)
            self.translate_model_entry.configure(state=state)
            self.translate_prompt_text.configure(state=state)
            if running:
                self._set_status("\u5904\u7406\u4e2d...")
            else:
                if self.status_var.get() == "\u5904\u7406\u4e2d...":
                    self._set_status("\u5c31\u7eea")

        self._ui_call(apply_state)

    def _set_progress(self, value: int) -> None:
        self._ui_call(lambda: self.progress.configure(value=value))

    def _set_status(self, text: str) -> None:
        self._ui_call(lambda: self.status_var.set(text))

    def _log(self, message: str) -> None:
        self.log_queue.put((message, "info"))

    def _log_error(self, message: str) -> None:
        self.log_queue.put((message, "error"))

    def _flush_log_queue(self) -> None:
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                if level == "error":
                    self.log_text.insert("end", message + "\n", "error")
                else:
                    self.log_text.insert("end", message + "\n")
                self.log_text.configure(state="disabled")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.app.after(120, self._flush_log_queue)

    def _ui_call(self, func) -> None:
        self.app.after(0, func)

    def _open_output_dir(self, path: str) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform.startswith("darwin"):
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            pass

    def _model_path(self) -> str:
        model_name = self.model_var.get().strip() or "ggml-base.bin"
        return os.path.join(self._base_dir(), "models", model_name)

    def _base_dir(self) -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def _language_code(self) -> str:
        label = self.lang_var.get().strip()
        for name, code in LANG_OPTIONS:
            if name == label:
                return code
        return "zh"

    def _translate_language_label(self) -> str:
        label = self.translate_lang_var.get().strip()
        for name, code in TRANSLATE_LANG_OPTIONS:
            if name == label:
                return name
        return ""

    def _translate_language_code_from_label(self, label: str) -> str:
        for name, code in TRANSLATE_LANG_OPTIONS:
            if name == label:
                return code
        return ""

    def run(self) -> None:
        self.app.mainloop()


if __name__ == "__main__":
    WhisperApp().run()
