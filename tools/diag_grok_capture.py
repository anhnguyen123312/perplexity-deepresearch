#!/usr/bin/env python3
"""Verify fix: dismiss the 'Grok Build' promo modal, then capture statsig."""
import os, time, tempfile, json
from cloakbrowser import launch_persistent_context
from deep_research.grok.cookies import get_grok_cookies

raw = get_grok_cookies()
cookies = [{"name": k, "value": v, "domain": ".grok.com", "path": "/",
            "secure": True, "httpOnly": False, "sameSite": "Lax"} for k, v in raw.items()]
udd = tempfile.mkdtemp(prefix="grok_diag2_")
headless = os.environ.get("GROK_STATSIG_HEADLESS", "0") == "1"
ctx = launch_persistent_context(udd, headless=headless, no_viewport=True, locale="en-US", humanize=True)
report = {"captured_statsig": None}
try:
    ctx.add_cookies(cookies)
    page = ctx.new_page()
    def on_request(req):
        if req.method == "POST" and req.url.endswith("/rest/app-chat/conversations/new"):
            sid = req.headers.get("x-statsig-id")
            if sid:
                report["captured_statsig"] = sid
            try:
                body = req.post_data
                if body:
                    import json as _j
                    b = _j.loads(body)
                    report["real_modeId"] = b.get("modeId")
                    report["real_model"] = b.get("modelName") or b.get("model")
                    report["real_body_keys"] = sorted(b.keys())
                    with open("/tmp/grok_real_body.json", "w") as _f:
                        _f.write(_j.dumps(b, indent=1))
            except Exception as _e:
                report["body_err"] = str(_e)[:100]
    page.on("request", on_request)
    page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)

    # --- DISMISS the 'Grok Build' promo modal blocking the composer ---
    dismissed = []
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    for sel in ['[aria-label="Close"]', '[aria-label="Dismiss"]',
                'button:has-text("×")', 'button:has-text("✕")',
                'dialog button[aria-label]', '[role="dialog"] button']:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=2000); dismissed.append(sel); page.wait_for_timeout(500)
                break
        except Exception:
            continue
    report["dismissed_via"] = dismissed
    page.wait_for_timeout(1000)
    report["contenteditable_after"] = page.locator('[contenteditable="true"]').count()

    # --- submit a tiny chat ---
    for sel in ['[contenteditable="true"]', "textarea"]:
        try:
            box = page.locator(sel).first
            box.wait_for(state="visible", timeout=8000)
            box.click(); box.fill("."); page.wait_for_timeout(300); box.press("Enter")
            report["submit_sel"] = sel
            break
        except Exception as e:
            report[f"submit_err::{sel}"] = str(e)[:80]
    deadline = time.time() + 30
    while time.time() < deadline and report["captured_statsig"] is None:
        page.wait_for_timeout(500)
    report["statsig_len"] = len(report["captured_statsig"]) if report["captured_statsig"] else 0
    page.screenshot(path="/tmp/grok_diag2.png")
finally:
    try: ctx.close()
    except Exception: pass
report.pop("captured_statsig", None)  # don't print the secret id
print(json.dumps(report, indent=1, default=str))
