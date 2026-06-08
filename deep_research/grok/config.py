"""Grok.com endpoints, headers, and mode IDs."""

import os
import re
from pathlib import Path

from .. import cloak


def grok_proxy_url() -> str | None:
    """Outbound proxy for grok traffic (env ``GROK_PROXY``), or None.

    Cloudflare hard-blocks datacenter server IPs for grok.com, but CloakBrowser
    can still solve the JS challenge through a proxy (verified via Oxylabs DC).
    Set ``GROK_PROXY=http://user:pass@host:port`` so BOTH the rnet hot path and
    the CloakBrowser capture exit through the SAME IP — the earned cf_clearance
    is IP-bound, so they must match. Required to run grok-web on a datacenter host.
    """
    return os.environ.get("GROK_PROXY") or None


def grok_proxy_playwright() -> dict | None:
    """``GROK_PROXY`` as a Playwright/CloakBrowser ``proxy=`` dict, or None."""
    url = grok_proxy_url()
    if not url:
        return None
    m = re.match(r"https?://(?:([^:@]+):([^@]+)@)?([^:/]+):(\d+)", url)
    if not m:
        return None
    user, pw, host, port = m.groups()
    cfg: dict = {"server": f"http://{host}:{port}"}
    if user:
        cfg["username"], cfg["password"] = user, pw
    return cfg


GROK_BASE = "https://grok.com"
CONVERSATIONS_NEW = f"{GROK_BASE}/rest/app-chat/conversations/new"
ADD_RESPONSE_TMPL = f"{GROK_BASE}/rest/app-chat/conversations/{{conversation_id}}/responses"
LIST_MODELS = f"{GROK_BASE}/rest/models"
LIST_MODES = f"{GROK_BASE}/rest/modes"

# Mode IDs. auto/fast/expert verified working 2026-06-09 (live grok.com web).
MODE_AUTO = "auto"
MODE_FAST = "fast"
MODE_EXPERT = "expert"
# "heavy" is TIER-GATED: it needs a SuperGrok Heavy subscription. On lower tiers
# grok.com returns 403 {"code":7,"message":"Model is not found"}. Kept in
# VALID_MODES so Heavy-tier accounts can use it; lower tiers surface the 403.
MODE_HEAVY = "heavy"
# UI "Grok 4.3 (beta)" modeId "grok-420-computer-use-sa" was RETIRED by grok.com
# (~2026-06: the chat endpoint returns 403 {"code":7,"message":"Model is not found"}).
# "auto" lets the server pick the best model for the account tier (Grok 4.x for
# SuperGrok) — the closest stand-in. Kept as an alias so callers/imports survive.
MODE_GROK_4_3_BETA = "auto"

VALID_MODES = {MODE_AUTO, MODE_FAST, MODE_EXPERT, MODE_HEAVY}

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
