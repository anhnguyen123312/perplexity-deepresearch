# plan.md — Onboard profile per-provider + bỏ scan-all

## Mục tiêu
Lấy cookie từ **1 profile user đã onboard** (không scan hết). Chưa onboard → tự chọn+nhớ+báo.

## Các phần (đã làm)
- [x] **P1** `profile_config`: `get_chosen_profile` / `set_chosen_profile`. → verify: smoke set/get.
- [x] **P2** `cookies.py` (pplx): `_harvest_perplexity_profile` + `_resolve_perplexity_profile` + rewrite
  `get_cookies` (single-profile, auto-pick+remember/warn, DB-lock→relaunch). → verify: TestResolvePerplexityProfile + TestGetCookies.
- [x] **P3** `grok/cookies.py`: `_harvest_grok_profile` + `_resolve_grok_profile` + rewrite
  `get_grok_cookies_cached`. → verify: TestResolveGrokProfile + TestGrokCookiesCacheMiss.
- [x] **P4** `onboard.py`: pin chosen profile per provider (`_save_cookies`) + summary line. → verify: 263 pass.
- [x] **P5** Show profile (tối giản theo "bỏ qua"): `_note_active_profile` stderr ở selection moments.

## Tuỳ chọn (chưa làm — không bắt buộc)
- [ ] `deep-research-config use-profile <provider> <name>` để set chosen profile qua CLI (hiện set qua onboard/env).
- [ ] `cli rescan` cân nhắc theo chosen profile thay vì scan-all (đang giữ scan-all vì là lệnh explicit).
- [ ] (Nếu user muốn) show profile trong payload MCP response — hiện bỏ qua theo yêu cầu.

## STATUS: P1–P5 done. 263 tests pass, ruff clean, smoke OK.
