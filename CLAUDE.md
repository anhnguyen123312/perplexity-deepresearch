# Perplexity Deep Research

## Test Commands

### Linux / macOS
```bash
# All tests (must use venv)
source .venv/bin/activate && python -m pytest tests/ -v

# Specific file
source .venv/bin/activate && python -m pytest tests/test_browser_control.py -v

# With coverage
source .venv/bin/activate && python -m pytest tests/ --cov=perplexity_deep_research --cov-report=term-missing
```

### Windows (PowerShell)
```powershell
# All tests
.\.venv\Scripts\Activate.ps1; python -m pytest tests/ -v

# Specific file
.\.venv\Scripts\Activate.ps1; python -m pytest tests/test_browser_control.py -v

# With coverage
.\.venv\Scripts\Activate.ps1; python -m pytest tests/ --cov=perplexity_deep_research --cov-report=term-missing
```

## Project Structure

- `perplexity_deep_research/` — Main package (MCP server, API client, cookie extraction, browser control)
- `tests/` — Test suite (all mocked — no real Chrome/API needed)
- `setup_cookies.py` / `setup_cookies.bat` — Windows-only interactive cookie setup
- `perplexity_deep_research/win_cookie_helper.py` — Elevated (UAC) helper for Windows v20 cookie decryption

Cross-platform: macOS (AppleScript / Keychain) · Linux (pgrep/pkill / Secret Service) · Windows (tasklist/taskkill / DPAPI via rookiepy)

## Development

- Python 3.12+ required
- Virtual env at `.venv/`
- Install (POSIX): `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Install (Windows): `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"`
