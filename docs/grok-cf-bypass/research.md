# Grok CF Bypass — Research (2026-05-14)

## STATUS: SOLVED ✅ — Patchright v1.59.1 + Chrome 148 channel

Same flagged IP (1.53.246.225) now passes both nopecha + grok.com:

| Site | Result | Time |
|---|---|---|
| nopecha.com/demo/cloudflare | PASS | 19.6s |
| grok.com | PASS (title='Grok', body shows 'Sign in/Imagine/...') | 7.1s |

Code that works:
```python
from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=udd,
        channel="chrome",       # uses LOCAL Chrome 148 (not bundled Chromium)
        headless=False,
        no_viewport=True,
    )
```

## Why earlier attempts failed

- curl_cffi chrome142 + cf_clearance → 403 (TLS impersonate ≠ Chrome 148 → CF rejects)
- cloakbrowser → Chromium 145 (stuck for macOS arm64) ≠ user's Chrome 148 (version mismatch)
- Real Chrome 148 via plain Playwright → playwright injects `--enable-automation` + `navigator.webdriver` → CF detects
- Camoufox v135 (Firefox C++ patches) → different engine, FF fingerprint dragnet by CF
- Proxy 42.96.3.54 datacenter (AS135918) → CF auto-flags datacenter ASN
- WARP (1.1.1.1) → CF knows own WARP IPs, still challenges

## Why Patchright works where others don't

1. `channel="chrome"` → spawns LOCAL Chrome 148 binary (no version mismatch)
2. Runtime CDP patches → strips `Runtime.enable` / `Page.enable` automation hooks at CDP layer (CDP-Patches lib)
3. Removes Playwright-specific args: `--enable-automation`, `--remote-debugging-pipe` leakage, MojoJS bindings
4. `no_viewport=True` → uses real screen size (no 800x600 leak)
5. Persistent context → cookies/cache accumulate naturally
6. NO custom UA/headers → defaults to real Chrome 148 UA from binary

## Old root cause (now disproven)

Initial diagnosis was "IP flagged" because curl -sI returned `cf-mitigated: challenge` and
all earlier tools failed. But Patchright passes on the same IP — proves the IP gets the
INTERACTIVE challenge (not hard-block), and Patchright's CDP patches make the env look
legitimate enough that CF auto-grants clearance.

CF dùng combo:
1. JA3/JA4 TLS fingerprint
2. IP reputation (decisive khi risky)
3. JS challenge solve
4. cf_clearance signed token

Khi IP-rep cao, CF **buộc** interactive solve (mouse move, click "I am human") —
headless không qua được dù tool perfect.

## Tools comparison (May 2026) — vẫn cần khi IP clean

| Tool | Engine | Status | CF bypass |
|---|---|---|---|
| Camoufox v150 | Firefox C++ patches | active, top-tier | **0% detection** when IP clean |
| Nodriver | Chrome CDP-direct | active | passes where Patchright fails |
| Patchright | Patched playwright | weaker | fixed CDP leaks |
| cloakbrowser | Patched Chromium 145 | stuck ở 145 cho macOS | mismatch w/ local Chrome 148 |
| FlareSolverr | Docker, real Chromium | active | works nhưng chậm |
| curl_cffi | TLS only, chrome142 max | can't solve JS | dùng sau khi solved |
| rnet (Rust) | TLS, chrome137+ | active | sau khi solved |

## Fix options (ranked)

### A. Residential proxy (production grade)
- BrightData / IPRoyal / Smartproxy / Webshare residential pool
- Cost: $3-15/GB
- Route Camoufox/cloakbrowser/curl_cffi qua proxy → clean IP → CF cấp clearance
- **Best long-term solution**

### B. Cooldown + retry (cheap)
- Stop testing 30-60 min, CF risk score decay
- Then retry với patched Chromium / Camoufox

### C. Attach vào Chrome đang chạy của user (zero-cost)
- User's Chrome 148 already has CF trust accumulated (cookies, ML history)
- Quit Chrome, relaunch với `--remote-debugging-port=9222`
- `connect_over_cdp` từ Python, dispatch fetch() từ session đó
- Cookie + IP + fp identical → CF không challenge
- **Cần user restart Chrome**

### D. VPN / different network
- Hotspot mobile / VPN clean IP → giống A nhưng manual

### E. FlareSolverr docker sidecar
- Docker container chạy Chromium auto-solve, proxy returned cookies
- Tốn time/RAM nhưng all-Python integration

## Decision needed

~~Đang chờ user chọn~~ → **Patchright giải quyết, không cần proxy/CDP/FlareSolverr**.

## Next steps

1. Verify `/rest/modes` API call qua Patchright session (in progress)
2. Refactor `deep_research/grok/browser.py`: thay cloakbrowser bằng Patchright + `channel="chrome"`
3. Sync `config.py` IMPERSONATE_TARGET với Chrome 148 nếu giữ curl_cffi (hoặc bỏ hẳn curl_cffi, gọi API qua Patchright page.evaluate)
4. End-to-end test MCP grok_search

## Streaming (2026-05-15) — SSE pattern like perplexity

Production path is now **fully streaming** — NDJSON lines arrive at Python as Grok emits them, mirroring `perplexity client._collect_events` (`response.iter_content` loop).

`GrokBrowser.chat_stream(body, sid, on_line, ...)`:
- JS uses `r.body.getReader()` + `TextDecoder` → splits on `\n` → calls `await window.__grokOnLine(line)` per frame
- Python side installs `page.expose_function("__grokOnLine", self._dispatch_line)` lazily AFTER first navigation
- `GrokClient.search()` accumulates tokens/ids in an `on_line` closure as frames arrive

### Gotchas hit & fixed

1. **curl_cffi STILL gets 403** even after Patchright harvests fresh `cf_clearance` — TLS JA3/JA4 binding is per-browser. Solution: dispatch via `page.evaluate(fetch(...))` so cookies + TLS fingerprint match the browser that just cleared CF.
2. **`page.expose_function` BEFORE `goto()` causes `ERR_NAME_NOT_RESOLVED`** in headless Patchright. Must install AFTER first navigation (set `_line_fn_installed` lazy flag).
3. **headless=True ≠ headless=False for CF** — Patchright's own README says "don't use headless". In headless mode CF managed challenge does NOT auto-clear (page sits on "Just a moment..."), statsig submit times out. Default to `headless=False`; brief visible window per call is the tradeoff for reliability.
4. **Stale persistent profile** can break DNS — clearing `~/.cache/grok-search/chrome-profile/` fixes; cookies are restored via `add_cookies` from config.json.

### Verified timings (post-refactor, headless=False)

- Cold start (no statsig cache): first line @ +6.4s, full answer in 17.5s, 52 stream frames
- Warm start (cached statsig): first line @ +2.5s, full answer in 7.5s, 13 stream frames

## Sources

- https://github.com/daijro/camoufox
- https://github.com/ultrafunkamsterdam/nodriver
- https://github.com/pim97/anti-detect-browser-tools-tech-comparison
- https://scrapfly.io/blog/posts/how-to-bypass-cloudflare-anti-scraping
- https://roundproxies.com/blog/best-patchright-alternatives/
