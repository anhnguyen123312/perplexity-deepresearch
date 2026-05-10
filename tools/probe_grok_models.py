"""Fetch /rest/models, /rest/modes, /rest/skills, /rest/auth/get-user from grok.com."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from curl_cffi import requests
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def make_session():
    raw = chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
    sess = requests.Session(impersonate="chrome142")
    for k, v in raw.items():
        sess.cookies.set(k, v, domain=".grok.com")
    sess.headers.update({
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/147.0.0.0 Safari/537.36",
    })
    return sess


def main() -> int:
    sess = make_session()

    targets = [
        ("models", "POST", "/rest/models", {"locale": "en-US"}),
        ("modes", "POST", "/rest/modes", {"locale": "en-US"}),
        ("skills", "POST", "/rest/skills", {"locale": "en-US"}),
        ("rate_limits", "POST", "/rest/rate-limits",
         {"requestKind": "DEFAULT", "modelName": "grok-3"}),
        ("get_user", "GET", "/rest/auth/get-user", None),
        ("get_auth_status", "GET", "/rest/auth/get-auth-status", None),
        ("feature_controls", "GET", "/rest/auth/get-user-feature-controls",
         None),
    ]

    for name, method, path, body in targets:
        url = f"https://grok.com{path}"
        try:
            if method == "POST":
                r = sess.post(url, json=body or {}, timeout=20)
            else:
                r = sess.get(url, timeout=20)
            ct = r.headers.get("content-type", "")
            print(f"  {method} {path:60s} → {r.status_code} | {ct}",
                  flush=True)
            out = DOC_DIR / f"{name}.json"
            if "json" in ct:
                try:
                    data = r.json()
                    out.write_text(json.dumps(data, indent=2, default=str))
                except Exception:
                    out.write_text(r.text)
            else:
                out.write_text(r.text[:5000])
        except Exception as e:
            print(f"  {method} {path:60s} → ERR {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
