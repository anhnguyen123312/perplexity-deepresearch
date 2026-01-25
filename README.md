# Perplexity Deep Research MCP Server

A Python MCP server that provides automated browser-based cookie extraction for Perplexity AI API access, with 4 research tools.

## Features

- **Automated Cookie Extraction**: Reads cookies directly from Chrome's SQLite database
- **Auto-Refresh**: Automatically refreshes expired cookies on 401/403 errors
- **Chrome Impersonation**: Uses curl_cffi for TLS fingerprinting
- **4 MCP Tools**:
  - `deep_research` - Exhaustive multi-step research (pplx_alpha model)
  - `ask` - Pro mode with citations (pplx_pro model)
  - `search` - Quick basic search (turbo model)
  - `follow_up` - Continue conversation with context

## Prerequisites

### Required

1. **macOS** (v1 supports macOS only)
2. **Google Chrome** installed
3. **Logged into Perplexity.ai** in Chrome
4. **Python 3.12+**

### macOS Permissions (CRITICAL)

#### 1. Full Disk Access

Required for reading Chrome's cookie database.

**Setup:**
1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **+** button
3. Add your terminal app:
   - **Terminal.app**: `/System/Applications/Utilities/Terminal.app`
   - **iTerm2**: `/Applications/iTerm.app`
   - **VS Code Terminal**: `/Applications/Visual Studio Code.app`
4. Toggle the switch to **ON**
5. **Restart your terminal** for changes to take effect

**Verification:**
```bash
ls ~/Library/Application\ Support/Google/Chrome/Default/Cookies
# Should list the file, not "Permission denied"
```

#### 2. Keychain Access

Required for decrypting Chrome's cookie encryption key.

**Setup:**
- macOS will prompt automatically on first run
- Click **Allow** when prompted for "Chrome Safe Storage" access
- If you accidentally denied: Open **Keychain Access.app** → Search "Chrome Safe Storage" → Right-click → Get Info → Access Control → Add your terminal app

## Installation

```bash
# Clone or navigate to project directory
cd /path/to/perplexity-deep-research

# Install dependencies with UV
uv sync

# Verify installation
uv run python -c "from perplexity_deep_research import __version__; print(__version__)"
```

## Usage

### As MCP Server

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "perplexity-deep-research": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/perplexity-deep-research",
        "run",
        "perplexity-deep-research"
      ]
    }
  }
}
```

### Manual Testing

```bash
# Test cookie extraction
uv run python -c "from perplexity_deep_research.cookies import get_cookies; print(get_cookies())"

# Run MCP server
uv run perplexity-deep-research
```

### Available Tools

#### 1. deep_research

Exhaustive multi-step research with detailed citations.

```python
deep_research(
    query="What is quantum computing?",
    sources=["web"],  # optional
    language="en-US"  # optional
)
```

#### 2. ask

Pro mode for high-quality answers.

```python
ask(
    query="Explain machine learning",
    sources=["web"],
    language="en-US"
)
```

#### 3. search

Quick basic search.

```python
search(
    query="Python tutorial",
    sources=["web"],
    language="en-US"
)
```

#### 4. follow_up

Continue a previous conversation.

```python
follow_up(
    query="Tell me more about that",
    backend_uuid="uuid-from-previous-response"
)
```

## How It Works

### Cookie Extraction Flow

1. **Try extraction first**: Attempts to read Chrome's cookie database without prompting
2. **Handle Chrome locking**: If database is locked (Chrome running), prompts user to close Chrome
3. **Extract cookies**: Reads encrypted cookies from SQLite database
4. **Decrypt**: Uses macOS Keychain to decrypt Chrome's encryption key
5. **Cache**: Saves cookies to `~/.local/share/perplexity-deep-research/cookies.json` (24h expiry)
6. **Relaunch**: Automatically relaunches Chrome after extraction

### Cookie Storage

- **Location**: `~/.local/share/perplexity-deep-research/cookies.json`
- **Expiry**: 24 hours
- **Override**: Set `PERPLEXITY_COOKIES_FILE` env var for custom location

### Auto-Refresh

When API returns 401/403:
1. Re-extract cookies from Chrome
2. Recreate session with new cookies
3. Retry request once
4. If still fails, raise `AuthenticationError`

## Troubleshooting

### "Permission denied" when reading cookies

**Cause**: Full Disk Access not granted to terminal app.

**Solution**:
1. Grant Full Disk Access (see Prerequisites above)
2. **Restart your terminal** (critical!)
3. Verify: `ls ~/Library/Application\ Support/Google/Chrome/Default/Cookies`

### "Keychain access denied"

**Cause**: Keychain access not granted for "Chrome Safe Storage".

**Solution**:
1. Open **Keychain Access.app**
2. Search for **"Chrome Safe Storage"**
3. Right-click → **Get Info** → **Access Control**
4. Add your terminal app to the allowed list
5. Retry cookie extraction

### "Database is locked"

**Cause**: Chrome is running and locking the cookie database.

**Solution**:
- **Interactive mode**: Script will prompt to close Chrome
- **Non-interactive mode**: Set `PERPLEXITY_ALLOW_CHROME_QUIT=1` to auto-close
- **Manual**: Close Chrome manually and retry

### "Authentication failed after retry"

**Cause**: Perplexity session expired or invalid.

**Solution**:
1. Open Chrome
2. Go to https://www.perplexity.ai
3. Log out and log back in
4. Retry cookie extraction

### "No session token found"

**Cause**: Not logged into Perplexity in Chrome.

**Solution**:
1. Open Chrome
2. Go to https://www.perplexity.ai
3. Log in with your account
4. Retry cookie extraction

## Development

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=perplexity_deep_research --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_cookies.py -v
```

### Project Structure

```
perplexity-deep-research/
├── perplexity_deep_research/
│   ├── __init__.py
│   ├── browser_control.py  # macOS Chrome control
│   ├── client.py            # Perplexity API client
│   ├── config.py            # Configuration constants
│   ├── cookies.py           # Cookie extraction
│   ├── exceptions.py        # Custom exceptions
│   └── server.py            # MCP server with 4 tools
├── tests/
│   ├── test_browser_control.py
│   ├── test_client.py
│   ├── test_cookies.py
│   ├── test_integration.py
│   └── test_server.py
├── pyproject.toml
└── README.md
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PERPLEXITY_COOKIES_FILE` | Custom cookie file path | `~/.local/share/perplexity-deep-research/cookies.json` |
| `CHROME_PROFILE` | Chrome profile name | `Default` |
| `PERPLEXITY_ALLOW_CHROME_QUIT` | Auto-quit Chrome without prompt | `0` (disabled) |

## Limitations (v1)

- **macOS only**: Windows/Linux support planned for v2
- **Chrome only**: Firefox/Safari support planned for v2
- **No browser automation**: Reads cookies directly from database
- **Fixed follow_up mode**: Always uses turbo model (auto mode)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## Development Skills

This project follows strict testing and release workflows. See the [OpenCode Skills](https://github.com/anhnguyen123312/opencode-skills) for detailed guidelines:

- **Testing**: Every code change requires full test suite run
- **Coding**: Test-driven development with pre-commit checks
- **Release**: Full verification before any release

### Quick Reference

```bash
# After ANY code change
uv run pytest

# Before commit
uv run ruff format .
uv run ruff check --fix .
uv run mypy perplexity_deep_research
uv run pytest  # ALWAYS LAST

# Before release
uv run pytest --cov --cov-report=term-missing
```
