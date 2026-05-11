"""
Unified config store for perplexity + grok cookies.

Single ``config.json`` holds per-provider expire policy and per-Chrome-profile
cookie entries. Replaces the legacy ``cookies.json`` (perplexity-only, single
profile, single expire). On first load, an existing legacy ``cookies.json`` is
migrated in once and left in place for rollback safety.

Schema (version 1)::

    {
      "version": 1,
      "providers": {
        "perplexity": {
          "expire_seconds": 86400,
          "profiles": {
            "<chrome_profile>": {
              "cookies": {...},
              "extracted_at": "ISO-8601 UTC",
              "expires_at":   "ISO-8601 UTC"
            }
          }
        },
        "grok": { ... }
      }
    }

All timestamps are stored as ISO-8601 with explicit UTC offset so the file is
portable across machines and timezones (matters for the import/export flow).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


CURRENT_VERSION = 1

PROVIDER_PERPLEXITY = "perplexity"
PROVIDER_GROK = "grok"
ALL_PROVIDERS = (PROVIDER_PERPLEXITY, PROVIDER_GROK)

DEFAULT_EXPIRE_SECONDS: dict[str, int] = {
    PROVIDER_PERPLEXITY: 86400,   # 24h — matches legacy COOKIE_MAX_AGE
    PROVIDER_GROK: 43200,         # 12h — grok sessions roll faster in practice
}


def get_config_path() -> Path:
    """Resolve ``config.json`` location at call time.

    Resolution order:
      1. ``PERPLEXITY_CONFIG_FILE`` env var (absolute path)
      2. Platform data dir:
         - Windows: ``%LOCALAPPDATA%/perplexity-deep-research/config.json``
         - POSIX:   ``${XDG_DATA_HOME:-~/.local/share}/perplexity-deep-research/config.json``
    """
    if env := os.environ.get("PERPLEXITY_CONFIG_FILE"):
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    return Path(base) / "perplexity-deep-research" / "config.json"


def _legacy_cookies_path() -> Path:
    """Location of the pre-config-store ``cookies.json`` (perplexity-only)."""
    if env := os.environ.get("PERPLEXITY_COOKIES_FILE"):
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    return Path(base) / "perplexity-deep-research" / "cookies.json"


def _empty_config() -> dict:
    return {
        "version": CURRENT_VERSION,
        "providers": {
            name: {
                "expire_seconds": DEFAULT_EXPIRE_SECONDS[name],
                "profiles": {},
            }
            for name in ALL_PROVIDERS
        },
    }


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; assume UTC when the offset is missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_schema(config: dict) -> dict:
    """Validate / repair a config dict; raise on incompatible version."""
    if "version" not in config:
        config["version"] = CURRENT_VERSION
    elif config["version"] != CURRENT_VERSION:
        raise ValueError(
            f"Unsupported config version {config['version']!r} "
            f"(expected {CURRENT_VERSION})"
        )
    config.setdefault("providers", {})
    for name in ALL_PROVIDERS:
        provider = config["providers"].setdefault(name, {})
        provider.setdefault("expire_seconds", DEFAULT_EXPIRE_SECONDS[name])
        provider.setdefault("profiles", {})
    return config


def _migrate_legacy(config: dict) -> bool:
    """Import a legacy ``cookies.json`` into the perplexity provider.

    Only fires when the perplexity profiles dict is empty (so a re-run is a
    no-op). Returns True iff an entry was added.
    """
    legacy = _legacy_cookies_path()
    if not legacy.exists():
        return False
    perplexity = config["providers"][PROVIDER_PERPLEXITY]
    if perplexity["profiles"]:
        return False
    try:
        data = json.loads(legacy.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    cookies = data.get("cookies")
    extracted_at = data.get("extracted_at")
    if not cookies or not extracted_at:
        return False
    try:
        extracted_dt = _parse_iso(extracted_at)
    except ValueError:
        return False
    profile_name = os.environ.get("CHROME_PROFILE_USED") or "Default"
    expires_dt = extracted_dt + timedelta(seconds=perplexity["expire_seconds"])
    perplexity["profiles"][profile_name] = {
        "cookies": cookies,
        "extracted_at": extracted_dt.isoformat(),
        "expires_at": expires_dt.isoformat(),
    }
    return True


def load_config(path: Optional[Path] = None) -> dict:
    """Load the config; migrate legacy ``cookies.json`` on first run."""
    path = path or get_config_path()
    if path.exists():
        try:
            config = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            config = _empty_config()
        return _ensure_schema(config)
    config = _empty_config()
    if _migrate_legacy(config):
        save_config(config, path)
    return config


def save_config(config: dict, path: Optional[Path] = None) -> None:
    """Atomic write of the config dict (validates schema first)."""
    path = path or get_config_path()
    _ensure_schema(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, sort_keys=False))
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Expire-policy helpers
# --------------------------------------------------------------------------- #


def get_expire_seconds(provider: str, path: Optional[Path] = None) -> int:
    return load_config(path)["providers"][provider]["expire_seconds"]


def set_expire_seconds(provider: str, seconds: int, path: Optional[Path] = None) -> None:
    if provider not in ALL_PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; valid: {ALL_PROVIDERS}")
    if seconds <= 0:
        raise ValueError("expire_seconds must be positive")
    config = load_config(path)
    config["providers"][provider]["expire_seconds"] = int(seconds)
    save_config(config, path)


# --------------------------------------------------------------------------- #
# Per-profile entry CRUD
# --------------------------------------------------------------------------- #


def save_profile_entry(
    provider: str,
    chrome_profile: str,
    cookies: dict,
    path: Optional[Path] = None,
) -> dict:
    """Persist ``cookies`` for ``(provider, chrome_profile)`` with computed expiry.

    Returns the entry that was written (handy for tests and CLI output).
    """
    if provider not in ALL_PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; valid: {ALL_PROVIDERS}")
    config = load_config(path)
    expire_s = config["providers"][provider]["expire_seconds"]
    now = datetime.now(timezone.utc)
    entry = {
        "cookies": cookies,
        "extracted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expire_s)).isoformat(),
    }
    config["providers"][provider]["profiles"][chrome_profile] = entry
    save_config(config, path)
    return entry


def get_profile_entry(
    provider: str, chrome_profile: str, path: Optional[Path] = None
) -> Optional[dict]:
    config = load_config(path)
    return config["providers"][provider]["profiles"].get(chrome_profile)


def is_expired(entry: dict) -> bool:
    return datetime.now(timezone.utc) >= _parse_iso(entry["expires_at"])


def list_valid_profiles(provider: str, path: Optional[Path] = None) -> list[str]:
    config = load_config(path)
    profiles = config["providers"][provider]["profiles"]
    return [name for name, entry in profiles.items() if not is_expired(entry)]


def invalidate_profile(
    provider: str, chrome_profile: str, path: Optional[Path] = None
) -> None:
    """Force-expire a stored entry (sets ``expires_at`` to now).

    Used by API clients when a stored cookie set fails auth — the next call
    will trigger a fresh scan instead of reusing the stale entry.
    """
    config = load_config(path)
    entry = config["providers"][provider]["profiles"].get(chrome_profile)
    if entry is None:
        return
    entry["expires_at"] = datetime.now(timezone.utc).isoformat()
    save_config(config, path)


def get_first_valid(
    provider: str,
    preferred_order: Optional[list[str]] = None,
    path: Optional[Path] = None,
) -> Optional[tuple[str, dict]]:
    """Return ``(profile_name, entry)`` for the first non-expired profile.

    ``preferred_order`` is consulted first (preserves caller's preferred Chrome
    profile order); profiles outside that list are tried last in insertion
    order. Returns ``None`` when every stored entry has expired or none exist.
    """
    config = load_config(path)
    profiles = config["providers"][provider]["profiles"]
    order: list[str] = []
    if preferred_order:
        for name in preferred_order:
            if name in profiles and name not in order:
                order.append(name)
    for name in profiles:
        if name not in order:
            order.append(name)
    for name in order:
        entry = profiles[name]
        if not is_expired(entry):
            return name, entry
    return None


# --------------------------------------------------------------------------- #
# Import / Export
# --------------------------------------------------------------------------- #


def export_config(dest: Path, path: Optional[Path] = None) -> Path:
    """Atomic copy of the active config to ``dest``. Returns the dest path."""
    config = load_config(path)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, sort_keys=False))
    os.replace(tmp, dest)
    return dest


def import_config(
    src: Path, merge: bool = True, path: Optional[Path] = None
) -> dict:
    """Import an exported config.

    ``merge=True`` (default): per-provider, per-profile dict update — new
    profiles are added, existing profiles are overwritten by the incoming
    entry. The provider ``expire_seconds`` from the incoming file wins when
    present.

    ``merge=False``: replace the entire config with the imported one (after
    schema validation).
    """
    src = Path(src)
    try:
        imported = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot read config from {src}: {e}") from e
    if imported.get("version") != CURRENT_VERSION:
        raise ValueError(
            f"Config version mismatch: file is {imported.get('version')!r}, "
            f"expected {CURRENT_VERSION}"
        )
    if "providers" not in imported:
        raise ValueError("Imported config missing 'providers' key")

    if not merge:
        save_config(_ensure_schema(imported), path)
        return load_config(path)

    current = load_config(path)
    for provider_name, provider_data in imported["providers"].items():
        target = current["providers"].setdefault(
            provider_name,
            {
                "expire_seconds": DEFAULT_EXPIRE_SECONDS.get(provider_name, 86400),
                "profiles": {},
            },
        )
        if "expire_seconds" in provider_data:
            target["expire_seconds"] = provider_data["expire_seconds"]
        for profile_name, entry in provider_data.get("profiles", {}).items():
            target["profiles"][profile_name] = entry
    save_config(current, path)
    return current
