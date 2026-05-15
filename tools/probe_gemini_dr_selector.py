"""Probe gemini.google.com/u/{N}/app DOM after JS render to locate the
Deep Research toggle. Outputs every visible interactive element's
aria-label / text so we can pick a stable selector.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perplexity_deep_research.cookies import (
    _profile_cookie_db,
    list_chrome_profiles_ordered,
)
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "gemini-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def fetch_cookies(profile_name: str) -> list[dict]:
    profiles = list_chrome_profiles_ordered()
    target = next((p for p in profiles if p.name == profile_name), None)
    db = _profile_cookie_db(target)
    raw = chrome_cookies(
        url="https://gemini.google.com/",
        browser=BrowserType.CHROME,
        cookie_file=str(db.resolve()),
    )
    return [
        {"name": n, "value": v, "domain": ".google.com", "path": "/",
         "secure": True, "httpOnly": False, "sameSite": "None"}
        for n, v in raw.items()
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="Default")
    ap.add_argument("--authuser", type=int, default=6)
    args = ap.parse_args()

    cookies = fetch_cookies(args.profile)
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="en-US")
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(f"https://gemini.google.com/u/{args.authuser}/app",
                  wait_until="domcontentloaded", timeout=30_000)
        # Wait for Angular hydration
        page.wait_for_timeout(7000)

        # Click the "Tools" button to expand the picker
        try:
            tools_btn = page.locator('button:has-text("Tools")').first
            tools_btn.click(timeout=3000)
            page.wait_for_timeout(1500)
            print("[ok] Clicked Tools button")
        except Exception as e:
            print(f"[warn] Couldn't click Tools: {e}")

        # Collect every button/role-button with aria-label or text
        result = page.evaluate("""() => {
            const out = [];
            const sels = ['button', '[role="button"]', 'mat-chip', '[role="menuitem"]'];
            const seen = new Set();
            for (const sel of sels) {
                for (const el of document.querySelectorAll(sel)) {
                    const r = el.getBoundingClientRect();
                    const visible = r.width > 0 && r.height > 0;
                    const aria = el.getAttribute('aria-label') || '';
                    const text = (el.innerText || '').slice(0, 80).replace(/\\s+/g,' ').trim();
                    const dti = el.getAttribute('data-test-id') || '';
                    const key = `${aria}::${text}::${dti}`;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({tag: el.tagName.toLowerCase(), aria, text, dti, visible});
                }
            }
            return out;
        }""")

        # Filter to ones plausibly DR-related
        candidates = [
            r for r in result
            if any(kw in (r["aria"] + r["text"] + r["dti"]).lower()
                   for kw in ("deep", "research", "tool", "canvas", "sâu", "nghiên"))
        ]

        out_path = DOC_DIR / f"dr_selectors_u{args.authuser}.json"
        out_path.write_text(json.dumps({
            "total_elements": len(result),
            "dr_candidates": candidates,
            "all": result,
        }, indent=2, ensure_ascii=False))

        print(f"Total interactive elements: {len(result)}")
        print(f"DR/research candidates: {len(candidates)}")
        for c in candidates:
            print(f"  tag={c['tag']} aria={c['aria']!r} text={c['text']!r} dti={c['dti']!r}")
        print(f"\nSaved → {out_path.relative_to(REPO_ROOT.parent)}")

        ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
