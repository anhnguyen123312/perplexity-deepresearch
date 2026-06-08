# plan.md — Cloak self-heal (phased, ngắn gọn)

Mục tiêu: cloak tự bám Chrome + tự phát hiện & phục hồi Cloudflare → "dùng mượt mà".
Nguyên tắc: surgical, mỗi dòng truy về root-cause; chạy `gitnexus_impact` trước khi sửa symbol; test sau mỗi phase.

## P0 — Module `cloak.py` (xoá drift tận gốc) ⏳ CORE
File mới `deep_research/cloak.py` — thuần, không network, không side-effect ở import:
- `detect_chrome_major() -> int|None` (macOS/Linux/Win, cache 24h trong config.json `settings`).
- `cloakbrowser_binary_major() -> int|None` (đọc `cloakbrowser.binary_info()['version']`, defensive).
- `pick_curl_cffi_target(major) -> str` (nearest-lower trong tập curl_cffi **thực có**, introspect).
- `pick_rnet_emulation(major) -> Emulation` (nearest-lower trong `rnet.Emulation` **thực có**).
- `build_ua(major)`, `build_sec_ch_ua(major)` (khớp target — INVARIANT §2 research.md).
- `is_cloudflare_challenge(status, headers, text) -> bool` (predicate §4, dùng chung).
→ verify: `tests/test_cloak.py` (detect parse, nearest-lower edge, predicate cho mọi tier CF). Pure → mock hết.

## P1 — Wire vào client (diệt bug version + detect CF) ⏳
- **Perplexity** (`config.py` + `perplexity/client.py`): UA/sec-ch-ua/impersonate **động** từ cloak
  (148→chrome146, UA=146). Bỏ hằng `Chrome/130`. `_request_with_retry`: chèn `is_cloudflare_challenge`
  → tách nhánh CF vs auth.
- **Grok** (`grok/config.py` + `grok/client.py`): rnet Emulation + UA + sec-ch-ua **động** từ
  `cloakbrowser_binary_major()` (đúng issuer, hết hardcode 145). `search()`: detect CF trên status/body.
- **Fix mâu thuẫn headless**: `capture_statsig_id_via_chrome` + `grok_refresh_statsig` → `headless=False`
  trên nhánh CF (cloakbrowser headful 83% vs 50%).
→ verify: `pytest tests/ -v` xanh; live `perplexity_search` + `grok_4_3` (1 query nhỏ) trả lời.

## P2 — Self-heal sâu (ladder + breaker) 
- `is_cloudflare_challenge` → nhánh browser-solve cho **Perplexity** (hiện chưa có): reuse cloakbrowser/
  patchright headful, harvest cf_clearance vào perplexity store.
- **CDP-attach Chrome thật** (cross-platform hoá `tools/test_chrome_copy_cdp.py`): copy profile (Chrome v136+),
  `--remote-debugging-port`, `Network.getAllCookies` / `page.evaluate(fetch)`. Fallback bền nhất.
- **Circuit breaker + cooldown**: lưu `{cf_fails, last_fail_ts, cooldown_until}` trong config.json per provider;
  K fail/cửa sổ → cooldown (CF risk decay) + exponential backoff; lỗi **actionable**.
→ verify: unit test breaker (mock clock); integration mock CF 503/200-interstitial.

## P3 — Hygiene 
- Nâng `rnet` ≥0.11 (mở Chrome146/147) trong pyproject; cập nhật `pick_rnet_emulation`.
- cloakbrowser: cân nhắc `ensure_binary`/update lên 146 + đồng bộ grok major theo binary.
- Tài liệu README "Config store" thêm mục cloak-version cache + breaker.
→ verify: full suite + smoke.

## Thứ tự thực thi
P0 (an toàn, đứng một mình) → impact-analysis → P1 (surgical hot-path) → test → P2 → P3.
Trạng thái cập nhật ở cuối file này mỗi phase.

---
### STATUS (2026-06-08)
- [x] **P0** — `deep_research/cloak.py` + `tests/test_cloak.py` (17 test). Smoke thật:
  detect Chrome 148 → perplexity `chrome146`+UA146 (TLS↔UA khớp), grok 145 (theo binary cloakbrowser).
- [x] **P1** — wired: perplexity `_create_session` + CF-detect trong `_request_with_retry`;
  grok config UA/TLS động + `_ensure_client` emulation động + CF-detect trong `search`;
  `capture_statsig_id_via_chrome` đổi sang **headless=False** (CF cần headful). **255/255 test xanh.**
- [ ] **P2** — browser-solve cho Perplexity; CDP-attach Chrome thật (Chrome v136+ phải copy profile);
  circuit-breaker + cooldown (lưu trong config.json).
- [ ] **P3** — nâng `rnet>=0.11` (mở Chrome146/147) + cloakbrowser auto-update 146.

Lint còn lại đều **pre-existing** (không phải thay đổi này): `perplexity/client.py` 2×E402
(import sau `logging.basicConfig`), `grok/client.py` 1×F401 `asyncio` unused. Để nguyên (surgical).
`detect_changes` báo "critical" = artifact fan-in của `GrokClient.search` (mọi grok tool đi qua), không phải lỗi.
