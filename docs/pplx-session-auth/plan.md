# Plan — Perplexity per-account session cookie (2026-11-11)

Problem: onboard reports Perplexity "not signed in" although Chrome is logged in.

1. Probe live: cookie names in Chrome + whether `x-pplx-account` is required → research.md. DONE
2. Tests first (tests/test_cookies.py, tests/test_client.py): new cookie accepted, preferred over
   legacy next-auth, last-active account picked, header sent / not sent. → verify: they fail.
3. Code: config.py constants · cookies.py `_pplx_session_cookie_name`, `normalize_cookies`,
   `_has_perplexity_session`, `pplx_account_id` · client.py header in `_create_session`.
   → verify: full suite green.
4. Live: onboard-style harvest of the signed-in profile + one real `perplexity_ask` via the client.
5. Review (code-reviewer + security-reviewer), then commit gate.
