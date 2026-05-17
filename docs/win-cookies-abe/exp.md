# Empirical Test — Chrome v20 ABE on Windows

## Setup
- Host: `DESKTOP-GUDV5VP` (user `midds`)
- Chrome version: 130+ (v20 ABE)
- 4 profiles: Default, Profile 1, Profile 2, Profile 3 — only Default signed in to perplexity.ai/grok.com
- Repo: `c84ebe5` (v0.4.0)

## Test 1 — rookiepy direct
```
rookiepy.chrome(domains=["perplexity.ai"])
→ RuntimeError: decrypt_encrypted_value failed at rookie-rs/src/browser/chromium.rs:201:3
```
Confirmed v20 ABE blocks rookiepy regardless of admin.

## Test 2 — Real chrome.exe + copy User Data + CDP
- Hypothesis: Real `C:\Program Files\Google\Chrome\Application\chrome.exe` passes elevation_service path validation. Copy User Data → non-default user-data-dir bypasses Chrome 136+ CDP block.
- Result:
  - ✅ Chrome 136+ DOES allow `--remote-debugging-port` on copied user-data-dir
  - ✅ CDP connection works (after `--remote-allow-origins=*`)
  - ✅ SQLite copy contains 1597 cookies (35 perplexity/grok), all `v20` prefix
  - ❌ **Chrome decrypts ZERO of them** when launched with `--user-data-dir=<copy>`
  - Only fresh `__cf_bm` cookie set during navigation appears

**Conclusion:** `app_bound_encrypted_key` in Local State is bound to the ORIGINAL user-data-dir path string at unwrap time. Same machine + same user account + same chrome.exe binary → still fails because dir path differs. Method 1 / Method 2 from research are dead for v20.

## Test 3 — File lock with --kill-chrome
- `Default/Cookies` (legacy path) → not locked, copies via shutil.copy2
- `Default/Network/Cookies` (active path) → exclusive lock, requires `taskkill /F` + sleep before copy
- After kill+/F, file becomes copyable but WAL data may be lost if Chrome was mid-write
- After Chrome stable-dead, scan_profiles.py confirmed Default/Network/Cookies has 1597 valid v20 rows

## Decision after empirical test
- Method 1 (copy User Data) → DEAD (v20 path-bind)
- Method 2 (CDP on default profile) → DEAD (Chrome 136 block, can't bypass with copy because of #1)
- Method 3 (COM IElevator) → Works but admin + AV-flag, fragile across Chrome versions
- **Method 5 (Playwright + storage_state + one-time login) → only sustainable path**

## Restored State
- User's Chrome was killed during testing — must relaunch normally on the Windows machine
- Temp dir `C:\Users\midds\AppData\Local\Temp\pdr-chrome-copy` cleaned up
- User Data NOT modified (we only READ the original profile, copied to temp)
