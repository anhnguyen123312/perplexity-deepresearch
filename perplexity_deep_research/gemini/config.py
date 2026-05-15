"""gemini.google.com endpoints, headers, and DR-flag indices.

All values verified live on 2026-05-15 against
`https://gemini.google.com/u/{authuser}/app`. See
`docs/gemini-mcp/ref.md` for the full reverse-engineering log.
"""

from __future__ import annotations

from pathlib import Path


GEMINI_BASE = "https://gemini.google.com"


def app_url(authuser: int) -> str:
    """Per-account home URL (also where we scrape SNlM0e + cfb2h)."""
    return f"{GEMINI_BASE}/u/{authuser}/app"


def stream_generate_url(authuser: int) -> str:
    return (
        f"{GEMINI_BASE}/u/{authuser}/_/BardChatUi/data/"
        "assistant.lamda.BardFrontendService/StreamGenerate"
    )


def batch_execute_url(authuser: int) -> str:
    return f"{GEMINI_BASE}/u/{authuser}/_/BardChatUi/data/batchexecute"


# Internal batchexecute rpcids used for stage-3 polling.
# Source: HanaokaYuzu/Gemini-API src/gemini_webapi/constants.py
RPCID_READ_CHAT = "hNvQHb"
RPCID_DR_STATUS = "kwDCne"


# curl_cffi impersonation target (matches user's installed Chrome 148)
IMPERSONATE_TARGET = "chrome146"

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

# Default request locale
DEFAULT_HL = "en"

# Stage-1 (plan) usually returns in <30s. Stage-2 (full research) can take
# 5-15 min, so the streaming read needs a generous timeout.
PLAN_STAGE_TIMEOUT_SECS = 60
RESEARCH_STAGE_TIMEOUT_SECS = 30 * 60   # 30 min hard cap

# Stage-3 polling defaults. Gemini Deep Research typically completes in
# 5-15 min. We poll READ_CHAT every 30s up to a 30-min ceiling.
POLL_INTERVAL_SECS = 30
POLL_TIMEOUT_SECS = 30 * 60

# Inner-array indices that flip Deep Research mode on. See ref.md §3.
DR_FLAG_INDEX_49 = 49
DR_FLAG_INDEX_54 = 54
DR_FLAG_INDEX_55 = 55

# Minimum cookies that signal an authenticated google.com session
GEMINI_AUTH_COOKIES: tuple[str, ...] = ("__Secure-1PSID", "SAPISID")


# Model selection — sets the `x-goog-ext-525001261-jspb` header AND the
# `inner[79]` slot in the StreamGenerate body. Captured live 2026-05-15 on
# Default/u/3 by clicking the model picker and observing the POST.
#
# JSPB header layout (verified):
#   [1, null, null, null, "<model_id>", null, null, 0, [4],
#    null, null, <capacity>, null, null, <rev>, null, "<per-request UUID>"]
# where <rev> ALSO appears as inner[79] in the body.
#
# Pinning model="pro" without also flipping inner[79] to 3 causes the stream
# to abort with BardErrorInfo code 1099 mid-frame.
#
# Default model (Flash, no header) uses inner[79] = 5.
MODELS: dict[str, tuple[str, int, int]] = {
    # "Pro — Giải toán và lập trình nâng cao với 3.1 Pro"
    # → (model_id, capacity, rev)
    "pro": ("e6fa609c3fa255c0", 2, 3),
}

# inner[79] value when no model is overridden (matches captured Flash DR)
DEFAULT_INNER79_REV = 5
