# ref.md — Code anchors (cloak / CF / self-heal)

## Hot path — Perplexity
- `deep_research/perplexity/client.py`
  - `PerplexityClient.__init__` (101) → `_create_session` (108): `impersonate="chrome"` (122) — TLS=chrome146.
  - `_refresh_cookies` (130): chỉ `extract_cookies_with_relaunch()` + re-bootstrap. **Không** giải CF.
  - `_request_with_retry` (138): rẽ nhánh `status in (401,403)` → refresh once; `429`→RateLimit; `>=400`→error.
    **Đây là nơi chèn CF-detector + routing.**
  - `_collect_events` (250): parser SSE; CF HTML 200 lọt vào đây → rỗng.
  - `search` (455): retry loop MAX_RETRIES (backoff 2s/4s) quanh PerplexityError/RateLimitError.
- `deep_research/config.py`
  - `DEFAULT_HEADERS` (30): UA `Chrome/130` + `sec-ch-ua v=130` (36,44) 🔴.
  - `SSE_REQUEST_HEADERS` (48).
- `deep_research/cookies.py`
  - `extract_cookies_with_relaunch` (527), `extract_cookies_all_profiles` (478), `get_cookies` (652),
    `list_chrome_profiles_ordered` (102), `_extract_cookies_windows_rookiepy` (335),
    `normalize_cookies` (165), `to_http_cookies` (207).

## Hot path — Grok
- `deep_research/grok/client.py`
  - `_ensure_client` (53): `Emulation.Chrome145` + `CHROME_UA` (56-59).
  - `_build_headers` (72): `SEC_CH_UA`, `x-statsig-id`, cookie header.
  - `_post_chat` (160): rnet POST, parse `int(str(resp.status).split()[0])`.
  - `search` (180): loop attempt (0,1); `status in (401,403)` → `_drop_client_and_invalidate_cache` +
    `get_statsig_id(refresh=True)` → retry. **Nơi chèn CF-detector + headful.**
- `deep_research/grok/config.py`
  - `IMPERSONATE_TARGET="Chrome145"` (30), `CHROME_UA` 145 (35), `SEC_CH_UA` 145 (41), `DEFAULT_DEVICE_ENV` (58).
- `deep_research/grok/statsig.py`
  - `capture_statsig_id_via_chrome(headless=True)` (59) 🔴 default → `_do_capture...` (89):
    `from cloakbrowser import launch_persistent_context` (98), `humanize=True` (122),
    harvest cf_clearance/__cf_bm (159-166), merge `save_profile_entry` (182).
  - `get_statsig_id(refresh)` (192).
- `deep_research/grok/cookies.py`
  - `get_grok_cookies_cached` (118), `invalidate_grok_cache` (153), `extract_grok_cookies_all_profiles` (90),
    auth signal cookie = `sso` (28).

## Store / state
- `deep_research/profile_config.py`
  - `save_profile_entry` (208), `get_first_valid` (336), `is_expired` (240), `invalidate_profile` (250),
    `get_provider_statsig`/`set_provider_statsig` (266/274), `get_provider_settings`/`set` (290/301).
  - `DEFAULT_EXPIRE_SECONDS` (49): perplexity 86400, grok 43200, gemini 1200.
  - Có sẵn slot `statsig` + `settings` per provider → **nhét được cloak-version cache + breaker state**.

## Browser control
- `deep_research/browser_control.py`: `is_chrome_running` (104), `quit_chrome` (177), `relaunch_chrome` (236),
  `ensure_chrome_accessible` (288), `_find_chrome_exe_windows` (87). Cross-platform process control.

## MCP surface
- `deep_research/server.py`: tools `perplexity_*` (51-210), `grok_*` (213-303), `grok_refresh_statsig` (277),
  `gemini_*` (322-388). Lazy singletons `_client/_grok/_gemini` (22-24).

## Prototypes (tools/)
- `tools/test_chrome_copy_cdp.py` — CDP attach to real chrome.exe, `Network.getAllCookies` (Windows POC).
- `tools/replay_capture.py`, `tools/statsig_bridge.js`, `tools/capture_statsig_via_chrome.py`,
  `tools/grok_smoke_test.py`, `tools/scan_profiles.py`.

## Tests liên quan
- `tests/test_client.py`: `TestClientUsesChromImpersonation` (94), `TestClientUsesDefaultHeaders` (118).
- `tests/test_grok_no_chrome_when_cached.py`: đảm bảo cached path KHÔNG mở Chrome.
- `tests/test_browser_control.py`.
