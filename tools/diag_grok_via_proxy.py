#!/usr/bin/env python3
"""Decisive test: can CloakBrowser clear grok.com CF through a DATACENTER proxy
(simulates running on the datacenter prod IP)? Reports title/cf + statsig capture."""
import os, time, tempfile, json, sys
from cloakbrowser import launch_persistent_context
from deep_research.grok.cookies import get_grok_cookies

PROXY = os.environ.get("GROK_TEST_PROXY")  # http://user:pass@host:port
if not PROXY:
    print(json.dumps({"error": "set GROK_TEST_PROXY"})); sys.exit(1)
# parse
import re
m = re.match(r"https?://(?:([^:@]+):([^@]+)@)?([^:/]+):(\d+)", PROXY)
user, pw, host, port = m.group(1), m.group(2), m.group(3), m.group(4)
proxy_cfg = {"server": f"http://{host}:{port}"}
if user: proxy_cfg["username"] = user; proxy_cfg["password"] = pw

raw = get_grok_cookies()
cookies = [{"name": k, "value": v, "domain": ".grok.com", "path": "/",
            "secure": True, "httpOnly": False, "sameSite": "Lax"} for k, v in raw.items()
           if k in ("sso", "sso-rw", "x-userid")]  # ship only login cookies (cf_clearance is IP-bound)
udd = tempfile.mkdtemp(prefix="grok_proxytest_")
report = {"statsig": None, "proxy": f"{host}:{port}"}
try:
    ctx = launch_persistent_context(udd, headless=True, no_viewport=True,
                                    locale="en-US", humanize=True, proxy=proxy_cfg)
except Exception as e:
    print(json.dumps({"error": f"launch with proxy failed: {e}", "proxy": f"{host}:{port}"})); sys.exit(1)
try:
    ctx.add_cookies(cookies)
    page = ctx.new_page()
    page.on("request", lambda r: report.update(statsig=r.headers.get("x-statsig-id"))
            if r.method == "POST" and r.url.endswith("/conversations/new") and r.headers.get("x-statsig-id") else None)
    page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(8000)
    report["title"] = page.title()
    body = (page.inner_text("body")[:200] if page.locator("body").count() else "")
    report["cf_challenge"] = any(s in body for s in ["Just a moment", "Verifying", "review the security"])
    for _ in range(3):
        page.keyboard.press("Escape"); page.wait_for_timeout(400)
    report["composer"] = page.locator('[contenteditable="true"]').count()
    try:
        box = page.locator('[contenteditable="true"]').first
        box.wait_for(state="visible", timeout=8000); box.click(); box.fill("."); box.press("Enter")
        deadline = time.time() + 30
        while time.time() < deadline and not report["statsig"]:
            page.wait_for_timeout(500)
    except Exception as e:
        report["submit_err"] = str(e)[:100]
    page.screenshot(path="/tmp/grok_proxytest.png")
finally:
    try: ctx.close()
    except Exception: pass
report["statsig_captured"] = bool(report.pop("statsig", None))
print(json.dumps(report, indent=1, default=str))
