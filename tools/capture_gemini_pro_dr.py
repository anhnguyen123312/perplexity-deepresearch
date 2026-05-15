"""Capture StreamGenerate with model=Pro AND Deep Research enabled.

Flow:
  1. Open Gemini in /u/{authuser}/app
  2. Click model picker → select Pro (3.1 Pro)
  3. Open Tools → click Deep research
  4. Fill query, submit
  5. Dump every StreamGenerate request/response
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from playwright.sync_api import Request, Response, sync_playwright
from playwright_stealth import Stealth

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perplexity_deep_research.cookies import _profile_cookie_db, list_chrome_profiles_ordered
from pycookiecheat import BrowserType, chrome_cookies

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "gemini-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def fetch_cookies(profile_name: str) -> list[dict]:
    profiles = list_chrome_profiles_ordered()
    target = next((p for p in profiles if p.name == profile_name), None)
    db = _profile_cookie_db(target)
    raw = chrome_cookies(url="https://gemini.google.com/", browser=BrowserType.CHROME, cookie_file=str(db.resolve()))
    return [{"name": n, "value": v, "domain": ".google.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "None"} for n, v in raw.items()]


def is_target_traffic(url: str) -> bool:
    return "StreamGenerate" in url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="Default")
    ap.add_argument("--authuser", type=int, default=3)
    ap.add_argument("--query", default="Comprehensive XAUUSD trading analysis 2026")
    ap.add_argument("--wait-secs", type=int, default=15)
    args = ap.parse_args()

    cookies = fetch_cookies(args.profile)
    print(f"[i] {len(cookies)} cookies", flush=True)

    requests_log: list[dict] = []

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="en-US")
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req: Request) -> None:
            if not is_target_traffic(req.url):
                return
            requests_log.append({
                "url": req.url,
                "method": req.method,
                "headers": dict(req.headers),
                "post_data": req.post_data,
            })

        page.on("request", on_request)

        page.goto(f"https://gemini.google.com/u/{args.authuser}/app", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(5000)

        # ---- Open model picker ----
        print("[i] Opening model picker…", flush=True)
        picker_selectors = [
            'button[aria-label*="model" i]',
            'button[data-test-id*="bard-mode" i]',
            'bard-mode-switcher button',
            'div[role="button"]:has-text("2.5 Flash")',
            'div[role="button"]:has-text("Flash")',
        ]
        opened = False
        for sel in picker_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    print(f"[ok] opened picker via {sel}", flush=True)
                    opened = True
                    break
            except Exception as e:
                print(f"[skip] {sel}: {e}", flush=True)
        if not opened:
            print("[warn] couldn't open model picker — dumping ALL buttons for inspection", flush=True)
        page.wait_for_timeout(1500)

        # Enumerate visible Pro candidates
        items = page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('button, [role="option"], [role="menuitem"]')) {
                const r = el.getBoundingClientRect();
                if (r.width === 0) continue;
                const text = (el.innerText||'').slice(0, 80).replace(/\\s+/g,' ').trim();
                const aria = el.getAttribute('aria-label') || '';
                if (/pro|3\\.1/i.test(text + ' ' + aria)) out.push({tag: el.tagName.toLowerCase(), aria, text});
            }
            return out;
        }""")
        print("[i] Pro-ish items visible:", flush=True)
        for it in items[:15]:
            print(f"   {it}", flush=True)

        # Try to click a Pro option
        pro_clicked = False
        for sel in [
            'button:has-text("3.1 Pro")',
            '[role="option"]:has-text("3.1 Pro")',
            '[role="menuitemradio"]:has-text("Pro")',
            'button:has-text("Pro")',
            '[role="option"]:has-text("Pro")',
            '[role="menuitem"]:has-text("Pro")',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=2000)
                    print(f"[ok] clicked Pro via {sel}", flush=True)
                    pro_clicked = True
                    break
            except Exception as e:
                print(f"[skip Pro] {sel}: {e}", flush=True)
        if not pro_clicked:
            print("[warn] no Pro option clicked", flush=True)
        page.wait_for_timeout(800)

        # ---- Open Tools (en="Tools", vi="Công cụ") ----
        tools_opened = False
        for sel in (
            'button:has-text("Tools")',
            'button:has-text("Công cụ")',
            'button[aria-label*="tool" i]',
            'button[aria-label*="công cụ" i]',
            'toolbox-drawer-item button',
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=2500)
                    print(f"[ok] Tools opened via {sel}", flush=True)
                    tools_opened = True
                    break
            except Exception as e:
                print(f"[skip tools] {sel}: {e}", flush=True)
        if not tools_opened:
            # Enumerate left-rail buttons to discover the localised label
            labels = page.evaluate("""() => {
                const out = [];
                for (const el of document.querySelectorAll('button')) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0) continue;
                    const text = (el.innerText||'').slice(0, 60).replace(/\\s+/g,' ').trim();
                    const aria = el.getAttribute('aria-label') || '';
                    if (text || aria) out.push({text, aria});
                }
                return out;
            }""")
            print("[dbg] visible buttons (first 25):", flush=True)
            for it in labels[:25]:
                print(f"   {it}", flush=True)
        page.wait_for_timeout(1200)

        # ---- Click Deep research (en/vi) ----
        for sel in (
            'button:has-text("Deep research")',
            'button:has-text("Deep Research")',
            'button:has-text("Nghiên cứu chuyên sâu")',
            'button:has-text("Nghiên cứu sâu")',
            '[role="menuitem"]:has-text("Deep research")',
            '[role="menuitem"]:has-text("Nghiên cứu")',
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=2500)
                    print(f"[ok] DR enabled via {sel}", flush=True)
                    break
            except Exception as e:
                print(f"[skip DR] {sel}: {e}", flush=True)
        page.wait_for_timeout(800)

        # ---- Fill + submit ----
        for sel in ['rich-textarea div[contenteditable="true"]', 'div[contenteditable="true"][role="textbox"]']:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click()
                    loc.fill(args.query)
                    break
            except Exception:
                pass
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
        page.wait_for_timeout(args.wait_secs * 1000)
        ctx.close()
        browser.close()

    out = DOC_DIR / "send_pro_dr_requests.json"
    out.write_text(json.dumps(requests_log, indent=2, ensure_ascii=False, default=str))
    print(f"[i] Captured {len(requests_log)} StreamGenerate requests → {out.relative_to(REPO_ROOT.parent)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
