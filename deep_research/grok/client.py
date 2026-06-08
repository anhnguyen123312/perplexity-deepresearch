"""GrokClient: send a query to grok.com and stream back the answer.

Lightweight pattern (2026-05-18):

- Hot path uses **rnet** (Rust HTTP client on BoringSSL) with
  ``Emulation.Chrome145`` to replay ``cf_clearance`` cookies that
  CloakBrowser earned. BoringSSL matches Cloak's TLS handshake closely
  enough (incl. GREASE ext 17613) for Cloudflare to honour the cookie.
- Browser fires **only** on 401/403: the existing
  :func:`~deep_research.grok.statsig.get_statsig_id` refresh path launches
  CloakBrowser ephemerally, captures a fresh ``x-statsig-id`` AND merges
  freshly-issued ``cf_clearance`` / ``__cf_bm`` into the on-disk config
  store, then exits. The retry then sees the refreshed cookies via
  :func:`~deep_research.grok.cookies.get_grok_cookies_cached`.

curl_cffi (and rnet) cannot replay ``cf_clearance`` issued to a UA other
than ``Chrome/145.0.0.0`` — the cookie is bound to the exact UA + TLS that
solved the challenge. The constants in :mod:`.config` are pinned to match.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from rnet import Emulation
from rnet.blocking import Client as BlockingClient

from .. import cloak
from .config import (
    CHROME_UA,
    CONVERSATIONS_NEW,
    DEFAULT_DEVICE_ENV,
    MODE_GROK_4_3_BETA,
    SEC_CH_UA,
    VALID_MODES,
)
from .cookies import get_grok_cookies_cached, invalidate_grok_cache
from .statsig import get_statsig_id


CHAT_PATH = "/rest/app-chat/conversations/new"


class GrokClient:
    """Synchronous client wrapping grok.com's chat-send endpoint."""

    def __init__(self) -> None:
        self._client: BlockingClient | None = None

    def _ensure_client(self) -> BlockingClient:
        if self._client is None:
            self._client = BlockingClient(
                # rnet TLS target follows CloakBrowser's bundled Chromium major
                # (the browser that earns cf_clearance); nearest-available rnet
                # Emulation, falling back to the pinned Chrome145.
                emulation=cloak.get_rnet_emulation(cloak.grok_major())
                or Emulation.Chrome145,
                user_agent=CHROME_UA,
                cookie_store=True,
            )
        return self._client

    def _drop_client_and_invalidate_cache(self) -> None:
        """Forget the in-memory rnet client and expire stored grok entries.

        Called after a 401/403 so the retry path triggers a fresh
        CloakBrowser capture (which also harvests new cf_clearance /
        __cf_bm into the config store) instead of reusing dead cookies.
        """
        self._client = None
        invalidate_grok_cache()

    def _build_headers(self, statsig_id: str, cookies: dict[str, str]) -> dict[str, str]:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {
            "accept": "*/*",
            "accept-language": "en-US",
            "content-type": "application/json",
            "origin": "https://grok.com",
            "referer": "https://grok.com/",
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": cloak.sec_ch_ua_platform(),
            "x-statsig-id": statsig_id,
            "x-xai-request-id": str(uuid.uuid4()),
            "cookie": cookie_header,
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
            "linkQuery": False,
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

    def _post_chat(
        self,
        client: BlockingClient,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[int, str]:
        """rnet POST returning (status_code, full body text).

        rnet's blocking ``Response.status`` is a ``StatusCode`` that
        stringifies as e.g. ``"200 OK"``. Parse out the integer.
        """
        resp = client.post(
            CONVERSATIONS_NEW,
            headers=headers,
            body=json.dumps(body).encode("utf-8"),
        )
        status_code = int(str(resp.status).split()[0])
        text = resp.text()
        return status_code, text

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

        # First attempt with cached cookies+statsig; on 401/403, refresh once
        # via CloakBrowser (statsig.py + cookie harvest), then retry.
        for attempt in (0, 1):
            # ORDER MATTERS: on a refresh attempt we want the *new* cookies
            # that the CloakBrowser capture path merged into profile_config,
            # so ``get_grok_cookies_cached`` must run AFTER ``get_statsig_id``.
            statsig_id = get_statsig_id(CHAT_PATH, "POST", refresh=(attempt == 1))
            cookies = get_grok_cookies_cached()
            headers = self._build_headers(statsig_id, cookies)
            body = self._build_body(query, mode)
            client = self._ensure_client()

            t0 = time.time()
            try:
                status_code, text = self._post_chat(client, body, headers)
            except Exception as e:
                self._drop_client_and_invalidate_cache()
                return {"error": f"rnet request error: {e}"}

            # A Cloudflare managed-challenge (HTML "Just a moment..." / cf-ray)
            # is NOT grok's JSON anti-bot 403 — it needs a fresh cf_clearance,
            # which the attempt-1 refresh earns by driving CloakBrowser headful.
            # Distinguish it so the surfaced error is actionable.
            if cloak.is_cloudflare_challenge(status_code, {}, text):
                if attempt == 0:
                    self._drop_client_and_invalidate_cache()
                    continue
                return {
                    "error": (
                        "Cloudflare challenge on grok.com that CloakBrowser could "
                        "not clear. Your IP may be flagged — wait a few minutes or "
                        "switch network/proxy."
                    ),
                    "status": status_code,
                }

            if status_code in (401, 403):
                # Either Cloudflare invalidated cf_clearance (cookie expired
                # or fingerprint drifted) or grok L7 anti-bot rejected the
                # statsig-id. Both are fixed by re-running the CloakBrowser
                # capture: it warms a fresh cf_clearance AND records a new
                # x-statsig-id, persisting both to ``profile_config``.
                if attempt == 0:
                    self._drop_client_and_invalidate_cache()
                    continue
                return {
                    "error": f"{status_code} from grok.com: {text[:500]}",
                    "status": status_code,
                }

            if status_code != 200:
                return {
                    "error": f"HTTP {status_code}: {text[:500]}",
                    "status": status_code,
                }

            # 200 — text is the full ndjson stream. Parse line by line.
            answer_parts: list[str] = []
            conversation_id: str | None = None
            response_id: str | None = None
            line_count = 0

            for line in text.splitlines():
                if not line:
                    continue
                line_count += 1
                try:
                    j = json.loads(line)
                except json.JSONDecodeError:
                    continue

                answer_parts.extend(
                    self._walk_tokens(j, include_thinking=include_thinking)
                )
                ids = self._walk_for_keys(j, ("conversationId", "responseId"))
                conversation_id = conversation_id or ids.get("conversationId")
                if response_id is None:
                    rid = ids.get("responseId")
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
