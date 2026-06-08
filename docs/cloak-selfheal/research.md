# research.md — Cloak self-heal (2026-06-08)

Nguồn: phân tích code + live `perplexity_search` (MCP) + 2 research agent (web 2026) +
`docs/grok-cf-bypass/research.md` cũ. **Không đoán** — mỗi claim có anchor/nguồn.

## 1. Cloudflare cf_clearance bound vào cái gì (2026)
| Signal | Bound | Tolerance |
|---|---|---|
| IP | **cứng** | đổi IP giữa session → block ngay |
| TLS JA3/JA4 + HTTP/2 SETTINGS | **cứng** | lệch → 403/challenge ngay |
| User-Agent | **chặt** | **lệch 1 major → re-challenge** ("Just a moment") |
| `sec-ch-ua` | có | phải khớp UA major |
| `__cf_bm` (cookie kèm) | có | cấp cùng cf_clearance, cần cả hai |

**Failure modes:**
- Bot Management (trả phí): **403 không có trang challenge** (chặn trước qua JA3/JA4 + IP-rep).
- Free managed challenge: **503 + HTML "Just a moment..."**.
- UA/TLS lệch khi replay: 403 hoặc interstitial tùy tier site.
- **Tụt nhiều major = soft degradation**: CF theo dõi JA4 `browser_ratio_1h` (tỉ lệ traffic thật của 1 JA4).
  Fingerprint cũ (chrome145 khi Chrome thật 148) có ratio thấp → **tần suất challenge tăng dần theo thời gian**,
  KHÔNG phải bật/tắt nhị phân. → **đây chính là "hay dính" gián đoạn**.

Nguồn: CF JA3/JA4 docs, blog.cloudflare.com/ja4-signals, roundproxies cf-clearance 2026,
và chính `grok/config.py:27-38` (production-confirmed: "145↔146 drift triggers interstitial").

## 2. INVARIANT VÀNG (quyết định toàn bộ thiết kế)
> **UA + `sec-ch-ua` phải khớp major của TARGET impersonation đã chọn — KHÔNG phải Chrome local.**
> Dùng TLS `chrome146` + UA `Chrome/148` = lệch detectable. "Nearest-lower" target thì AN TOÀN
> (curl_cffi chỉ thêm target mới khi fingerprint đổi).

Hệ quả cho từng provider:
- **Perplexity** (curl_cffi): chọn target = nearest ≤ Chrome local trong tập curl_cffi hỗ trợ
  (148 → `chrome146`). Set UA + sec-ch-ua = **146** (khớp target). → diệt bug 130-vs-146.
- **Grok** (rnet replay cf_clearance do cloakbrowser earn): cf_clearance UA-tight. cloakbrowser binary thật =
  **145** → rnet target + UA **bắt buộc = 145** (đúng hiện trạng, nhưng phải đọc **động** từ
  `cloakbrowser.binary_info()`, không hardcode). Replay cf_clearance-148 bằng rnet-146/147 sẽ re-challenge.
  → muốn lên 148 phải: (a) rnet hỗ trợ 148 **và** (b) issuer browser = 148. Hiện rnet kẹt 145/147.

## 3. Version landscape (đo + web, 2026-06)
- **Chrome local máy = 148.0.7778.215**.
- **curl_cffi 0.15.0**: targets ...`chrome142, chrome145, chrome146`; `impersonate="chrome"`→**chrome146**.
  Nearest-lower an toàn. 148 chưa có (146 là mới nhất).
- **rnet đang cài**: API đời cũ, `Emulation.Chrome*` **max 145**. wreq/rnet **v0.11.0 (Apr 2026)** mới thêm
  **Chrome 146–147**; **Chrome 148 chưa có** (06/2026). → nâng rnet mở được 146/147, vẫn chưa tới 148.
- **cloakbrowser 0.3.28**: binary thật **Chromium 145.0.7632.109.2** (bundled 146 chưa tải).
  `cloakbrowser.CHROMIUM_VERSION="146..."`, `binary_info()['version']="145..."` → **đọc binary_info, không tin hằng số**.

## 4. Predicate phát hiện Cloudflare challenge (thiếu trong code hiện tại)
Ưu tiên (confidence cao→thấp): `cf-mitigated: challenge` (định danh chính thức) > `server: cloudflare`+`cf-ray`
> `503`+CF > `403/429`+CF+non-HTML (Bot Mgmt hard block) > body markers (`__cf_chl`,
`challenges.cloudflare.com`, "Just a moment...", "Enable JavaScript and cookies to continue",
"Checking your browser") > `200`+CF+body<10KB+"cloudflare" in `<title>` (interstitial ẩn).
→ Tách 3 nhánh: **CF-challenge** (browser-solve) vs **auth-expired 401/403** (re-read cookie) vs **429** (backoff).
Nguồn: developers.cloudflare.com/cloudflare-challenges/.../detect-response, http.dev/cf-mitigated.

## 5. Browser-solver SOTA 2026 (earn cf_clearance)
Benchmark 31 target CF (Ian L. Paterson 2026):
| Rank | Tool | Blocked/31 | Headless | Ghi chú |
|---|---|---|---|---|
| 1 | **nodriver** | 0 | **OK** | raw CDP, không có Playwright control-plane (giờ CF detect được shim này); AGPL, asyncio-only |
| 2 | **cloakbrowser** | 2 | 50% headless / **83% headful** | 49 patch C++; API kiểu Playwright; **headless tụt mạnh** |
| 3 | curl_cffi | 2 | n/a | TLS-only, không chạy JS |
- **headless=False (hoặc `"virtual"`/Xvfb trên Linux) vẫn an toàn nhất.** → bug grok `headless=True` phải đổi.
- **patchright** `channel="chrome"` (Chrome 148 thật) mạnh hơn bundled Chromium; có regression sau vài bản.
- **CDP-attach Chrome thật** = zero fingerprint mismatch NHƯNG **Chrome v136+ từ chối `--remote-debugging-port`
  trên default `--user-data-dir`** (hardening). Phải copy profile sang dir khác (đúng hướng
  `tools/test_chrome_copy_cdp.py`) rồi attach. Sau `goto`, đọc cookie qua `Network.getAllCookies`,
  hoặc `page.evaluate(fetch(...))` để TLS+cookie+IP đồng nhất (curl_cffi vẫn 403 vì JA3 per-browser —
  đã ghi ở research cũ gotcha #1). Pitfall: 2 Chrome không share user-data-dir; port 9222 chỉ bind 127.0.0.1.

## 6. Self-heal ladder (chuẩn scraper bền 2026)
1. cached cookie + impersonation aligned (fast).
2. auth 401/403 (không phải CF) → invalidate + re-read cookie DB → retry.
3. **CF challenge** → browser-solve **headful**, harvest cf_clearance/__cf_bm → re-align → retry.
4. CF lặp lại (IP bị flag) → **cooldown** cho CF risk-score decay + exponential backoff, số lần có hạn.
5. **circuit breaker**: K lần CF-fail trong cửa sổ → short-circuit sang cooldown, tránh càng đánh càng bị nghi.
6. cạn nước → lỗi **actionable** ("CF đang challenge IP; đợi N phút / đổi mạng / residential proxy"),
   KHÔNG phải 403 chung chung.
Tham chiếu: FlareSolverr/Byparr, scrapling, botasaurus, cloudscraper-successors; "cooldown để risk decay".

## 7. Kết luận → cơ chế "tự fix"
Ba lớp: **(A) Xoá drift tận gốc** — module `cloak.py` detect Chrome major động + chọn target nearest từ tập
lib **thực có** + dựng UA/sec-ch-ua khớp target (invariant §2). Cache trong config.json, refresh ~daily.
**(B) Detect đúng** — predicate `is_cloudflare_challenge()` dùng chung 2 client. **(C) Ladder + breaker** —
route đúng nhánh, headful solve khi CF, cooldown/backoff, lỗi actionable, lưu breaker state trong config.
→ Triển khai chi tiết trong `plan.md`.
