"""
Wave A1-A2: capture gemini.google.com homepage for a given (Chrome profile, authuser).

Outputs to docs/gemini-mcp/:
    homepage_<profile>_u<N>.html   raw HTML
    cookies_<profile>.json         google.com cookies (shared per profile)
    wiz_<profile>_u<N>.json        extracted: SNlM0e, bl, user.email, user.gaia, has_advanced

Usage:
    python tools/capture_gemini.py --profile Default --authuser 0
    python tools/capture_gemini.py --profile Default --authuser 0 --headless
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Reuse helpers from the perplexity package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deep_research.cookies import (  # noqa: E402
    _profile_cookie_db,
    list_chrome_profiles_ordered,
)
from pycookiecheat import BrowserType, chrome_cookies  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "gemini-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


def fetch_google_cookies(profile_name: str) -> list[dict]:
    """Extract cookies for google.com from the given Chrome profile."""
    profiles = list_chrome_profiles_ordered()
    target = next((p for p in profiles if p.name == profile_name), None)
    if target is None:
        raise SystemExit(
            f"Chrome profile {profile_name!r} not found. "
            f"Available: {[p.name for p in profiles]}"
        )
    db = _profile_cookie_db(target)
    if db is None:
        raise SystemExit(f"No cookie DB for profile {profile_name!r}")

    raw = chrome_cookies(
        url="https://gemini.google.com/",
        browser=BrowserType.CHROME,
        cookie_file=str(db.resolve()),
    )
    cookies = []
    for name, value in raw.items():
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "None",
        })
    return cookies


_WIZ_PATTERNS = {
    "SNlM0e": re.compile(r'"SNlM0e":"([^"]+)"'),
    "cfb2h": re.compile(r'"cfb2h":"([^"]+)"'),
    "bl": re.compile(r'"cfb2h":"([^"]+)"'),  # alias check
    "WIZ_global_data_block": re.compile(
        r"window\.WIZ_global_data\s*=\s*(\{.+?\});",
        re.DOTALL,
    ),
}


def extract_wiz(html: str) -> dict:
    """Pull the interesting bootstrap fields out of the homepage HTML."""
    out: dict[str, object] = {}
    for key, pat in _WIZ_PATTERNS.items():
        m = pat.search(html)
        out[key] = m.group(1) if m else None

    # Try to parse the JSON block (best effort — may need cleanup).
    block = out.get("WIZ_global_data_block")
    if isinstance(block, str):
        try:
            out["WIZ_global_data"] = json.loads(block)
        except json.JSONDecodeError as e:
            out["WIZ_global_data_parse_error"] = str(e)
            out["WIZ_global_data_first_400"] = block[:400]
        out["WIZ_global_data_block"] = f"<{len(block)} chars>"

    # Heuristics for account info
    email_m = re.search(r'"([^"]+@[^"]+\.[a-zA-Z]{2,})"', html)
    out["first_email_in_html"] = email_m.group(1) if email_m else None

    out["has_try_advanced_cta"] = (
        "Try Gemini Advanced" in html or "Get Gemini Advanced" in html
    )
    out["has_deep_research_label"] = "Deep Research" in html
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="Default", help="Chrome profile name")
    ap.add_argument("--authuser", type=int, default=0, help="Google account index in /u/N/")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    print(f"[i] Reading cookies from Chrome profile {args.profile!r}", flush=True)
    cookies = fetch_google_cookies(args.profile)
    print(f"[i] Got {len(cookies)} cookies for .google.com", flush=True)

    cookie_path = DOC_DIR / f"cookies_{args.profile}.json"
    cookie_path.write_text(json.dumps(cookies, indent=2))

    # Sanity print of key cookies
    key_names = ("__Secure-1PSID", "__Secure-1PSIDTS", "SAPISID", "SID", "HSID")
    have = {c["name"] for c in cookies}
    missing = [k for k in key_names if k not in have]
    print(f"[i] Key cookies present: {[k for k in key_names if k in have]}", flush=True)
    if missing:
        print(f"[warn] Missing key cookies: {missing}", flush=True)

    url = f"https://gemini.google.com/u/{args.authuser}/app"
    print(f"[i] Navigating to {url}", flush=True)

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
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3000)
        html = page.content()
        final_url = page.url
        ctx.close()
        browser.close()

    print(f"[i] Final URL: {final_url}", flush=True)
    print(f"[i] HTML size: {len(html):,} chars", flush=True)

    html_path = DOC_DIR / f"homepage_{args.profile}_u{args.authuser}.html"
    html_path.write_text(html)
    print(f"[i] Saved {html_path.relative_to(REPO_ROOT.parent)}", flush=True)

    wiz = extract_wiz(html)
    wiz["final_url"] = final_url
    wiz["html_size"] = len(html)
    wiz["redirected_to_login"] = (
        "ServiceLogin" in final_url or "accounts.google.com" in final_url
    )
    wiz_path = DOC_DIR / f"wiz_{args.profile}_u{args.authuser}.json"
    wiz_path.write_text(json.dumps(wiz, indent=2, ensure_ascii=False, default=str))
    print(f"[i] Saved {wiz_path.relative_to(REPO_ROOT.parent)}", flush=True)

    print()
    print("==== Summary ====")
    print(f"redirected_to_login: {wiz['redirected_to_login']}")
    print(f"SNlM0e present:      {bool(wiz['SNlM0e'])}")
    print(f"bl (cfb2h) present:  {bool(wiz['cfb2h'])}")
    print(f"first email in HTML: {wiz['first_email_in_html']}")
    print(f"has_try_advanced:    {wiz['has_try_advanced_cta']}")
    print(f"has_deep_research:   {wiz['has_deep_research_label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
