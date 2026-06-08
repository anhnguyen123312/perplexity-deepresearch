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

## Next
- Confirm headless capture works (fix) → prod path.
- Full GrokClient.search end-to-end (answer).
- Portable sso/cookie export → prod import (sso portable, cf_clearance earned on prod).
- Deploy + prod smoke.
