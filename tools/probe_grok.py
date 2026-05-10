"""
Probe grok.com via curl_cffi (Chrome JA3 impersonation) + Chrome cookies.

Goal: bypass Cloudflare without a browser, fetch homepage, extract any API
endpoint hints (build manifest / __NEXT_DATA__ / inline script tags) so we
can target the actual chat-send endpoint without needing Playwright.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from curl_cffi import requests
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    raw = chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
    print(f"[i] cookies: {list(raw.keys())}", flush=True)

    # Match real Chrome 147 fingerprint as closely as possible.
    # curl_cffi only ships up to chrome142 — use that for JA3/HTTP2 frames.
    # Override UA to match user's actual Chrome (cf_clearance is UA-bound).
    sess = requests.Session(impersonate="chrome142")
    for k, v in raw.items():
        sess.cookies.set(k, v, domain=".grok.com")

    # Pass NO headers dict so curl_cffi keeps its default Chrome header
    # ordering. Override only the UA via default_headers if needed.
    real_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    )
    sess.headers.update({"user-agent": real_ua})

    r = sess.get("https://grok.com/", timeout=30)
    print(f"[i] GET / status={r.status_code} len={len(r.text)}", flush=True)

    if r.status_code != 200:
        print(f"[err] body[:400]={r.text[:400]!r}", flush=True)
        return 1

    html_path = DOC_DIR / "homepage.html"
    html_path.write_text(r.text)
    print(f"[i] saved homepage → {html_path}", flush=True)

    # Hunt for API hints
    api_hits = sorted(set(re.findall(r"/api/[A-Za-z0-9_/\-\.]+", r.text)))
    rest_hits = sorted(set(re.findall(r"/rest/[A-Za-z0-9_/\-\.]+", r.text)))
    fetch_hits = sorted(set(re.findall(r'fetch\("([^"]+)"', r.text)))
    next_data = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S
    )
    print(f"[i] /api/ paths ({len(api_hits)}): {api_hits[:20]}", flush=True)
    print(f"[i] /rest/ paths ({len(rest_hits)}): {rest_hits[:20]}", flush=True)
    print(f"[i] fetch() ({len(fetch_hits)}): {fetch_hits[:10]}", flush=True)
    if next_data:
        try:
            nd = json.loads(next_data.group(1))
            (DOC_DIR / "next_data.json").write_text(
                json.dumps(nd, indent=2, default=str)
            )
            print("[i] saved __NEXT_DATA__", flush=True)
        except Exception as e:
            print(f"[warn] __NEXT_DATA__ parse: {e}", flush=True)

    # Try known endpoints
    for path in [
        "/api/auth/session",
        "/api/user/me",
        "/rest/app-chat/conversations",
        "/api/conversations",
    ]:
        try:
            rr = sess.get(f"https://grok.com{path}", timeout=15)
            preview = rr.text[:200] if rr.text else ""
            print(f"  probe {path:50s} → {rr.status_code} | {preview!r}",
                  flush=True)
        except Exception as e:
            print(f"  probe {path:50s} → ERR {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
