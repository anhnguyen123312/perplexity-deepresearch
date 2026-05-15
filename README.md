# Perplexity Deep Research MCP Server

> Bring Perplexity AI's deep research capabilities to Claude Desktop

A powerful MCP server that provides automated browser-based cookie extraction for Perplexity AI, enabling deep research, pro-mode search, and more directly within Claude Desktop.

## 🚀 Quick Start

### Installation

```bash
pip install git+https://github.com/anhnguyen123312/perplexity-deepresearch.git
```

### Claude Desktop Setup

Add to your Claude Desktop config:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "perplexity": {
      "command": "deep-research"
    }
  }
}
```

Restart Claude Desktop. Done!

## 📖 Usage

### In Claude Desktop

**Deep Research** - Comprehensive multi-step research
```
Use deep_research to find: "What are the latest advances in quantum computing?"
```

**Ask** - Pro mode with citations
```
Use ask to explain: "How does machine learning work?"
```

**Search** - Quick answers
```
Use search for: "Python asyncio tutorial"
```

**Follow Up** - Continue conversation
```
Use follow_up to ask: "Tell me more about that"
```

## 🔐 Permissions (Automatic)

**No manual setup required!** The app handles everything through guided prompts. On first use:

### macOS
1. **Full Disk Access** - A dialog will guide you to System Settings to allow reading Chrome's cookie database.
2. **Keychain Password** - A secure macOS prompt will ask for your password to decrypt the cookies.

### Linux
1. **Cookie file access** - Chrome cookies are read from `~/.config/google-chrome/` or `~/.config/chromium/`.
2. **Secret Service** - Cookie decryption uses D-Bus Secret Service (GNOME Keyring / KWallet). Ensure your keyring is unlocked.

### Windows
Chrome 127+ on Windows uses **App-Bound Encryption** (v20 cookies) which blocks
direct decryption from outside Chrome. Two paths are supported:

1. **One-shot interactive setup (recommended)**:
   ```powershell
   python setup_cookies.py
   ```
   Paste the `__Secure-next-auth.session-token` value from Chrome DevTools →
   Application → Cookies. The cookie is saved to
   `%LOCALAPPDATA%\perplexity-deep-research\cookies.json` and reused for 24h.

2. **Elevated extraction via rookiepy** (requires admin + `pip install rookiepy`):
   ```cmd
   setup_cookies.bat
   ```
   Right-click → "Run as administrator". Closes Chrome, extracts the
   session cookie via `rookiepy`, then reopens Chrome.

Just follow the on-screen instructions - no complex manual configuration needed.

## ✨ Features

- 🔄 **Auto-refresh**: Automatically refreshes expired cookies on 401/403 errors.
- 🔒 **Secure Integration**: Uses macOS Keychain or Linux Secret Service for secure cookie decryption.
- 🚀 **4 Research Tools**: Access `deep_research`, `ask`, `search`, and `follow_up`.
- 💾 **Smart Caching**: 24-hour cookie caching for faster performance.
- 🎯 **Chrome Impersonation**: Uses TLS fingerprinting to match your browser.

## 📋 Requirements

- **macOS**, **Linux** (Kali, Ubuntu, Debian, etc.), or **Windows 10/11**
- **Python 3.12+**
- **Google Chrome** or **Chromium**
- **Perplexity.ai account** (logged in Chrome/Chromium)

### Linux-specific requirements

- `secretstorage` (installed automatically) for GNOME Keyring / D-Bus Secret Service
- Chrome/Chromium installed via standard package manager

### Windows-specific requirements

- `rookiepy` and `pywin32` (installed automatically via `pyproject.toml`)
- Chrome 127+ uses App-Bound Encryption — see the **Windows** section under
  Permissions for the supported setup paths.

## 🗄️ Config store

Cookies for **perplexity** and **grok** are stored together in a single
versioned `config.json`. One entry is kept per Chrome profile so multi-account
setups fall back across signed-in profiles without re-scanning.

**Location**
- POSIX: `~/.local/share/perplexity-deep-research/config.json`
- Windows: `%LOCALAPPDATA%\perplexity-deep-research\config.json`
- Override: `PERPLEXITY_CONFIG_FILE=/path/to/config.json`

**Layout**
```json
{
  "version": 1,
  "providers": {
    "perplexity": {
      "expire_seconds": 86400,
      "profiles": {
        "Default": {
          "cookies": {"session_token": "…", "csrf_token": "…"},
          "extracted_at": "2026-05-11T23:48:00+00:00",
          "expires_at":   "2026-05-12T23:48:00+00:00"
        }
      }
    },
    "grok": { "expire_seconds": 43200, "profiles": { … } }
  }
}
```

Defaults: perplexity 24h, grok 12h. When an entry expires, the next call
re-harvests Chrome and persists every signed-in profile. Legacy `cookies.json`
is auto-migrated on first load (the old file is preserved for rollback).

**CLI** (installed as `deep-research-config`)

```bash
deep-research-config show                       # masked
deep-research-config show --reveal              # full cookie values
deep-research-config export ~/pdr-snapshot.json # for another machine
deep-research-config import ~/pdr-snapshot.json # merge (default)
deep-research-config import ~/pdr-snapshot.json --replace
deep-research-config set-expire perplexity 43200
deep-research-config rescan grok                # force re-harvest
```

Also callable as `python -m deep_research.cli …`.

## 🔧 Troubleshooting

<details>
<summary><b>"Permission denied" when reading cookies</b></summary>

**Cause**: Full Disk Access not granted to the app or terminal.
**Solution**:
1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**.
2. Ensure your terminal or Claude Desktop has access.
3. Restart the application.
</details>

<details>
<summary><b>"Keychain access denied"</b></summary>

**Cause**: Keychain access not granted for "Chrome Safe Storage".
**Solution**:
1. Open **Keychain Access.app**.
2. Search for **"Chrome Safe Storage"**.
3. Right-click → **Get Info** → **Access Control**.
4. Ensure the application is in the allowed list.
</details>

<details>
<summary><b>"Database is locked"</b></summary>

**Cause**: Chrome is running and locking the cookie database.
**Solution**:
- The script will prompt you to close Chrome.
- Alternatively, set `PERPLEXITY_ALLOW_CHROME_QUIT=1` to auto-close.
</details>

<details>
<summary><b>"Authentication failed" or "No session token"</b></summary>

**Solution**:
1. Open Chrome and go to [perplexity.ai](https://www.perplexity.ai).
2. Log out and log back in.
3. Retry the operation.
</details>

## 🛠️ Development

### Project Structure
```
deep-research/
├── deep_research/
│   ├── browser_control.py    # Chrome control
│   ├── cookies.py            # Cookie extraction (shared)
│   ├── onboard.py            # Interactive onboarding CLI
│   ├── server.py             # MCP server (all 3 providers)
│   ├── perplexity/client.py  # Perplexity API client
│   ├── grok/                 # Grok client + statsig
│   └── gemini/               # Gemini Deep Research client
└── tests/                    # Comprehensive test suite
```

### Manual Testing
```bash
# Onboard: pick Chrome profile + Google account, harvest cookies
deep-research-onboard

# Run MCP server manually
deep-research
```

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `PERPLEXITY_CONFIG_FILE` | Unified config.json path (perplexity + grok) | `~/.local/share/.../config.json` (POSIX) · `%LOCALAPPDATA%\perplexity-deep-research\config.json` (Windows) |
| `PERPLEXITY_COOKIES_FILE` | Legacy cookie file path (auto-migrated into config.json) | `~/.local/share/.../cookies.json` (POSIX) · `%LOCALAPPDATA%\perplexity-deep-research\cookies.json` (Windows) |
| `CHROME_PROFILE` | Chrome profile name | `Default` |
| `PERPLEXITY_ALLOW_CHROME_QUIT` | Auto-quit Chrome | `0` |
| `PERPLEXITY_TIMEOUT` | Per-request timeout (s) | `900` |
| `PERPLEXITY_MAX_RETRIES` | 401/403 cookie-refresh retries | `2` |

## 📄 License

MIT
