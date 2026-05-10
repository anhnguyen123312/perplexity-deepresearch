"""Tests for browser_control module."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from perplexity_deep_research.browser_control import (
    ChromeAccessResult,
    check_full_disk_access,
    ensure_chrome_accessible,
    is_chrome_running,
    prompt_close_chrome,
    prompt_keychain_password,
    quit_chrome,
    relaunch_chrome,
    show_full_disk_access_dialog,
)


@pytest.fixture(autouse=True)
def _default_is_windows_false(request):
    """Default `_is_windows()` to False so macOS/Linux tests work on a Windows host.

    Windows-specific test classes (`*Windows`) explicitly re-patch `_is_windows`
    to True inside each test, which supersedes this fixture for the duration
    of that `with patch(...)` block.
    """
    cls = getattr(request.node, "cls", None)
    if cls is not None and cls.__name__.endswith("Windows"):
        yield
        return
    with patch(
        "perplexity_deep_research.browser_control._is_windows", return_value=False
    ):
        yield


class TestIsChromeRunningMacOS:
    def test_is_chrome_running_true(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "true\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    result = is_chrome_running()

        assert result is False
        mock_run.assert_called_once()

    def test_is_chrome_running_timeout(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("osascript", 5),
                ):
                    result = is_chrome_running()

        assert result is False

    def test_is_chrome_running_subprocess_error(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.SubprocessError("error"),
                ):
                    result = is_chrome_running()

        assert result is False


class TestIsChromeRunningLinux:
    def test_is_chrome_running_true_linux(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=True,
            ):
                with patch("subprocess.run", return_value=mock_result):
                    result = is_chrome_running()

        assert result is True

    def test_is_chrome_running_false_linux(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=True,
            ):
                with patch("subprocess.run", return_value=mock_result):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "subprocess.run", side_effect=[mock_result] + [mock_check] * 25
                ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", side_effect=[mock_result, mock_check]):
                    with patch("time.sleep"):
                        result = relaunch_chrome()

        assert result is True

    def test_relaunch_chrome_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""

        mock_check = MagicMock()
        mock_check.stdout = "false\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", side_effect=[mock_result, mock_check]):
                    with patch("time.sleep"):
                        result = relaunch_chrome()

        assert result is False

    def test_relaunch_chrome_subprocess_error(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.SubprocessError("error"),
                ):
                    result = relaunch_chrome()

        assert result is False


class TestEnsureChromeAccessible:
    def test_ensure_chrome_accessible_returns_result(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "false\n"
        mock_result.returncode = 1

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", return_value=mock_result):
                    result = ensure_chrome_accessible()

        assert isinstance(result, ChromeAccessResult)
        assert hasattr(result, "was_running")
        assert hasattr(result, "was_quit")
        assert hasattr(result, "accessible")

    def test_ensure_chrome_accessible_not_running(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "false\n"
        mock_result.returncode = 1

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
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


class TestPromptKeychainPasswordMacOS:
    def test_prompt_keychain_password_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test_password\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch("subprocess.run", return_value=mock_result):
                result = prompt_keychain_password()

        assert result == "test_password"

    def test_prompt_keychain_password_cancelled(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch("subprocess.run", return_value=mock_result):
                result = prompt_keychain_password()

        assert result is None

    def test_prompt_keychain_password_timeout(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("osascript", 120),
            ):
                result = prompt_keychain_password()

        assert result is None

    def test_prompt_keychain_password_subprocess_error(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "subprocess.run",
                side_effect=subprocess.SubprocessError("error"),
            ):
                result = prompt_keychain_password()

        assert result is None


class TestPromptKeychainPasswordLinux:
    def test_prompt_password_linux_success(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("getpass.getpass", return_value="linux_password"):
                    result = prompt_keychain_password()

        assert result == "linux_password"

    def test_prompt_password_linux_non_interactive(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch("sys.stdin.isatty", return_value=False):
                result = prompt_keychain_password()

        assert result is None

    def test_prompt_password_linux_cancelled(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("getpass.getpass", side_effect=KeyboardInterrupt()):
                    result = prompt_keychain_password()

        assert result is None


class TestCheckFullDiskAccess:
    def test_check_full_disk_access_has_access_macos(self, tmp_path) -> None:
        cookie_file = tmp_path / "Cookies"
        cookie_file.write_bytes(b"test")

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "perplexity_deep_research.browser_control.Path.home",
                    return_value=tmp_path,
                ):
                    with patch("builtins.open", MagicMock()):
                        result = check_full_disk_access()

        assert result is True

    def test_check_full_disk_access_permission_denied(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "builtins.open", side_effect=PermissionError("access denied")
                ):
                    result = check_full_disk_access()

        assert result is False

    def test_check_full_disk_access_file_not_found(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "builtins.open", side_effect=FileNotFoundError("not found")
                ):
                    result = check_full_disk_access()

        assert result is True

    def test_check_full_disk_access_linux(self, tmp_path) -> None:
        # Create a Chrome cookie file on "Linux"
        cookie_file = tmp_path / ".config/google-chrome/Default/Cookies"
        cookie_file.parent.mkdir(parents=True)
        cookie_file.write_bytes(b"test")

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control.Path.home",
                    return_value=tmp_path,
                ):
                    result = check_full_disk_access()

        assert result is True

    def test_check_full_disk_access_linux_no_chrome(self, tmp_path) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control.Path.home",
                    return_value=tmp_path,
                ):
                    result = check_full_disk_access()

        # No cookie file found = not a permission issue
        assert result is True


class TestShowFullDiskAccessDialog:
    def test_show_full_disk_access_dialog_opens_settings(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Open Settings"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    show_full_disk_access_dialog()

        assert mock_run.call_count == 2

    def test_show_full_disk_access_dialog_cancelled(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    show_full_disk_access_dialog()

        assert mock_run.call_count == 1

    def test_show_full_disk_access_dialog_timeout(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=False,
            ):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("osascript", 60),
                ):
                    show_full_disk_access_dialog()

    def test_show_full_disk_access_dialog_linux(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_linux",
                return_value=True,
            ):
                with patch("builtins.print") as mock_print:
                    show_full_disk_access_dialog()

        # Should have printed Linux-specific instructions
        assert mock_print.call_count >= 1


class TestIsChromeRunningWindows:
    def test_is_chrome_running_true_windows(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "chrome.exe                    1234 Console   1   100,000 K\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch("subprocess.run", return_value=mock_result) as mock_run:
                        result = is_chrome_running()

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "tasklist"
        assert "chrome.exe" in " ".join(call_args)

    def test_is_chrome_running_false_windows(self) -> None:
        mock_result = MagicMock()
        # tasklist on Windows prints an info banner when no matches found
        mock_result.stdout = "INFO: No tasks are running which match the specified criteria.\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch("subprocess.run", return_value=mock_result):
                        result = is_chrome_running()

        assert result is False

    def test_is_chrome_running_windows_timeout(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "subprocess.run",
                        side_effect=subprocess.TimeoutExpired("tasklist", 5),
                    ):
                        result = is_chrome_running()

        assert result is False


class TestQuitChromeWindows:
    def test_quit_chrome_windows_success(self) -> None:
        # First call: taskkill. Subsequent: is_chrome_running poll → false (chrome gone)
        mock_taskkill = MagicMock()
        mock_taskkill.stdout = ""
        mock_check_gone = MagicMock()
        mock_check_gone.stdout = "INFO: No tasks are running\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "subprocess.run",
                        side_effect=[mock_taskkill, mock_check_gone],
                    ) as mock_run:
                        with patch("time.sleep"):
                            result = quit_chrome()

        assert result is True
        # First call must be taskkill /F /IM chrome.exe
        first_call = mock_run.call_args_list[0][0][0]
        assert first_call[0] == "taskkill"
        assert "/F" in first_call
        assert "chrome.exe" in first_call

    def test_quit_chrome_windows_subprocess_error(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "subprocess.run",
                        side_effect=subprocess.SubprocessError("nope"),
                    ):
                        result = quit_chrome()

        assert result is False


class TestRelaunchChromeWindows:
    def test_relaunch_chrome_windows_success(self, tmp_path) -> None:
        chrome_exe = tmp_path / "chrome.exe"
        chrome_exe.write_bytes(b"")

        mock_running = MagicMock()
        mock_running.stdout = "chrome.exe  1234 Console  1  100 K\n"

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "perplexity_deep_research.browser_control._find_chrome_exe_windows",
                        return_value=str(chrome_exe),
                    ):
                        with patch("subprocess.Popen") as mock_popen:
                            with patch(
                                "subprocess.run", return_value=mock_running
                            ):
                                with patch("time.sleep"):
                                    result = relaunch_chrome()

        assert result is True
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == [str(chrome_exe)]

    def test_relaunch_chrome_windows_no_exe_found(self) -> None:
        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "perplexity_deep_research.browser_control._find_chrome_exe_windows",
                        return_value=None,
                    ):
                        result = relaunch_chrome()

        assert result is False

    def test_relaunch_chrome_windows_popen_error(self, tmp_path) -> None:
        chrome_exe = tmp_path / "chrome.exe"
        chrome_exe.write_bytes(b"")

        with patch(
            "perplexity_deep_research.browser_control._is_macos", return_value=False
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_windows",
                return_value=True,
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch(
                        "perplexity_deep_research.browser_control._find_chrome_exe_windows",
                        return_value=str(chrome_exe),
                    ):
                        with patch(
                            "subprocess.Popen",
                            side_effect=OSError("denied"),
                        ):
                            result = relaunch_chrome()

        assert result is False


class TestFindChromeExeWindows:
    def test_finds_program_files_install(self, tmp_path, monkeypatch) -> None:
        from perplexity_deep_research.browser_control import _find_chrome_exe_windows

        prog_files = tmp_path / "Program Files"
        chrome_exe = prog_files / "Google" / "Chrome" / "Application" / "chrome.exe"
        chrome_exe.parent.mkdir(parents=True)
        chrome_exe.write_bytes(b"")

        monkeypatch.setenv("PROGRAMFILES", str(prog_files))
        monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "Program Files (x86)"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

        assert _find_chrome_exe_windows() == str(chrome_exe)

    def test_returns_none_when_not_installed(self, tmp_path, monkeypatch) -> None:
        from perplexity_deep_research.browser_control import _find_chrome_exe_windows

        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
        monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "pfx86"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))

        assert _find_chrome_exe_windows() is None


class TestPromptKeychainPasswordWindows:
    def test_returns_none_on_windows(self) -> None:
        # On Windows DPAPI handles decryption — no password prompt needed
        with patch(
            "perplexity_deep_research.browser_control._is_windows", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_macos", return_value=False
            ):
                result = prompt_keychain_password()

        assert result is None


class TestCheckFullDiskAccessWindows:
    def test_returns_true_on_windows(self) -> None:
        # Windows has no equivalent to macOS Full Disk Access
        with patch(
            "perplexity_deep_research.browser_control._is_windows", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_macos", return_value=False
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    assert check_full_disk_access() is True


class TestShowFullDiskAccessDialogWindows:
    def test_noop_on_windows(self) -> None:
        # Should be a no-op on Windows — no exception, no prints
        with patch(
            "perplexity_deep_research.browser_control._is_windows", return_value=True
        ):
            with patch(
                "perplexity_deep_research.browser_control._is_macos", return_value=False
            ):
                with patch(
                    "perplexity_deep_research.browser_control._is_linux",
                    return_value=False,
                ):
                    with patch("subprocess.run") as mock_run:
                        with patch("builtins.print") as mock_print:
                            show_full_disk_access_dialog()

        mock_run.assert_not_called()
        mock_print.assert_not_called()
