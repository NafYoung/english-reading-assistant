from pathlib import Path
import unittest


class LauncherScriptTests(unittest.TestCase):
    def test_run_command_targets_expected_env_and_entry(self) -> None:
        launcher_path = Path(__file__).resolve().parent.parent / "run.command"
        content = launcher_path.read_text(encoding="utf-8")

        self.assertIn('ENV_NAME="english-reading-assistant"', content)
        self.assertIn("python main.py", content)
        self.assertIn("conda activate", content)


if __name__ == "__main__":
    unittest.main()
