# Cloak Refresh 2026 — Plan

Mục tiêu: cloak hết "cũ" + bớt dính Cloudflare ở perplexity & grok.
Nguyên tắc: surgical, mỗi bước verify riêng. Theo thứ tự rủi ro tăng dần.

## P1 — PPLX: đồng bộ identity về Chrome 146 (rủi ro thấp, tác động cao)
File: `deep_research/config.py`
- `DEFAULT_HEADERS`: UA Chrome/130 → **Chrome/146**; `sec-ch-ua` v="130" → v="146"
  (format Chrome 146: `"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="99"`).
- `impersonate="chrome"` (client.py:122) → pin **`impersonate="chrome146"`** (khớp tường minh, khỏi lệ thuộc alias).
- Đảm bảo `SSE_REQUEST_HEADERS` kế thừa UA/sec-ch-ua mới (không tự khai bản cũ).
- Verify: `pytest tests/ -k perplex` + 1 lần gọi thật `perplexity_search` smoke (nếu có cookie).
- verify-impact: `gitnexus_impact DEFAULT_HEADERS upstream` trước khi sửa.

## P2 — GROK: bỏ headless regression (rủi ro thấp, tác động cao)
File: `deep_research/grok/statsig.py`
- `_do_capture..` / `capture_statsig_id_via_chrome`: default `headless=False`.
- Thêm env override: `GROK_HEADLESS=1` mới chạy headless (mặc định visible).
- Cập nhật docstring statsig.py:13 ("headless") cho khớp.
- Verify: `pytest tests/test_grok_no_chrome_when_cached.py` + smoke `grok_search` cold (xoá statsig cache).

## P3 — Nâng cloakbrowser + cân nhắc binary 146 (rủi ro thấp)
File: `pyproject.toml`
- `cloakbrowser>=0.3.28` → `>=0.3.31`. `pip install -U cloakbrowser`.
- KHÔNG đổi grok sang TLS 146 (rnet trần 145) — giữ chuỗi 145 nhất quán.
- (tuỳ chọn) `cloakbrowser.ensure_binary()` activate 146 CHỈ KHI cũng nâng được rnet→146; nếu không, giữ 145 để khớp rnet.
- Verify: import + `binary_info()` chạy; full `pytest`.

## P4 — PPLX: warm cf_clearance khi 401/403 (rủi ro trung bình, LÀM SAU)
File: `deep_research/perplexity/client.py` + có thể `cookies.py`
- Khi `_request_with_retry` gặp 401/403: trước khi retry, chạy CloakBrowser ephemeral
  vào `https://www.perplexity.ai/` để lấy `cf_clearance`/`__cf_bm`, merge vào cookie store
  (pattern y hệt grok `_do_capture_statsig_id_via_chrome` phần harvest cookies).
- Giữ headless=False (cùng lý do P2).
- Verify: ép 403 (cookie rởm) → quan sát có warm + pass; `pytest`.

## Thứ tự thực thi
P1 → verify → P2 → verify → P3 → verify → (chốt với user) → P4.

## Ngoài phạm vi (ghi nhận, không tự làm)
- Chrome thật = 148; cả curl_cffi (max 146) lẫn rnet (max 145) đều chưa tới 148.
  Khớp 148 hoàn hảo cần lib mới hơn — chờ upstream. Mục tiêu thực tế = 146 (pplx) / 145 (grok).
- Residential proxy (research.md mục A) nếu IP bị flag nặng — cần user quyết, tốn phí.
