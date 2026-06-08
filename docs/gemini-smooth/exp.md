# Gemini "mượt" — Experiments / kết quả thực thi

Date: 2026-06-08. Tất cả verify trên máy thật (.venv), không đoán.

## Đã sửa (surgical)

### A. Align fingerprint (RC3)
- `cloak.py`: + `gemini_cloak()` (= curl_cffi local-Chrome cloak, dùng chung với Perplexity).
- `gemini/config.py`: bỏ hardcode TLS146/UA148; derive `IMPERSONATE_TARGET/CHROME_UA/SEC_CH_UA/
  SEC_CH_UA_PLATFORM` từ `cloak.gemini_cloak()`.
- `gemini/client.py` `_build_headers` + `_batch_execute`: + `sec-ch-ua` / `-mobile` / `-platform`.
- `gemini/csrf.py` `_fetch_homepage`: + sec-ch-ua.
- Verdict introspect: `IMPERSONATE=chrome146, UA major=146, SEC_CH_UA v=146` → **UA==TLS==sec-ch-ua = True**
  (trước: TLS146 vs UA148, thiếu sec-ch-ua).

### B. Non-blocking + resumable (RC1 — fix chính)
- `gemini/client.py`: + `start_deep_research()` (stage1+2, KHÔNG poll) + `poll_once()` (1 READ_CHAT).
- `server.py`:
  - `gemini_deep_research(query, wait=False)` → default **non-blocking**: start + trả `{status:"running",
    conversation_id, plan_*, next:"call gemini_deep_research_poll(...)"}`. `wait=True` = blocking cũ (escape hatch).
  - + tool `gemini_deep_research_poll(conversation_id)` → 1 status read, trả `{done, in_progress, text, …}`.
- Singleton `_gemini` giữ session ấm giữa các tool-call; poll resumable (CSRF cache trong profile_config
  sống qua restart). Mỗi call < ~60s → không chạm timeout client.

## Verify (bằng chứng)
- `python -m pytest tests/ -q` → **284 passed** (trước 276; +8 test: start/poll/fingerprint).
- Smoke introspect: UA==TLS aligned; `_build_headers` có sec-ch-ua trio; tools đăng ký:
  `gemini_deep_research`, `gemini_deep_research_poll`, `gemini_refresh_csrf`.
- Smoke server: wait=False→start+next; poll→done+text; wait=True→full_deep_research. PASS.

## Impact (gitnexus)
- `gemini_deep_research`: LOW risk, 0 upstream (tool lá) → an toàn đổi default.
- `_build_headers` CRITICAL là **trùng tên Grok** — không đụng Grok.
- ⚠️ gitnexus index STALE (chứa symbol `gemini_start_research/poll` cũ không có trong file) → dựa vào pytest;
  cần `npx gitnexus analyze` sau khi commit.

## Cách dùng mới (mượt)
1. `gemini_deep_research("câu hỏi")` → trả ngay `conversation_id` + plan (status=running).
2. Lặp `gemini_deep_research_poll(conversation_id)` ~30s/lần tới khi `done=true` → lấy `text` (report).
   (Muốn 1-shot blocking cũ: `gemini_deep_research(query, wait=True)`.)

## Chưa làm (ngoài phạm vi, ghi nhận)
- RC2 (Gemini error-chip cold fail): để retry sẵn có lo, không over-engineer.
- Verify body inner-array vs capture web: thiếu `docs/gemini-mcp/ref.md` (mất) — cần 1 capture live để khoá.
