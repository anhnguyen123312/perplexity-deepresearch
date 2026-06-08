"""Grok.com endpoints, headers, and mode IDs."""

from pathlib import Path

from .. import cloak


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

# The grok hot path replays a ``cf_clearance`` that CloakBrowser earned, so the
# impersonation must follow CloakBrowser's *bundled Chromium* major — NOT the
# user's local Chrome. ``cf_clearance`` is bound to the exact UA + TLS that
# solved the challenge; even a 1-major drift triggers the "Just a moment..."
# interstitial on replay. ``cloak.grok_major()`` reads the binary version at
# runtime (falling back to 145) so this self-corrects when CloakBrowser updates.
GROK_MAJOR = cloak.grok_major()
IMPERSONATE_TARGET = f"Chrome{GROK_MAJOR}"
CHROME_UA = cloak.build_ua(GROK_MAJOR)
SEC_CH_UA = cloak.build_sec_ch_ua(GROK_MAJOR)

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
