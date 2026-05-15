"""Tests for Gemini Deep Research stage-1 error detection and stage-3 polling.

Covers:
* ``_detect_stage1_error`` — silent error chip + empty-plan detection
* ``_batch_execute`` — frame extraction + reject_code surfacing
* ``_read_chat_status`` — ack-chip vs finalised report disambiguation
* ``poll_research`` — done / hard-stop / timeout / rate-limit backoff
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from deep_research.gemini import client as gclient
from deep_research.gemini.client import (
    GeminiClient,
    _detect_stage1_error,
)


# ---------------------------------------------------------------------- #
# _detect_stage1_error
# ---------------------------------------------------------------------- #


class TestDetectStage1Error:
    def test_non_dr_call_never_flags_error(self):
        parsed = {"text": "I'm sorry, it looks like something went wrong"}
        assert _detect_stage1_error(parsed, deep_research=False, conversation_id=None) is None

    def test_apology_chip_flagged_on_fresh_dr(self):
        parsed = {
            "text": "I'm sorry, it looks like something went wrong. Please try again.",
            "plan_steps": [],
            "plan_title": None,
        }
        msg = _detect_stage1_error(parsed, deep_research=True, conversation_id=None)
        assert msg is not None
        assert "error chip" in msg

    def test_apology_chip_flagged_even_on_stage2(self):
        # Stage-2 confirmation: conversation_id IS set; but apology phrases
        # never legitimately appear, so still flag.
        parsed = {"text": "I'm sorry, but I can't help with that."}
        msg = _detect_stage1_error(parsed, deep_research=True, conversation_id="c_abc")
        assert msg is not None

    def test_empty_plan_on_fresh_dr_is_error(self):
        parsed = {"text": "", "plan_steps": [], "plan_title": None}
        msg = _detect_stage1_error(parsed, deep_research=True, conversation_id=None)
        assert msg is not None
        assert "no Deep Research plan" in msg

    def test_empty_plan_on_stage2_is_NOT_error(self):
        # Stage-2 ack chip ("Great. While I'm researching..."): no plan,
        # but conversation_id is set, so we must not flag.
        parsed = {
            "text": "Great. While I'm researching, you can continue chatting.",
            "plan_steps": [],
            "plan_title": None,
        }
        assert _detect_stage1_error(parsed, deep_research=True, conversation_id="c_abc") is None

    def test_valid_plan_passes(self):
        parsed = {
            "text": "Here is my plan…",
            "plan_steps": [{"id": "s1", "title": "Step 1", "body": "x"}],
            "plan_title": "Research plan",
        }
        assert _detect_stage1_error(parsed, deep_research=True, conversation_id=None) is None


# ---------------------------------------------------------------------- #
# _batch_execute
# ---------------------------------------------------------------------- #


def _wrap_batchexecute(inner_frame: list) -> str:
    """Build a minimal batchexecute envelope wrapping one wrb.fr frame.

    Live shape::

        )]}}'\n
        5318\n
        [["wrb.fr","hNvQHb","<inner_json>",null,null,null,"1"]]\n

    The outer JSON is a list-of-frames; ``arr[0]`` is the wrb.fr row.
    The leading digit run is the chunk size (skipped by ``_batch_execute``).
    """
    payload = json.dumps([inner_frame])
    return f")]}}'\n{len(payload)}\n{payload}\n"


def _stub_csrf(*_a, **_kw):
    return {"at": "SNlM0e-test", "bl": "boq_bard.test", "email": "x@y"}


@pytest.fixture
def client(monkeypatch):
    c = GeminiClient()
    c._cookies = {"__Secure-1PSID": "v", "SAPISID": "s"}
    c._chrome_profile = "Default"
    fake_sess = MagicMock()
    c._sess = fake_sess

    monkeypatch.setattr(gclient, "get_csrf", _stub_csrf)
    monkeypatch.setattr(c, "_ensure_session", MagicMock(return_value=fake_sess))
    monkeypatch.setattr(c, "_drop_session_and_invalidate", MagicMock())
    return c


class TestBatchExecute:
    def test_returns_parsed_body(self, client):
        body_obj = [["turn1", "fake"]]
        inner_frame = ["wrb.fr", "hNvQHb", json.dumps(body_obj), None, None, None, "1"]
        resp = MagicMock(status_code=200, text=_wrap_batchexecute(inner_frame))
        client._sess.post.return_value = resp

        out = client._batch_execute(authuser=0, rpcid="hNvQHb", payload_obj=[1])
        assert out["body"] == body_obj
        assert out["reject_code"] is None

    def test_surfaces_reject_code(self, client):
        # Frame with reject_code at frame[5][0] and empty body at frame[2]
        inner_frame = ["wrb.fr", "hNvQHb", None, None, None, [7]]
        resp = MagicMock(status_code=200, text=_wrap_batchexecute(inner_frame))
        client._sess.post.return_value = resp

        out = client._batch_execute(authuser=0, rpcid="hNvQHb", payload_obj=[1])
        assert out["body"] is None
        assert out["reject_code"] == 7

    def test_empty_response_returns_none(self, client):
        resp = MagicMock(status_code=200, text=")]}}'\n2\n[]\n")
        client._sess.post.return_value = resp
        out = client._batch_execute(authuser=0, rpcid="hNvQHb", payload_obj=[1])
        assert out["body"] is None
        assert out["reject_code"] is None


# ---------------------------------------------------------------------- #
# _read_chat_status
# ---------------------------------------------------------------------- #


def _make_turn(*, completion: int | None, immersive_md: str = "",
               chip_text: str = "", progress: object = None, title: str = ""):
    """Build a READ_CHAT turn structure matching live shape."""
    cand: list = [
        "rc_abc",        # 0: rcid
        [chip_text],     # 1: chip text
        None, None, None, None, None, None,  # 2-7
        [completion] if completion is not None else None,  # 8: completion_status
        None, None, None,                     # 9-11
        # 12: progress signal at [12][6][0]
        [None, None, None, None, None, None, [progress]] if progress is not None else None,
        None, None, None, None, None, None, None, None, None,  # 13-21
        None, None, None, None, None, None, None, None,        # 22-29
    ]
    # cand[30]: immersive document
    if immersive_md or title:
        cand.append([[None, None, title, None, immersive_md]])
    else:
        cand.append([])
    # Pad to safety
    while len(cand) < 32:
        cand.append(None)
    # turn structure: turn[3][0] = [cand]
    return [None, ["c_test", "r_test"], None, [[cand]]]


class TestReadChatStatus:
    def test_finalised_report_returns_done(self, client, monkeypatch):
        body = [[_make_turn(completion=2, immersive_md="# Report\n\nFinal text",
                            title="Report Title")]]
        monkeypatch.setattr(client, "_batch_execute",
                            MagicMock(return_value={"body": body, "reject_code": None}))
        out = client._read_chat_status(conversation_id="c_test", authuser=0)
        assert out["done"] is True
        assert out["text"].startswith("# Report")
        assert out["title"] == "Report Title"
        assert out["raw_status"] == 2

    def test_ack_chip_is_in_progress(self, client, monkeypatch):
        # completion=2 but no immersive markdown = stage-2 ack chip
        body = [[_make_turn(completion=2, immersive_md="",
                            chip_text="Great. While I'm researching…")]]
        monkeypatch.setattr(client, "_batch_execute",
                            MagicMock(return_value={"body": body, "reject_code": None}))
        out = client._read_chat_status(conversation_id="c_test", authuser=0)
        assert out["done"] is False
        assert out["in_progress"] is True

    def test_progress_signal_means_in_progress(self, client, monkeypatch):
        body = [[_make_turn(completion=1, progress=42)]]
        monkeypatch.setattr(client, "_batch_execute",
                            MagicMock(return_value={"body": body, "reject_code": None}))
        out = client._read_chat_status(conversation_id="c_test", authuser=0)
        assert out["done"] is False
        assert out["in_progress"] is True

    def test_reject_code_surfaces_as_in_progress(self, client, monkeypatch):
        monkeypatch.setattr(client, "_batch_execute",
                            MagicMock(return_value={"body": None, "reject_code": 7}))
        out = client._read_chat_status(conversation_id="c_test", authuser=0)
        assert out["done"] is False
        assert out["in_progress"] is True
        assert out["reject_code"] == 7
        assert "code 7" in (out["reason"] or "")

    def test_hard_stop_when_no_progress_no_completion(self, client, monkeypatch):
        body = [[_make_turn(completion=None, chip_text="Usage limit reached")]]
        monkeypatch.setattr(client, "_batch_execute",
                            MagicMock(return_value={"body": body, "reject_code": None}))
        out = client._read_chat_status(conversation_id="c_test", authuser=0)
        assert out["done"] is False
        assert out["in_progress"] is False
        assert out["reason"]


# ---------------------------------------------------------------------- #
# poll_research
# ---------------------------------------------------------------------- #


class TestPollResearch:
    def test_returns_immediately_when_done(self, client, monkeypatch):
        monkeypatch.setattr(client, "_read_chat_status", MagicMock(return_value={
            "done": True, "in_progress": False, "text": "# Final",
            "title": "T", "rcid": "rc_1", "reason": None, "raw_status": 2,
            "reject_code": None,
        }))
        out = client.poll_research(conversation_id="c_test", authuser=0,
                                    poll_interval=0.01, timeout=5.0)
        assert out["done"] is True
        assert out["text"] == "# Final"
        assert out["polls"] == 1
        assert out["timed_out"] is False

    def test_returns_on_hard_stop(self, client, monkeypatch):
        monkeypatch.setattr(client, "_read_chat_status", MagicMock(return_value={
            "done": False, "in_progress": False, "text": None,
            "title": None, "rcid": "rc_1", "reason": "Usage limit",
            "raw_status": None, "reject_code": None,
        }))
        out = client.poll_research(conversation_id="c_test", authuser=0,
                                    poll_interval=0.01, timeout=5.0)
        assert out["done"] is False
        assert out["reason"] == "Usage limit"
        assert out["timed_out"] is False

    def test_loops_until_done(self, client, monkeypatch):
        calls = [
            {"done": False, "in_progress": True, "text": None, "title": None,
             "rcid": None, "reason": None, "raw_status": 1, "reject_code": None},
            {"done": False, "in_progress": True, "text": None, "title": None,
             "rcid": "rc_x", "reason": None, "raw_status": 1, "reject_code": None},
            {"done": True, "in_progress": False, "text": "# Done", "title": "T",
             "rcid": "rc_x", "reason": None, "raw_status": 2, "reject_code": None},
        ]
        monkeypatch.setattr(client, "_read_chat_status",
                            MagicMock(side_effect=calls))
        monkeypatch.setattr(gclient.time, "sleep", lambda _s: None)

        out = client.poll_research(conversation_id="c_test", authuser=0,
                                    poll_interval=0.01, timeout=5.0)
        assert out["done"] is True
        assert out["polls"] == 3
        assert out["text"] == "# Done"

    def test_times_out(self, client, monkeypatch):
        in_progress = {"done": False, "in_progress": True, "text": None,
                       "title": None, "rcid": None, "reason": None,
                       "raw_status": 1, "reject_code": None}
        monkeypatch.setattr(client, "_read_chat_status",
                            MagicMock(return_value=in_progress))
        monkeypatch.setattr(gclient.time, "sleep", lambda _s: None)
        # Force the wall clock forward so the timeout fires on the 2nd loop.
        seq = iter([0.0, 0.0, 100.0, 100.0, 100.0])
        monkeypatch.setattr(gclient.time, "time", lambda: next(seq))

        out = client.poll_research(conversation_id="c_test", authuser=0,
                                    poll_interval=0.01, timeout=5.0)
        assert out["timed_out"] is True
        assert out["done"] is False

    def test_backs_off_on_reject_code(self, client, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(gclient.time, "sleep", lambda s: sleeps.append(s))
        calls = [
            {"done": False, "in_progress": True, "text": None, "title": None,
             "rcid": None, "reason": "rate-limit", "raw_status": None,
             "reject_code": 7},
            {"done": True, "in_progress": False, "text": "# Done",
             "title": "T", "rcid": "rc_x", "reason": None, "raw_status": 2,
             "reject_code": None},
        ]
        monkeypatch.setattr(client, "_read_chat_status",
                            MagicMock(side_effect=calls))
        out = client.poll_research(conversation_id="c_test", authuser=0,
                                    poll_interval=1.0, timeout=60.0)
        assert out["done"] is True
        # Backoff must enforce >= 15s after the reject_code
        assert any(s >= 15.0 for s in sleeps), f"sleeps={sleeps}"
