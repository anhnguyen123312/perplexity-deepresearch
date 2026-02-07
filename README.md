# Perplexity Deep Research MCP Server

> Bring Perplexity AI's deep research capabilities to Claude Desktop

A powerful MCP server that provides automated browser-based cookie extraction for Perplexity AI, enabling deep research, pro-mode search, and more directly within Claude Desktop.

## 🚀 Quick Start

### Installation

```bash
pip install git+https://github.com/anhnguyen123312/perplexity-deepresearch.git
```

### Claude Desktop Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "perplexity": {
      "command": "perplexity-deep-research"
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

**No manual setup required!** The app handles everything through guided dialogs. On first use:

1. **Full Disk Access** - A dialog will guide you to System Settings to allow reading Chrome's cookie database.
2. **Keychain Password** - A secure macOS prompt will ask for your password to decrypt the cookies.

Just follow the on-screen instructions - no complex manual configuration needed.

## ✨ Features

- 🔄 **Auto-refresh**: Automatically refreshes expired cookies on 401/403 errors.
- 🔒 **Secure Integration**: Uses macOS Keychain for secure cookie decryption.
- 🚀 **4 Research Tools**: Access `deep_research`, `ask`, `search`, and `follow_up`.
- 💾 **Smart Caching**: 24-hour cookie caching for faster performance.
- 🎯 **Chrome Impersonation**: Uses TLS fingerprinting to match your browser.

## 📋 Requirements

- **macOS** (v1 supports macOS only)
- **Python 3.12+**
- **Google Chrome**
- **Perplexity.ai account** (logged in Chrome)

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
perplexity-deep-research/
├── perplexity_deep_research/
│   ├── browser_control.py  # macOS Chrome control
│   ├── client.py            # Perplexity API client
│   ├── cookies.py           # Cookie extraction
│   └── server.py            # MCP server implementation
└── tests/                  # Comprehensive test suite
```

### Manual Testing
```bash
# Test cookie extraction
perplexity-deep-research --test-cookies

# Run MCP server manually
perplexity-deep-research
```

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `PERPLEXITY_COOKIES_FILE` | Custom cookie file path | `~/.local/share/.../cookies.json` |
| `CHROME_PROFILE` | Chrome profile name | `Default` |
| `PERPLEXITY_ALLOW_CHROME_QUIT` | Auto-quit Chrome | `0` |

## 📄 License

MIT
