# Perplexity intercept-test — "request giống web 100%?" (2026-06-08, ulw)

Method: review + INTERCEPT thật. Ground-truth = live Playwright `request.all_headers()`
capture của POST `/rest/sse/perplexity_ask` (bộ `request.headers` cũ THIẾU header browser
tự thêm → capture cũ không đầy đủ). Wire-test = bắn curl_cffi thật qua local echo server.

## Phát hiện & sửa (header)

Bug gốc: `DEFAULT_HEADERS` (session) rò **nav-only headers** lên SSE POST (XHR). Web thật (XHR)
gửi bộ khác. Đã sửa `config.SSE_REQUEST_HEADERS` để tái tạo CHÍNH XÁC bộ XHR low-entropy:

| Header | Web XHR thật | Trước | Sau |
|---|---|---|---|
| sec-fetch-dest | empty | document (rò nav) | empty ✅ |
| sec-fetch-mode | cors | navigate (rò nav) | cors ✅ |
| sec-fetch-site | same-origin | same-origin | same-origin ✅ |
| priority | u=1, i | u=0, i (nav) rồi bị suppress nhầm | u=1, i ✅ |
| accept-language | en-US,en;q=0.9 | suppress nhầm | gửi ✅ |
| origin | https://www.perplexity.ai | **THIẾU** | gửi ✅ |
| sec-fetch-user / upgrade-insecure-requests / cache-control / dnt | absent | rò nav | suppress (None) ✅ |

`None` value → libcurl xoá header (verified on-wire: KHÔNG có literal "None").

## Kết quả wire-test (verified)
On-wire app-relevant header KEY-set = **17 key khớp CHÍNH XÁC** web thật:
accept, accept-language, content-type, origin, priority, referer, sec-ch-ua,
sec-ch-ua-mobile, sec-ch-ua-platform, sec-fetch-{dest,mode,site}, user-agent,
x-perplexity-request-{endpoint,reason,try-number}, x-request-id.
- missing=NONE, extra=NONE, nav-leak=NONE, literal-None=NONE.

## Body (params) — 100% khớp
35 params key-set khớp; mọi static value khớp; supported_block_use_cases (32 item) +
supported_features byte-identical; version=2.18. mode "pro" = (copilot, pplx_pro) khớp capture.

## Gap còn lại (không vượt được / cần quyết)
1. **sec-ch-ua / UA major = 146** (ta) vs **147/148** (Chrome thật) — trần curl_cffi 0.15 (max chrome146).
   Nội bộ nhất quán (UA=sec-ch-ua=TLS=146); không phải lệch key-set. Muốn 147+ phải đợi curl_cffi.
2. **High-entropy client hints** (sec-ch-ua-arch/bitness/full-version[-list]/model/platform-version):
   web thật gửi, ta KHÔNG. Cố ý bỏ — device-specific + chỉ gửi sau khi server cấp Accept-CH; server
   không bắt buộc (MCP vẫn chạy). Giả chúng = thêm rủi ro bất nhất. Để trống = trạng thái client "chưa được cấp".
3. **Deep-research mode — BÀI HỌC (v0.8.0→v0.8.1)**: từng đổi sang ("asi","pplx_asi") tưởng là
   "web 100%". SAI: capture `captured_modes.json` entry0 có **`query_source: "computer"`** → đó là
   request của **Perplexity Comet / computer-use agent**, KHÔNG phải Deep Research. LIVE TEST chứng minh:
   asi/pplx_asi → `error_code: GENERIC_FAILED_RESPONSE` ("Please try again later"), `_extras` cho thấy
   account free (subscription_tier=null). Đã **REVERT về ("copilot","pplx_alpha")** — verified live RA
   kết quả (7.6s, 505 ký tự, 10 citations). Bug phụ đã sửa luôn: `_finalize_chunks` so `status=="FAILED"`
   (hoa) nhưng server gửi `'failed'` (thường) → normalize `.upper()` + surface error_code/text.
   **Quy tắc: capture phải kiểm `query_source` (home vs computer) trước khi tin là mode nào.**

## Artefacts
- tools/capture_perplexity_full_headers.py — capture all_headers() (đã redact secret ở output json).
- tools/verify_request_parity.py — wire-level intercept harness (exit0=PARITY OK).
- tests/test_request_parity.py — 8 test (wire-level header parity + None-suppression + body). 292 passed.
