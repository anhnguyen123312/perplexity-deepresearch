# Research — Perplexity auth moved off next-auth (probed 2026-11-11)

Chrome cookie DB, perplexity.ai, names only (macOS, this machine):
- Profile 19 (signed in now): `__Secure-pplx.session.<account-uuid>` (30-day expiry, set 2026-11-09),
  `__Host-pplx-last-active-account` (value == the same uuid). No `*next-auth.session-token`.
- Profile 6: legacy `__Secure-next-auth.session-token` last set 2026-07-30, `__Secure-pplx.session.<uuid>`
  set 2026-08-11 → the legacy cookie stops being refreshed once the new one exists, but stays in the DB.
- pycookiecheat does NOT filter expired cookies (`chrome.py` query has no expires_utc filter).

Live requests (curl_cffi, same headers/impersonation as the client, cookie = session cookie only):

| request | /api/auth/session | /rest/user/settings |
|---|---|---|
| cookie only | 200, `{}` (anonymous) | 200, query_count 0, tier None |
| cookie + `x-pplx-account: <uuid>` | 200, user present | 200, query_count 2976, subscription active |

Conclusion (CONFIRMED by the table): the session cookie only authenticates together with the
`x-pplx-account` header carrying the uuid from the cookie name.
Probe script: scratchpad `probe_pplx_auth.py` (not committed; prints no secret values).
