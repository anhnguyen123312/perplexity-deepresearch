"""Tests for grok statsig capture helpers: profile key + headless default."""

from __future__ import annotations

import pytest

from deep_research import profile_config
from deep_research.grok import statsig


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.delenv("CHROME_PROFILE", raising=False)
    monkeypatch.delenv("CHROME_PROFILE_USED_GROK", raising=False)
    monkeypatch.delenv("GROK_STATSIG_HEADLESS", raising=False)


# --- _capture_profile_name: must match the key get_grok_cookies_cached reads ---
def test_capture_profile_name_defaults_to_default():
    assert statsig._capture_profile_name() == "Default"


def test_capture_profile_name_prefers_chosen():
    profile_config.set_chosen_profile("grok", "Profile 2")
    assert statsig._capture_profile_name() == "Profile 2"


def test_capture_profile_name_env_wins(monkeypatch):
    profile_config.set_chosen_profile("grok", "Profile 2")
    monkeypatch.setenv("CHROME_PROFILE", "Profile 9")
    assert statsig._capture_profile_name() == "Profile 9"


def test_capture_profile_name_legacy_env_fallback(monkeypatch):
    monkeypatch.setenv("CHROME_PROFILE_USED_GROK", "Profile 7")
    assert statsig._capture_profile_name() == "Profile 7"


# --- _default_headless: env override + headless-server detection ---
def test_default_headless_env_override(monkeypatch):
    monkeypatch.setenv("GROK_STATSIG_HEADLESS", "1")
    assert statsig._default_headless() is True
    monkeypatch.setenv("GROK_STATSIG_HEADLESS", "0")
    assert statsig._default_headless() is False


def test_default_headless_is_headless_by_default(monkeypatch):
    # No GROK_STATSIG_HEADLESS set → headless (hidden window), regardless of OS.
    monkeypatch.delenv("GROK_STATSIG_HEADLESS", raising=False)
    assert statsig._default_headless() is True


def test_default_headless_env_zero_forces_headful(monkeypatch):
    monkeypatch.setenv("GROK_STATSIG_HEADLESS", "0")
    assert statsig._default_headless() is False
