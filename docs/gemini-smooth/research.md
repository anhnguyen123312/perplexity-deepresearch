# Gemini "mượt" — Root cause (symptoms: chờ lâu / dead / phải nhắc lại)

Date: 2026-06-08. Method: trace source + introspect. Không đoán.

## Triệu chứng (user)
Dùng `gemini_deep_research` → chờ rất lâu, có khi dead, phải nhắc lại mới ra kết quả.

## Đường đi thực
`server.gemini_deep_research(query, poll_interval=30, timeout=1800)`
→ `client.full_deep_research`:
  1. submit(deep_research=True)          # stage-1 plan (~<30s)
  2. submit("Start research", ids…)      # stage-2 confirm
  3. poll_research: vòng lặp READ_CHAT mỗi 30s tới khi done hoặc **timeout 1800s (30 phút)**

→ Toàn bộ là **MỘT lời gọi MCP đồng bộ, chặn tới 30 phút**, không phát progress.

## Bằng chứng then chốt
- `config.POLL_TIMEOUT_SECS=1800`, `POLL_INTERVAL_SECS=30`; tool default y hệt.
- `poll_research` chỉ `done` khi `completion==2 AND immersive_markdown (cand[30][0][4])`.
- Auth GIỮA chừng ổn định → KHÔNG phải nguyên nhân chết:
  - `csrf.CSRF_TTL_SECS=1800` (30m) ≥ độ dài run.
  - `_ensure_session` cache `self._sess`, không re-check expiry giữa run.
  - cookie expire gemini=1200s nhưng chỉ kích hoạt khi 401/403, không tự ngắt session đang chạy.

## Root cause
- **RC1 (chính, kiến trúc):** long synchronous MCP tool. Một call chặn 5–30 phút vượt
  timeout phía client → client hủy call (→ "dead"), kết quả không về (→ "phải nhắc lại"),
  không feedback (→ "chờ lâu"). KHÔNG resumable: gọi lại = chạy lại từ đầu.
- **RC2 (phụ):** cold-start stage-1 thỉnh thoảng fail khi CSRF/cookie chưa ấm → trả error.
- **RC3 (liên quan):** fingerprint lệch (TLS chrome146 vs UA Chrome/148, thiếu sec-ch-ua)
  → tăng rủi ro BardErrorInfo/silent fail (xem docs/web-parity-audit/exp.md).

## Hướng sửa (kiến trúc, vì RC1 là kiến trúc)
Tách 1 call-chặn-30-phút → flow **non-blocking, resumable, agent-driven**:
- `gemini_deep_research_start(query)` → stage1+stage2, trả NHANH `{conversation_id, plan…, status:"running"}`.
- `gemini_deep_research_poll(conversation_id)` → MỘT READ_CHAT, trả `{done, in_progress, text?, elapsed}`.
- Mỗi call < ~60s → không chạm timeout client. Lỗi 1 poll = poll lại CÙNG conversation (không restart).
- Giữ `gemini_deep_research` cũ (backward-compat) nhưng degrade an toàn: quá ngưỡng ngắn → trả
  `{status:"running", conversation_id, next:"poll"}` thay vì chặn tiếp.
Cộng thêm: align fingerprint (RC3) + warm CSRF ở start (RC2).
