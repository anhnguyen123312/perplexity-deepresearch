"""GrokClient: send a query to grok.com and stream back the answer.

Verified end-to-end (2026-05-11) for both `auto` and `grok-420-computer-use-sa`
(Grok 4.3 beta) modes. See `docs/grok-mcp/research.md` for the full schema and
reverse-engineering notes.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from curl_cffi import requests

from .config import (
    CHROME_UA,
    CONVERSATIONS_NEW,
    DEFAULT_DEVICE_ENV,
    IMPERSONATE_TARGET,
    MODE_GROK_4_3_BETA,
    SEC_CH_UA,
    STREAM_TIMEOUT_SECS,
    VALID_MODES,
)
from .cookies import get_grok_cookies_cached, invalidate_grok_cache
from .statsig import get_statsig_id


CHAT_PATH = "/rest/app-chat/conversations/new"


class GrokClient:
    """Synchronous client wrapping grok.com's chat-send endpoint."""

    def __init__(self) -> None:
        self._sess: requests.Session | None = None
        self._cookies: dict[str, str] | None = None

    def _ensure_session(self) -> requests.Session:
        if self._sess is None:
            self._cookies = get_grok_cookies_cached()
            sess = requests.Session(impersonate=IMPERSONATE_TARGET)
            for k, v in self._cookies.items():
                sess.cookies.set(k, v, domain=".grok.com")
            sess.headers.update({"user-agent": CHROME_UA})
            self._sess = sess
        return self._sess

    def _drop_session_and_invalidate_cache(self) -> None:
        """Forget the in-memory session and expire stored grok entries.

        Called after a 401/403 so the next ``_ensure_session`` triggers a
        fresh Chrome scan + cache save instead of reusing dead cookies.
        """
        self._sess = None
        self._cookies = None
        invalidate_grok_cache()

    def _build_headers(self, statsig_id: str) -> dict[str, str]:
        return {
            "user-agent": CHROME_UA,
            "accept": "*/*",
            "accept-language": "en-US",
            "content-type": "application/json",
            "origin": "https://grok.com",
            "referer": "https://grok.com/",
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "x-statsig-id": statsig_id,
            "x-xai-request-id": str(uuid.uuid4()),
        }

    def _build_body(self, query: str, mode_id: str) -> dict[str, Any]:
        return {
            "temporary": False,
            "message": query,
            "fileAttachments": [],
            "imageAttachments": [],
            "disableSearch": False,
            "enableImageGeneration": True,
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "enableImageStreaming": True,
            "imageGenerationCount": 2,
            "forceConcise": False,
            "enableSideBySide": True,
            "sendFinalMetadata": True,
            "disableTextFollowUps": False,
            "responseMetadata": {},
            "disableMemory": False,
            "forceSideBySide": False,
            "isAsyncChat": False,
            "disableSelfHarmShortCircuit": False,
            "collectionIds": [],
            "disabledConnectorIds": [],
            "deviceEnvInfo": DEFAULT_DEVICE_ENV,
            "modeId": mode_id,
        }

    @staticmethod
    def _walk_tokens(obj: Any, include_thinking: bool = False) -> list[str]:
        """Collect `token` strings from a streamed frame.

        Each grok SSE frame carries a single ``token`` dict like::

            {"token": "...", "isThinking": false, "messageTag": "final", ...}

        When ``isThinking`` is ``True`` (Grok 4.3 beta / Expert / Heavy modes),
        the token belongs to the chain-of-thought / tool-call trace (including
        inline ``<xai:tool_usage_card>`` XML). Those would otherwise be
        concatenated into the final answer and produce garbled output. By
        default we keep only the final-answer tokens (``isThinking == False``);
        pass ``include_thinking=True`` to keep everything (legacy behaviour).
        """
        out: list[str] = []
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                tok = cur.get("token")
                if isinstance(tok, str):
                    if include_thinking or cur.get("isThinking") is not True:
                        out.append(tok)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        return out

    @staticmethod
    def _walk_for_keys(obj: Any, keys: tuple[str, ...]) -> dict[str, Any]:
        """Return the first encountered values for the requested top-level keys."""
        found: dict[str, Any] = {}
        stack = [obj]
        while stack and len(found) < len(keys):
            cur = stack.pop()
            if isinstance(cur, dict):
                for k in keys:
                    if k not in found and k in cur:
                        found[k] = cur[k]
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        return found

    def search(
        self,
        query: str,
        mode: str = MODE_GROK_4_3_BETA,
        include_thinking: bool = False,
    ) -> dict[str, Any]:
        """Send `query` to grok.com using the given mode_id. Returns
        ``{"answer", "conversation_id", "response_id", "mode", "elapsed_secs",
        "stream_lines"}`` on success, or ``{"error": str}`` on failure.

        Thinking/tool-call traces (``isThinking == True``) are stripped from
        the answer by default. Set ``include_thinking=True`` to keep them
        (useful for debugging or for showing the reasoning chain).
        """
        if mode not in VALID_MODES:
            return {
                "error": f"Invalid mode {mode!r}. Valid: {sorted(VALID_MODES)}"
            }

        sess = self._ensure_session()

        # First attempt with cached statsig-id; on 403 anti-bot, refresh once.
        for attempt in (0, 1):
            statsig_id = get_statsig_id(CHAT_PATH, "POST",
                                         refresh=(attempt == 1))
            headers = self._build_headers(statsig_id)
            body = self._build_body(query, mode)

            t0 = time.time()
            r = sess.post(
                CONVERSATIONS_NEW,
                json=body,
                headers=headers,
                timeout=STREAM_TIMEOUT_SECS,
                stream=True,
            )

            if r.status_code == 403:
                # 403 has two causes:
                # 1. Statsig anti-bot — refresh statsig-id and retry.
                # 2. Stale grok cookies — invalidate the config-store entry
                #    so the next call re-scans Chrome.
                err_body = b"".join(r.iter_content()).decode(
                    "utf-8", "replace"
                )
                if attempt == 0 and "anti-bot" in err_body.lower():
                    continue
                self._drop_session_and_invalidate_cache()
                return {
                    "error": f"403 from grok.com: {err_body[:500]}",
                    "status": 403,
                }

            if r.status_code == 401:
                err_body = b"".join(r.iter_content()).decode(
                    "utf-8", "replace"
                )
                self._drop_session_and_invalidate_cache()
                return {
                    "error": f"401 from grok.com: {err_body[:500]}",
                    "status": 401,
                }

            if r.status_code != 200:
                err_body = b"".join(r.iter_content()).decode(
                    "utf-8", "replace"
                )
                return {
                    "error": f"HTTP {r.status_code}: {err_body[:500]}",
                    "status": r.status_code,
                }

            # 200 — consume stream
            answer_parts: list[str] = []
            conversation_id: str | None = None
            response_id: str | None = None
            line_count = 0

            for raw_line in r.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", "replace") \
                    if isinstance(raw_line, bytes) else raw_line
                line_count += 1
                try:
                    j = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Reconstruct answer from token frames
                answer_parts.extend(
                    self._walk_tokens(j, include_thinking=include_thinking)
                )

                # Capture identifiers (first occurrence wins)
                ids = self._walk_for_keys(
                    j, ("conversationId", "responseId")
                )
                conversation_id = conversation_id or ids.get("conversationId")
                if response_id is None:
                    rid = ids.get("responseId")
                    # Skip the userResponse echo; take the assistant's
                    if rid and "userResponse" not in line:
                        response_id = rid

            elapsed = time.time() - t0
            answer = "".join(answer_parts)

            return {
                "answer": answer,
                "conversation_id": conversation_id,
                "response_id": response_id,
                "mode": mode,
                "elapsed_secs": round(elapsed, 2),
                "stream_lines": line_count,
            }

        return {"error": "exhausted retries"}
