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

# curl_cffi impersonate target — chrome146 is the highest chrome profile
# shipped by curl_cffi 0.15.0; closest match to the user's installed Chrome 148.
IMPERSONATE_TARGET = "chrome146"

# Match Chrome version on the user's machine; cf_clearance is UA-bound
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

SEC_CH_UA = '"Not.A;Brand";v="99", "Chrome";v="148", "Chromium";v="148"'

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
