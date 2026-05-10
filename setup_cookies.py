"""
Interactive cookie setup for Perplexity Deep Research on Windows.

Guides user to extract session token from Chrome DevTools.
"""

import json
import os
import sys
from pathlib import Path


def get_output_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    return Path(local_app_data) / "perplexity-deep-research" / "cookies.json"


def main():
    print("=" * 50)
    print("  Perplexity Deep Research - Cookie Setup")
    print("=" * 50)
    print()
    print("This sets up your Perplexity session cookie.")
    print()
    print("Steps:")
    print("  1. Open Chrome and go to https://www.perplexity.ai")
    print("  2. Press F12 to open DevTools")
    print("  3. Click 'Application' tab (top bar)")
    print("  4. Expand 'Cookies' in left sidebar")
    print("  5. Click 'https://www.perplexity.ai'")
    print("  6. Find '__Secure-next-auth.session-token'")
    print("  7. Double-click the Value cell and copy it (Ctrl+C)")
    print()

    token = input("Paste the session token value here: ").strip()
    if not token:
        print("No token provided. Aborting.")
        sys.exit(1)

    cookies = {
        "session_token": token,
        "session_token_name": "__Secure-next-auth.session-token",
    }

    # Also ask for CSRF token (optional)
    print()
    print("(Optional) Find '__Secure-next-auth.csrf-token' in the same list.")
    csrf = input("Paste CSRF token value (or press Enter to skip): ").strip()
    if csrf:
        cookies["csrf_token"] = csrf
        cookies["csrf_token_name"] = "__Secure-next-auth.csrf-token"

    from datetime import datetime

    output_path = get_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"cookies": cookies, "extracted_at": datetime.now().isoformat()}
    output_path.write_text(json.dumps(data, indent=2))

    print()
    print(f"Saved to: {output_path}")
    print("The MCP server will use these cookies automatically.")
    print("Re-run this script when your session expires.")


if __name__ == "__main__":
    main()
