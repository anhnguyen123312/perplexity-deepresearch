"""Visit /computer/connectors and dump every API call so we can find
the canonical connector list endpoint + slug schema.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIES_FILE = Path.home() / ".local/share/perplexity-deep-research/cookies.json"
OUT_DIR = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert")


def load_cookies():
    data = json.loads(COOKIES_FILE.read_text())
    cookies = data["cookies"]
    return [
        {
            "name": cookies["session_token_name"],
            "value": cookies["session_token"],
            "domain": ".perplexity.ai",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    requests_log = []
    responses_log = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
        )
        ctx.add_cookies(load_cookies())
        page = ctx.new_page()

        def on_req(r):
            url = r.url
            if "perplexity.ai" not in url:
                return
            if any(x in url for x in (".js", ".css", ".woff", ".png", ".svg", ".jpg", ".webp")):
                return
            requests_log.append({
                "ts": datetime.now().isoformat(),
                "method": r.method,
                "url": url,
                "post_data": r.post_data,
            })

        def on_resp(r):
            url = r.url
            if "perplexity.ai" not in url:
                return
            if any(x in url for x in (".js", ".css", ".woff", ".png", ".svg", ".jpg", ".webp")):
                return
            ct = (r.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            try:
                body = r.text()
            except Exception:
                return
            responses_log.append({
                "ts": datetime.now().isoformat(),
                "url": url,
                "status": r.status,
                "body": body[:50000],
            })
            # save inline
            (OUT_DIR / "connectors_api_responses.json").write_text(
                json.dumps(responses_log, indent=2, default=str)
            )

        page.on("request", on_req)
        page.on("response", on_resp)

        page.goto("https://www.perplexity.ai/computer/connectors",
                  wait_until="domcontentloaded", timeout=20000)
        time.sleep(8)
        # scroll to trigger lazy loads
        page.mouse.wheel(0, 1200)
        time.sleep(2)
        page.mouse.wheel(0, 1200)
        time.sleep(3)

        (OUT_DIR / "connectors_api_requests.json").write_text(
            json.dumps(requests_log, indent=2, default=str)
        )

        # Show top JSON-bearing endpoints
        print(f"[done] requests={len(requests_log)} responses={len(responses_log)}",
              file=sys.stderr)
        for r in responses_log[:30]:
            print(f"  {r['status']} {r['url']}", file=sys.stderr)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
