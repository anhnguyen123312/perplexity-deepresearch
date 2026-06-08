# Cloak Refresh 2026 — Experiments / Evidence log

Tất cả chạy trên máy thật (.venv, python 3.14), 2026-06-08. Không đoán.

## E1 — curl_cffi "chrome" alias resolve

```
normalize_browser_type("chrome") = chrome146
DEFAULT_CHROME = chrome146
```
curl_cffi explicit list có: …chrome142, chrome145, **chrome146** (+ alias `chrome`→146).
→ Perplexity đang gửi TLS Chrome146 nhưng header khai Chrome130. MÂU THUẪN.

## E2 — rnet emulation ceiling

```
rnet 3.0.0rc22
Chrome: …Chrome143, Chrome144, Chrome145   (KHÔNG có 146+)
Edge:   …Edge145
Firefox: Firefox145/146/147
Safari: …SafariIos26_2, SafariIpad26_2
```
→ rnet hiện KHÔNG thể giả Chrome146. stable 2.4.2 còn cũ hơn (08/2025). Grok hot-path
muốn >145 thì phải đổi sang curl_cffi(chrome146) hoặc Edge145/Firefox147.

## E3 — cloakbrowser binary thật

```
binary_info(): version=145.0.7632.109.2 (ĐANG dùng)
                bundled_version=146.0.7680.177.3 (CHROMIUM_VERSION, chưa activate)
package=0.3.28 ; latest=0.3.31 (2026-05-26)
```
→ Binary active = 145, khớp UA/TLS grok. Bundled 146 chưa chạy (cần ensure_binary/update).

## E4 — headless contradiction (grok bug)

```
statsig.py:62  headless: bool = True          ← default hiện tại
research.md#120 "headless=True ... CF challenge does NOT auto-clear ... Default to headless=False"
```
Không có caller nào truyền headless=False, không có env override.
→ Mỗi lần grok phải capture/refresh (lần đầu hoặc sau 401/403) chạy CloakBrowser **headless**
→ kẹt "Just a moment...", statsig submit timeout → grok "dính cloudflare".

## E5 — perplexity refresh không warm cf_clearance

`client._refresh_cookies()` → `extract_cookies_with_relaunch()` chỉ đọc lại cookie DB Chrome.
Không có bước stealth-browser warm `cf_clearance` như grok. Nếu CF đã challenge,
retry vẫn thiếu cf_clearance hợp lệ.

## Verdict (đã đủ, không cần thêm probe)

3 lỗi độc lập:
1. **PPLX header/TLS mismatch** (130 vs 146) — sửa config = nhất quán 146. RỦI RO THẤP, tác động CAO.
2. **GROK headless default** — đổi về False + env override. RỦI RO THẤP, tác động CAO.
3. **PPLX refresh thiếu cf_clearance warm** — mượn CloakBrowser như grok. RỦI RO TRUNG BÌNH.

Phụ: nâng cloakbrowser 0.3.28→0.3.31; cân nhắc activate binary 146.
