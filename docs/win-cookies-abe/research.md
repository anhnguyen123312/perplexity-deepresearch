# Chrome v20 App-Bound Encryption (ABE) — Auto-Extract Cookies trên Windows

> **Research date:** 2026-05-11
> **Target:** Python project, Windows 10/11, Chrome 130+ (v20 ABE)
> **Mục tiêu:** Auto-extract decrypted cookies cho perplexity.ai / grok.com — KHÔNG bắt user paste thủ công

---

## TL;DR — Recommendation

**Method ưu tiên cho project này: Playwright `storage_state` + one-time login flow (Method 5 dưới đây).**

Lý do ngắn gọn:

1. Tránh hoàn toàn ABE — không đụng vào SQLite cookies db, không cần decrypt.
2. Không cần admin, không kill Chrome user, không bị AV/EDR flag, không phụ thuộc binary thứ ba.
3. Pure Python, ~30 dòng, dùng đúng `playwright>=1.59.0` đã có trong deps.
4. Tương thích với cả perplexity.ai (Cloudflare bot detection thường reject headless — cần headed một lần đầu).
5. Bền vững với Chrome update (Google đã siết liên tục: Chrome 127 ABE, Chrome 133 đổi ChaCha20-Poly1305, Chrome 136 chặn `--remote-debugging-port` cho default profile, Chrome 137 thêm CNG layer cho domain hosts, Chrome 144 đổi sang `IElevator2` Mojo IPC).

**Fallback method nếu phải lấy session từ Chrome user đang dùng (không re-login): COM `IElevator` qua `comtypes` (Method 3)** — nhưng cần admin và bị EDR detect mạnh.

**KHÔNG dùng:** `--remote-debugging-port` của thewh1teagle gist (đã chết từ Chrome 136), `runassu` PoC (cần SYSTEM + chỉ Chrome ≤136 non-domain), Playwright copy `User Data` (path-validation fail).

---

## 1. Background — Tại sao rookiepy / pycookiecheat fail

Từ Chrome 127 (07/2024) Google enable App-Bound Encryption:

- Cookie có prefix bytes `v20` thay vì `v10`.
- Master key nằm trong `Local State` ở field `os_crypt.app_bound_encrypted_key` (base64), prefix `APPB`.
- Key blob được wrap **2 lớp DPAPI**: trước bằng **SYSTEM DPAPI** (chỉ SYSTEM mới unwrap được lớp ngoài), sau đó bằng **user DPAPI**.
- Việc unwrap lớp SYSTEM được delegate qua **`elevation_service.exe`** (Chrome's COM elevation service) — nó kiểm tra **path validation**: process gọi phải nằm trong `C:\Program Files\Google\Chrome\Application\` (hoặc Program Files (x86)).
- Sau khi unwrap xong còn `PostProcessData()` step nữa: từ Chrome 133 dùng ChaCha20-Poly1305 key hardcode trong `elevation_service.exe`, từ Chrome 137 quay lại AES-256-GCM nhưng thêm CNG-derived `encrypted_aes_key` cho máy domain-joined.
- Cookie value cuối cùng decrypt bằng AES-256-GCM với master key đó.

`rookiepy` và `pycookiecheat` chỉ biết v10 (CryptUnprotectData trực tiếp), nên với v20 trả về `decrypt_encrypted_value failed`. Run as Administrator KHÔNG đủ — admin ≠ SYSTEM, và admin cũng không pass path validation.

---

## 2. Phương pháp — So sánh 5 cách

### Method 1 — Playwright `launch_persistent_context` với copy User Data dir

**Ý tưởng:** Copy `%LOCALAPPDATA%\Google\Chrome\User Data` sang temp dir, mở bằng Playwright Chromium.

**Verdict: KHÔNG WORK cho v20 cookies.**

| Yếu tố | Chi tiết |
|---|---|
| Decrypt v20? | **Không** — `app_bound_encrypted_key` blob có path-validation embed; `elevation_service.exe` reject vì process gọi (Playwright Chromium) không nằm trong Chrome install dir. Playwright dùng Chromium build riêng, không có `elevation_service.exe` bundled. |
| Admin | Không |
| Kill Chrome user | Có (phải close để copy User Data sạch — SQLite WAL lock) |
| Code phức tạp | Thấp (~10 dòng) |
| AV risk | Thấp |
| Headless flag bot trên perplexity? | Có — Cloudflare detect Chromium JA3 + missing headed signals |

Có một vài blog macOS bảo "đổi `--use-mock-keychain` thành `--use-real-keychain`" — đó là mac trick, **không apply cho Windows** vì Windows path validation strict hơn nhiều.

**Conclusion:** Đừng làm. Cookies copy ra sẽ là blob mã hoá rác.

---

### Method 2 — `--remote-debugging-port` + CDP `Network.getAllCookies`

**Ý tưởng:** Kill chrome.exe của user, relaunch với `--remote-debugging-port=9222 --user-data-dir=<user's User Data>`, attach WebSocket, gọi `Network.getAllCookies`. (Đây chính là gist `thewh1teagle/359675c2f5ea4920949448ec705f9fb2`.)

**Verdict: ĐÃ CHẾT từ Chrome 136 (03/2025).**

Google fix: từ Chrome 136, `--remote-debugging-port` và `--remote-debugging-pipe` **bị bỏ qua** nếu `--user-data-dir` không trỏ đến **non-default** directory. Nếu trỏ đến User Data thật → port không mở.
Workaround duy nhất: dùng custom data dir → fresh profile → user phải re-login → defeat purpose.

| Yếu tố | Chi tiết |
|---|---|
| Decrypt v20? | N/A — CDP trả cookie đã decrypt bởi Chrome process. Nhưng Chrome 136+ block. |
| Admin | Không |
| Kill Chrome user | **Có** — phải `taskkill /F /IM chrome.exe`, rất hostile UX |
| Code phức tạp | Trung bình (~50 dòng với `websocket-client`) |
| AV risk | Trung bình — process arg `--remote-debugging-port` được EDR watch (SpecterOps công khai documented từ 2022). |
| Tình trạng 2026 | **Broken cho default profile** |

Comment trên gist (cập nhật 11/2025): "It doesn't work anymore."

Có hack hostile hơn: thay shortcut chrome.exe của user để lần next họ mở Chrome đã có flag → vẫn cần re-login vì user-data-dir khác. Đã vào territory malware, không phù hợp project này.

**Conclusion:** Không xài.

---

### Method 3 — COM `IElevator` từ Python (`comtypes`)

**Ý tưởng:** Gọi trực tiếp `IElevator::DecryptData()` của `elevation_service.exe`, pass blob `app_bound_encrypted_key`, nhận lại 32-byte AES key, sau đó AES-256-GCM decrypt từng cookie value trong SQLite.

**Verdict: WORK nhưng cần admin và bị EDR flag.**

CLSID/IID (Chrome stable):
- `CLSID_ELEVATOR = {708860E0-F641-4611-8895-7D867DD3675B}`
- `IID_IELEVATOR = {463ABECF-410D-407F-8AF5-0DF35A005CC8}`

Path validation: process gọi phải ở `C:\Program Files\Google\Chrome\Application\` → cách phổ biến là copy script (hoặc Python interpreter) vào đó (cần admin write), hoặc inject DLL vào running chrome.exe.

POC khung Python (chỉ structure — chưa bao gồm full COM type-library binding):

```python
import comtypes.client, base64, json, os, sqlite3, shutil
from pathlib import Path
from Crypto.Cipher import AES  # pycryptodome

CLSID_ELEVATOR = "{708860E0-F641-4611-8895-7D867DD3675B}"
IID_IELEVATOR  = "{463ABECF-410D-407F-8AF5-0DF35A005CC8}"

# Step 1: Read Local State
local_state = json.loads(
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"))
    .read_text(encoding="utf-8")
)
abe_blob = base64.b64decode(local_state["os_crypt"]["app_bound_encrypted_key"])
assert abe_blob[:4] == b"APPB"
abe_blob = abe_blob[4:]

# Step 2: Call IElevator (script must be running from Chrome install dir!)
elevator = comtypes.client.CreateObject(CLSID_ELEVATOR)
plaintext_key, last_error = elevator.DecryptData(abe_blob, "")  # returns 32-byte key
master_key = bytes(plaintext_key)

# Step 3: Decrypt cookie values from SQLite
db = Path(os.path.expandvars(
    r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"
))
shutil.copy(db, "Cookies.tmp")  # avoid SQLite lock from running Chrome
con = sqlite3.connect("Cookies.tmp")
for host, name, value, enc in con.execute(
    "SELECT host_key, name, value, encrypted_value FROM cookies"
):
    if enc[:3] != b"v20":
        continue
    nonce, ct, tag = enc[3:15], enc[15:-16], enc[-16:]
    plain = AES.new(master_key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ct, tag)
    # plain has 32-byte SHA256(host) prefix + actual cookie value
    cookie_value = plain[32:].decode("utf-8", errors="ignore")
    print(host, name, cookie_value)
```

| Yếu tố | Chi tiết |
|---|---|
| Decrypt v20? | **Có**, đến Chrome 143 (Chrome 144 đổi sang `IElevator2` Mojo IPC — sẽ phải migrate) |
| Admin | **Có** — để copy script vào `Program Files\Google\Chrome\Application\` HOẶC để inject |
| Kill Chrome user | Không bắt buộc (Chrome có thể vẫn mở; chỉ cần copy `Cookies` SQLite ra temp) |
| Code phức tạp | **Cao** — định nghĩa COM interface, type lib introspection, AES-GCM, SQLite parsing |
| AV risk | **Cao** — EDR sinh DPAPI audit events 4692/4693, watch process từ Chrome dir |
| Maintenance | Phải theo dõi Chrome ABE updates (133, 137, 144 đều đổi format) |

**Conclusion:** Chỉ dùng nếu BẮT BUỘC lấy session từ Chrome đang chạy của user mà không thể re-login, và user accept admin prompt.

---

### Method 4 — Open-source bypass tools

#### 4a. `xaitax/Chrome-App-Bound-Encryption-Decryption`
- **Latest release v0.20.0 (05/02/2026)**, đang maintain rất tích cực.
- C++ binary, **no admin** required từ v0.5+ — dùng Direct Syscall + Reflective Process Hollowing để inject vào Chrome process (auto-spawn Chrome nếu chưa chạy).
- Output JSON: `cookies.json`, `passwords.json`, `payments.json`, `iban.json`.
- **Không có Python wrapper**. Tích hợp = `subprocess.run(["chromelevator.exe", "all"])` rồi parse JSON.
- Hỗ trợ Chrome / Edge / Brave / Avast.
- **AV risk: Rất cao** — Direct syscalls + reflective hollowing là malware-grade technique; Defender + nhiều EDR sẽ flag binary này. Phải user disable AV hoặc add exclusion.

#### 4b. `runassu/chrome_v20_decryption`
- Pure Python PoC, last meaningful update **23/10/2024 cho Chrome 130**.
- **Cần admin + SYSTEM** (dùng `pypsexec.Client` để chạy as SYSTEM) để unwrap lớp DPAPI ngoài rồi unwrap lớp user DPAPI.
- Không dùng COM — reimplement toàn bộ chuỗi DPAPI + hardcoded key extract từ `elevation_service.exe`.
- Issue #2: fail trên Chrome ≥134 vì format byte đầu thay đổi.
- Vẫn là reference tốt để học flow ABE.

#### 4c. `thewh1teagle` gist `d0bbc6bc678812e39cba74e1d407e5c7`
- Pure Python, last update **23/10/2024**.
- Cần `pywin32`, `pycryptodome`, `pypsexec`. Logic giống runassu, gọn hơn.
- Verified với Chrome 130.0.6723.70.
- Cần admin/SYSTEM (qua psexec).

#### 4d. `oma68s/chrome-app-bound-encryption-decryption` & forks
- Fork-style, claim "no admin user mode" — mượn kỹ thuật DLL inject của xaitax.

| Tool | Lang | No-Admin | Kill Chrome | AV Flag | 2026 Status |
|---|---|---|---|---|---|
| xaitax | C++ exe | Yes | Auto-handle | High | **Maintained** |
| runassu | Python | No (SYSTEM) | No | High | Stale (Chrome 130) |
| thewh1teagle gist | Python | No (SYSTEM) | No | High | Stale (Chrome 130) |

**Conclusion:** Nếu chấp nhận ship `chromelevator.exe` kèm theo Python tool và user disable AV, đây là path "không cần re-login" tốt nhất 2026. Nhưng cho project này nó overkill.

---

### Method 5 — Playwright fresh profile + one-time login + `storage_state` ✅

**Ý tưởng:** Lần đầu chạy, mở Playwright Chromium **headed** (visible), user đăng nhập perplexity.ai trong cửa sổ đó, gọi `context.storage_state(path="state.json")`. Lần sau chạy load lại file JSON đó. Tuyệt đối không đụng vào Chrome browser của user.

**Tại sao đây là answer cho project này:**

1. **Né ABE 100%** — không đọc/copy/decrypt anything từ Chrome.
2. **No admin, no kill, no AV flag, no platform-specific code.**
3. Playwright đã có sẵn trong deps.
4. `storage_state` JSON portable, dễ refresh khi session expire.
5. Cloudflare/perplexity reject **headless** Playwright nhưng OK với **headed first-launch**. Sau khi có cookies, các call API trực tiếp (httpx + cookies) hoặc Playwright headed-with-state đều pass.

POC working code:

```python
# perplexity_login.py
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

STATE_FILE = Path("perplexity_state.json")

async def login_once():
    """Run this ONCE. User logs in manually inside the opened browser."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await page.goto("https://www.perplexity.ai/")
        print("[*] Log in manually then press Enter in this terminal...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await ctx.storage_state(path=str(STATE_FILE))
        print(f"[+] Saved {STATE_FILE}")
        await browser.close()


async def use_session():
    """Subsequent runs: replay state, no UI."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # still headed for Cloudflare
        ctx = await browser.new_context(storage_state=str(STATE_FILE))
        page = await ctx.new_page()
        await page.goto("https://www.perplexity.ai/api/auth/session")
        print(await page.content())
        await browser.close()


if __name__ == "__main__":
    if not STATE_FILE.exists():
        asyncio.run(login_once())
    asyncio.run(use_session())
```

| Yếu tố | Chi tiết |
|---|---|
| Decrypt v20? | N/A — không cần |
| Admin | Không |
| Kill Chrome user | Không |
| Code phức tạp | **Rất thấp** (~30 dòng) |
| AV risk | None |
| One-time manual step | Login 1 lần đầu (không phải paste cookie) |
| Tương lai-proof | Có — Playwright API ổn định |

**Caveats:**
- Nếu perplexity.ai dùng Cloudflare turnstile → headless có thể fail; giữ headed cho cả `use_session()`.
- Session expire định kỳ (Perplexity ~30 ngày). Khi expire, xoá `state.json` → re-run `login_once()`.
- Nếu cần extract cookies từ state.json để feed cho `httpx`/`requests` → chỉ cần parse `state["cookies"]`, mỗi entry có `name`, `value`, `domain`, `path`...

---

## 3. Decision Matrix cho project này

| Use case | Method nên dùng |
|---|---|
| User chấp nhận login 1 lần trong Playwright window | **Method 5** ✅ (DEFAULT) |
| User KHÔNG muốn login, có Chrome đang open & là admin | Method 3 (COM IElevator) |
| User KHÔNG muốn login, không phải admin | Method 4a (ship `chromelevator.exe`, AV exclusion) |
| Chrome ≤126 (legacy v10) | rookiepy / pycookiecheat vẫn chạy |

**Recommendation: implement Method 5 ngay, để Method 3 làm optional fallback nếu user request nâng cao.** Không bao giờ ship Method 4a tự động — đó là decision của user.

---

## 4. Test plan

1. Implement `perplexity_login.py` ở trên trong `tools/` của project.
2. Lần 1: chạy → browser mở → login Perplexity → Enter → kiểm tra `perplexity_state.json` xuất hiện và contains cookie `__Secure-next-auth.session-token` (hoặc tương tự).
3. Lần 2: chạy → browser mở (headed) → tự động vào `/api/auth/session` → trả JSON có `user.email` của user.
4. Test refresh: xoá file → re-login flow.
5. Test convert state.json → httpx Cookie jar:
   ```python
   import json, httpx
   state = json.loads(open("perplexity_state.json").read())
   jar = httpx.Cookies()
   for c in state["cookies"]:
       jar.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
   r = httpx.get("https://www.perplexity.ai/api/auth/session", cookies=jar)
   assert r.status_code == 200
   ```

---

## 5. References (chính, ≥ 8)

1. **xaitax/Chrome-App-Bound-Encryption-Decryption** — flagship bypass tool, v0.20.0 02/2026: <https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption>
2. **runassu/chrome_v20_decryption** — Python PoC, reference cho ABE decryption flow: <https://github.com/runassu/chrome_v20_decryption>
3. **thewh1teagle gist — v20 cookie decrypt Python (DPAPI route)**: <https://gist.github.com/thewh1teagle/d0bbc6bc678812e39cba74e1d407e5c7>
4. **thewh1teagle gist — Remote Debugging route (đã chết Chrome 136)**: <https://gist.github.com/thewh1teagle/359675c2f5ea4920949448ec705f9fb2>
5. **Google Chrome blog — `--remote-debugging-port` security change Chrome 136**: <https://developer.chrome.com/blog/remote-debugging-port>
6. **CyberArk C4 Bomb — Blowing Up Chrome's AppBound Cookie Encryption**: <https://www.cyberark.com/resources/threat-research-blog/c4-bomb-blowing-up-chromes-appbound-cookie-encryption>
7. **Elastic Security Labs — Katz and Mouse Game (MaaS infostealers vs ABE)**: <https://www.elastic.co/security-labs/katz-and-mouse-game>
8. **SpecterOps — Hands in the Cookie Jar (CDP cookie dumping)**: <https://posts.specterops.io/hands-in-the-cookie-jar-dumping-cookies-with-chromiums-remote-debugger-port-34c4f468844e>
9. **Alexander Hagenah (xaitax) — Decrypting Edge's App-Bound Encryption (COM type-lib introspection in Python)**: <https://medium.com/@xaitax/the-curious-case-of-the-cantankerous-com-decrypting-microsoft-edges-app-bound-encryption-266cc52bc417>
10. **DeepWiki — ABE COM Servers & Interfaces**: <https://deepwiki.com/xaitax/Chrome-App-Bound-Encryption-Decryption/6.1-abe-com-servers>
11. **Red Canary — Stealers evolve to bypass Chrome's app-bound encryption**: <https://redcanary.com/blog/threat-intelligence/google-chrome-app-bound-encryption/>
12. **Bleeping Computer — New tool bypasses Google Chrome's new cookie encryption system**: <https://www.bleepingcomputer.com/news/security/new-tool-bypasses-google-chromes-new-cookie-encryption-system/>
13. **Playwright issue #36139 — `storage_state` and persistent context behavior**: <https://github.com/microsoft/playwright/issues/36139>
14. **Playwright issue #35836 — `launchPersistentContext` and existing Chrome profiles**: <https://github.com/microsoft/playwright/issues/35836>
15. **Justin Bui (slyd0g) — Debugging Cookie Dumping Failures with Chromium's Remote Debugger**: <https://slyd0g.medium.com/debugging-cookie-dumping-failures-with-chromiums-remote-debugger-8a4c4d19429f>
16. **AlterLab — Playwright Anti-Bot Detection: What Works (2026)**: <https://alterlab.io/blog/playwright-bot-detection-what-actually-works-in-2026>

---

## 6. Open questions / cần verify thêm

- Cookie name chính xác Perplexity dùng cho session-token (test thực tế trong `state.json`).
- Cloudflare turnstile reaction với Playwright headed launched từ stock Chromium — nếu fail, xét `playwright-stealth` hoặc undetected-chromedriver alt.
- Chrome 144 đổi sang `IElevator2` (Mojo IPC) — chưa thấy public PoC Python; nếu lock-in Method 3 cần monitor.
