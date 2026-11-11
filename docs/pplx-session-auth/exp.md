# Exp — pplx session auth fix (2026-11-11)

- Repro on master: `onboard._harvest_perplexity(Profile 19)` → ✗ "profile not signed in" although Chrome is logged in.
- Fix branch: same call → perplexity ✓; client session carries `x-pplx-account`;
  `/rest/user/settings` query_count 2976 (real account); Pro query "17*23" → `391`, model `pplx_pro`.
- Tests: 300 pass before, 306 pass after (6 new: cookie accepted, preferred over stale next-auth,
  last-active account picked, session detection, legacy → no account id, client header).
- Lesson: when a site "logs out" a cookie-auth tool, list cookie NAMES in the profile DB first —
  the cookie was renamed, and the account id moved into a required header.
- Lesson: run scratch scripts with `PYTHONPATH=<worktree>`; the venv's editable install points at the main checkout.
- Not fixed (out of scope): `setup_cookies.py` + README manual flow still tell users to paste
  `__Secure-next-auth.session-token`; pycookiecheat keeps expired cookies, so auto-pick can choose a
  profile whose only session cookie is long expired.
