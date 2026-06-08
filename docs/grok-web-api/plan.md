# Grok Web → Durable API (login once + refresh + deploy prod)

Goal: dùng grok.com WEB như API/CLI, login 1 lần → tự refresh → deploy prod (headless server) chạy bền.

## Findings (evidence, máy thật 2026-06-09)
- Auth web = cookies từ Chrome local: `sso`/`sso-rw` (X SSO login) + `cf_clearance` (Cloudflare) + `x-statsig-id` (anti-bot fingerprint, capture qua CloakBrowser).
- **Longevity: sso/sso-rw = 116–150 NGÀY; cf_clearance ≈ 300–365 ngày; statsig reusable hours/days.** → "login once" = vài tháng. Refresh problem chủ yếu là cf_clearance+statsig (CF layer), KHÔNG phải login.
- Hot path: rnet (BoringSSL Chrome145) replay cf_clearance — **không cần Chrome ở mỗi call**. Browser chỉ chạy khi 401/403 (refresh).
- Endpoint: `POST https://grok.com/rest/app-chat/conversations/new` (ndjson stream). Modes: grok_4_3/expert/heavy/search.
- Multi-account: 5 Chrome profiles signed-in (Default, Profile 6/7/16/22) → có thể rotate.
- Repo portable knobs: `PERPLEXITY_CONFIG_FILE` (store cookies+statsig), `CHROME_PROFILE`, `GROK_STATSIG_HEADLESS`.

## ROOT CAUSE (local refresh broken — what user feels)
Cached cf_clearance/statsig stale → 401/403 → CloakBrowser **HEADLESS fails to clear CF** ("Failed to capture x-statsig-id"). brain cloak-refresh-2026 E4: headless CF clear ~50% vs headful ~83%. v0.8.3 defaulted headless.

## Plan
### P1 — Fix refresh reliability (local) [BLOCKER]
- statsig.py: on headless capture FAIL, auto-retry HEADFUL once (fallback), not just env. Keep GROK_STATSIG_HEADLESS override.
- Upgrade cloakbrowser 0.3.28→0.3.31 (better fingerprint patches → higher CF clear).
- Verify: grok search succeeds locally after stale-cache (cold capture).

### P2 — Login-once durability
- sso 150d → fine. Add a `grok` session export/import: dump chosen profile's cookies(sso/sso-rw/cf_clearance)+statsig → portable JSON (PERPLEXITY_CONFIG_FILE format). CLI: `deep-research-config export-grok <file>`.
- On responses, capture Set-Cookie rolling sso/cf_clearance → persist (auto-extend). [verify grok sets-cookie on 200]

### P3 — Prod deploy (headless server 187.77.146.166)
- Install: uv tool install package on prod. Ship portable config → set PERPLEXITY_CONFIG_FILE.
- Hot path rnet works headless w/ shipped cf_clearance (no Chrome).
- Prod refresh: CloakBrowser under **xvfb-run** (virtual display → headful on headless server). RISK: datacenter IP may get harder CF challenge + cf_clearance is IP-bound → may need residential proxy on prod OR periodic re-export from local.
- Run as service (systemd) — MCP stdio or HTTP transport (FastMCP) for API access.

### P4 — Test
- Local: grok_search returns answer (cold + warm). 
- Prod: call deployed grok → real answer. Confirm refresh works on prod (force stale → re-capture).

## Sequencing
P1 (fix+verify local) → P2 (portability) → P3 (deploy) → P4 (prod test). Don't ask, self-test each.

## Open risks
- cf_clearance IP-binding: solved-on-local may not work from prod IP → prod must self-capture (xvfb) or use residential proxy.
- Headless CF ~50%: mitigate via cloakbrowser upgrade + xvfb-headful + retry.
