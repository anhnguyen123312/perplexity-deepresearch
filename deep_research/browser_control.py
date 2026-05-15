"""
Cross-platform browser control functions.

Provides Chrome detection, interactive/non-interactive prompting,
quit/relaunch functionality, and structured result tracking.

Supports macOS (AppleScript), Linux (pgrep/pkill), and Windows (tasklist/taskkill).
"""

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChromeAccessResult:
    """Result of attempting to ensure Chrome accessibility for cookie extraction.

    Attributes:
        was_running: True if Chrome was running when check started
        was_quit: True if Chrome was quit during this operation
        accessible: True if Chrome cookies are now accessible
    """

    was_running: bool
    was_quit: bool
    accessible: bool


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_windows() -> bool:
    return sys.platform == "win32"


def _find_chrome_process_name() -> str | None:
    """Find the running Chrome process name on Linux.

    Returns:
        str: Process name if found, None otherwise
    """
    for name in ("google-chrome", "chrome", "chromium-browser", "chromium"):
        try:
            result = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return name
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            continue
    return None


def _find_chrome_command() -> str | None:
    """Find the Chrome executable on Linux.

    Returns:
        str: Path to Chrome executable if found, None otherwise
    """
    for cmd in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
        try:
            result = subprocess.run(
                ["which", cmd],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            continue
    return None


def _find_chrome_exe_windows() -> str | None:
    """Find the Chrome executable on Windows.

    Returns:
        str: Path to chrome.exe if found, None otherwise
    """
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def is_chrome_running() -> bool:
    """Check if Google Chrome is currently running.

    Uses AppleScript on macOS, pgrep on Linux.

    Returns:
        bool: True if Chrome is running, False otherwise
    """
    if _is_macos():
        script = 'tell application "System Events" to (name of processes) contains "Google Chrome"'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip().lower() == "true"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    elif _is_windows():
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "chrome.exe" in result.stdout.lower()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    elif _is_linux():
        return _find_chrome_process_name() is not None
    return False


def prompt_close_chrome() -> bool:
    """Prompt user for permission to close Chrome.

    Contract: ALWAYS returns bool, NEVER raises exceptions.

    Behavior:
    - If PERPLEXITY_ALLOW_CHROME_QUIT=1 env var set: returns True (auto-approve)
    - If not running in TTY (non-interactive): returns False
    - If interactive: prompts user and returns their choice

    Returns:
        bool: True if user approves closing Chrome, False otherwise
    """
    if os.environ.get("PERPLEXITY_ALLOW_CHROME_QUIT") == "1":
        return True

    try:
        if not sys.stdin.isatty():
            return False
    except Exception:
        return False

    try:
        print(
            "\n⚠️  Google Chrome is currently running and blocking cookie access.",
            file=sys.stderr,
        )
        print(
            "Would you like to close Chrome? Your tabs will be restored when you reopen it.",
            file=sys.stderr,
        )
        response = input("Close Chrome? (y/N): ")
        return response.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt, OSError):
        return False


def quit_chrome() -> bool:
    """Gracefully quit Google Chrome.

    Uses AppleScript on macOS, pkill (SIGTERM) on Linux.
    Polls for process exit with 500ms intervals, up to 10 second timeout.

    Returns:
        bool: True if Chrome quit successfully, False otherwise
    """
    if _is_macos():
        quit_script = 'tell application "Google Chrome" to quit'
        try:
            subprocess.run(
                ["osascript", "-e", quit_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    elif _is_windows():
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "chrome.exe"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    elif _is_linux():
        proc_name = _find_chrome_process_name()
        if not proc_name:
            return True  # Already not running
        try:
            subprocess.run(
                ["pkill", "-TERM", "-x", proc_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    else:
        return False

    max_wait = 10.0
    poll_interval = 0.5
    elapsed = 0.0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        if not is_chrome_running():
            return True

    return False


def relaunch_chrome() -> bool:
    """Relaunch Google Chrome.

    Uses AppleScript on macOS, launches Chrome executable on Linux.

    Returns:
        bool: True if Chrome was relaunched successfully, False otherwise
    """
    if _is_macos():
        activate_script = 'tell application "Google Chrome" to activate'
        try:
            subprocess.run(
                ["osascript", "-e", activate_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False
    elif _is_windows():
        chrome_exe = _find_chrome_exe_windows()
        if not chrome_exe:
            return False
        try:
            subprocess.Popen(
                [chrome_exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except (OSError, subprocess.SubprocessError):
            return False
    elif _is_linux():
        chrome_cmd = _find_chrome_command()
        if not chrome_cmd:
            return False
        try:
            subprocess.Popen(
                [chrome_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError):
            return False
    else:
        return False

    time.sleep(1.0)
    return is_chrome_running()


def ensure_chrome_accessible() -> ChromeAccessResult:
    """Orchestrate the prompt->quit flow to ensure Chrome cookies are accessible.

    This function coordinates checking if Chrome is running, prompting the user
    for permission to quit, and quitting Chrome if approved.

    Contract: NEVER raises exceptions. Returns structured result.

    Returns:
        ChromeAccessResult: Structured result with was_running, was_quit, accessible fields
    """
    was_running = is_chrome_running()

    if not was_running:
        return ChromeAccessResult(was_running=False, was_quit=False, accessible=True)

    if not prompt_close_chrome():
        return ChromeAccessResult(was_running=True, was_quit=False, accessible=False)

    quit_success = quit_chrome()

    return ChromeAccessResult(
        was_running=True,
        was_quit=quit_success,
        accessible=quit_success,
    )


def prompt_keychain_password() -> str | None:
    """Prompt user for password to decrypt Chrome cookies.

    On macOS, uses a secure AppleScript dialog (Keychain password).
    On Linux, uses terminal getpass (GNOME Keyring / kwallet password not
    typically required as pycookiecheat handles D-Bus Secret Service).
    On Windows, returns None (DPAPI handles decryption transparently).

    Returns:
        str: Password entered by user, or None if cancelled
    """
    if _is_windows():
        return None  # DPAPI handles decryption transparently
    elif _is_macos():
        script = """
        tell application "System Events"
            activate
            set userPassword to text returned of (display dialog "Perplexity Deep Research needs your password to access Chrome cookies from Keychain.

This is your macOS login password." default answer "" with hidden answer with title "Keychain Access Required" buttons {"Cancel", "OK"} default button "OK")
            return userPassword
        end tell
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes to enter password
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return None
    else:
        # On Linux, try terminal-based password prompt
        import getpass

        try:
            if not sys.stdin.isatty():
                return None
            password = getpass.getpass(
                "Enter password to decrypt Chrome cookies (or Ctrl+C to cancel): "
            )
            return password if password else None
        except (EOFError, KeyboardInterrupt, OSError):
            return None


def check_full_disk_access() -> bool:
    """Check if terminal can read Chrome cookie database.

    On macOS, checks Full Disk Access permission.
    On Linux, checks if the Chrome cookie file is readable.
    On Windows, not applicable (always returns True).

    Returns:
        bool: True if has access, False otherwise
    """
    if _is_windows():
        return True
    elif _is_macos():
        cookie_path = (
            Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
        )
    elif _is_linux():
        # Check common Linux Chrome cookie paths
        candidates = [
            Path.home() / ".config/google-chrome/Default/Cookies",
            Path.home() / ".config/chromium/Default/Cookies",
        ]
        cookie_path = None
        for candidate in candidates:
            if candidate.exists():
                cookie_path = candidate
                break
        if cookie_path is None:
            return True  # No cookie file found, not a permission issue
    else:
        return True

    try:
        with open(cookie_path, "rb") as f:
            f.read(1)
        return True
    except PermissionError:
        return False
    except FileNotFoundError:
        return True  # File doesn't exist, but that's not a permission issue


def show_full_disk_access_dialog():
    """Show instructions for granting cookie access.

    On macOS, shows an AppleScript dialog and opens System Settings.
    On Linux, prints instructions to stderr.
    On Windows, not applicable (no-op).
    """
    if _is_windows():
        return
    elif _is_macos():
        script = """
        tell application "System Events"
            activate
            display dialog "Perplexity Deep Research needs Full Disk Access to read Chrome cookies.

Please grant access:
1. Open System Settings -> Privacy & Security -> Full Disk Access
2. Click + and add your terminal app
3. Toggle ON and restart your terminal

Click OK to open System Settings." with title "Full Disk Access Required" buttons {"Cancel", "Open Settings"} default button "Open Settings"
        end tell
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if "Open Settings" in result.stdout or result.returncode == 0:
                subprocess.run(
                    [
                        "open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
                    ]
                )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
    elif _is_linux():
        print(
            "\nPerplexity Deep Research cannot read Chrome cookies.",
            file=sys.stderr,
        )
        print(
            "Please ensure Chrome/Chromium is installed and you have read access to:",
            file=sys.stderr,
        )
        print(
            "  ~/.config/google-chrome/Default/Cookies",
            file=sys.stderr,
        )
        print(
            "  or ~/.config/chromium/Default/Cookies",
            file=sys.stderr,
        )
