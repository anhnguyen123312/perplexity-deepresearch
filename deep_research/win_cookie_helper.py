"""
Windows cookie extraction helper — runs elevated to decrypt Chrome v20 cookies.

Usage: python win_cookie_helper.py <output_json_path>

If not running as admin, re-launches itself elevated via UAC prompt.
"""

import ctypes
import json
import os
import subprocess
import sys


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_elevated(output_path: str) -> int:
    """Re-launch this script as admin via ShellExecuteW (UAC prompt)."""
    params = f'"{__file__}" "{output_path}"'
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 0  # SW_HIDE
    )
    # ShellExecuteW returns >32 on success
    return ret


def main():
    if len(sys.argv) != 2:
        print("Usage: win_cookie_helper.py <output_json_path>", file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[1]

    if not _is_admin():
        ret = _relaunch_elevated(output_path)
        if ret <= 32:
            print("UAC elevation denied or failed", file=sys.stderr)
            sys.exit(1)
        # Wait for the elevated process to write the output file
        import time
        for _ in range(30):
            time.sleep(1)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 2:
                sys.exit(0)
        print("Elevated process did not produce output in time", file=sys.stderr)
        sys.exit(1)

    # Running as admin — extract cookies
    import rookiepy

    raw_cookies = rookiepy.chrome(domains=["perplexity.ai"])
    cookies = {c["name"]: c["value"] for c in raw_cookies}

    with open(output_path, "w") as f:
        json.dump(cookies, f)

    print(f"Extracted {len(cookies)} cookies", file=sys.stderr)


if __name__ == "__main__":
    main()
