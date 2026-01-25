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
