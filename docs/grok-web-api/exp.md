# Grok Web API — Experiments / Evidence (2026-06-09)

## ★ BREAKTHROUGH: statsig capture failure was a PROMO MODAL, not Cloudflare

Symptom: `GrokClient.search()` → "Failed to capture x-statsig-id from grok.com" (both
headless AND headful). brain `cloak-refresh-2026` blamed headless CF clear (~50%). WRONG.

Diagnostic (tools/diag_grok_capture.py, screenshot /tmp/grok_diag.png):
- `cf_challenge: false`, page title "Grok", user clearly logged in (sidebar + vho687133@gmail.com).
- `[contenteditable]=0, textarea=0` — composer ABSENT.
- Only GET `/conversations?pageSize=...` fired; NO POST `/conversations/new` → statsig never sent.
- Screenshot showed a **"Grok Build [Bản beta]" promo modal** overlaying the composer.

Fix: press **Escape** before locating the input. Verified:
- headful: `contenteditable 0 -> 1` after Esc, `statsig_len 94` CAPTURED.
- Applied to `deep_research/grok/statsig.py` `_do_capture_statsig_id_via_chrome` (Esc×3 after page load, before the input loop).
- Esc is a keypress → works headless too → **prod (headless server) viable WITHOUT xvfb/residential-proxy** for the capture step (pending headless confirmation test).

## Auth longevity (login once is real)
- sso/sso-rw expiry 116–150 days; cf_clearance ~300–365 days; statsig cache 1y / reuse hours-days.
- 5 Chrome profiles signed into grok.com (Default, Profile 6/7/16/22) → multi-account capable.

## cli-chat-proxy (OIDC) is NOT a web substitute
- /v1/models on cli-chat-proxy = only `grok-composer-2.5-fast`, `grok-build` (coding). No grok-4/web-search/research modes. → must use grok.com WEB for research tools.

## Prod facts (187.77.146.166)
- Ubuntu 24.04 x86_64, py3.12, NO uv/chromium/xvfb, datacenter IPv6, `1tokenai.service` running.
- cf_clearance is IP-bound → prod must self-capture (cloakbrowser bundles Chromium). cf_challenge was false locally (valid cookies) → test whether prod datacenter IP triggers CF.

## DONE (local, committed v0.8.4–0.8.7)
- modal-dismiss (Escape) + modeId auto + linkQuery → local grok web works (auto/expert/fast).
- GROK_PROXY support (rnet + cloakbrowser), login-only capture cookies, get_grok_cookies_cached in capture, reuse-stored-when-proxied. All verified locally + sim-prod (config+proxy, no Chrome): search→'4'.

## ★★ PROD SOLVED (datacenter 187.77.146.166) — grok-web answers via sticky proxy + UA pinning
Working architecture (verified: prod `GrokClient.search` → '4'):
1. A CF-CLEARABLE host (local macOS) captures cf_clearance+statsig through a STICKY proxy
   session (Oxylabs `customer-<user>-sessid-grok1` → pins ONE exit IP, e.g. 82.23.41.51 — shared
   by local AND prod, verified identical). CloakBrowser solves CF there (it CAN'T on prod Linux).
2. Ship the session json (cf_clearance + statsig + sso login) to prod (scp).
3. PROD runs **rnet-only** (NO browser) through the SAME sticky session, with the UA PINNED to the
   issuing browser: `GROK_MAJOR=145`, `GROK_UA="Mozilla/5.0 (Macintosh...Chrome/145.0.0.0...)"`,
   `GROK_SEC_CH_UA_PLATFORM='"macOS"'`. Same IP (sticky) + same UA (pinned) → cf_clearance valid → 200.
4. Refresh: cf_clearance/__cf_bm are short-lived → `tools/grok-refresh-ship.sh` on the CF-clearable
   host re-captures + ships every ~5 min (cron). statsig reuses for hours.
Prod env file: /root/grok.env (GROK_PROXY sticky, GROK_MAJOR/GROK_UA/GROK_SEC_CH_UA_PLATFORM,
PERPLEXITY_CONFIG_FILE=/root/grok_session.json, CHROME_PROFILE=grok-prod).

### Root-cause chain solved (each a separate bug, all fixed)
1. "Failed to capture statsig" = "Grok Build" promo modal hid the composer (NOT Cloudflare) → Esc dismiss.
2. modeId "grok-420-computer-use-sa"/"heavy" retired (403 Model not found) → "auto"/fast/expert; +linkQuery.
3. Datacenter IP CF-blocked → route via proxy (GROK_PROXY → rnet + cloakbrowser).
4. dc.oxylabs rotates IP → Oxylabs STICKY session (`customer-<user>-sessid-X`) pins one IP cross-machine.
5. Capture read live Chrome cookies → get_grok_cookies_cached (config store) on headless host.
6. Cache entry expires (__cf_bm ~30min) → reuse stored login when GROK_PROXY set (no Chrome fallback).
7. Capture cookies: inject login-only + unconditional-Esc (count() broke early behind modal).
8. cf_clearance bound to issuing browser UA → cross-machine UA mismatch (local mac/145 vs prod linux/146)
   → GROK_MAJOR/GROK_UA/GROK_SEC_CH_UA_PLATFORM env pin UA identical on capture + serve.

## (historical) PROD WALL notes — superseded by SOLVED above
Verified exhaustively:
1. Datacenter IP: grok.com curl → 403 `cf-mitigated: challenge`.
2. CloakBrowser on prod Linux CANNOT clear CF: headless AND headful-via-xvfb, cloakbrowser 146,
   5 reload retries — ALL stay `title:"Just a moment..."` cf=true. (On local macOS it clears.)
3. dc.oxylabs.io ROTATES exit IP per connection → cf_clearance earned on local-via-proxy is
   bound to a different IP than prod-rnet-via-proxy gets → 403. (Local works b/c capture+hotpath
   share a short proxy window.) No sticky session on this dc plan (user `techopenclaw_oKzhz`).
→ Two independent blockers. grok-web CANNOT self-run on the datacenter prod.

## PATHS TO PROD (need a user infra decision — all need a NON-datacenter exit IP)
A. Residential STICKY proxy (e.g. Oxylabs residential pr.oxylabs.io with `-sessid-`): local (or prod)
   captures + prod rnet share ONE residential IP → cf_clearance valid. Code ready (GROK_PROXY).
   Needs residential proxy creds (current plan is datacenter-only; pr.oxylabs.io test → 000).
B. Run grok-web on a RESIDENTIAL host (e.g. the local mac, or a residential VPS) — where CloakBrowser
   clears CF today. Expose as MCP (stdio) / HTTP (FastMCP). No code change; just run there.
C. Capture-and-ship cron from a residential host through a STICKY proxy + prod rnet-only through the
   same sticky session (combines A+B; only viable with sticky residential).

Recommendation: B (run where it works) for immediate use, or A (buy residential sticky) for true
datacenter-prod deploy. deploy_grok_prod.sh handles install+xvfb but the CF clear needs A/B/C.
