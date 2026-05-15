"""GeminiClient — Deep Research over gemini.google.com.

Wire schema and DR flag indices are documented in ``docs/gemini-mcp/ref.md``.
Verified live 2026-05-15 against ``/u/6/app`` (Premium account).

DR is a 3-stage flow (mirrors HanaokaYuzu/Gemini-API):
  1. Plan generation        — POST StreamGenerate with DR flags ON
  2. Plan confirmation      — POST StreamGenerate again with the same conv_id
                              and the prompt "Start research" (or the value
                              Gemini suggested in the plan)
  3. Status polling         — POST batchexecute rpcid=kwDCne every ~10s until
                              the research finishes (returns final report)

This module currently implements stages 1+2 (the request that triggers the
long-running research). Stage 3 polling is deliberately omitted from the first
slice — once the request is fired, the report becomes visible inside the
Gemini UI and can be fetched separately.
"""

from __future__ import annotations

import json
import random
import re
import secrets
import time
import uuid
from typing import Any

from curl_cffi import requests

from .config import (
    CHROME_UA,
    DEFAULT_HL,
    DEFAULT_INNER79_REV,
    IMPERSONATE_TARGET,
    MODELS,
    PLAN_STAGE_TIMEOUT_SECS,
    POLL_INTERVAL_SECS,
    POLL_TIMEOUT_SECS,
    RPCID_READ_CHAT,
    batch_execute_url,
    stream_generate_url,
)
from .cookies import get_gemini_cookies_cached, invalidate_gemini_cache
from .csrf import get_csrf, invalidate_csrf


_RID_INITIAL_MIN = 100_000
_RID_INITIAL_MAX = 9_999_999
_RID_INCREMENT = 100_000


# Generic-error chip phrases Gemini emits when stage-1 silently fails
# (no plan, no candidate IDs, just an apologetic refusal). Matched
# case-insensitively as substrings. See docs/gemini-mcp/research.md Wave F.
_STAGE1_ERROR_PATTERNS: tuple[str, ...] = (
    "i'm sorry, it looks like something went wrong",
    "i'm sorry, but i can't help with that",
    "something went wrong. please try again",
    "i can't create a plan for that",
    "i'm unable to research that",
)

# Minimum sleep applied between polls after a reject_code response, so we
# don't hammer batchexecute when Gemini has rate-limited us. See Task #4.
_POLL_BACKOFF_MIN_SECS = 15.0


def _detect_stage1_error(
    parsed: dict[str, Any],
    deep_research: bool,
    conversation_id: str | None,
) -> str | None:
    """Return an error message when stage-1 looks like a silent failure.

    Two failure shapes show up live:

    * Gemini returned a generic apology chip — the parsed text matches one of
      the known error phrases. Always treated as failure (even for stage-2
      confirmations, since the ack chip never contains these phrases).
    * Gemini accepted the request but returned NO plan — empty ``plan_steps``
      and ``plan_title``. Only treated as failure for a fresh DR request
      (``conversation_id is None``); stage-2 confirmations legitimately
      come back without a plan.
    """
    if not deep_research:
        return None
    text = (parsed.get("text") or "").strip()
    text_lower = text.lower()
    for pattern in _STAGE1_ERROR_PATTERNS:
        if pattern in text_lower:
            preview = text[:240]
            return f"Gemini returned an error chip: {preview!r}"
    if conversation_id is None:
        # Fresh DR plan request — must come back with a plan
        plan_steps = parsed.get("plan_steps") or []
        plan_title = parsed.get("plan_title")
        if not plan_steps and not plan_title:
            preview = text[:240] if text else "<empty>"
            return (
                "Stage-1 returned no Deep Research plan "
                f"(plan_steps=0, plan_title=None). Preview: {preview!r}"
            )
    return None


class GeminiClient:
    """Synchronous client for gemini.google.com Deep Research."""

    def __init__(self) -> None:
        self._sess: requests.Session | None = None
        self._cookies: dict[str, str] | None = None
        self._chrome_profile: str | None = None
        self._f_sid: int = random.randint(-(2**63), 2**63 - 1)
        self._reqid: int = random.randint(_RID_INITIAL_MIN, _RID_INITIAL_MAX)

    # ------------------------------------------------------------------ #
    # session / auth
    # ------------------------------------------------------------------ #

    def _ensure_session(self, chrome_profile: str | None = None) -> requests.Session:
        if (
            self._sess is None
            or (chrome_profile is not None and chrome_profile != self._chrome_profile)
        ):
            name, cookies = get_gemini_cookies_cached(chrome_profile)
            self._chrome_profile = name
            self._cookies = cookies
            sess = requests.Session(impersonate=IMPERSONATE_TARGET)
            for k, v in cookies.items():
                sess.cookies.set(k, v, domain=".google.com")
            sess.headers.update({"user-agent": CHROME_UA})
            self._sess = sess
        return self._sess

    def _drop_session_and_invalidate(self, authuser: int) -> None:
        """Forget session, invalidate cookies + CSRF cache."""
        if self._chrome_profile is not None:
            invalidate_csrf(self._chrome_profile, authuser)
        invalidate_gemini_cache()
        self._sess = None
        self._cookies = None
        self._chrome_profile = None

    # ------------------------------------------------------------------ #
    # body construction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_inner_array(
        query: str,
        language: str,
        deep_research: bool,
        conversation_id: str | None = None,
        response_id: str | None = None,
        choice_id: str | None = None,
        inner79_rev: int = DEFAULT_INNER79_REV,
    ) -> list:
        """Return the 80-element inner-array. See ref.md §3.

        When ``conversation_id`` / ``response_id`` / ``choice_id`` are given,
        the call continues an existing conversation (slot 2 of the inner array
        carries those IDs instead of empty strings).
        """
        inner: list[Any] = [None] * 80
        if deep_research:
            inner[0] = [
                query, 0, None, None, None, None, 0, None, None,
                [None, None, None, None, None, None, []],
            ]
        else:
            inner[0] = [query, 0, None, None, None, None, 0]
        inner[1] = [language]
        meta_prefix = [
            conversation_id or "",
            response_id or "",
            choice_id or "",
        ]
        inner[2] = meta_prefix + [None, None, None, None, None, None, ""]
        if deep_research:
            inner[3] = "!" + secrets.token_urlsafe(2000)
            inner[4] = uuid.uuid4().hex
        inner[6] = [0]
        inner[7] = 1
        inner[10] = 1
        inner[11] = 0
        inner[17] = [[0]]
        inner[18] = 0
        inner[27] = 1
        inner[30] = [4]
        inner[41] = [1]
        if deep_research:
            inner[49] = 1
            inner[54] = [[[[[1]]]]]
            inner[55] = [[1]]
        inner[53] = 0
        inner[59] = str(uuid.uuid4()).upper()
        inner[61] = []
        inner[68] = 1
        inner[79] = inner79_rev
        return inner

    def _build_body(
        self,
        query: str,
        language: str,
        at: str,
        deep_research: bool,
        conversation_id: str | None = None,
        response_id: str | None = None,
        choice_id: str | None = None,
        inner79_rev: int = DEFAULT_INNER79_REV,
    ) -> dict[str, str]:
        inner = self._build_inner_array(
            query,
            language,
            deep_research,
            conversation_id=conversation_id,
            response_id=response_id,
            choice_id=choice_id,
            inner79_rev=inner79_rev,
        )
        f_req = [None, json.dumps(inner, separators=(",", ":"))]
        return {
            "f.req": json.dumps(f_req, separators=(",", ":")),
            "at": at,
        }

    def _build_query_params(self, bl: str) -> dict[str, str]:
        self._reqid += _RID_INCREMENT
        return {
            "bl": bl,
            "f.sid": str(self._f_sid),
            "hl": DEFAULT_HL,
            "_reqid": str(self._reqid),
            "rt": "c",
        }

    def _build_headers(
        self,
        ext_uuid: str | None = None,
        model: str | None = None,
    ) -> dict[str, str]:
        h = {
            "user-agent": CHROME_UA,
            "accept": "*/*",
            "accept-language": "en-US",
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "origin": "https://gemini.google.com",
            "referer": "https://gemini.google.com/",
            "x-same-domain": "1",
        }
        if ext_uuid:
            h["x-goog-ext-525005358-jspb"] = json.dumps([ext_uuid, 1])
        # Browser always sends these two on StreamGenerate (verified live).
        # Empirically required when the model header is set to Pro 3.1 + DR —
        # without them the stream aborts with BardErrorInfo code 1099.
        h["x-goog-ext-73010989-jspb"] = "[0]"
        h["x-goog-ext-73010990-jspb"] = "[0,0,0]"
        if model:
            spec = MODELS.get(model.lower())
            if spec is None:
                raise ValueError(
                    f"unknown model {model!r} — known: {sorted(MODELS)}"
                )
            model_id, capacity, rev = spec
            jspb = [
                1, None, None, None, model_id, None, None, 0, [4],
                None, None, capacity, None, None, rev, None,
                str(uuid.uuid4()).upper(),
            ]
            h["x-goog-ext-525001261-jspb"] = json.dumps(jspb, separators=(",", ":"))
        return h

    # ------------------------------------------------------------------ #
    # stream parsing
    # ------------------------------------------------------------------ #

    @staticmethod
    def _strip_xssi(body: str) -> str:
        return body.lstrip().removeprefix(")]}'").lstrip()

    @staticmethod
    def _iter_frames(body: str):
        """Yield each ``wrb.fr`` frame's inner-JSON value.

        Gemini frames are length-prefixed (``<decimal>\\n<json>``) but the
        length INCLUDES the trailing newline. We use ``json.raw_decode`` to
        consume each frame regardless of exact byte count. Footer frames
        (``di``, ``af.httprm``, ``e``) are emitted but caller filters.
        """
        decoder = json.JSONDecoder()
        text = body
        pos = 0
        n = len(text)
        while pos < n:
            # Skip whitespace + length prefix digits
            while pos < n and (text[pos].isspace() or text[pos].isdigit()):
                pos += 1
            if pos >= n:
                return
            try:
                arr, end = decoder.raw_decode(text, pos)
            except json.JSONDecodeError:
                return
            pos = end
            if not (isinstance(arr, list) and arr and isinstance(arr[0], list)):
                continue
            frame_head = arr[0][0] if arr[0] else None
            if frame_head != "wrb.fr":
                continue
            try:
                inner_str = arr[0][2]
                if not isinstance(inner_str, str):
                    continue
                yield json.loads(inner_str)
            except (IndexError, json.JSONDecodeError):
                continue

    @staticmethod
    def _walk_for_plan_dict(obj: Any) -> dict | None:
        """Find the deeply nested ``{"56":[...]}`` dict that holds the
        structured DR plan. Returns the dict (with the "56" key) or None.
        """
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "56" in cur and isinstance(cur["56"], list):
                    return cur
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        return None

    @staticmethod
    def _parse_frames(frames: list[Any]) -> dict[str, Any]:
        """Reduce a list of decoded ``wrb.fr`` inner JSONs to a summary dict."""
        conv_id: str | None = None
        resp_id: str | None = None
        candidate_ids: list[str] = []
        title: str | None = None
        status_lines: list[str] = []
        text_chunks: list[str] = []
        plan_title: str | None = None
        plan_steps: list[dict[str, Any]] = []
        plan_eta_text: str | None = None

        for f in frames:
            if not isinstance(f, list):
                continue
            # f[1] = [conv_id?, resp_id?]
            if len(f) > 1 and isinstance(f[1], list):
                ids = f[1]
                for v in ids:
                    if isinstance(v, str):
                        if v.startswith("c_") and not conv_id:
                            conv_id = v
                        elif v.startswith("r_") and not resp_id:
                            resp_id = v
            # f[2] = delta dict — may carry status "7" or title "11"
            if len(f) > 2 and isinstance(f[2], dict):
                delta = f[2]
                status = delta.get("7")
                if (
                    isinstance(status, list)
                    and len(status) > 5
                    and isinstance(status[5], list)
                    and status[5]
                ):
                    s = status[5][0]
                    if isinstance(s, str):
                        status_lines.append(s)
                t = delta.get("11")
                if isinstance(t, list) and t and isinstance(t[0], str):
                    title = title or t[0]
            # f[4] = candidate array
            if len(f) > 4 and isinstance(f[4], list):
                for cand in f[4]:
                    if not (isinstance(cand, list) and cand and isinstance(cand[0], str)):
                        continue
                    cid = cand[0]
                    if cid.startswith("rc_") and cid not in candidate_ids:
                        candidate_ids.append(cid)
                    # cand[1] = [text-so-far]
                    if len(cand) > 1 and isinstance(cand[1], list) and cand[1]:
                        blob = cand[1][0]
                        if isinstance(blob, str) and blob:
                            text_chunks.append(blob)
                    # plan struct is buried deep — walk to find it
                    plan_dict = GeminiClient._walk_for_plan_dict(cand)
                    if plan_dict is not None and not plan_steps:
                        plan_arr = plan_dict["56"]
                        if isinstance(plan_arr, list) and plan_arr:
                            if isinstance(plan_arr[0], str):
                                plan_title = plan_title or plan_arr[0]
                            if len(plan_arr) > 1 and isinstance(plan_arr[1], list):
                                for step in plan_arr[1]:
                                    if isinstance(step, list) and len(step) >= 3:
                                        plan_steps.append({
                                            "id": step[0],
                                            "title": step[1],
                                            "body": step[2],
                                        })
                        # ETA text often at plan_dict.get("57")
                        eta = plan_dict.get("57")
                        if isinstance(eta, list) and eta and isinstance(eta[0], str):
                            plan_eta_text = eta[0]

        return {
            "ok": True,
            "conversation_id": conv_id,
            "response_id": resp_id,
            "candidate_ids": candidate_ids,
            "title": title,
            "status_lines": status_lines,
            "plan_title": plan_title,
            "plan_steps": plan_steps,
            "plan_eta": plan_eta_text,
            "text": "\n\n".join(text_chunks) if text_chunks else None,
        }

    # ------------------------------------------------------------------ #
    # batchexecute (stage-3 polling)
    # ------------------------------------------------------------------ #

    def _batch_execute(
        self,
        authuser: int,
        rpcid: str,
        payload_obj: Any,
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """POST one batchexecute RPC and return the parsed wrb.fr frame.

        Returns ``{"body": <parsed_obj_or_None>, "reject_code": <int_or_None>}``.

        * ``body`` is the decoded JSON at frame[2] when the call succeeds, or
          ``None`` when the frame is empty / rejected.
        * ``reject_code`` is the gRPC status code at frame[5][0] (e.g. 7 =
          ``RESOURCE_EXHAUSTED`` when called too fast). ``None`` when the call
          succeeded.

        Raises ``RuntimeError`` on transport-level failure.
        """
        sess = self._ensure_session(chrome_profile)
        chrome_profile_used = self._chrome_profile or "Default"

        for attempt in (0, 1):
            try:
                csrf = get_csrf(
                    chrome_profile_used,
                    authuser,
                    self._cookies or {},
                    refresh=(attempt == 1),
                )
            except Exception as e:
                if attempt == 0:
                    self._drop_session_and_invalidate(authuser)
                    sess = self._ensure_session(chrome_profile)
                    chrome_profile_used = self._chrome_profile or "Default"
                    continue
                raise RuntimeError(f"CSRF fetch failed: {e}") from e

            self._reqid += _RID_INCREMENT
            params = {
                "rpcids": rpcid,
                "hl": language,
                "_reqid": str(self._reqid),
                "rt": "c",
                "source-path": "/app",
                "bl": csrf["bl"],
                "f.sid": str(self._f_sid),
            }
            f_req = [[[rpcid, json.dumps(payload_obj, separators=(",", ":")), None, "generic"]]]
            data = {
                "at": csrf["at"],
                "f.req": json.dumps(f_req, separators=(",", ":")),
            }
            headers = {
                "user-agent": CHROME_UA,
                "accept": "*/*",
                "accept-language": "en-US",
                "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                "origin": "https://gemini.google.com",
                "referer": "https://gemini.google.com/",
                "x-same-domain": "1",
            }

            r = sess.post(
                batch_execute_url(authuser),
                params=params,
                data=data,
                headers=headers,
                timeout=timeout,
            )

            if r.status_code in (401, 403) and attempt == 0:
                self._drop_session_and_invalidate(authuser)
                sess = self._ensure_session(chrome_profile)
                chrome_profile_used = self._chrome_profile or "Default"
                continue

            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")

            body = self._strip_xssi(r.text)
            # batchexecute frames mirror StreamGenerate; scan for our rpcid's
            # wrb.fr row and lift body (frame[2]) + reject code (frame[5][0]).
            decoder = json.JSONDecoder()
            pos = 0
            n = len(body)
            while pos < n:
                while pos < n and (body[pos].isspace() or body[pos].isdigit()):
                    pos += 1
                if pos >= n:
                    break
                try:
                    arr, end = decoder.raw_decode(body, pos)
                except json.JSONDecodeError:
                    break
                pos = end
                if not (isinstance(arr, list) and arr and isinstance(arr[0], list)):
                    continue
                row = arr[0]
                if len(row) < 3 or row[0] != "wrb.fr" or row[1] != rpcid:
                    continue
                inner_str = row[2]
                reject_code = None
                if len(row) > 5 and isinstance(row[5], list) and row[5]:
                    rc = row[5][0]
                    if isinstance(rc, int):
                        reject_code = rc
                parsed: Any = None
                if isinstance(inner_str, str):
                    try:
                        parsed = json.loads(inner_str)
                    except json.JSONDecodeError:
                        parsed = None
                return {"body": parsed, "reject_code": reject_code}
            return {"body": None, "reject_code": None}

        raise RuntimeError("exhausted retries")

    def _read_chat_status(
        self,
        conversation_id: str,
        authuser: int,
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Inspect the latest model turn in a conversation.

        Maps to Hanaoka's ``ChatMixin.read_chat`` decision tree:

        * candidate[8][0] == 2     → finished successfully
        * candidate[12][6][0] != None → still generating
        * otherwise                → interrupted / blocked
        """
        payload = [conversation_id, limit, None, 1, [1], [4], None, 1]
        resp = self._batch_execute(
            authuser=authuser,
            rpcid=RPCID_READ_CHAT,
            payload_obj=payload,
            chrome_profile=chrome_profile,
            language=language,
        )
        body = resp["body"]
        reject_code = resp["reject_code"]
        out = {
            "done": False,
            "in_progress": False,
            "text": None,
            "title": None,
            "rcid": None,
            "reason": None,
            "raw_status": None,
            "reject_code": reject_code,
        }
        if reject_code is not None:
            # Treat any rejection (7 = RESOURCE_EXHAUSTED, etc.) as a
            # transient poll error; the caller will back off and retry.
            out["in_progress"] = True
            out["reason"] = f"batchexecute rejected (code {reject_code})"
            return out
        if not isinstance(body, list) or not body:
            return out
        turns = body[0]
        if not isinstance(turns, list):
            return out
        # turns[0] is the most-recent (model) turn for a DR run
        for turn in turns:
            if not isinstance(turn, list):
                continue
            try:
                candidates = turn[3][0]
            except (IndexError, TypeError):
                continue
            if not isinstance(candidates, list) or not candidates:
                continue
            cand = candidates[0]
            if not isinstance(cand, list):
                continue
            # rcid
            if cand and isinstance(cand[0], str):
                out["rcid"] = cand[0]
            # Default text = the chat reply (cand[1][0]). For DR, this is just
            # the chip placeholder ("I'm done researching…") — the real
            # markdown report lives in the immersive document at cand[30].
            try:
                txt = cand[1][0]
                if isinstance(txt, str):
                    out["text"] = txt
            except (IndexError, TypeError):
                pass
            # DR immersive report override: cand[30][0] = [id, id, title, id,
            # markdown_body, citations, …]. Verified live 2026-05-15 on the
            # XAUUSD conversation.
            immersive_markdown = ""
            try:
                imm = cand[30]
                if isinstance(imm, list) and imm:
                    item = imm[0]
                    if isinstance(item, list) and len(item) >= 5:
                        if isinstance(item[2], str):
                            out["title"] = item[2]
                        if isinstance(item[4], str) and item[4]:
                            immersive_markdown = item[4]
                            out["text"] = immersive_markdown
            except (IndexError, TypeError):
                pass
            # completion_status
            completion = None
            try:
                completion = cand[8][0]
            except (IndexError, TypeError):
                pass
            out["raw_status"] = completion
            # progress signal
            progress = None
            try:
                progress = cand[12][6][0]
            except (IndexError, TypeError):
                pass
            # Stage-2's "Great, I'll let you know when done" ack also reports
            # completion_status==2 with NO immersive document. The actual DR
            # report only arrives later, once cand[30][0][4] is populated.
            # So: done only when both status=2 AND we have immersive markdown.
            if completion == 2 and immersive_markdown:
                out["done"] = True
            elif completion == 2 and not immersive_markdown:
                # Ack chip — research is still running on the server.
                out["in_progress"] = True
            elif progress is not None:
                out["in_progress"] = True
            else:
                # Stopped — usage cap / policy / etc. Try to grab a reason.
                try:
                    reason = cand[1][0] if isinstance(cand[1][0], str) else None
                except (IndexError, TypeError):
                    reason = None
                out["reason"] = (
                    reason
                    or "Gemini stopped generating "
                    "(safety policy, content filter, or usage limit)."
                )
            return out
        return out

    def poll_research(
        self,
        conversation_id: str,
        authuser: int,
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        poll_interval: float = POLL_INTERVAL_SECS,
        timeout: float = POLL_TIMEOUT_SECS,
    ) -> dict[str, Any]:
        """Stage-3: poll READ_CHAT until the research report is finalised.

        Returns::

            {
              "ok": True,
              "done": bool,
              "conversation_id": str,
              "rcid": str | None,
              "text": str | None,          # final markdown report
              "elapsed_secs": float,
              "polls": int,
              "reason": str | None,        # set when Gemini stopped early
              "timed_out": bool,
            }
        """
        t0 = time.time()
        polls = 0
        last: dict[str, Any] = {}
        while True:
            polls += 1
            try:
                last = self._read_chat_status(
                    conversation_id=conversation_id,
                    authuser=authuser,
                    chrome_profile=chrome_profile,
                    language=language,
                )
            except Exception as e:
                # Transient read errors: count, sleep, retry until timeout.
                last = {"done": False, "in_progress": True, "text": None,
                        "title": None, "rcid": None,
                        "reason": f"poll error: {e}", "raw_status": None}
            if last.get("done"):
                return {
                    "ok": True,
                    "done": True,
                    "conversation_id": conversation_id,
                    "rcid": last.get("rcid"),
                    "title": last.get("title"),
                    "text": last.get("text"),
                    "elapsed_secs": round(time.time() - t0, 2),
                    "polls": polls,
                    "reason": None,
                    "timed_out": False,
                }
            if last.get("reason") and not last.get("in_progress"):
                # Hard stop (safety policy / cap).
                return {
                    "ok": True,
                    "done": False,
                    "conversation_id": conversation_id,
                    "rcid": last.get("rcid"),
                    "title": last.get("title"),
                    "text": last.get("text"),
                    "elapsed_secs": round(time.time() - t0, 2),
                    "polls": polls,
                    "reason": last["reason"],
                    "timed_out": False,
                }
            if (time.time() - t0) >= timeout:
                return {
                    "ok": True,
                    "done": False,
                    "conversation_id": conversation_id,
                    "rcid": last.get("rcid"),
                    "title": last.get("title"),
                    "text": last.get("text"),
                    "elapsed_secs": round(time.time() - t0, 2),
                    "polls": polls,
                    "reason": last.get("reason"),
                    "timed_out": True,
                }
            # Back off on rate-limit (reject_code=7 = RESOURCE_EXHAUSTED) by
            # enforcing a minimum interval so we don't keep triggering it.
            if last.get("reject_code") is not None:
                effective_interval = max(poll_interval, _POLL_BACKOFF_MIN_SECS)
            else:
                effective_interval = poll_interval
            time.sleep(effective_interval)

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def submit(
        self,
        query: str,
        authuser: int,
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        deep_research: bool = False,
        timeout: int = PLAN_STAGE_TIMEOUT_SECS,
        conversation_id: str | None = None,
        response_id: str | None = None,
        choice_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """One StreamGenerate round-trip. Returns parsed metadata.

        Result shape::

            {
              "ok": True,
              "conversation_id": "c_...",
              "response_id": "r_...",
              "candidate_ids": ["rc_..."],
              "title": "<auto-title from Gemini>",
              "plan_text": "<plan markdown>" | None,
              "text": "<flattened content>" | None,
              "raw_frames": <count>,
              "elapsed_secs": float
            }
        """
        sess = self._ensure_session(chrome_profile)
        chrome_profile_used = self._chrome_profile or "Default"

        for attempt in (0, 1):
            try:
                csrf = get_csrf(
                    chrome_profile_used,
                    authuser,
                    self._cookies or {},
                    refresh=(attempt == 1),
                )
            except Exception as e:
                if attempt == 0:
                    self._drop_session_and_invalidate(authuser)
                    sess = self._ensure_session(chrome_profile)
                    chrome_profile_used = self._chrome_profile or "Default"
                    continue
                return {"error": f"CSRF fetch failed: {e}"}

            params = self._build_query_params(csrf["bl"])
            inner79_rev = (
                MODELS[model.lower()][2] if model and model.lower() in MODELS
                else DEFAULT_INNER79_REV
            )
            data = self._build_body(
                query,
                language,
                csrf["at"],
                deep_research,
                conversation_id=conversation_id,
                response_id=response_id,
                choice_id=choice_id,
                inner79_rev=inner79_rev,
            )
            # Extract UUID from inner array to echo in header
            inner_json = json.loads(json.loads(data["f.req"])[1])
            ext_uuid = inner_json[59] if isinstance(inner_json, list) and len(inner_json) > 59 else None
            headers = self._build_headers(ext_uuid=ext_uuid, model=model)

            t0 = time.time()
            r = sess.post(
                stream_generate_url(authuser),
                params=params,
                data=data,
                headers=headers,
                timeout=timeout,
            )

            if r.status_code in (401, 403) and attempt == 0:
                self._drop_session_and_invalidate(authuser)
                sess = self._ensure_session(chrome_profile)
                chrome_profile_used = self._chrome_profile or "Default"
                continue

            if r.status_code != 200:
                return {
                    "error": f"HTTP {r.status_code}: {r.text[:500]}",
                    "status": r.status_code,
                }

            raw_body = r.text
            body = self._strip_xssi(raw_body)
            frames = list(self._iter_frames(body))

            # Debug hook — set GEMINI_DEBUG_DUMP=<path> to capture the raw body
            import os as _os
            dump_path = _os.environ.get("GEMINI_DEBUG_DUMP")
            if dump_path:
                from pathlib import Path as _Path
                _Path(dump_path).write_text(raw_body)

            parsed = self._parse_frames(frames)
            parsed["raw_frames"] = len(frames)
            parsed["elapsed_secs"] = round(time.time() - t0, 2)
            parsed["deep_research"] = deep_research
            parsed["chrome_profile"] = chrome_profile_used
            parsed["authuser"] = authuser
            parsed["model"] = model

            err_msg = _detect_stage1_error(parsed, deep_research, conversation_id)
            if err_msg:
                parsed["ok"] = False
                parsed["error"] = err_msg
            return parsed

        return {"error": "exhausted retries"}

    def deep_research(
        self,
        query: str,
        authuser: int,
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Stage-1 only: submit the DR plan request and return the plan.

        The full research run (stage 2+3) is fired separately via
        :meth:`start_research` once the caller has reviewed the plan. Two-stage
        is intentional — the plan stage costs <30 s and is enough to validate
        the wire, while the full run is 5-15 min and benefits from explicit
        opt-in.
        """
        return self.submit(
            query,
            authuser=authuser,
            chrome_profile=chrome_profile,
            language=language,
            deep_research=True,
            model=model,
        )

    def start_research(
        self,
        authuser: int,
        conversation_id: str,
        response_id: str,
        choice_id: str,
        confirm_prompt: str = "Start research",
        chrome_profile: str | None = None,
        language: str = DEFAULT_HL,
        model: str | None = None,
        wait: bool = False,
        poll_interval: float = POLL_INTERVAL_SECS,
        timeout: float = POLL_TIMEOUT_SECS,
    ) -> dict[str, Any]:
        """Stage-2: confirm a previously generated plan. Triggers the long run.

        Gemini's UI sends the plain string "Start research" (or the suggested
        confirm prompt) as a normal DR-flagged StreamGenerate inside the same
        conversation. The IDs from the plan response (``conversation_id``,
        ``response_id``, ``choice_id``) rehydrate that context.

        When ``wait=True``, this method blocks after the confirmation lands
        and polls Gemini's batchexecute (``READ_CHAT``) every ``poll_interval``
        seconds until the report is finalised or ``timeout`` elapses. The
        final report markdown is then attached to the result under
        ``poll.text``.
        """
        result = self.submit(
            confirm_prompt,
            authuser=authuser,
            chrome_profile=chrome_profile,
            language=language,
            deep_research=True,
            conversation_id=conversation_id,
            response_id=response_id,
            choice_id=choice_id,
            model=model,
        )
        if not wait:
            return result
        if not result.get("ok"):
            return result
        cid = result.get("conversation_id") or conversation_id
        poll = self.poll_research(
            conversation_id=cid,
            authuser=authuser,
            chrome_profile=chrome_profile,
            language=language,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        result["poll"] = poll
        return result

    def refresh_csrf(self, authuser: int, chrome_profile: str | None = None) -> dict[str, Any]:
        """Force-refresh the cached SNlM0e + cfb2h for one Google account."""
        sess = self._ensure_session(chrome_profile)  # noqa: F841
        chrome_profile_used = self._chrome_profile or "Default"
        try:
            csrf = get_csrf(
                chrome_profile_used,
                authuser,
                self._cookies or {},
                refresh=True,
            )
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {
            "ok": True,
            "chrome_profile": chrome_profile_used,
            "authuser": authuser,
            "snlm0e_prefix": csrf["at"][:24] + "…",
            "bl": csrf["bl"],
            "email": csrf.get("email"),
        }
