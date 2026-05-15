from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from english_reading_assistant.desktop_launcher import (
    APP_NAME,
    BACKGROUND_LAUNCHER_NAME,
    DesktopLauncherError,
    build_launcher_applescript,
    find_icon_source,
    install_desktop_launcher,
)


class DesktopLauncherTests(unittest.TestCase):
    def test_build_launcher_applescript_uses_background_shell_script(self) -> None:
        launcher_path = Path("/Users/demo/My Project/run_background.command")

        script = build_launcher_applescript(launcher_path)

        self.assertIn(
            'set launcherPath to "/Users/demo/My Project/run_background.command"',
            script,
        )
        self.assertIn("do shell script quoted form of launcherPath", script)
        self.assertNotIn('tell application "Terminal"', script)

    @patch("english_reading_assistant.desktop_launcher.shutil.which")
    @patch("english_reading_assistant.desktop_launcher.subprocess.run")
    def test_install_desktop_launcher_invokes_osacompile(
        self,
        mock_run,
        mock_which,
    ) -> None:
        mock_which.return_value = "/usr/bin/osacompile"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_dir = temp_root / "project"
            project_dir.mkdir()
            (project_dir / BACKGROUND_LAUNCHER_NAME).write_text(
                "#!/bin/zsh\n",
                encoding="utf-8",
            )
            output_path = temp_root / "Desktop" / APP_NAME

            created_path = install_desktop_launcher(project_dir, output_path)

        self.assertEqual(created_path, output_path)
        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/osacompile", "-o", str(output_path)])
        self.assertEqual(Path(command[3]).suffix, ".applescript")
        self.assertFalse(Path(command[3]).exists())
        self.assertTrue(mock_run.call_args.kwargs["check"])
        self.assertTrue(mock_run.call_args.kwargs["capture_output"])
        self.assertTrue(mock_run.call_args.kwargs["text"])

    def test_find_icon_source_returns_project_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "project"
            icon_path = project_dir / "assets" / "app-icon.png"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(b"png")

            self.assertEqual(find_icon_source(project_dir), icon_path)

    @patch("english_reading_assistant.desktop_launcher.shutil.which")
    def test_install_desktop_launcher_rejects_existing_output(self, mock_which) -> None:
        mock_which.return_value = "/usr/bin/osacompile"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_dir = temp_root / "project"
            project_dir.mkdir()
            (project_dir / BACKGROUND_LAUNCHER_NAME).write_text(
                "#!/bin/zsh\n",
                encoding="utf-8",
            )
            output_path = temp_root / "Desktop" / APP_NAME
            output_path.parent.mkdir()
            output_path.mkdir()

            with self.assertRaisesRegex(DesktopLauncherError, "已存在"):
                install_desktop_launcher(project_dir, output_path)

    @patch("english_reading_assistant.desktop_launcher.shutil.which")
    @patch("english_reading_assistant.desktop_launcher.install_custom_icon")
    @patch("english_reading_assistant.desktop_launcher.subprocess.run")
    def test_install_desktop_launcher_can_replace_existing_output(
        self,
        mock_run,
        mock_install_custom_icon,
        mock_which,
    ) -> None:
        mock_which.return_value = "/usr/bin/osacompile"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_dir = temp_root / "project"
            project_dir.mkdir()
            (project_dir / BACKGROUND_LAUNCHER_NAME).write_text(
                "#!/bin/zsh\n",
                encoding="utf-8",
            )
            output_path = temp_root / "Desktop" / APP_NAME
            output_path.parent.mkdir()
            output_path.mkdir()
            (output_path / "old.txt").write_text("legacy", encoding="utf-8")
            icon_path = project_dir / "assets" / "app-icon.png"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(b"png")

            created_path = install_desktop_launcher(
                project_dir,
                output_path,
                overwrite_existing=True,
            )

        self.assertEqual(created_path, output_path)
        self.assertEqual(mock_run.call_count, 1)
        mock_install_custom_icon.assert_called_once_with(output_path, icon_path)


if __name__ == "__main__":
    unittest.main()
