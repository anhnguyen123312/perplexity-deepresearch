# Exp — dependency upper bounds (2026-11-11)

- Trigger: `uv tool install --force git+…@v0.9.1` re-resolved every dependency (Python 3.14 → 3.15).
  The MCP server then crashed on import: `No module named 'mcp.server.fastmcp'` (mcp 2.x removed
  FastMCP), and Claude Code showed `deep-research` as disconnected.
- Fresh resolve vs the known-good `.venv`:

| package | .venv (good) | fresh resolve | effect |
|---|---|---|---|
| mcp | 1.26.0 | 2.3.0 | server crashes on import |
| curl_cffi | 0.15.0 | 0.17.0 (0.16.3 too) | tests/test_request_parity.py fails: no `priority` header |
| cloakbrowser | 0.3.28 | 0.7.1 | ImportError with playwright 1.65 (`playwright._impl._js_handle`) → Grok statsig capture off; cloak.py swallows it |

- The 2 parity failures another machine reported "on stock v0.9.0" match the curl_cffi ≥0.16 row.
- Fix: `mcp<2`, `curl-cffi<0.16`, `cloakbrowser<0.4`. Fresh install from the branch (Python 3.15, no other
  constraints): mcp 1.30, curl_cffi 0.15.0, cloakbrowser 0.3.32, playwright 1.65; 306 tests pass;
  MCP initialize + 14 tools. A fresh env with the same bounds answered a live perplexity_ask through MCP (pplx_pro).
- Lesson: after reinstalling the tool, probe the MCP server over stdio (initialize + tools/list), not just an import.
- Local recovery: `uv tool install --force --python 3.14 --constraints <uv pip freeze of .venv> git+…@<tag>`.
- Unverified: Grok/Gemini live on playwright 1.65; whether curl_cffi ≥0.16 also drops `priority` on the real
  HTTP/2 wire (the parity test uses a local HTTP/1.1 server).
