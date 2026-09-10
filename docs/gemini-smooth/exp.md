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

## 2026-09-10 — BUG: ack chip "đang chạy" bị phân loại thành "đã dừng"

Phát hiện khi verify live (`c_037bc2a4af5a0b03`).

`_read_chat_status` nhận ack chip **chỉ khi** `completion == 2`. Nhưng Gemini đang trả:

```
raw_status = 1        (không phải 2)
progress   = None     (cand[12][6][0] trống)
text       = "Tôi đang tiến hành. Khi nghiên cứu hoàn tất, tôi sẽ thông báo…
              http://googleusercontent.com/immersive_entry_chip/0"
```

→ rơi vào nhánh `else` = "Stopped (safety policy / usage limit)", trong khi run vẫn khoẻ.

**Hệ quả nặng**: `poll_research` bail khi `reason and not in_progress`
→ `gemini_deep_research(wait=True)` **trả về sau 0.7s** trên budget 600s, `polls=1`,
báo dừng giả. Đường non-blocking vẫn tới đích nếu caller phớt lờ `in_progress`,
nhưng docstring lại dạy caller tin vào nó.

**Fix**: thêm nhánh trước `else` — text chứa `DR_CHIP_MARKER = "immersive_entry_chip"`
nghĩa là immersive doc đã gắn và đang chạy → `in_progress = True`.
Đặt **sau** nhánh `progress is not None` để không đổi hành vi cũ, chỉ cứu case bị
gán nhầm "stopped". Case stop thật (`test_hard_stop_when_no_progress_no_completion`,
chip_text không có marker) vẫn giữ nguyên.

Verified live cùng conversation: trước `in_progress=False, reason="Tôi đang tiến hành…"`
→ sau `in_progress=True, reason=None`, `raw_status` vẫn 1.

**Chưa có mẫu stop thật** (hết quota/policy) để đối chứng — nếu sau này bắt được,
kiểm tra lại xem nó có kèm marker không.
