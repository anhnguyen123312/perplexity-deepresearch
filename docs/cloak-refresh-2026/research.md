# Cloak Refresh 2026 — Research

Issue: cloak "bị cũ", hay dính Cloudflare ở **perplexity** và **grok**.
Date: 2026-06-08. Method: đọc source + introspect packages đã cài (không đoán).

## Môi trường thực (evidence)

| Thứ | Giá trị thực | Nguồn |
|---|---|---|
| Chrome thật của máy | **148.0.7778.215** | `Google Chrome --version` |
| curl_cffi | 0.15.0 (PyPI latest) | `pip` |
| curl_cffi `impersonate="chrome"` | → resolve **chrome146** | `normalize_browser_type("chrome")` |
| curl_cffi hỗ trợ rõ ràng | …chrome142, chrome145, **chrome146** | `BrowserTypeLiteral` |
| rnet | 3.0.0rc22 (pin trong pyproject) | `importlib.metadata` |
| rnet max emulation | **Chrome145** (không có 146+) | `dir(rnet.Emulation)` |
| cloakbrowser package | 0.3.28 (latest = 0.3.31) | `pip` |
| cloakbrowser binary ĐANG CHẠY | **145.0.7632.109.2** | `cloakbrowser.binary_info()` |
| cloakbrowser bundled_version | 146.0.7680.177.3 (chưa active) | `binary_info()` |

## Root cause — PERPLEXITY (nặng nhất) ❌

`deep_research/perplexity/client.py` + `deep_research/config.py`:

- Session: `impersonate="chrome"` → curl_cffi gửi TLS/JA3/JA4 + HTTP2 của **Chrome 146**.
- Nhưng `DEFAULT_HEADERS` (config.py:30-45) hardcode:
  - `user-agent: ...Chrome/130.0.0.0...`
  - `sec-ch-ua: "Chromium";v="130", "Google Chrome";v="130"...`
- → Cloudflare cross-check **TLS(146) ↔ UA(130) ↔ sec-ch-ua(130)**: lệch **16 major version**.
  Đây là tín hiệu bot kinh điển (TLS nói tôi là Chrome 146, header nói tôi là Chrome 130).
- `SSE_REQUEST_HEADERS` không có sec-ch-ua/UA riêng → kế thừa bộ 130 sai.
- Refresh path (`_refresh_cookies` → `extract_cookies_with_relaunch`) chỉ lấy lại cookie từ
  Chrome local; KHÔNG warm `cf_clearance` qua browser stealth như grok. Nếu CF đã ra
  managed challenge, cookie mới vẫn không kèm `cf_clearance` hợp lệ → vẫn 403.

Kết luận: perplexity identity **vừa cũ (130) vừa mâu thuẫn nội bộ (TLS 146 vs UA 130)**.

## Root cause — GROK (đảo giả thuyết ban đầu)

Chuỗi danh tính grok **nhất quán ở 145**:
- rnet `Emulation.Chrome145` (rc22 max tới 145) — TLS 145
- `CHROME_UA` = Chrome/145, `SEC_CH_UA` v=145
- cloakbrowser binary active = **145**.0.7632.109.2

→ Pin 145 KHÔNG phải bug; nó khớp với trần của rnet + binary cloak hiện tại.

**Bug grok thật = headless regression:**
- `deep_research/grok/statsig.py:62` → `headless: bool = True` (default).
- `docs/grok-cf-bypass/research.md` gotcha #3 (đã verify trước đây) ghi rõ:
  > "headless=True ≠ headless=False for CF — In headless mode CF managed challenge
  > does NOT auto-clear (page sits on 'Just a moment...'), statsig submit times out.
  > Default to headless=False."
- Commit `a2cb348` (rnet hot-path + ephemeral CloakBrowser) đã đưa default về `headless=True`,
  mâu thuẫn với kết luận đã chốt → đây là nguyên nhân grok "hay dính cloudflare" khi phải
  refresh (capture lần đầu / sau 401-403): CloakBrowser headless không clear được challenge.
- Không có env override (`GROK_HEADLESS`) → người dùng không tự sửa được.

Phụ: cloakbrowser 0.3.28 (cũ 3 bản so với 0.3.31, ra 2026-05-26) — nên nâng để lấy
patch fingerprint mới + có đường lên binary 146/147 khi rnet kịp 146.

## Vì sao "cũ" lại dính nhiều hơn giữa 2026

CF xoay vòng baseline fingerprint theo Chrome stable. Tháng 6/2026 Chrome stable ~148.
JA3/UA của Chrome 130 (perplexity) đã rời rất xa baseline → bucket nghi ngờ cao → ép
interactive challenge. 145 (grok) gần hơn nhiều nhưng vẫn phải dựa vào browser warm
`cf_clearance`; nếu warm bằng headless thì hỏng.

## Trần kỹ thuật (không thể vượt bằng config)

- rnet rc22 KHÔNG có Chrome146+ → muốn TLS 146/147/148 phải đợi rnet bản mới HOẶC
  chuyển grok hot-path sang curl_cffi `chrome146` (curl_cffi đã có 146).
- curl_cffi max public = chrome146 → perplexity có thể lên 146 NGAY (sửa header cho khớp).
- Khớp tuyệt đối Chrome 148 chưa khả thi với HTTP-only lib; mục tiêu thực tế = **146**
  (gần baseline + nội bộ nhất quán), browser stealth lo phần `cf_clearance`.

## Sources
- Local introspection (rnet/curl_cffi/cloakbrowser) — authoritative cho máy này
- docs/grok-cf-bypass/research.md (lịch sử đã verify)
- PyPI release metadata (cloakbrowser 0.3.31 @ 2026-05-26)
