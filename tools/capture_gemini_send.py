"""
Wave A4-A5: capture batchexecute traffic when submitting a query on gemini.google.com.

Flow:
  1. Open https://gemini.google.com/u/{authuser}/app with Chrome cookies.
  2. (Optional) Click the Deep Research toggle in the toolbar.
  3. Fill the rich-textarea with --query and submit.
  4. Hook every request/response on .google.com under /_/BardChatUi/data/ .
  5. Save full request/response artifacts to docs/gemini-mcp/.

Usage:
  python tools/capture_gemini_send.py --authuser 6 --query "What is 2+2?"
  python tools/capture_gemini_send.py --authuser 6 --query "Trends in MCP" --deep-research

Outputs:
  send_<mode>_requests.json     Every batchexecute POST captured (method, URL, headers, body)
  send_<mode>_responses.json    Decoded JSON responses (where content-type allowed)
  send_<mode>_stream.txt        Streamed bodies for endpoints returning text/plain or event-stream
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Request, Response, sync_playwright
from playwright_stealth import Stealth

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perplexity_deep_research.cookies import (  # noqa: E402
    _profile_cookie_db,
    list_chrome_profiles_ordered,
)
from pycookiecheat import BrowserType, chrome_cookies  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "gemini-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def fetch_cookies(profile_name: str) -> list[dict]:
    profiles = list_chrome_profiles_ordered()
    target = next((p for p in profiles if p.name == profile_name), None)
    if target is None:
        raise SystemExit(f"Chrome profile {profile_name!r} not found")
    db = _profile_cookie_db(target)
    if db is None:
        raise SystemExit(f"No cookie DB for {profile_name!r}")
    raw = chrome_cookies(
        url="https://gemini.google.com/",
        browser=BrowserType.CHROME,
        cookie_file=str(db.resolve()),
    )
    return [
        {
            "name": n,
            "value": v,
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "None",
        }
        for n, v in raw.items()
    ]


def is_batch_traffic(url: str) -> bool:
    return "/_/BardChatUi/data/" in url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="Default")
    ap.add_argument("--authuser", type=int, default=6)
    ap.add_argument("--query", default="What is 2+2? Answer in 1 word.")
    ap.add_argument(
        "--deep-research",
        action="store_true",
        help="Click the Deep Research toggle before submitting",
    )
    ap.add_argument(
        "--wait-secs", type=int, default=20,
        help="Seconds to wait after submit before closing (default 20)."
    )
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    mode_tag = "dr" if args.deep_research else "chat"
    cookies = fetch_cookies(args.profile)
    print(f"[i] {len(cookies)} cookies loaded from {args.profile!r}", flush=True)

    network_requests: list[dict] = []
    json_responses: list[dict] = []
    stream_bodies: list[dict] = []

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req: Request) -> None:
            if not is_batch_traffic(req.url):
                return
            try:
                network_requests.append({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                })
            except Exception as e:
                network_requests.append({"err": str(e), "url": req.url})

        def on_response(resp: Response) -> None:
            if not is_batch_traffic(resp.url):
                return
            if resp.request.method == "OPTIONS":
                return
            ct = resp.headers.get("content-type", "")
            try:
                body_text = resp.text()
            except Exception as e:
                json_responses.append({"url": resp.url, "err": str(e)})
                return
            # Google batchexecute and StreamGenerate start with `)]}'` XSSI guard
            stream_bodies.append({
                "url": resp.url,
                "status": resp.status,
                "content_type": ct,
                "body": body_text,
            })

        page.on("request", on_request)
        page.on("response", on_response)

        url = f"https://gemini.google.com/u/{args.authuser}/app"
        print(f"[i] Navigating to {url}", flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3000)
        print(f"[i] Final URL: {page.url}", flush=True)

        # Try to enable Deep Research toggle if requested.
        # Flow confirmed via probe_gemini_dr_selector.py:
        #   1. Click "Tools" button to expand the picker menu
        #   2. Click "Deep research" item inside the menu
        if args.deep_research:
            print("[i] Opening Tools menu…", flush=True)
            try:
                tools_btn = page.locator('button:has-text("Tools")').first
                tools_btn.click(timeout=3000)
                page.wait_for_timeout(1500)
                print("[ok] Tools menu opened", flush=True)
            except Exception as e:
                print(f"[err] Couldn't open Tools menu: {e}", flush=True)

            print("[i] Clicking Deep research toggle…", flush=True)
            dr_clicked = False
            for sel in (
                'button:has-text("Deep research")',
                'button:has-text("Deep Research")',
                '[role="menuitem"]:has-text("Deep research")',
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        loc.click(timeout=2000)
                        print(f"[ok] Clicked DR toggle via: {sel}", flush=True)
                        dr_clicked = True
                        break
                except Exception as e:
                    print(f"[skip] {sel}: {e}", flush=True)
            if not dr_clicked:
                print("[warn] No DR toggle found — proceeding without it", flush=True)
            page.wait_for_timeout(800)

        # Fill the rich-textarea
        print(f"[i] Submitting query: {args.query!r}", flush=True)
        textarea_selectors = [
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'textarea',
        ]
        filled = False
        for sel in textarea_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click()
                    loc.fill(args.query)
                    filled = True
                    print(f"[ok] Filled input via: {sel}", flush=True)
                    break
            except Exception as e:
                print(f"[skip] {sel}: {e}", flush=True)
        if not filled:
            print("[err] No input element found — aborting", flush=True)
            ctx.close()
            browser.close()
            return 1

        page.wait_for_timeout(400)
        # Submit: press Enter (works for most chat inputs)
        page.keyboard.press("Enter")
        print(f"[i] Submitted. Waiting {args.wait_secs}s…", flush=True)
        page.wait_for_timeout(args.wait_secs * 1000)

        ctx.close()
        browser.close()

    # Save artifacts
    req_path = DOC_DIR / f"send_{mode_tag}_requests.json"
    resp_path = DOC_DIR / f"send_{mode_tag}_responses.json"
    stream_path = DOC_DIR / f"send_{mode_tag}_stream.txt"

    req_path.write_text(json.dumps(network_requests, indent=2, ensure_ascii=False, default=str))
    resp_path.write_text(json.dumps(json_responses, indent=2, ensure_ascii=False, default=str))
    if stream_bodies:
        stream_path.write_text(
            "\n\n=====\n\n".join(
                f"URL: {s['url']}\nCT: {s['content_type']}\nSTATUS: {s['status']}\n\n{s['body']}"
                for s in stream_bodies
            )
        )

    print()
    print("==== Summary ====")
    print(f"requests captured:  {len(network_requests)}")
    print(f"json responses:     {len(json_responses)}")
    print(f"stream responses:   {len(stream_bodies)}")
    print(f"saved → {req_path.relative_to(REPO_ROOT.parent)}")
    if stream_bodies:
        print(f"saved → {stream_path.relative_to(REPO_ROOT.parent)}")
    if network_requests:
        first = network_requests[0]
        print()
        print(f"First request URL: {first.get('url', '')[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
