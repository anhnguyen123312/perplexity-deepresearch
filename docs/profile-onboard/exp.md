# exp.md — Onboard chọn profile per-provider, bỏ scan-all (2026-06-08)

## Yêu cầu
"Phần scan các profile chrome để lấy cookies của các provider — sửa để **onboard cho user hiểu**,
**không scan hết**; khi dùng **show profile đang dùng**."

## Quyết định của user (AskUserQuestion)
- **Fallback khi chưa onboard** → *Tự chọn + nhớ lại + báo*: 1 profile signed-in → tự dùng + lưu làm default;
  nhiều profile → dùng Default/đầu tiên + **cảnh báo** chạy `deep-research-onboard`; **không scan-all âm thầm**.
- **Show profile** → *bỏ qua* → chỉ giữ 1 dòng log stderr ở thời điểm SELECT profile (không đụng schema response).

## Hiện trạng cũ (nguyên nhân "scan hết")
- `cookies.get_cookies()` (pplx) + `grok/cookies.get_grok_cookies_cached()`:
  cache miss → `extract_*_all_profiles()` **duyệt MỌI profile, giải mã cookie, persist hết** rồi trả preferred.
- `onboard.py` đã cho chọn 1 profile + show email, **nhưng** chỉ lưu `chrome_profile` setting cho **gemini**
  (dòng 285-291). pplx/grok không nhớ "profile đã chọn".
- `gemini/cookies.py` **đã có** pattern chuẩn: pin `chrome_profile`, đọc đúng 1 profile → dùng làm khuôn mẫu.

## Thay đổi (per-provider, mô phỏng gemini)
1. `profile_config.py`: thêm `get_chosen_profile(provider)` / `set_chosen_profile(provider, name)`
   (thin wrapper trên `settings.chrome_profile`).
2. `cookies.py` (perplexity): thêm `_harvest_perplexity_profile` (1 profile) + `_resolve_perplexity_profile(chosen)`
   (chosen → đúng profile đó; chưa có → auto-pick first signed-in: 1 profile→nhớ, nhiều→cảnh báo;
   none→`CookieExtractionError` actionable). Rewrite `get_cookies()`: cache(chosen) → resolver single →
   persist 1 → return. **Bỏ `extract_cookies_all_profiles()` khỏi runtime.** DB-lock → vẫn fallback relaunch.
3. `grok/cookies.py`: tương tự (`_harvest_grok_profile` + `_resolve_grok_profile` + rewrite `get_grok_cookies_cached`).
4. `onboard.py`: `_save_cookies` giờ **pin chosen profile** cho mọi provider harvest được; thêm dòng summary
   "→ Default Chrome profile for …".
5. `_note_active_profile()` (stderr) chỉ in ở 2 case: `remembered` (1 profile, đã lưu) / `temporary` (nhiều, cảnh báo onboard).

## Giữ nguyên (không phá)
- Env `CHROME_PROFILE` vẫn override (power user). `CHROME_PROFILES`/`CHROME_SCAN_PROFILES` còn đó.
- `extract_*_all_profiles` còn (dùng bởi `cli rescan` — lệnh explicit, không phải runtime auto).
- Windows: rookiepy gộp mọi profile → synthetic "Default" (không tách được per-profile — như cũ).
- Gemini: vốn đã config-only; nay nhất quán (onboard cũng pin qua `_save_cookies`).

## Verify
- `pytest tests/ -v` → **263 passed** (+8 test mới: resolver single/remember/warn/raise cho pplx & grok).
- `ruff check` các file đổi → **All checks passed**.
- Smoke (config tạm, không đọc Chrome): set/get chosen OK; `get_cookies()` trả cache theo chosen, **không scan**.

## Lưu ý rủi ro
- `gitnexus impact get_grok_cookies_cached` = **HIGH** — artifact fan-in (`grok_search` → mọi grok tool đi qua);
  signature giữ nguyên `dict[str,str]`, callers không vỡ; 263 test phủ. Đã cẩn trọng.
