"""
Capture grok.com network traffic for a query with model=Grok 4.3 (beta).

Reuses the user's existing Chrome cookies (via pycookiecheat) so no manual
login is needed.

Usage:
    python tools/capture_grok.py [--query TEXT] [--wait-secs N]

Outputs to ``docs/grok-mcp/``:
    - grok43_query.json    (most recent POST that looks like a chat send)
    - all_network.json     (every grok.com / x.ai non-asset request)
    - model_options.json   (each JSON response we observed)
    - grok43_stream.txt    (raw streaming body if we caught one)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Request, Response, sync_playwright
from playwright_stealth import Stealth
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def is_grok_traffic(url: str) -> bool:
    if not ("grok.com" in url or "x.ai" in url):
        return False
    return not any(url.endswith(ext) for ext in (
        ".png", ".jpg", ".jpeg", ".webp", ".svg",
        ".woff", ".woff2", ".ttf", ".css", ".ico"
    ))


def fetch_chrome_cookies(url: str) -> list[dict]:
    """Extract Chrome cookies for *url* via pycookiecheat → Playwright shape."""
    raw = chrome_cookies(url, browser=BrowserType.CHROME)
    cookies = []
    for name, value in raw.items():
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".grok.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        })
    return cookies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="What is 2+2? Answer briefly.")
    parser.add_argument("--wait-secs", type=int, default=60)
    parser.add_argument("--headless", action="store_true",
                        help="Run headless (default: headful so you can see what happens)")
    args = parser.parse_args()

    print("[i] Extracting grok.com cookies from Chrome…", flush=True)
    cookies = fetch_chrome_cookies("https://grok.com/")
    print(f"[i] Got {len(cookies)} cookies for grok.com", flush=True)
    if not cookies:
        print("[err] No cookies — log in to grok.com in Chrome first.", flush=True)
        return 1
    (DOC_DIR / "cookies.json").write_text(json.dumps(cookies, indent=2))

    network: list[dict] = []
    json_responses: list[dict] = []
    stream_bodies: list[dict] = []

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/130.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Saigon",
        )
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req: Request):
            if not is_grok_traffic(req.url):
                return
            try:
                pd = req.post_data
                pd_parsed: object | None = None
                if pd:
                    try:
                        pd_parsed = json.loads(pd)
                    except json.JSONDecodeError:
                        pd_parsed = pd
                network.append({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": pd_parsed,
                })
            except Exception as e:
                network.append({"err": str(e), "url": req.url})

        def on_response(resp: Response):
            if not is_grok_traffic(resp.url):
                return
            ct = resp.headers.get("content-type", "")
            try:
                if "json" in ct and resp.request.method != "OPTIONS":
                    body = resp.json()
                    json_responses.append({
                        "url": resp.url,
                        "status": resp.status,
                        "body": body,
                    })
                elif "event-stream" in ct or "text/plain" in ct or "ndjson" in ct:
                    body_text = resp.text()
                    stream_bodies.append({
                        "url": resp.url,
                        "status": resp.status,
                        "content_type": ct,
                        "body": body_text,
                    })
            except Exception as e:
                json_responses.append({"url": resp.url, "err": str(e)})

        page.on("request", on_request)
        page.on("response", on_response)

        print("[i] Navigating to https://grok.com/ …", flush=True)
        page.goto("https://grok.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # Verify login
        try:
            page_text = page.locator("body").inner_text()[:300]
            print(f"[i] Page snippet: {page_text!r}", flush=True)
        except Exception:
            pass

        # Submit query
        try:
            box = page.locator("textarea").first
            box.click()
            box.fill(args.query)
            page.wait_for_timeout(400)
            box.press("Enter")
            print(f"[i] Submitted query: {args.query!r}", flush=True)
        except Exception as e:
            print(f"[warn] Couldn't auto-submit: {e}", flush=True)

        # Let the stream finish
        page.wait_for_timeout(args.wait_secs * 1000)

        ctx.close()
        browser.close()

    # Save artifacts
    (DOC_DIR / "all_network.json").write_text(
        json.dumps(network, indent=2, default=str)
    )
    (DOC_DIR / "model_options.json").write_text(
        json.dumps(json_responses, indent=2, default=str)
    )
    if stream_bodies:
        (DOC_DIR / "grok43_stream.txt").write_text(
            "\n\n=====\n\n".join(
                f"URL: {s['url']}\nCT: {s['content_type']}\nSTATUS: {s['status']}\n\n{s['body']}"
                for s in stream_bodies
            )
        )

    grok43_query = None
    for entry in reversed(network):
        if entry.get("method") == "POST" and entry.get("post_data"):
            pd = entry["post_data"]
            pd_str = json.dumps(pd) if isinstance(pd, (dict, list)) else str(pd)
            if any(k in pd_str.lower() for k in ("query", "message", "prompt", "model")):
                grok43_query = entry
                break
    if grok43_query is not None:
        (DOC_DIR / "grok43_query.json").write_text(
            json.dumps(grok43_query, indent=2, default=str)
        )
        print(f"[ok] Saved grok43_query.json: {grok43_query['url']}", flush=True)
    else:
        print("[warn] No query POST detected — see all_network.json", flush=True)

    print(f"[done] {len(network)} requests, {len(json_responses)} json, "
          f"{len(stream_bodies)} streams", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
