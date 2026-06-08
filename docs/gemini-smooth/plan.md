# Gemini "mượt" — Plan (surgical, mỗi bước verify)

## A. Align fingerprint (RC3 + goal "giống web") — rủi ro thấp
- `cloak.py`: thêm `gemini_cloak()` = dùng chung curl_cffi local-Chrome cloak (như Perplexity).
- `gemini/config.py`: `IMPERSONATE_TARGET`/`CHROME_UA` derive từ `cloak.gemini_cloak()`; thêm
  `SEC_CH_UA`, `SEC_CH_UA_PLATFORM`. (Bỏ hardcode TLS146/UA148.)
- `gemini/client.py` `_build_headers` + `_batch_execute`: thêm `sec-ch-ua`/`-mobile`/`-platform`.
- `gemini/csrf.py` `_fetch_homepage`: thêm sec-ch-ua (kế thừa qua config).
- Verify: UA major == TLS major; pytest -k gemini.

## B. Non-blocking + resumable (RC1) — fix chính
- `gemini/client.py`:
  - `start_deep_research(...)`: stage1 plan + stage2 confirm, **KHÔNG poll**, trả `{conversation_id,
    response_id, choice_id, plan_title, plan_steps, status:"running"}` (nhanh ~30–60s).
  - `poll_once(conversation_id, ...)`: MỘT `_read_chat_status`, trả `{done, in_progress, text, title, reason}`.
- `server.py`:
  - tool `gemini_deep_research_start(query)` → `start_deep_research(**cfg)`.
  - tool `gemini_deep_research_poll(conversation_id)` → `poll_once(...)`.
  - `gemini_deep_research(query, wait=False)`: default **non-blocking** = start + trả handle +
    `next:"poll"`. `wait=True` = giữ blocking cũ (`full_deep_research`) làm escape hatch.
- Mỗi tool-call < ~60s → không chạm timeout client. Singleton `_gemini` giữ session ấm giữa các call;
  poll resumable kể cả khi server restart (CSRF cache trong profile_config).
- Verify: test start trả conversation_id không poll; test poll_once 1 lần; full pytest.

## Ngoài phạm vi (không tự làm)
- RC2 (Gemini error-chip cold fail) để retry sẵn có lo; không over-engineer.
- gitnexus index stale → rely on pytest; analyze lại sau khi commit.
