"""
macOS browser control functions using AppleScript.

Provides Chrome detection, interactive/non-interactive prompting,
quit/relaunch functionality, and structured result tracking.
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


def is_chrome_running() -> bool:
    """Check if Google Chrome is currently running on macOS.

    Uses AppleScript to query System Events for running processes.

    Returns:
        bool: True if Chrome is running, False otherwise
    """
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
    """Gracefully quit Google Chrome using AppleScript.

    Sends quit command and polls for process exit with 500ms intervals,
    up to 10 second timeout.

    Returns:
        bool: True if Chrome quit successfully, False otherwise
    """
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
    """Relaunch Google Chrome using AppleScript.

    Activates Chrome and verifies it's running.

    Returns:
        bool: True if Chrome was relaunched successfully, False otherwise
    """
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

    time.sleep(1.0)
    return is_chrome_running()


def ensure_chrome_accessible() -> ChromeAccessResult:
    """Orchestrate the prompt→quit flow to ensure Chrome cookies are accessible.

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
    """Prompt user for keychain password using macOS secure dialog.

    Returns:
        str: Password entered by user, or None if cancelled
    """
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


def check_full_disk_access() -> bool:
    """Check if terminal has Full Disk Access permission.

    Returns:
        bool: True if has access, False otherwise
    """
    cookie_path = (
        Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    )
    try:
        # Try to open the file - will fail without Full Disk Access
        with open(cookie_path, "rb") as f:
            f.read(1)
        return True
    except PermissionError:
        return False
    except FileNotFoundError:
        return True  # File doesn't exist, but that's not a permission issue


def show_full_disk_access_dialog():
    """Show dialog explaining how to grant Full Disk Access."""
    script = """
    tell application "System Events"
        activate
        display dialog "Perplexity Deep Research needs Full Disk Access to read Chrome cookies.

Please grant access:
1. Open System Settings → Privacy & Security → Full Disk Access
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
            # Open System Settings to Full Disk Access
            subprocess.run(
                [
                    "open",
                    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
                ]
            )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass
