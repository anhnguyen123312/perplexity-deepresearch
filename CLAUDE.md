# Perplexity Deep Research

## Test Commands

```bash
# Run all tests (must use venv)
cd /home/kali/perplexity-deepresearch && source .venv/bin/activate && python -m pytest tests/ -v

# Run specific test file
cd /home/kali/perplexity-deepresearch && source .venv/bin/activate && python -m pytest tests/test_browser_control.py -v

# Run with coverage
cd /home/kali/perplexity-deepresearch && source .venv/bin/activate && python -m pytest tests/ --cov=perplexity_deep_research --cov-report=term-missing
```

## Project Structure

- `perplexity_deep_research/` - Main package (MCP server, API client, cookie extraction, browser control)
- `tests/` - Test suite (125 tests, all mocked - no real Chrome/API needed)
- Cross-platform: macOS (AppleScript/Keychain) + Linux (pgrep/pkill/Secret Service)

## Development

- Python 3.12+ required
- Virtual env at `.venv/`
- Install: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
