import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import main


class MainEntryTests(unittest.TestCase):
    def test_main_returns_zero_when_app_launches(self) -> None:
        with patch("main.launch_app", return_value=None) as mocked_launch:
            self.assertEqual(main.main(), 0)

        mocked_launch.assert_called_once_with()

    def test_main_returns_one_when_app_launch_fails(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with patch("main.launch_app", side_effect=RuntimeError("boom")):
                self.assertEqual(main.main(), 1)

        self.assertIn("应用启动失败：boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
