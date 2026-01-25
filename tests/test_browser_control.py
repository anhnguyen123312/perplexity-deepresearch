"""Tests for browser_control module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from perplexity_deep_research.browser_control import (
    ChromeAccessResult,
    ensure_chrome_accessible,
    is_chrome_running,
    prompt_close_chrome,
    quit_chrome,
    relaunch_chrome,
)


class TestIsChromeRunning:
    def test_is_chrome_running_true(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "true\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = is_chrome_running()

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == [
            "osascript",
            "-e",
            'tell application "System Events" to (name of processes) contains "Google Chrome"',
        ]

    def test_is_chrome_running_false(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "false\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = is_chrome_running()

        assert result is False
        mock_run.assert_called_once()

    def test_is_chrome_running_timeout(self) -> None:
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 5)
        ):
            result = is_chrome_running()

        assert result is False

    def test_is_chrome_running_subprocess_error(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("error")):
            result = is_chrome_running()

        assert result is False


class TestQuitChrome:
    def test_quit_chrome_waits(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        call_count = 0

        def mock_run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result
            mock_check = MagicMock()
            mock_check.stdout = "false\n" if call_count >= 3 else "true\n"
            return mock_check

        with patch("subprocess.run", side_effect=mock_run_side_effect):
            with patch("time.sleep") as mock_sleep:
                result = quit_chrome()

        assert result is True
        assert mock_sleep.call_count >= 1

    def test_quit_chrome_timeout(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""

        mock_check = MagicMock()
        mock_check.stdout = "true\n"

        with patch("subprocess.run", side_effect=[mock_result] + [mock_check] * 25):
            with patch("time.sleep"):
                result = quit_chrome()

        assert result is False


class TestPromptCloseChrome:
    def test_prompt_interactive_yes(self) -> None:
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", return_value="y"):
                with patch("builtins.print"):
                    result = prompt_close_chrome()

        assert result is True

    def test_prompt_interactive_no(self) -> None:
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", return_value="n"):
                with patch("builtins.print"):
                    result = prompt_close_chrome()

        assert result is False

    def test_prompt_non_interactive_returns_false(self) -> None:
        with patch("sys.stdin.isatty", return_value=False):
            result = prompt_close_chrome()

        assert result is False

    def test_prompt_non_interactive_env_override(self) -> None:
        with patch.dict("os.environ", {"PERPLEXITY_ALLOW_CHROME_QUIT": "1"}):
            with patch("sys.stdin.isatty", return_value=False):
                result = prompt_close_chrome()

        assert result is True

    def test_prompt_isatty_exception_returns_false(self) -> None:
        mock_stdin = MagicMock()
        mock_stdin.isatty.side_effect = OSError("error")

        with patch("sys.stdin", mock_stdin):
            result = prompt_close_chrome()

        assert result is False

    def test_prompt_input_eof_returns_false(self) -> None:
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", side_effect=EOFError()):
                with patch("builtins.print"):
                    result = prompt_close_chrome()

        assert result is False

    def test_prompt_keyboard_interrupt_returns_false(self) -> None:
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", side_effect=KeyboardInterrupt()):
                with patch("builtins.print"):
                    result = prompt_close_chrome()

        assert result is False


class TestRelaunchChrome:
    def test_relaunch_chrome_success(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""

        mock_check = MagicMock()
        mock_check.stdout = "true\n"

        with patch("subprocess.run", side_effect=[mock_result, mock_check]):
            with patch("time.sleep"):
                result = relaunch_chrome()

        assert result is True

    def test_relaunch_chrome_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""

        mock_check = MagicMock()
        mock_check.stdout = "false\n"

        with patch("subprocess.run", side_effect=[mock_result, mock_check]):
            with patch("time.sleep"):
                result = relaunch_chrome()

        assert result is False

    def test_relaunch_chrome_subprocess_error(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("error")):
            result = relaunch_chrome()

        assert result is False


class TestEnsureChromeAccessible:
    def test_ensure_chrome_accessible_returns_result(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "false\n"

        with patch("subprocess.run", return_value=mock_result):
            result = ensure_chrome_accessible()

        assert isinstance(result, ChromeAccessResult)
        assert hasattr(result, "was_running")
        assert hasattr(result, "was_quit")
        assert hasattr(result, "accessible")

    def test_ensure_chrome_accessible_not_running(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "false\n"

        with patch("subprocess.run", return_value=mock_result):
            result = ensure_chrome_accessible()

        assert result == ChromeAccessResult(
            was_running=False, was_quit=False, accessible=True
        )

    def test_ensure_chrome_accessible_quit(self) -> None:
        call_count = 0

        def mock_run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.stdout = "true\n"
            elif call_count == 2:
                mock.stdout = ""
            else:
                mock.stdout = "false\n"
            return mock

        with patch("subprocess.run", side_effect=mock_run_side_effect):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("builtins.input", return_value="y"):
                    with patch("builtins.print"):
                        with patch("time.sleep"):
                            result = ensure_chrome_accessible()

        assert result == ChromeAccessResult(
            was_running=True, was_quit=True, accessible=True
        )

    def test_ensure_chrome_accessible_user_declines(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "true\n"

        with patch("subprocess.run", return_value=mock_result):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("builtins.input", return_value="n"):
                    with patch("builtins.print"):
                        result = ensure_chrome_accessible()

        assert result == ChromeAccessResult(
            was_running=True, was_quit=False, accessible=False
        )

    def test_ensure_chrome_accessible_non_interactive(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "true\n"

        with patch("subprocess.run", return_value=mock_result):
            with patch("sys.stdin.isatty", return_value=False):
                result = ensure_chrome_accessible()

        assert result == ChromeAccessResult(
            was_running=True, was_quit=False, accessible=False
        )


class TestChromeAccessResult:
    def test_dataclass_fields(self) -> None:
        result = ChromeAccessResult(was_running=True, was_quit=True, accessible=True)

        assert result.was_running is True
        assert result.was_quit is True
        assert result.accessible is True

    def test_dataclass_equality(self) -> None:
        result1 = ChromeAccessResult(was_running=True, was_quit=False, accessible=False)
        result2 = ChromeAccessResult(was_running=True, was_quit=False, accessible=False)

        assert result1 == result2
