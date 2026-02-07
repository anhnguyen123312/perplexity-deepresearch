"""
Perplexity API client with Chrome impersonation and auto-refresh.

Provides a client for interacting with the Perplexity AI API using curl_cffi
for Chrome impersonation and automatic cookie refresh on authentication errors.
"""

import json
import random
import time
from uuid import uuid4

from curl_cffi import requests

import logging
import sys

from .config import (
    API_VERSION,
    DEFAULT_HEADERS,
    ENDPOINT_AUTH_SESSION,
    ENDPOINT_SSE_ASK,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("perplexity-deep-research")
from .cookies import (
    extract_cookies_with_relaunch,
    get_cookies,
    save_cookies,
    to_http_cookies,
)
from .exceptions import AuthenticationError, PerplexityError, RateLimitError


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
        session = requests.Session(
            headers=DEFAULT_HEADERS.copy(),  # 20 Chrome-like headers
            cookies=http_cookies,
            impersonate="chrome",
        )
        return session

    def _add_random_delay(self):
        """Add random delay (1-3s) for rate limiting protection."""
        time.sleep(random.uniform(1.0, 3.0))

    def _refresh_cookies(self):
        """Re-extract cookies from Chrome and recreate session."""
        fresh_cookies = extract_cookies_with_relaunch()
        save_cookies(fresh_cookies)
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

    def parse_sse_response(self, response_stream) -> dict:
        """
        Parse SSE stream from Perplexity API.

        Implements the Answer Extraction Algorithm from plan lines 482-542.

        Args:
            response_stream: curl_cffi response with stream=True

        Returns:
            dict: Final parsed response with 'answer', 'backend_uuid', 'text'

        Raises:
            PerplexityError: If no valid response or answer found
        """
        chunks = []

        for chunk in response_stream.iter_lines(delimiter=b"\r\n\r\n"):
            content = chunk.decode("utf-8")

            if content.startswith("event: message\r\n"):
                try:
                    # Parse JSON after "event: message\r\ndata: " prefix
                    json_str = content[len("event: message\r\ndata: ") :]
                    content_json = json.loads(json_str)

                    # Parse nested 'text' field (contains step list)
                    if "text" in content_json and content_json["text"]:
                        try:
                            text_parsed = json.loads(content_json["text"])

                            # Extract answer from FINAL step
                            if isinstance(text_parsed, list):
                                for step in text_parsed:
                                    if step.get("step_type") == "FINAL":
                                        final_content = step.get("content", {})
                                        if "answer" in final_content:
                                            answer_data = json.loads(
                                                final_content["answer"]
                                            )
                                            content_json["answer"] = answer_data.get(
                                                "answer", ""
                                            )
                                            break

                            content_json["text"] = text_parsed
                        except (json.JSONDecodeError, TypeError, KeyError):
                            pass

                    chunks.append(content_json)
                except (json.JSONDecodeError, KeyError):
                    continue

            elif content.startswith("event: end_of_stream\r\n"):
                break

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
            mode: Logical mode ("deep research", "pro", "auto")
            sources: List of sources (e.g., ["web"])
            language: Language code (e.g., "en-US")
            follow_up: Optional backend_uuid for follow-up queries

        Returns:
            dict: Response with 'answer', 'citations', 'backend_uuid'
        """
        # Mode/model mapping
        mode_mapping = {
            "deep research": ("copilot", "pplx_alpha"),
            "pro": ("copilot", "pplx_pro"),
            "reasoning": ("copilot", "r1"),
            "auto": ("concise", "turbo"),
        }
        payload_mode, model_preference = mode_mapping[mode]

        # Build payload (plan lines 625-653)
        payload = {
            "query_str": query,
            "params": {
                "attachments": [],
                "frontend_context_uuid": str(uuid4()),
                "frontend_uuid": str(uuid4()),
                "is_incognito": False,
                "language": language,
                "last_backend_uuid": follow_up,  # None or string UUID
                "mode": payload_mode,
                "model_preference": model_preference,
                "source": "default",
                "sources": sources,
                "version": API_VERSION,
            },
        }

        # Make request with retry on transient errors
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._request_with_retry(
                    "POST", ENDPOINT_SSE_ASK, json=payload, stream=True
                )
                parsed = self.parse_sse_response(response)
                citations = self.extract_citations(parsed)

                return {
                    "answer": parsed["answer"],
                    "citations": citations,
                    "backend_uuid": parsed.get("backend_uuid", ""),
                }
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
