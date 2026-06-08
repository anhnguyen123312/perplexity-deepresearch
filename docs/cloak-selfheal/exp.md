# exp.md — Cloak self-heal: evidence & live findings (2026-06-08)

## Goal
Cloak (TLS/UA impersonation) bị **cũ** → Perplexity & Grok **hay dính Cloudflare**.
Cần **cơ chế tự-fix lỗi** (self-heal) để dùng mượt mà.

## Ground truth của máy (đo trực tiếp, không đoán)
| Thứ | Giá trị thật | Nguồn |
|---|---|---|
| Local Chrome | **148.0.7778.215** | `Google Chrome --version` |
| curl_cffi | **0.15.0**, `DEFAULT_CHROME = chrome146` | `import curl_cffi` |
| rnet | API đời cũ, `Emulation.Chrome*` **max = Chrome145** | `dir(rnet.Emulation)` |
| cloakbrowser | **0.3.28**, binary thật = **Chromium 145.0.7632.109.2** (bundled 146 chưa tải) | `cloakbrowser.binary_info()` |
| pyproject pin | `rnet>=3.0.0rc22`, `cloakbrowser>=0.3.28`, `curl-cffi>=0.15.0` | pyproject.toml |

## Cloak đang pin ở đâu (the "cũ")
| Provider | Hằng số | File:line | Lệch vs Chrome 148 |
|---|---|---|---|
| Perplexity | UA header `Chrome/130` + `sec-ch-ua v=130` | `config.py:36,44` | **−18** 🔴 |
| Perplexity | curl_cffi `impersonate="chrome"` → TLS **chrome146** | `perplexity/client.py:122` | TLS 146 vs UA 130 = **lệch nội bộ** 🔴 |
| Grok | `IMPERSONATE_TARGET="Chrome145"`, `CHROME_UA=145`, `SEC_CH_UA=145` | `grok/config.py:30,35,41` | −3 (nhất quán nội bộ với cloak 145) |
| Grok | rnet `Emulation.Chrome145` | `grok/client.py:56` | khớp cloakbrowser 145 ✓ nhưng kẹt trần 145 |
| Gemini | `IMPERSONATE_TARGET="chrome146"` | `gemini/config.py:39` | −2 (ít tệ nhất) |

→ **Bản chất "cloak cũ"**: mọi UA/TLS target là hằng số đông cứng tại 1 thời điểm.
Mỗi lần Chrome auto-update, khoảng cách rộng thêm. Không có cơ chế bám theo Chrome.

## Live reproduction
- `perplexity_search` (MCP) gọi thật → **TRẢ LỜI OK + citations** ngay lúc này.
  → Lỗi CF của Perplexity là **gián đoạn** (khi cookie hết hạn / risk score tăng / drift đủ lớn),
  KHÔNG phải hỏng vĩnh viễn. Đây là lý do "hay dính" chứ không "luôn chết".
- Perplexity answer tự confirm hướng fix: cf_clearance bound vào **JA3/JA4 + HTTP/2 order + UA**;
  best practice = detect Chrome version động rồi match `impersonate` + UA **chính xác**.

## Lỗ hổng cơ chế (vì sao "dính" mà không tự khỏi)
1. **Không detect Cloudflare challenge**: cả 2 client chỉ rẽ nhánh `status in (401,403)` + 429.
   Bỏ sót: header `cf-mitigated: challenge`, 503/429 CF, **200/503 kèm HTML "Just a moment..."**,
   body markers `__cf_chl` / `challenge-platform`. → CF interstitial 200 lọt vào parser SSE →
   `_collect_events` rỗng → báo "No response" chung chung, KHÔNG kích hoạt self-heal.
2. **Perplexity self-heal nông**: 401/403 chỉ `extract_cookies_with_relaunch()` = **đọc lại cookie DB**.
   KHÔNG giải CF challenge bao giờ. Nếu CF managed-challenge, đọc lại cookie vô ích
   (cookie DB không có cf_clearance mới trừ khi user tự vào Chrome). Perplexity **không có** browser-solve.
   (`perplexity/client.py:130-176`)
3. **Grok self-heal mâu thuẫn**: `capture_statsig_id_via_chrome(headless=True)` mặc định
   (`grok/statsig.py:62`), nhưng `docs/grok-cf-bypass/research.md` gotcha #3 ghi rõ:
   headless=True **KHÔNG** auto-clear managed challenge (kẹt ở "Just a moment..."). →
   path refresh fail đúng lúc cần nhất. `server.py:285 grok_refresh_statsig` cũng gọi headless mặc định.
4. **rnet kẹt trần Chrome145**: muốn bám Chrome lên 146/148 phải nâng rnet (bản wreq mới hỗ trợ 146+).

## Tài sản có sẵn (tái dùng cho self-heal)
- `tools/test_chrome_copy_cdp.py` — prototype **CDP-attach** vào chrome.exe thật (copy user-data-dir,
  `--remote-debugging-port`, `Network.getAllCookies`). Hướng "zero fingerprint mismatch".
- `tools/replay_capture.py`, `tools/statsig_bridge.js`, `tools/grok_smoke_test.py` — script thực nghiệm.
- `grok/statsig.py` đã có sẵn: launch cloakbrowser ephemeral, harvest cf_clearance/__cf_bm, merge vào config.
- `profile_config.py` — store cookie per-profile + expiry + statsig cache (đủ chỗ nhét health/breaker state).
- `docs/grok-cf-bypass/research.md` — não cũ: Patchright+Chrome148 SOLVED, ladder fix A–E, gotchas.

## Verdict
"Tự fix" = (1) **xoá drift tận gốc** bằng detect-Chrome-version-động + align UA/TLS;
(2) **detect đúng** CF-challenge vs auth-expired vs rate-limit; (3) **ladder leo thang** đúng nhánh
(re-read cookie → browser-solve headful → cooldown/backoff → lỗi actionable) + circuit breaker.
