# Web-parity audit — "có giống dùng web 100% không?"

Date: 2026-06-08. Method: đọc source + introspect runtime trên máy thật (Chrome local = **148**),
chạy full test (276 passed). Không đoán.

## Câu hỏi
Request mà MCP gửi đi (Perplexity / Grok / Gemini, mọi tool review) có **trùng 100%** với web app gốc?

## Bằng chứng runtime (introspect, Chrome thật = 148)

| Provider | Đường truyền | TLS/JA3 | UA major | sec-ch-ua | Nội bộ nhất quán? | = Chrome thật 148? |
|---|---|---|---|---|---|---|
| **Perplexity** | curl_cffi (cloak ĐỘNG) | chrome146 | 146 | v=146 | ✅ 146=146=146 | ❌ 146 vs 148 (trần curl_cffi) |
| **Grok** | rnet (cloak ĐỘNG theo binary) | Chrome145 | 145 | v=145 | ✅ 145=145=145 | ❌ 145 (cố ý — bind cf_clearance) |
| **Gemini** | curl_cffi (HARDCODE) | chrome146 | **148** | KHÔNG gửi | ❌ **146 ≠ 148** | UA đúng, TLS lệch |

## Verdict từng provider

### Perplexity ✅ (tối đa khả thi)
- `_create_session` dùng `cloak.perplexity_cloak()` → UA = sec-ch-ua = TLS = 146 (nhất quán).
- Body `_build_payload` captured live 2026-05-11; header SSE khớp web.
- Sai khác duy nhất: major 146 vs Chrome thật 148 — **trần thư viện** (curl_cffi 0.15 max = chrome146),
  không thể vượt bằng config. JA3↔UA cross-check của Cloudflare vẫn PASS vì nội bộ khớp.
- ⚠️ Doc nit: comment `search()` (client.py:514) ghi "asi/pplx_asi" nhưng code+test+docstring = **pplx_alpha**.
  `_finalize_chunks` lại nhắc `pplx_asi` credits → cần re-capture web thật để chốt deep-research dùng
  `pplx_alpha` hay `pplx_asi`. (Chưa verify được vì không có capture trong repo.)

### Grok ✅ (đúng thiết kế)
- `_ensure_client` dùng `cloak.get_rnet_emulation(cloak.grok_major())` → TLS=UA=sec-ch-ua=145 (nhất quán).
- Body `_build_body` khớp UI; mode IDs verified 2026-05-11 (/rest/modes).
- Pin 145 (≠148) là **bắt buộc**: cf_clearance bound vào CloakBrowser binary (Chromium 145) đã giải challenge.
  Lệch 1 major là dính "Just a moment...". → KHÔNG phải bug.

### Gemini ❌ (CHƯA giống web — điểm cần sửa)
1. **UA/TLS mismatch**: `gemini/config.py` HARDCODE `IMPERSONATE_TARGET="chrome146"` nhưng `CHROME_UA=Chrome/148`.
   Lệch 2 major. Chưa migrate sang cloak module như pplx/grok.
2. **Thiếu sec-ch-ua / sec-ch-ua-platform**: `_build_headers` (client.py:241) KHÔNG set 2 header này — browser
   thật LUÔN gửi trên StreamGenerate. (Test không bắt vì chỉ test parser.)
3. **Mất ref doc**: code trỏ `docs/gemini-mcp/ref.md` + `research.md` nhưng 2 file KHÔNG tồn tại → không verify
   được inner-array (80 phần tử) body so với capture web trong repo.
4. Giảm nhẹ: Gemini sau Google (không phải Cloudflare) nên ít cross-check JA3↔UA → vẫn chạy, nhưng
   **không "100% giống web"**.

## Kết luận
- Perplexity + Grok: **nhất quán nội bộ, gần web nhất có thể** (chặn bởi trần lib / ràng buộc cf_clearance).
  Đạt mức tối đa khả thi; không byte-identical major chỉ vì 146/145 < 148.
- Gemini: **CHƯA đạt** — UA/TLS lệch + thiếu sec-ch-ua + mất ref doc.

## Đề xuất sửa (Gemini, rủi ro thấp — theo đúng pattern pplx)
- Cho Gemini đi qua `cloak.perplexity_cloak()` (cùng path curl_cffi) → UA=sec-ch-ua=TLS=146 nhất quán.
- Thêm `sec-ch-ua` + `sec-ch-ua-platform` vào `_build_headers` + `_batch_execute` headers.
- Khôi phục/viết lại `docs/gemini-mcp/ref.md` từ 1 capture live để khoá schema body.
- Verify: `pytest tests/ -k gemini` + smoke `gemini_deep_research` 1 lần.
