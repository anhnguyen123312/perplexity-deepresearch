"""Tests for the unified perplexity + grok config store."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from deep_research import profile_config as pc


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect both config.json and the legacy cookies.json to tmp_path."""
    cfg = tmp_path / "config.json"
    legacy = tmp_path / "cookies.json"
    monkeypatch.setenv("PERPLEXITY_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(legacy))
    monkeypatch.delenv("CHROME_PROFILE_USED", raising=False)
    return {"config": cfg, "legacy": legacy}


# --------------------------------------------------------------------------- #
# US-001: schema + low-level API
# --------------------------------------------------------------------------- #


class TestSchema:
    def test_empty_load_returns_valid_skeleton(self, isolate_config):
        cfg = pc.load_config()
        assert cfg["version"] == pc.CURRENT_VERSION
        assert set(cfg["providers"].keys()) >= {"perplexity", "grok"}
        assert cfg["providers"]["perplexity"]["expire_seconds"] == 86400
        assert cfg["providers"]["grok"]["expire_seconds"] == 43200
        assert cfg["providers"]["perplexity"]["profiles"] == {}
        assert cfg["providers"]["grok"]["profiles"] == {}
        # Not implicitly written
        assert not isolate_config["config"].exists()

    def test_save_then_load_roundtrip(self, isolate_config):
        cfg = pc.load_config()
        cfg["providers"]["perplexity"]["expire_seconds"] = 100
        pc.save_config(cfg)
        assert isolate_config["config"].exists()
        cfg2 = pc.load_config()
        assert cfg2["providers"]["perplexity"]["expire_seconds"] == 100

    def test_save_is_atomic(self, isolate_config):
        """save_config must use a tmp file + os.replace (no half-written config)."""
        cfg = pc.load_config()
        cfg["providers"]["perplexity"]["expire_seconds"] = 7
        pc.save_config(cfg)
        # Tmp file must not linger
        assert not isolate_config["config"].with_suffix(".json.tmp").exists()
        # Content must be valid JSON
        content = json.loads(isolate_config["config"].read_text())
        assert content["providers"]["perplexity"]["expire_seconds"] == 7

    def test_save_rejects_bad_version(self, isolate_config):
        with pytest.raises(ValueError, match="Unsupported config version"):
            pc.save_config({"version": 99, "providers": {}})

    def test_set_expire_seconds_persists(self, isolate_config):
        pc.set_expire_seconds("perplexity", 3600)
        assert pc.get_expire_seconds("perplexity") == 3600

    def test_set_expire_rejects_unknown_provider(self, isolate_config):
        with pytest.raises(ValueError, match="Unknown provider"):
            pc.set_expire_seconds("bogus", 1000)

    def test_set_expire_rejects_non_positive(self, isolate_config):
        with pytest.raises(ValueError, match="positive"):
            pc.set_expire_seconds("perplexity", 0)


# --------------------------------------------------------------------------- #
# US-002: per-profile entry CRUD
# --------------------------------------------------------------------------- #


class TestProfileEntry:
    def test_save_and_get_profile_entry(self, isolate_config):
        cookies = {"session_token": "tok", "session_token_name": "next-auth.session-token"}
        entry = pc.save_profile_entry("perplexity", "Default", cookies)
        assert entry["cookies"] == cookies
        assert "extracted_at" in entry
        assert "expires_at" in entry

        loaded = pc.get_profile_entry("perplexity", "Default")
        assert loaded == entry

    def test_get_missing_profile_returns_none(self, isolate_config):
        assert pc.get_profile_entry("perplexity", "Profile 99") is None

    def test_is_expired_true_when_past(self, isolate_config):
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        assert pc.is_expired({"expires_at": past}) is True

    def test_is_expired_false_when_future(self, isolate_config):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        assert pc.is_expired({"expires_at": future}) is False

    def test_list_valid_profiles_excludes_expired(self, isolate_config):
        # Active entry
        pc.save_profile_entry("perplexity", "Default", {"session_token": "a"})
        # Manually expire a second profile
        pc.save_profile_entry("perplexity", "Profile 1", {"session_token": "b"})
        cfg = pc.load_config()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cfg["providers"]["perplexity"]["profiles"]["Profile 1"]["expires_at"] = past
        pc.save_config(cfg)

        valid = pc.list_valid_profiles("perplexity")
        assert valid == ["Default"]

    def test_get_first_valid_honors_preferred_order(self, isolate_config):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "default"})
        pc.save_profile_entry("perplexity", "Profile 1", {"session_token": "p1"})
        result = pc.get_first_valid("perplexity", preferred_order=["Profile 1", "Default"])
        assert result is not None
        name, entry = result
        assert name == "Profile 1"
        assert entry["cookies"]["session_token"] == "p1"

    def test_get_first_valid_skips_expired(self, isolate_config):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "default"})
        pc.save_profile_entry("perplexity", "Profile 1", {"session_token": "p1"})
        cfg = pc.load_config()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cfg["providers"]["perplexity"]["profiles"]["Default"]["expires_at"] = past
        pc.save_config(cfg)
        result = pc.get_first_valid(
            "perplexity", preferred_order=["Default", "Profile 1"]
        )
        assert result is not None
        name, _ = result
        assert name == "Profile 1"

    def test_get_first_valid_returns_none_when_all_expired(self, isolate_config):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "x"})
        cfg = pc.load_config()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cfg["providers"]["perplexity"]["profiles"]["Default"]["expires_at"] = past
        pc.save_config(cfg)
        assert pc.get_first_valid("perplexity") is None

    def test_invalidate_profile_forces_re_scan(self, isolate_config):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "x"})
        pc.invalidate_profile("perplexity", "Default")
        entry = pc.get_profile_entry("perplexity", "Default")
        assert pc.is_expired(entry)

    def test_invalidate_missing_profile_is_noop(self, isolate_config):
        # Should not raise
        pc.invalidate_profile("perplexity", "Profile 99")


# --------------------------------------------------------------------------- #
# US-003: legacy cookies.json migration
# --------------------------------------------------------------------------- #


class TestLegacyMigration:
    def test_migrates_legacy_cookies(self, isolate_config, monkeypatch):
        legacy = isolate_config["legacy"]
        legacy.parent.mkdir(parents=True, exist_ok=True)
        extracted_at = datetime.now(timezone.utc).isoformat()
        legacy.write_text(json.dumps({
            "cookies": {"session_token": "tok", "session_token_name": "next-auth.session-token"},
            "extracted_at": extracted_at,
        }))
        monkeypatch.setenv("CHROME_PROFILE_USED", "Profile 2")

        cfg = pc.load_config()

        assert "Profile 2" in cfg["providers"]["perplexity"]["profiles"]
        entry = cfg["providers"]["perplexity"]["profiles"]["Profile 2"]
        assert entry["cookies"]["session_token"] == "tok"
        # expires_at = extracted + default expire (86400)
        ext = pc._parse_iso(entry["extracted_at"])
        exp = pc._parse_iso(entry["expires_at"])
        assert (exp - ext).total_seconds() == pytest.approx(86400, abs=1)
        # Config file was written
        assert isolate_config["config"].exists()
        # Legacy file is preserved
        assert legacy.exists()

    def test_migration_is_idempotent(self, isolate_config):
        import copy

        legacy = isolate_config["legacy"]
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({
            "cookies": {"session_token": "tok"},
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }))

        cfg1 = pc.load_config()
        first_entry = copy.deepcopy(
            cfg1["providers"]["perplexity"]["profiles"]["Default"]
        )

        # Mutate config to prove second load doesn't overwrite migration
        cfg1["providers"]["perplexity"]["profiles"]["Default"]["cookies"]["session_token"] = "modified"
        pc.save_config(cfg1)

        cfg2 = pc.load_config()
        assert cfg2["providers"]["perplexity"]["profiles"]["Default"]["cookies"]["session_token"] == "modified"
        # Migration must NOT re-run on second load (still 'modified', not reset to 'tok')
        assert first_entry["cookies"]["session_token"] == "tok"

    def test_no_legacy_file_no_migration(self, isolate_config):
        cfg = pc.load_config()
        assert cfg["providers"]["perplexity"]["profiles"] == {}

    def test_malformed_legacy_skipped(self, isolate_config):
        legacy = isolate_config["legacy"]
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("not json")
        cfg = pc.load_config()
        assert cfg["providers"]["perplexity"]["profiles"] == {}


# --------------------------------------------------------------------------- #
# US-006: import / export
# --------------------------------------------------------------------------- #


class TestImportExport:
    def test_export_then_import_roundtrip(self, isolate_config, tmp_path):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "a"})
        pc.save_profile_entry("grok", "Default", {"sso": "b"})

        dest = tmp_path / "export.json"
        pc.export_config(dest)
        assert dest.exists()
        exported = json.loads(dest.read_text())
        assert exported["version"] == pc.CURRENT_VERSION
        assert exported["providers"]["perplexity"]["profiles"]["Default"]["cookies"]["session_token"] == "a"
        assert exported["providers"]["grok"]["profiles"]["Default"]["cookies"]["sso"] == "b"

        # Simulate a fresh machine by wiping the active config
        isolate_config["config"].unlink()
        assert pc.load_config()["providers"]["perplexity"]["profiles"] == {}

        pc.import_config(dest)
        cfg = pc.load_config()
        assert cfg["providers"]["perplexity"]["profiles"]["Default"]["cookies"]["session_token"] == "a"
        assert cfg["providers"]["grok"]["profiles"]["Default"]["cookies"]["sso"] == "b"

    def test_import_merge_keeps_old_and_new(self, isolate_config, tmp_path):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "old"})

        # Build an exported config from a parallel store
        external_config_path = tmp_path / "other-config.json"
        other_cfg = {
            "version": pc.CURRENT_VERSION,
            "providers": {
                "perplexity": {
                    "expire_seconds": 86400,
                    "profiles": {
                        "Profile 1": {
                            "cookies": {"session_token": "imported"},
                            "extracted_at": datetime.now(timezone.utc).isoformat(),
                            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        }
                    },
                },
                "grok": {"expire_seconds": 43200, "profiles": {}},
            },
        }
        external_config_path.write_text(json.dumps(other_cfg))

        pc.import_config(external_config_path, merge=True)
        cfg = pc.load_config()
        # both profiles must be present
        assert "Default" in cfg["providers"]["perplexity"]["profiles"]
        assert "Profile 1" in cfg["providers"]["perplexity"]["profiles"]
        assert cfg["providers"]["perplexity"]["profiles"]["Default"]["cookies"]["session_token"] == "old"
        assert cfg["providers"]["perplexity"]["profiles"]["Profile 1"]["cookies"]["session_token"] == "imported"

    def test_import_replace_overwrites(self, isolate_config, tmp_path):
        pc.save_profile_entry("perplexity", "Default", {"session_token": "old"})

        external = tmp_path / "external.json"
        external.write_text(json.dumps({
            "version": pc.CURRENT_VERSION,
            "providers": {
                "perplexity": {"expire_seconds": 86400, "profiles": {}},
                "grok": {"expire_seconds": 43200, "profiles": {}},
            },
        }))
        pc.import_config(external, merge=False)
        cfg = pc.load_config()
        assert cfg["providers"]["perplexity"]["profiles"] == {}

    def test_import_preserves_timestamps(self, isolate_config, tmp_path):
        fixed_extracted = "2023-01-01T00:00:00+00:00"
        fixed_expires = "2099-01-01T00:00:00+00:00"
        external = tmp_path / "external.json"
        external.write_text(json.dumps({
            "version": pc.CURRENT_VERSION,
            "providers": {
                "perplexity": {
                    "expire_seconds": 86400,
                    "profiles": {
                        "Default": {
                            "cookies": {"session_token": "ported"},
                            "extracted_at": fixed_extracted,
                            "expires_at": fixed_expires,
                        }
                    },
                },
                "grok": {"expire_seconds": 43200, "profiles": {}},
            },
        }))
        pc.import_config(external)
        entry = pc.get_profile_entry("perplexity", "Default")
        assert entry["extracted_at"] == fixed_extracted
        assert entry["expires_at"] == fixed_expires

    def test_import_version_mismatch_raises(self, isolate_config, tmp_path):
        external = tmp_path / "bad.json"
        external.write_text(json.dumps({"version": 99, "providers": {}}))
        with pytest.raises(ValueError, match="version mismatch"):
            pc.import_config(external)

    def test_import_missing_providers_raises(self, isolate_config, tmp_path):
        external = tmp_path / "bad.json"
        external.write_text(json.dumps({"version": pc.CURRENT_VERSION}))
        with pytest.raises(ValueError, match="missing 'providers'"):
            pc.import_config(external)
