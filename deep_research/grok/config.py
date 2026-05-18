"""Grok.com endpoints, headers, and mode IDs."""

from pathlib import Path


GROK_BASE = "https://grok.com"
CONVERSATIONS_NEW = f"{GROK_BASE}/rest/app-chat/conversations/new"
ADD_RESPONSE_TMPL = f"{GROK_BASE}/rest/app-chat/conversations/{{conversation_id}}/responses"
LIST_MODELS = f"{GROK_BASE}/rest/models"
LIST_MODES = f"{GROK_BASE}/rest/modes"

# Mode IDs (verified 2026-05-11 via /rest/modes)
MODE_AUTO = "auto"
MODE_FAST = "fast"
MODE_EXPERT = "expert"
MODE_HEAVY = "heavy"
MODE_GROK_4_3_BETA = "grok-420-computer-use-sa"  # UI: "Grok 4.3 (beta)"

VALID_MODES = {MODE_AUTO, MODE_FAST, MODE_EXPERT, MODE_HEAVY, MODE_GROK_4_3_BETA}

# Default model — server picks the right one based on user tier
DEFAULT_MODEL_NAME = None  # let server decide

# rnet emulation target — must match the Chrome major that CloakBrowser's
# binary reports via ``navigator.userAgent``. CloakBrowser 0.3.28 ships
# Chromium 146 (per the README), but the wrapper spoofs ``Chrome/145.0.0.0``
# in the UA — and ``cf_clearance`` is bound to that exact UA + the TLS
# fingerprint of the binary's BoringSSL build. Use rnet's Chrome145
# emulation so the replayed TLS handshake matches what Cloudflare expects.
IMPERSONATE_TARGET = "Chrome145"

# Cloak's actual emitted UA — see ``ua_test`` script in docs/grok-cloakbrowser/exp.md.
# Pinned to Chrome 145 because cf_clearance is UA-bound (any 145↔146 drift
# triggers the "Just a moment..." interstitial on replay).
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

SEC_CH_UA = '"Not.A;Brand";v="99", "Chrome";v="145", "Chromium";v="145"'

# Where we cache the captured x-statsig-id (path+method bound, deterministic)
def get_state_dir() -> Path:
    p = Path.home() / ".cache" / "grok-search"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_statsig_cache_path() -> Path:
    return get_state_dir() / "statsig_id.json"


# Stream timeout
STREAM_TIMEOUT_SECS = 180

# Default deviceEnvInfo block (what the UI sends; harmless static values)
DEFAULT_DEVICE_ENV = {
    "darkModeEnabled": False,
    "devicePixelRatio": 1,
    "screenWidth": 1280,
    "screenHeight": 720,
    "viewportWidth": 1280,
    "viewportHeight": 720,
}
