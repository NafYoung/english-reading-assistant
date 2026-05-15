import unittest
from pathlib import Path

from english_reading_assistant.ui import (
    build_markdown_export_content,
    build_output_line_styles,
    build_output_metrics,
    build_text_metrics,
    classify_output_line,
    is_supported_import_file,
)


class UiHelperTests(unittest.TestCase):
    def test_build_text_metrics_handles_empty_content(self) -> None:
        self.assertEqual(build_text_metrics(""), "0 字符 · 0 行")
        self.assertEqual(build_text_metrics("\n"), "0 字符 · 0 行")

    def test_build_text_metrics_counts_characters_and_lines(self) -> None:
        self.assertEqual(build_text_metrics("Hello"), "5 字符 · 1 行")
        self.assertEqual(build_text_metrics("Hello\nWorld"), "11 字符 · 2 行")

    def test_build_output_metrics_respects_placeholder_state(self) -> None:
        self.assertEqual(
            build_output_metrics("任意内容", is_placeholder=True),
            "等待解析结果",
        )
        self.assertEqual(
            build_output_metrics("解析完成", is_placeholder=False),
            "4 字符 · 1 行 · 可复制",
        )

    def test_classify_output_line_marks_semantic_sections(self) -> None:
        self.assertEqual(
            classify_output_line("【整篇总览】", is_placeholder=False),
            "section_title",
        )
        self.assertEqual(
            classify_output_line("1. 中文意思：示例", is_placeholder=False),
            "numbered_heading",
        )
        self.assertEqual(
            classify_output_line("保存到 Obsidian 失败：boom", is_placeholder=False),
            "error",
        )
        self.assertEqual(
            classify_output_line("已保存到 Obsidian：/tmp/demo.md", is_placeholder=False),
            "success",
        )

    def test_build_output_line_styles_handles_placeholder_lists(self) -> None:
        styles = build_output_line_styles(
            "请将英文原文贴到左侧输入区。\n\n1. 整篇总览",
            is_placeholder=True,
        )

        self.assertEqual(styles[0][1], "placeholder")
        self.assertEqual(styles[1][1], "spacer")
        self.assertEqual(styles[2][1], "placeholder_list")

    def test_is_supported_import_file_accepts_text_and_markdown(self) -> None:
        self.assertTrue(is_supported_import_file(Path("article.txt")))
        self.assertTrue(is_supported_import_file(Path("article.md")))
        self.assertTrue(is_supported_import_file(Path("article.markdown")))
        self.assertFalse(is_supported_import_file(Path("article.pdf")))

    def test_build_markdown_export_content_includes_source_and_result(self) -> None:
        exported = build_markdown_export_content("Source text", "Result text")

        self.assertIn("# English Reading Assistant 导出", exported)
        self.assertIn("## 英文原文", exported)
        self.assertIn("Source text", exported)
        self.assertIn("## 解析结果", exported)
        self.assertIn("Result text", exported)


if __name__ == "__main__":
    unittest.main()
