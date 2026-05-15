import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from english_reading_assistant.config import (
    AppConfig,
    ConfigError,
    load_config,
    load_obsidian_config,
)
from english_reading_assistant.llm_client import (
    LLMRequestError,
    analyze_text,
    build_api_endpoint,
    build_overview_prompt,
    build_user_prompt,
    extract_error_detail,
    get_retry_timeout_seconds,
    parse_response_content,
    split_text_into_chunks,
)


class LoadConfigTests(unittest.TestCase):
    def test_load_config_reads_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "test-key",
                        "model": "deepseek-chat",
                        "system_prompt": "请使用简体中文回答",
                        "timeout_seconds": 12,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model, "deepseek-chat")
        self.assertEqual(config.system_prompt, "请使用简体中文回答")
        self.assertEqual(config.timeout_seconds, 12.0)

    def test_load_config_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "",
                        "model": "deepseek-chat",
                        "system_prompt": "请使用简体中文回答",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "未找到 API 密钥"):
                load_config(config_path)

    def test_load_obsidian_config_reads_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "vault"
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "test-key",
                        "model": "deepseek-chat",
                        "system_prompt": "请使用简体中文回答",
                        "obsidian": {
                            "vault_path": str(vault_path),
                            "note_path": "Inbox/English Reading.md",
                        },
                    }
                ),
                encoding="utf-8",
            )

            obsidian_config = load_obsidian_config(config_path)

        self.assertEqual(obsidian_config.vault_path, str(vault_path))
        self.assertEqual(obsidian_config.note_path, "Inbox/English Reading.md")

    def test_load_obsidian_config_rejects_absolute_note_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "vault"
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "test-key",
                        "model": "deepseek-chat",
                        "system_prompt": "请使用简体中文回答",
                        "obsidian": {
                            "vault_path": str(vault_path),
                            "note_path": "/absolute/path.md",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "note_path 必须是相对路径"):
                load_obsidian_config(config_path)


class PromptAndResponseTests(unittest.TestCase):
    def test_build_api_endpoint_handles_base_or_full_path(self) -> None:
        self.assertEqual(
            build_api_endpoint("https://api.deepseek.com/v1"),
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(
            build_api_endpoint("https://api.deepseek.com/v1/chat/completions"),
            "https://api.deepseek.com/v1/chat/completions",
        )

    def test_build_user_prompt_includes_source_text(self) -> None:
        prompt = build_user_prompt("This is a test sentence.")
        self.assertIn("中文意思", prompt)
        self.assertIn("This is a test sentence.", prompt)

    def test_build_user_prompt_marks_chunk_context_for_long_article(self) -> None:
        prompt = build_user_prompt("Part content.", part_index=2, total_parts=4)
        self.assertIn("第 2 / 4 部分", prompt)
        self.assertIn("请只解析当前这一部分", prompt)

    def test_build_overview_prompt_includes_all_part_results(self) -> None:
        prompt = build_overview_prompt(["第一部分结果", "第二部分结果"])
        self.assertIn("整合出一版整篇总览", prompt)
        self.assertIn("第 1 部分解析", prompt)
        self.assertIn("第 2 部分解析", prompt)

    def test_extract_error_detail_prefers_api_message(self) -> None:
        raw_error = json.dumps(
            {
                "error": {
                    "message": "Insufficient Balance",
                    "code": "insufficient_balance",
                }
            }
        )
        self.assertEqual(
            extract_error_detail(raw_error),
            "Insufficient Balance (code: insufficient_balance)",
        )

    def test_parse_response_content_returns_model_text(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "中文意思：这是一个测试。\n\n重点单词：test = 测试"
                    }
                }
            ]
        }
        self.assertIn("中文意思", parse_response_content(payload))

    def test_get_retry_timeout_seconds_uses_longer_retry_budget(self) -> None:
        self.assertEqual(get_retry_timeout_seconds(30), 90.0)
        self.assertEqual(get_retry_timeout_seconds(75), 150.0)

    def test_split_text_into_chunks_prefers_paragraph_boundaries(self) -> None:
        long_text = (
            "Paragraph one. " * 60
            + "\n\n"
            + "Paragraph two. " * 60
            + "\n\n"
            + "Paragraph three. " * 60
        )

        chunks = split_text_into_chunks(long_text, max_chars=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

    @patch("english_reading_assistant.llm_client.execute_request")
    @patch("english_reading_assistant.llm_client.load_config")
    def test_analyze_text_retries_once_after_timeout(
        self,
        mocked_load_config,
        mocked_execute_request,
    ) -> None:
        mocked_load_config.return_value = AppConfig(
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            model="deepseek-chat",
            system_prompt="请使用简体中文回答",
            timeout_seconds=30.0,
        )
        mocked_execute_request.side_effect = [
            TimeoutError("timed out"),
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "中文意思：重试后成功"
                            }
                        }
                    ]
                }
            ),
        ]

        result = analyze_text("A long article")

        self.assertEqual(result, "中文意思：重试后成功")
        self.assertEqual(mocked_execute_request.call_count, 2)
        first_call = mocked_execute_request.call_args_list[0]
        second_call = mocked_execute_request.call_args_list[1]
        self.assertEqual(first_call.args[1], 30.0)
        self.assertEqual(second_call.args[1], 90.0)

    @patch("english_reading_assistant.llm_client.execute_request")
    @patch("english_reading_assistant.llm_client.load_config")
    def test_analyze_text_reports_clear_timeout_after_retry(
        self,
        mocked_load_config,
        mocked_execute_request,
    ) -> None:
        mocked_load_config.return_value = AppConfig(
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            model="deepseek-chat",
            system_prompt="请使用简体中文回答",
            timeout_seconds=30.0,
        )
        mocked_execute_request.side_effect = [
            TimeoutError("timed out"),
            TimeoutError("timed out again"),
        ]

        with self.assertRaisesRegex(
            LLMRequestError,
            "当前超时设置：30 秒；已自动重试一次",
        ):
            analyze_text("A long article")

    @patch("english_reading_assistant.llm_client.perform_model_request")
    @patch("english_reading_assistant.llm_client.load_config")
    def test_analyze_text_splits_long_article_into_multiple_requests(
        self,
        mocked_load_config,
        mocked_perform_model_request,
    ) -> None:
        mocked_load_config.return_value = AppConfig(
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            model="deepseek-chat",
            system_prompt="请使用简体中文回答",
            timeout_seconds=30.0,
        )
        mocked_perform_model_request.side_effect = [
            "中文意思：第一部分",
            "中文意思：第二部分",
            "1. 整篇主旨：整篇总览",
        ]
        long_text = ("Paragraph one. " * 120) + "\n\n" + ("Paragraph two. " * 120)

        result = analyze_text(long_text)

        self.assertIn("已自动分成 2 部分解析", result)
        self.assertIn("【整篇总览】", result)
        self.assertIn("整篇主旨：整篇总览", result)
        self.assertIn("【第 1 部分】", result)
        self.assertIn("【第 2 部分】", result)
        self.assertEqual(mocked_perform_model_request.call_count, 3)

    @patch("english_reading_assistant.llm_client.perform_model_request")
    @patch("english_reading_assistant.llm_client.load_config")
    def test_analyze_text_keeps_part_results_when_overview_generation_fails(
        self,
        mocked_load_config,
        mocked_perform_model_request,
    ) -> None:
        mocked_load_config.return_value = AppConfig(
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            model="deepseek-chat",
            system_prompt="请使用简体中文回答",
            timeout_seconds=30.0,
        )
        mocked_perform_model_request.side_effect = [
            "中文意思：第一部分",
            "中文意思：第二部分",
            LLMRequestError("网络请求失败：连接超时"),
        ]
        long_text = ("Paragraph one. " * 120) + "\n\n" + ("Paragraph two. " * 120)

        result = analyze_text(long_text)

        self.assertIn("【整篇总览】", result)
        self.assertIn("生成失败：网络请求失败：连接超时", result)
        self.assertIn("已保留分段解析结果", result)
        self.assertIn("【第 1 部分】", result)
        self.assertIn("【第 2 部分】", result)


if __name__ == "__main__":
    unittest.main()
