from __future__ import annotations

from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from english_reading_assistant.config import ConfigError
from english_reading_assistant.llm_client import LLMRequestError, analyze_text
from english_reading_assistant.obsidian import ObsidianSaveError, append_to_obsidian_note


WINDOW_TITLE = "English Reading Assistant"
APP_BACKGROUND = "#F4EEE6"
CARD_BACKGROUND = "#FFFDF9"
HEADER_BACKGROUND = "#173A3B"
HEADER_TEXT = "#F7F3EC"
HEADER_MUTED = "#D6E2DF"
CARD_BORDER = "#D8CCBF"
INPUT_BACKGROUND = "#FCFAF6"
OUTPUT_BACKGROUND = "#FBF8F1"
TEXT_PRIMARY = "#21313A"
TEXT_MUTED = "#6A757E"
TEXT_SUCCESS = "#2F6F5E"
TEXT_ERROR = "#9B3D33"
PRIMARY_BUTTON = "#C46A3A"
PRIMARY_BUTTON_ACTIVE = "#AE592D"
SECONDARY_BUTTON = "#E9DED2"
SECONDARY_BUTTON_ACTIVE = "#DCCDBF"
PROGRESS_COLOR = "#2F6F5E"
DEFAULT_EXPORT_FILE_NAME = "english-reading-result.md"
SUPPORTED_IMPORT_FILE_SUFFIXES = {".txt", ".md", ".markdown"}

INITIAL_OUTPUT = (
    "请将英文原文贴到左侧输入区，然后点击「开始解析」。\n\n"
    "长文章会自动分段，并优先生成：\n"
    "1. 整篇总览\n"
    "2. 重点单词与短语\n"
    "3. 句型与语法解析"
)

SECTION_TITLE_RE = re.compile(r"^【.+】$")
NUMBERED_LINE_RE = re.compile(r"^\d+\.\s")
BULLET_LINE_RE = re.compile(r"^[-*]\s")
SUCCESS_PREFIXES = ("已保存到 Obsidian：",)
ERROR_PREFIXES = (
    "保存到 Obsidian 失败：",
    "网络请求失败：",
    "请求失败（HTTP",
    "发生未预期错误：",
    "生成失败：",
    "未找到",
)
NOTICE_PREFIXES = (
    "这篇文章较长，已自动分成",
    "正在解析中，请稍候...",
)


def build_text_metrics(content: str) -> str:
    normalized = content.rstrip("\n")
    if not normalized.strip():
        return "0 字符 · 0 行"
    return f"{len(normalized)} 字符 · {normalized.count(chr(10)) + 1} 行"


def build_output_metrics(content: str, *, is_placeholder: bool) -> str:
    if is_placeholder or not content.strip():
        return "等待解析结果"
    return f"{build_text_metrics(content)} · 可复制"


def is_supported_import_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in SUPPORTED_IMPORT_FILE_SUFFIXES


def build_markdown_export_content(source_text: str, result_text: str) -> str:
    sections = ["# English Reading Assistant 导出"]
    if source_text.strip():
        sections.append(f"## 英文原文\n\n{source_text.strip()}")
    sections.append(f"## 解析结果\n\n{result_text.strip()}")
    return "\n\n".join(sections) + "\n"


def classify_output_line(line: str, *, is_placeholder: bool) -> str:
    stripped = line.strip()
    if not stripped:
        return "spacer"
    if is_placeholder:
        if NUMBERED_LINE_RE.match(stripped):
            return "placeholder_list"
        return "placeholder"
    if stripped == "---":
        return "divider"
    if SECTION_TITLE_RE.match(stripped):
        return "section_title"
    if any(stripped.startswith(prefix) for prefix in SUCCESS_PREFIXES):
        return "success"
    if any(stripped.startswith(prefix) for prefix in ERROR_PREFIXES):
        return "error"
    if any(stripped.startswith(prefix) for prefix in NOTICE_PREFIXES):
        return "notice"
    if NUMBERED_LINE_RE.match(stripped):
        return "numbered_heading"
    if BULLET_LINE_RE.match(stripped):
        return "bullet"
    return "body"


def build_output_line_styles(content: str, *, is_placeholder: bool) -> list[tuple[str, str]]:
    return [
        (line, classify_output_line(line, is_placeholder=is_placeholder))
        for line in content.splitlines()
    ]


class EnglishReadingAssistantApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.last_source_text = ""
        self.last_result = ""
        self.current_output = INITIAL_OUTPUT
        self.output_is_placeholder = True
        self.is_busy = False
        self.status_var = tk.StringVar(value="准备就绪，可以粘贴文章开始解析。")
        self.input_meta_var = tk.StringVar(value="0 字符 · 0 行")
        self.output_meta_var = tk.StringVar(value="等待解析结果")
        self.imported_file_path: Path | None = None

        self.root.title(WINDOW_TITLE)
        self.root.geometry("1120x760")
        self.root.minsize(860, 620)
        self.root.configure(bg=APP_BACKGROUND)
        self.app_icon_image: tk.PhotoImage | None = None

        self._configure_styles()
        self._configure_window_icon()
        self._build_ui()
        self._set_output(INITIAL_OUTPUT, is_placeholder=True)
        self._refresh_input_meta()
        self._update_action_state()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Primary.TButton",
            font=("PingFang TC", 12, "bold"),
            padding=(18, 12),
            foreground=HEADER_TEXT,
            background=PRIMARY_BUTTON,
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", "#D5C6B6"),
                ("pressed", PRIMARY_BUTTON_ACTIVE),
                ("active", PRIMARY_BUTTON_ACTIVE),
            ],
            foreground=[("disabled", "#F6EFE8")],
        )

        style.configure(
            "Secondary.TButton",
            font=("PingFang TC", 11),
            padding=(14, 10),
            foreground=TEXT_PRIMARY,
            background=SECONDARY_BUTTON,
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("disabled", "#EEE6DD"),
                ("pressed", SECONDARY_BUTTON_ACTIVE),
                ("active", SECONDARY_BUTTON_ACTIVE),
            ],
            foreground=[("disabled", "#988A7E")],
        )

        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor="#E7DDD1",
            bordercolor="#E7DDD1",
            background=PROGRESS_COLOR,
            lightcolor=PROGRESS_COLOR,
            darkcolor=PROGRESS_COLOR,
        )

    def _configure_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app-icon.png"
        if not icon_path.is_file():
            return
        try:
            self.app_icon_image = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self.app_icon_image)
        except tk.TclError:
            self.app_icon_image = None

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg=APP_BACKGROUND)
        main.pack(fill="both", expand=True, padx=24, pady=24)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_header(main)
        self._build_content(main)
        self._build_status_bar(main)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(
            parent,
            bg=HEADER_BACKGROUND,
            highlightbackground="#2D5556",
            highlightthickness=1,
            padx=24,
            pady=22,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="English Reading Assistant",
            bg=HEADER_BACKGROUND,
            fg=HEADER_MUTED,
            font=("Avenir Next", 11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            header,
            text="把英文原文变成可快速复习的中文笔记",
            bg=HEADER_BACKGROUND,
            fg=HEADER_TEXT,
            font=("PingFang TC", 24, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(6, 8))

        tk.Label(
            header,
            text="适合精读文章、长文分段解析和保存到 Obsidian。",
            bg=HEADER_BACKGROUND,
            fg=HEADER_MUTED,
            font=("PingFang TC", 12),
            anchor="w",
        ).grid(row=2, column=0, sticky="w")

        chip_row = tk.Frame(header, bg=HEADER_BACKGROUND)
        chip_row.grid(row=3, column=0, sticky="w", pady=(16, 0))
        self._create_chip(chip_row, "整篇总览")
        self._create_chip(chip_row, "重点词汇")
        self._create_chip(chip_row, "语法解析")
        self._create_chip(chip_row, "Obsidian")

    def _create_chip(self, parent: tk.Frame, text: str) -> None:
        chip = tk.Label(
            parent,
            text=text,
            bg="#234B4C",
            fg=HEADER_TEXT,
            font=("PingFang TC", 10, "bold"),
            padx=10,
            pady=5,
        )
        chip.pack(side="left", padx=(0, 8))

    def _build_content(self, parent: tk.Frame) -> None:
        content = tk.Frame(parent, bg=APP_BACKGROUND)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._build_input_card(content)
        self._build_output_card(content)

    def _build_input_card(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg=CARD_BACKGROUND,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=18,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        self._build_card_header(
            card,
            title="原文输入区",
            description="粘贴英文原文。支持短句、整段文章和较长文本。",
            meta_var=self.input_meta_var,
        )

        self.input_text = tk.Text(
            card,
            wrap="word",
            height=20,
            font=("PingFang TC", 13),
            bg=INPUT_BACKGROUND,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=PRIMARY_BUTTON,
            padx=14,
            pady=14,
            spacing1=2,
            spacing2=4,
            spacing3=2,
            undo=True,
            selectbackground="#D9C9B7",
        )
        self.input_text.grid(row=1, column=0, sticky="nsew", pady=(14, 16))
        self.input_text.bind("<<Modified>>", self._on_input_modified)
        self.input_text.edit_modified(False)

        action_row = tk.Frame(card, bg=CARD_BACKGROUND)
        action_row.grid(row=2, column=0, sticky="ew")
        action_row.grid_columnconfigure(3, weight=1)

        self.parse_button = ttk.Button(
            action_row,
            text="开始解析",
            command=self._on_parse_click,
            style="Primary.TButton",
        )
        self.parse_button.grid(row=0, column=0, sticky="w")

        self.import_button = ttk.Button(
            action_row,
            text="导入 txt/md",
            command=self._on_import_click,
            style="Secondary.TButton",
        )
        self.import_button.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.clear_button = ttk.Button(
            action_row,
            text="清空原文",
            command=self._on_clear_click,
            style="Secondary.TButton",
        )
        self.clear_button.grid(row=0, column=2, sticky="w", padx=(10, 0))

        tk.Label(
            action_row,
            text="支持直接粘贴，或导入 UTF-8 编码的 txt / md 文件。",
            bg=CARD_BACKGROUND,
            fg=TEXT_MUTED,
            font=("PingFang TC", 10),
            anchor="e",
        ).grid(row=0, column=3, sticky="e")

    def _build_output_card(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg=CARD_BACKGROUND,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=18,
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        self._build_card_header(
            card,
            title="解析结果",
            description="优先显示整篇总览，再保留分段解析细节。",
            meta_var=self.output_meta_var,
        )

        self.output_text = ScrolledText(
            card,
            wrap="word",
            height=20,
            font=("PingFang TC", 13),
            bg=OUTPUT_BACKGROUND,
            fg=TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor="#A58B73",
            padx=14,
            pady=14,
            spacing1=2,
            spacing2=5,
            spacing3=2,
            state="disabled",
            insertbackground=TEXT_PRIMARY,
            selectbackground="#DCCDBA",
            cursor="arrow",
        )
        self._configure_output_tags()
        self.output_text.grid(row=1, column=0, sticky="nsew", pady=(14, 16))

        action_row = tk.Frame(card, bg=CARD_BACKGROUND)
        action_row.grid(row=2, column=0, sticky="ew")
        action_row.grid_columnconfigure(3, weight=1)

        self.copy_button = ttk.Button(
            action_row,
            text="复制结果",
            command=self._on_copy_click,
            style="Secondary.TButton",
        )
        self.copy_button.grid(row=0, column=0, sticky="w")

        self.save_button = ttk.Button(
            action_row,
            text="保存到 Obsidian",
            command=self._on_save_click,
            style="Secondary.TButton",
            state="disabled",
        )
        self.save_button.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.export_button = ttk.Button(
            action_row,
            text="导出 Markdown",
            command=self._on_export_click,
            style="Secondary.TButton",
        )
        self.export_button.grid(row=0, column=2, sticky="w", padx=(10, 0))

        tk.Label(
            action_row,
            text="解析完成后可复制、导出 Markdown，或直接追加到 Obsidian。",
            bg=CARD_BACKGROUND,
            fg=TEXT_MUTED,
            font=("PingFang TC", 10),
            anchor="e",
        ).grid(row=0, column=3, sticky="e")

    def _configure_output_tags(self) -> None:
        self.output_text.tag_configure(
            "placeholder",
            foreground=TEXT_MUTED,
            font=("PingFang TC", 12),
            spacing3=6,
        )
        self.output_text.tag_configure(
            "placeholder_list",
            foreground=HEADER_BACKGROUND,
            font=("PingFang TC", 13, "bold"),
            lmargin1=10,
            lmargin2=10,
            spacing1=6,
            spacing3=4,
        )
        self.output_text.tag_configure(
            "section_title",
            foreground=HEADER_BACKGROUND,
            font=("PingFang TC", 15, "bold"),
            spacing1=14,
            spacing3=8,
        )
        self.output_text.tag_configure(
            "numbered_heading",
            foreground=PRIMARY_BUTTON,
            font=("PingFang TC", 13, "bold"),
            spacing1=8,
            spacing3=5,
        )
        self.output_text.tag_configure(
            "notice",
            foreground=TEXT_SUCCESS,
            font=("PingFang TC", 12, "bold"),
            spacing1=6,
            spacing3=6,
        )
        self.output_text.tag_configure(
            "success",
            foreground=TEXT_SUCCESS,
            font=("PingFang TC", 12, "bold"),
            spacing1=10,
            spacing3=6,
        )
        self.output_text.tag_configure(
            "error",
            foreground=TEXT_ERROR,
            font=("PingFang TC", 12, "bold"),
            spacing1=10,
            spacing3=6,
        )
        self.output_text.tag_configure(
            "divider",
            foreground=CARD_BORDER,
            font=("Avenir Next", 11, "bold"),
            justify="center",
            spacing1=10,
            spacing3=10,
        )
        self.output_text.tag_configure(
            "bullet",
            foreground=TEXT_PRIMARY,
            lmargin1=18,
            lmargin2=18,
            spacing3=3,
        )
        self.output_text.tag_configure(
            "body",
            foreground=TEXT_PRIMARY,
            font=("PingFang TC", 13),
            spacing3=4,
        )
        self.output_text.tag_configure(
            "spacer",
            spacing1=3,
            spacing3=3,
        )

    def _render_output_content(self, content: str, *, is_placeholder: bool) -> None:
        line_styles = build_output_line_styles(content, is_placeholder=is_placeholder)
        if not line_styles and content:
            line_styles = [(content, "body")]

        for line, tag_name in line_styles:
            self.output_text.insert(tk.END, line, tag_name)
            self.output_text.insert(tk.END, "\n")

    def _build_card_header(
        self,
        parent: tk.Frame,
        *,
        title: str,
        description: str,
        meta_var: tk.StringVar,
    ) -> None:
        header = tk.Frame(parent, bg=CARD_BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text=title,
            bg=CARD_BACKGROUND,
            fg=TEXT_PRIMARY,
            font=("PingFang TC", 16, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            header,
            textvariable=meta_var,
            bg=CARD_BACKGROUND,
            fg=TEXT_MUTED,
            font=("Avenir Next", 10, "bold"),
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        tk.Label(
            header,
            text=description,
            bg=CARD_BACKGROUND,
            fg=TEXT_MUTED,
            font=("PingFang TC", 10),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_status_bar(self, parent: tk.Frame) -> None:
        footer = tk.Frame(parent, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.grid_columnconfigure(1, weight=1)

        self.progress = ttk.Progressbar(
            footer,
            mode="indeterminate",
            length=120,
            style="App.Horizontal.TProgressbar",
        )
        self.progress.grid(row=0, column=0, sticky="w")

        self.status_label = tk.Label(
            footer,
            textvariable=self.status_var,
            bg=APP_BACKGROUND,
            fg=TEXT_MUTED,
            font=("PingFang TC", 11),
            anchor="w",
        )
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(14, 0))

    def _on_input_modified(self, _: tk.Event) -> None:
        if not self.input_text.edit_modified():
            return

        self.input_text.edit_modified(False)
        self._refresh_input_meta()
        self._update_action_state()

    def _refresh_input_meta(self) -> None:
        self.input_meta_var.set(build_text_metrics(self.input_text.get("1.0", tk.END)))

    def _set_status(self, message: str, tone: str = "normal") -> None:
        color_map = {
            "normal": TEXT_MUTED,
            "busy": PRIMARY_BUTTON,
            "success": TEXT_SUCCESS,
            "error": TEXT_ERROR,
        }
        self.status_var.set(message)
        self.status_label.config(fg=color_map.get(tone, TEXT_MUTED))

    def _set_busy(self, is_busy: bool) -> None:
        self.is_busy = is_busy
        if is_busy:
            self.progress.start(10)
        else:
            self.progress.stop()
        self._update_action_state()

    def _update_action_state(self) -> None:
        input_has_text = bool(self.input_text.get("1.0", tk.END).strip())
        output_has_text = bool(self.current_output.strip()) and not self.output_is_placeholder

        self.parse_button.config(state="disabled" if self.is_busy or not input_has_text else "normal")
        self.import_button.config(state="disabled" if self.is_busy else "normal")
        self.clear_button.config(state="disabled" if self.is_busy or not input_has_text else "normal")
        self.copy_button.config(state="disabled" if self.is_busy or not output_has_text else "normal")
        self.export_button.config(state="disabled" if self.is_busy or not output_has_text else "normal")
        save_enabled = bool(self.last_source_text and self.last_result and not self.is_busy)
        self.save_button.config(state="normal" if save_enabled else "disabled")

    def _set_output(self, content: str, *, is_placeholder: bool) -> None:
        self.current_output = content
        self.output_is_placeholder = is_placeholder
        self.output_meta_var.set(
            build_output_metrics(content, is_placeholder=is_placeholder)
        )
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", tk.END)
        self._render_output_content(content, is_placeholder=is_placeholder)
        self.output_text.config(state="disabled")
        self._update_action_state()

    def _on_parse_click(self) -> None:
        source_text = self.input_text.get("1.0", tk.END).strip()
        if not source_text:
            self._set_output("请先输入英文原文。", is_placeholder=False)
            self._set_status("输入区为空，无法开始解析。", tone="error")
            return

        self.last_source_text = ""
        self.last_result = ""
        self._set_busy(True)
        self._set_output("正在解析中，请稍候...\n\n长文章会先分段，再生成整篇总览。", is_placeholder=False)
        self._set_status("正在请求模型并整理结果。", tone="busy")

        worker = threading.Thread(
            target=self._analyze_in_background,
            args=(source_text,),
            daemon=True,
        )
        worker.start()

    def _analyze_in_background(self, source_text: str) -> None:
        try:
            result = analyze_text(source_text)
            success = True
        except ConfigError as exc:
            result = str(exc)
            success = False
        except LLMRequestError as exc:
            result = str(exc)
            success = False
        except Exception as exc:  # pragma: no cover - final UI fallback
            result = f"发生未预期错误：{exc}"
            success = False

        self.root.after(0, self._finish_analysis, source_text, result, success)

    def _finish_analysis(self, source_text: str, result: str, success: bool) -> None:
        if success:
            self.last_source_text = source_text
            self.last_result = result
            self._set_output(result, is_placeholder=False)
            self._set_status("解析完成，可以复制结果或保存到 Obsidian。", tone="success")
        else:
            self.last_source_text = ""
            self.last_result = ""
            self._set_output(result, is_placeholder=False)
            self._set_status("解析失败，请检查配置或网络后重试。", tone="error")

        self._set_busy(False)

    def _on_import_click(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="选择英文原文文件",
            filetypes=[
                ("Text and Markdown", "*.txt *.md *.markdown"),
                ("Text", "*.txt"),
                ("Markdown", "*.md *.markdown"),
                ("All files", "*.*"),
            ],
        )
        if not selected_path:
            return

        file_path = Path(selected_path).expanduser()
        if not is_supported_import_file(file_path):
            self._set_status("只支持导入 txt / md / markdown 文件。", tone="error")
            return

        try:
            imported_text = file_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            self._set_status(f"导入文件失败：{exc}", tone="error")
            return

        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", imported_text)
        self.input_text.edit_modified(False)
        self.imported_file_path = file_path
        self.last_source_text = ""
        self.last_result = ""
        self._refresh_input_meta()
        self._set_output(INITIAL_OUTPUT, is_placeholder=True)
        self._set_status(f"已导入文件：{file_path.name}", tone="success")
        self._update_action_state()

    def _on_clear_click(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.edit_modified(False)
        self.imported_file_path = None
        self.last_source_text = ""
        self.last_result = ""
        self._refresh_input_meta()
        self._set_output(INITIAL_OUTPUT, is_placeholder=True)
        self._set_status("内容已清空，可以重新粘贴文章。", tone="normal")

    def _on_copy_click(self) -> None:
        if self.output_is_placeholder or not self.current_output.strip():
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_output)
        self.root.update_idletasks()
        self._set_status("结果已复制到剪贴板。", tone="success")

    def _on_export_click(self) -> None:
        if self.output_is_placeholder or not self.current_output.strip():
            self._set_status("当前没有可导出的解析结果。", tone="error")
            return

        initial_file = (
            f"{self.imported_file_path.stem}-analysis.md"
            if self.imported_file_path is not None
            else DEFAULT_EXPORT_FILE_NAME
        )
        export_path = filedialog.asksaveasfilename(
            title="导出解析结果",
            defaultextension=".md",
            initialfile=initial_file,
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not export_path:
            return

        source_text = self.last_source_text or self.input_text.get("1.0", tk.END).strip()
        export_content = build_markdown_export_content(source_text, self.current_output)
        try:
            Path(export_path).expanduser().write_text(export_content, encoding="utf-8")
        except OSError as exc:
            self._set_status(f"导出 Markdown 失败：{exc}", tone="error")
            return

        self._set_status(f"已导出 Markdown：{Path(export_path).name}", tone="success")

    def _on_save_click(self) -> None:
        if not self.last_source_text or not self.last_result:
            self._set_output("请先完成一次解析，再保存到 Obsidian。", is_placeholder=False)
            self._set_status("当前没有可保存的解析结果。", tone="error")
            return

        try:
            note_path = append_to_obsidian_note(self.last_source_text, self.last_result)
        except ObsidianSaveError as exc:
            self._set_output(
                f"{self.last_result}\n\n---\n保存到 Obsidian 失败：{exc}",
                is_placeholder=False,
            )
            self._set_status("保存到 Obsidian 失败。", tone="error")
            return

        self._set_output(
            f"{self.last_result}\n\n---\n已保存到 Obsidian：{note_path}",
            is_placeholder=False,
        )
        self._set_status("已保存到 Obsidian。", tone="success")


def launch_app() -> None:
    root = tk.Tk()
    EnglishReadingAssistantApp(root)
    root.mainloop()
