"""
Perplexity API client with Chrome impersonation and auto-refresh.

Provides a client for interacting with the Perplexity AI API using curl_cffi
for Chrome impersonation and automatic cookie refresh on authentication errors.
"""

import json
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

from curl_cffi import requests

from .. import cloak, profile_config

import logging
import sys

from ..config import (
    API_VERSION,
    DEFAULT_HEADERS,
    ENDPOINT_AUTH_SESSION,
    ENDPOINT_SSE_ASK,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    SSE_REQUEST_HEADERS,
    SUPPORTED_BLOCK_USE_CASES,
    SUPPORTED_FEATURES,
)


def _local_iana_timezone() -> str:
    """
    Return the local IANA timezone name (e.g. ``Asia/Saigon``).

    Perplexity's server rejects offset-style names like ``+07`` with a generic
    "Error in processing query." failure, so we resolve a real IANA zone via
    ``/etc/localtime`` or the ``TZ`` env var. Falls back to ``UTC`` only as a
    last resort.
    """
    import os
    from pathlib import Path

    tz_env = os.environ.get("TZ")
    if tz_env and "/" in tz_env:
        return tz_env

    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        target = os.readlink(localtime)
        # macOS: /var/db/timezone/zoneinfo/Asia/Saigon
        # Linux: /usr/share/zoneinfo/Asia/Saigon
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
        # Some distros use zoneinfo.default/...
        marker2 = "zoneinfo.default/"
        if marker2 in target:
            return target.split(marker2, 1)[1]

    try:
        from zoneinfo import ZoneInfo  # noqa: F401

        tz = datetime.now(timezone.utc).astimezone().tzinfo
        key = getattr(tz, "key", None)
        if key and "/" in key:
            return key
    except Exception:
        pass

    return "UTC"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("perplexity-deep-research")
from ..cookies import (
    get_cookies,
    to_http_cookies,
)
from ..exceptions import (
    AuthenticationError,
    BlockedError,
    PerplexityError,
    RateLimitError,
)


class PerplexityClient:
    """
    A client for interacting with the Perplexity AI API.

    Uses curl_cffi with Chrome impersonation for browser-like requests.
    Automatically refreshes cookies on 401/403 authentication errors.
    """

    def __init__(self):
        """Initialize client with cookies and session bootstrap."""
        cookies = get_cookies()
        self.session = self._create_session(cookies)
        # Bootstrap session - MUST call this in __init__
        self.session.get(ENDPOINT_AUTH_SESSION, timeout=REQUEST_TIMEOUT)

    def _create_session(self, cookies: dict) -> requests.Session:
        """
        Create curl_cffi session with Chrome impersonation.

        Args:
            cookies: Canonical cookie dict from get_cookies()

        Returns:
            requests.Session: Configured session with headers, cookies, impersonation
        """
        http_cookies = to_http_cookies(cookies)
        # Align UA + sec-ch-ua + TLS impersonation to the LOCAL Chrome so
        # Cloudflare's JA3/JA4-vs-UA cross-check stays consistent (the cloak
        # module picks the nearest curl_cffi target and a matching UA — fixes
        # the old hardcoded Chrome/130 header vs chrome146 TLS mismatch).
        c = cloak.perplexity_cloak()
        headers = DEFAULT_HEADERS.copy()  # 20 Chrome-like headers
        headers["user-agent"] = c["user_agent"]
        headers["sec-ch-ua"] = c["sec_ch_ua"]
        headers["sec-ch-ua-platform"] = c["sec_ch_ua_platform"]
        session = requests.Session(
            headers=headers,
            cookies=http_cookies,
            impersonate=c["impersonate"],
        )
        return session

    def _add_random_delay(self):
        """Add random delay (1-3s) for rate limiting protection."""
        time.sleep(random.uniform(1.0, 3.0))

    def _refresh_cookies(self):
        """Re-read cookies for the configured Chrome profile and rebuild the session.

        Expires the stored perplexity entries first so ``get_cookies`` re-extracts
        from Chrome (the onboarded / chosen profile, or auto-pick) instead of
        returning the cached set — keeping the refresh on the SAME profile the
        client reads from, and persisting through the unified config store
        (rather than the legacy single-profile ``cookies.json``).
        """
        config = profile_config.load_config()
        for name in list(
            config["providers"][profile_config.PROVIDER_PERPLEXITY]["profiles"]
        ):
            profile_config.invalidate_profile(profile_config.PROVIDER_PERPLEXITY, name)
        fresh_cookies = get_cookies()
        self.session = self._create_session(fresh_cookies)
        # Re-bootstrap session after refresh
        self.session.get(ENDPOINT_AUTH_SESSION, timeout=REQUEST_TIMEOUT)

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make request with auto-refresh on auth errors.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to session.request()

        Returns:
            requests.Response: Successful response

        Raises:
            AuthenticationError: If authentication fails after retry
            RateLimitError: If rate limit exceeded
            PerplexityError: For other HTTP errors
        """
        self._add_random_delay()
        response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)

        # Cloudflare challenge is distinct from a plain app 401/403: re-read
        # cookies once (may surface a fresh cf_clearance the user just cleared
        # in Chrome), then raise an ACTIONABLE error instead of a misleading
        # "Authentication failed". Detected via cf-mitigated / cf-ray / 503 /
        # interstitial markers — never fires on a normal SSE 200 response.
        if cloak.is_cloudflare_challenge(response.status_code, dict(response.headers)):
            self._refresh_cookies()
            self._add_random_delay()
            response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if cloak.is_cloudflare_challenge(response.status_code, dict(response.headers)):
                raise PerplexityError(
                    "Cloudflare challenge on perplexity.ai could not be cleared by the "
                    "cloak. Open https://www.perplexity.ai in Chrome to solve it, then "
                    "retry; if it persists your IP may be flagged — wait a few minutes "
                    "or switch network."
                )

        # Handle auth errors with retry
        if response.status_code in (401, 403):
            self._refresh_cookies()
            self._add_random_delay()
            response = self.session.request(
                method, url, timeout=REQUEST_TIMEOUT, **kwargs
            )
            if response.status_code in (401, 403):
                raise AuthenticationError("Authentication failed after retry")

        # Handle rate limiting
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded. Try again later.")

        # Handle other errors
        if response.status_code >= 400:
            raise PerplexityError(f"API error: HTTP {response.status_code}")

        return response

    def _has_final_answer(self, chunks: list[dict]) -> bool:
        return any(c.get("answer") for c in chunks)

    def _finalize_chunks(self, chunks: list[dict]) -> dict:
        """
        Drive the reconnect loop until a chunk has an extracted answer.

        Async modes (deep research / ASI) finish the initial stream with
        ``status=PENDING`` + ``reconnectable=true``; the actual answer arrives
        on a follow-up POST to ``/rest/sse/perplexity_ask/reconnect/{uuid}``
        with the last cursor. We retry until either an answer surfaces or the
        server reports a terminal failure.
        """
        if not chunks:
            raise PerplexityError("No response received from Perplexity API")

        max_reconnects = 60  # ~10 minutes at 10s intervals
        attempts = 0
        while not self._has_final_answer(chunks):
            last = chunks[-1]
            status = last.get("status")
            if status == "FAILED":
                raise PerplexityError(
                    f"Perplexity returned FAILED: {last.get('text') or last.get('_extras')}"
                )
            if status == "BLOCKED":
                # Server refused the request (e.g. tier-locked model: ASI /
                # Advanced Research consumes ``pplx_asi`` credits). The
                # ``locked_reason`` field carries the machine-readable cause.
                reason = last.get("locked_reason") or "unknown"
                model = last.get("user_selected_model") or last.get("display_model") or "?"
                hint = ""
                if reason == "insufficient_credits":
                    hint = (
                        " — your account has run out of credits for this tier."
                        " Try mode='auto' (free) or mode='pro' instead, or wait"
                        " until the monthly quota resets."
                    )
                raise BlockedError(
                    f"Perplexity returned BLOCKED ({reason}) for model={model}{hint}"
                )
            if not last.get("reconnectable") or not last.get("backend_uuid"):
                # Stream ended without answer and we cannot reconnect.
                raise PerplexityError("No answer found in Perplexity response")
            if attempts >= max_reconnects:
                raise PerplexityError("Perplexity reconnect loop timed out")

            backend_uuid = last["backend_uuid"]
            cursor = last.get("cursor")
            reconnect_url = f"{ENDPOINT_SSE_ASK}/reconnect/{backend_uuid}"
            body = {"cursor": cursor, "reconnectInitialSnapshot": True}

            headers = dict(SSE_REQUEST_HEADERS)
            headers["x-request-id"] = backend_uuid

            time.sleep(2.0)  # backoff between reconnects
            response = self._request_with_retry(
                "POST", reconnect_url, json=body, stream=True, headers=headers
            )
            new_chunks = self._collect_events(response)
            if not new_chunks:
                attempts += 1
                continue
            chunks.extend(new_chunks)
            attempts += 1

        # Find the chunk that carries the answer; fall back to the last.
        for c in reversed(chunks):
            if c.get("answer"):
                return c
        return chunks[-1]

    def _collect_events(self, response_stream) -> list[dict]:
        """
        Read message events from an SSE stream until ``end_of_stream``.

        Handles two on-the-wire variants emitted by perplexity.ai:

        * Initial ``/rest/sse/perplexity_ask`` stream — CRLF line endings
          with a space after the colon (``event: message\\r\\ndata: {...}\\r\\n\\r\\n``).
        * Reconnect ``/rest/sse/perplexity_ask/reconnect/{uuid}`` stream —
          standard SSE LF line endings with no space (``event:message\\ndata:{...}\\n\\n``),
          and the stream is prefixed by a ``: hello`` comment / heartbeat.

        Both forms are accepted by buffering raw bytes, normalising
        ``\\r\\n`` → ``\\n``, splitting on blank lines, and parsing each
        frame field-by-field (per the SSE spec).

        Side effect: parses the nested ``text`` field (legacy step list) and
        attaches ``answer`` to any chunk that contains a ``FINAL`` step.
        """
        chunks: list[dict] = []
        buf = b""

        for raw in response_stream.iter_content(chunk_size=4096):
            if not raw:
                continue
            buf += raw

            # Normalise CRLF to LF so frame separation is uniform.
            buf = buf.replace(b"\r\n", b"\n")

            # Frames are terminated by a blank line (LF LF).
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                if not frame.strip():
                    continue

                event_type = "message"  # SSE default per spec
                data_lines: list[str] = []
                for line in frame.decode("utf-8", "replace").split("\n"):
                    if not line or line.startswith(":"):
                        # blank inside a frame is impossible here; ``:`` is comment
                        continue
                    if ":" in line:
                        field, _, value = line.partition(":")
                        # SSE spec: a single leading space after the colon is stripped
                        if value.startswith(" "):
                            value = value[1:]
                    else:
                        field, value = line, ""
                    if field == "event":
                        event_type = value
                    elif field == "data":
                        data_lines.append(value)
                    # ignore unknown fields (id, retry, ...)

                if event_type == "end_of_stream":
                    return chunks

                if event_type != "message" or not data_lines:
                    continue

                payload_str = "\n".join(data_lines)
                try:
                    content_json = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                if "text" in content_json and content_json["text"]:
                    try:
                        text_parsed = json.loads(content_json["text"])
                        if isinstance(text_parsed, list):
                            for step in text_parsed:
                                if step.get("step_type") == "FINAL":
                                    final_content = step.get("content", {})
                                    if "answer" in final_content:
                                        answer_data = json.loads(
                                            final_content["answer"]
                                        )
                                        content_json["answer"] = (
                                            answer_data.get("answer", "")
                                        )
                                        break
                        content_json["text"] = text_parsed
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

                chunks.append(content_json)

        return chunks

    def parse_sse_response(self, response_stream) -> dict:
        """
        Parse SSE stream and return the final answer-bearing response.

        Kept for backwards compatibility with tests; new code should call
        ``_collect_events`` directly so callers can drive the reconnect loop.
        """
        chunks = self._collect_events(response_stream)
        if not chunks:
            raise PerplexityError("No response received from Perplexity API")

        final_response = chunks[-1]
        if "answer" not in final_response or not final_response["answer"]:
            raise PerplexityError("No answer found in Perplexity response")
        return final_response

    def extract_citations(self, response: dict) -> list[str]:
        """
        Extract citation URLs from Perplexity response.

        Implements the Citations Extraction Algorithm from plan lines 571-609.

        Args:
            response: The parsed JSON response from SSE stream

        Returns:
            list[str]: List of unique citation URLs, max 10
        """
        sources: list[str] = []

        # 1. Extract from text -> SEARCH_RESULTS step -> web_results
        text_items = response.get("text", [])
        if isinstance(text_items, list):
            for item in text_items:
                if isinstance(item, dict) and item.get("step_type") == "SEARCH_RESULTS":
                    content = item.get("content", {})
                    if isinstance(content, dict):
                        web_results = content.get("web_results", [])
                        if isinstance(web_results, list):
                            for wr in web_results[:10]:  # Cap at 10
                                if isinstance(wr, dict):
                                    url = wr.get("url")
                                    if url and url not in sources:
                                        sources.append(url)

        # 2. Also check widget_data for additional sources (backup)
        widget_data = response.get("widget_data", [])
        if isinstance(widget_data, list):
            for wd in widget_data[:5]:
                if isinstance(wd, dict):
                    url = wd.get("url")
                    if url and url not in sources and len(sources) < 10:
                        sources.append(url)

        return sources[:10]  # Final cap at 10 unique URLs

    def _build_payload(
        self,
        query: str,
        payload_mode: str,
        model_preference: str,
        sources: list[str],
        language: str,
        follow_up: str | None,
    ) -> dict:
        """
        Build the request payload that matches the perplexity.ai web client.

        Field set captured from a live web session on 2026-05-11. Most flags
        mirror the web app's defaults; deviating from them risks the server
        returning an alternate response shape that ``parse_sse_response``
        no longer understands.
        """
        frontend_uuid = str(uuid4())
        params = {
            "attachments": [],
            "language": language,
            "timezone": _local_iana_timezone(),
            "search_focus": "internet",
            "sources": sources,
            "frontend_uuid": frontend_uuid,
            "mode": payload_mode,
            "model_preference": model_preference,
            "is_related_query": False,
            "is_sponsored": False,
            "frontend_context_uuid": str(uuid4()),
            "prompt_source": "user",
            "query_source": "home",
            "is_incognito": False,
            "time_from_first_type": random.randint(800, 2500),
            "local_search_enabled": False,
            "use_schematized_api": True,
            "send_back_text_in_streaming_api": False,
            "supported_block_use_cases": list(SUPPORTED_BLOCK_USE_CASES),
            "client_coordinates": None,
            "mentions": [],
            "dsl_query": query,
            "skip_search_enabled": True,
            "is_nav_suggestions_disabled": False,
            "source": "default",
            "always_search_override": False,
            "override_no_search": False,
            "client_search_results_cache_key": frontend_uuid,
            "should_ask_for_mcp_tool_confirmation": True,
            "browser_agent_allow_once_from_toggle": False,
            "force_enable_browser_agent": False,
            "supported_features": list(SUPPORTED_FEATURES),
            "extended_context": False,
            "version": API_VERSION,
            "rum_session_id": str(uuid4()),
        }
        if follow_up:
            params["last_backend_uuid"] = follow_up
        return {"query_str": query, "params": params}

    def search(
        self,
        query: str,
        mode: str,
        sources: list[str],
        language: str,
        follow_up: str | None = None,
    ) -> dict:
        """
        Execute search query with specified mode.

        Args:
            query: The user's question
            mode: Logical mode ("deep research", "pro", "reasoning", "auto")
            sources: List of sources (e.g., ["web"])
            language: Language code (e.g., "en-US")
            follow_up: Optional backend_uuid for follow-up queries

        Returns:
            dict: Response with 'answer', 'citations', 'backend_uuid'
        """
        # Mode/model mapping (verified against live perplexity.ai web client
        # 2026-05-11: Pro = copilot/pplx_pro confirmed; deep research now uses
        # the asi/pplx_asi pair surfaced under "Advanced research" in the UI).
        mode_mapping = {
            "deep research": ("copilot", "pplx_alpha"),
            "pro": ("copilot", "pplx_pro"),
            "reasoning": ("copilot", "r1"),
            "auto": ("concise", "turbo"),
        }
        payload_mode, model_preference = mode_mapping[mode]
        payload = self._build_payload(
            query=query,
            payload_mode=payload_mode,
            model_preference=model_preference,
            sources=sources,
            language=language,
            follow_up=follow_up,
        )

        per_request_headers = dict(SSE_REQUEST_HEADERS)
        per_request_headers["x-request-id"] = payload["params"]["frontend_uuid"]

        # Make request with retry on transient errors
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._request_with_retry(
                    "POST",
                    ENDPOINT_SSE_ASK,
                    json=payload,
                    stream=True,
                    headers=per_request_headers,
                )
                chunks = self._collect_events(response)
                parsed = self._finalize_chunks(chunks)
                citations = self.extract_citations(parsed)

                return {
                    "answer": parsed["answer"],
                    "citations": citations,
                    "backend_uuid": parsed.get("backend_uuid", ""),
                }
            except BlockedError:
                # Permanent server-side block (e.g. insufficient_credits).
                # Retrying does not help — surface immediately.
                raise
            except (PerplexityError, RateLimitError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt * 2  # 2s, 4s backoff
                    logger.warning(
                        f"Attempt {attempt + 1}/{MAX_RETRIES + 1} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise last_error from e

        raise last_error  # Should not reach here
