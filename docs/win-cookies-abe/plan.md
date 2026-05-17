# Plan — Chrome v20 ABE auto-extract on Windows

## Vấn đề
- User trên Windows, Chrome 130+ dùng App-Bound Encryption v20
- `rookiepy.chrome(domains=["perplexity.ai"])` raise `RuntimeError: decrypt_encrypted_value failed` ngay cả khi chạy admin
- `cookies.json` fallback = manual paste → user không muốn

## Mục tiêu
Auto-extract cookie từ Chrome 130+ trên Windows **không** cần manual paste.

## Hướng tiếp cận (xếp ưu tiên)

### A. Playwright launch_persistent_context (đã có dep)
- Đọc Chrome user-data-dir thật của user → launch headless với `launch_persistent_context()`
- Goto `https://www.perplexity.ai` → page.context.cookies()
- **Ưu**: Chrome tự decrypt in-memory → không cần bypass ABE; codebase đã có playwright + stealth
- **Nhược**: Chrome đang mở cùng profile sẽ conflict → phải copy profile dir tạm hoặc xài CDP attach

### B. CDP attach vào Chrome đang chạy
- Khi user mở Chrome bình thường, attach via remote-debugging-pipe (Chromium-only) hoặc launch lại với `--remote-debugging-port=9222`
- `Storage.getCookies` qua DevTools Protocol → cookies decrypted
- **Nhược**: Chrome user phải khởi động với cờ debug từ đầu — không tự nhiên

### C. COM IElevator (xaitax/Chrome-App-Bound-Encryption-Decryption)
- Gọi COM elevation_service.exe `IElevator::DecryptData` để lấy app-bound key
- Decrypt cookies SQLite file thủ công
- **Nhược**: Cần admin + reverse-engineer COM interface; complex; mỗi version Chrome có thể đổi

### D. Native messaging extension
- Cài Chrome extension đọc cookies API → gửi sang native host
- **Nhược**: Yêu cầu user cài extension thủ công → vẫn là 1 dạng paste

## Quyết định ban đầu
**Hướng A** (Playwright + copy profile tạm) là khả thi nhất:
- Đã có dep playwright + playwright-stealth
- Không cần admin
- Không cần Chrome chạy theo cách đặc biệt
- Chỉ cần copy profile dir → launch headless persistent context → đọc cookies → tear down

## Steps
1. Research: xác nhận Playwright có thể decrypt ABE cookies từ profile copy (research.md)
2. Research: rủi ro lock SQLite khi copy profile khi Chrome đang mở
3. Implement `_extract_cookies_windows_playwright()` thay thế/bổ sung rookiepy path
4. Fallback chain trên Windows: rookiepy → playwright → cookies.json
5. Test trên máy Windows của user

## Done = ?
User chạy `tools\smoke_test.py pro web "..."` → cookie tự lấy được không cần paste
