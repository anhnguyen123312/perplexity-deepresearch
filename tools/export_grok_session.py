#!/usr/bin/env python3
"""Export the local grok LOGIN session to a portable config for a headless host.

A datacenter/server host has no Chrome to read cookies from. Ship the grok
`sso`/`sso-rw`/`x-userid` login cookies (valid ~months) in a PERPLEXITY_CONFIG_FILE.
The server earns its OWN cf_clearance/statsig via CloakBrowser through GROK_PROXY,
so we deliberately DROP the IP-bound cf_clearance/__cf_bm here.

Usage:
  python3 tools/export_grok_session.py [--out /tmp/grok_session.json] [--profile NAME]
"""
import argparse, json, sys
from deep_research import profile_config as pc
from deep_research.grok.cookies import get_grok_cookies_cached

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="/tmp/grok_session.json")
ap.add_argument("--profile", default="grok-prod")
a = ap.parse_args()

LOGIN = ("sso", "sso-rw", "x-userid", "grok_device_id")
CF_BOUND = {"cf_clearance", "__cf_bm"}

cookies = get_grok_cookies_cached()
login = {k: v for k, v in cookies.items() if k in LOGIN}
if "sso" not in login:
    sys.exit("ERROR: no `sso` cookie found — sign in to grok.com in Chrome first.")

# Minimal valid config: grok provider, one profile holding the login cookies.
# `expires_at` is required by profile_config.is_expired(); the sso login lasts
# ~150 days, so 120 days is a safe re-export reminder window.
import time
from datetime import datetime, timezone, timedelta
expires_at = (datetime.now(timezone.utc) + timedelta(days=120)).isoformat()
cfg = {
    "providers": {
        pc.PROVIDER_GROK: {
            "chosen": a.profile,
            "profiles": {
                a.profile: {
                    "cookies": login,
                    "ts": int(time.time()),
                    "expires_at": expires_at,
                },
            },
            "statsig": {},
        }
    }
}
with open(a.out, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"WROTE {a.out}  profile={a.profile!r}  login_cookies={sorted(login)}")
print(f"  ship to host, then: export PERPLEXITY_CONFIG_FILE=<path> GROK_PROXY=<proxy> CHROME_PROFILE={a.profile}")
print(f"  (dropped IP-bound: {sorted(CF_BOUND & set(cookies))} — server re-earns via CloakBrowser)")
