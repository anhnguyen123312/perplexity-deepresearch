"""Dynamic browser-fingerprint alignment + Cloudflare-challenge detection.

The "cloak" (TLS impersonation + ``user-agent`` / ``sec-ch-ua`` headers) must
track the locally installed Chrome so Cloudflare's JA3/JA4-vs-UA cross-checks
stay consistent. Hardcoded versions drift on every Chrome auto-update and raise
the challenge rate over time (Cloudflare's JA4 ``browser_ratio`` decays for an
ageing fingerprint), which is exactly the "cloak bị cũ → hay dính Cloudflare"
symptom this module exists to cure.

Design invariants (see ``docs/cloak-selfheal/research.md``):

* **UA + ``sec-ch-ua`` major MUST equal the chosen impersonation target major**
  — not necessarily the local Chrome major. Sending ``chrome146`` TLS with a
  ``Chrome/148`` UA header is a detectable mismatch.
* **"Nearest-lower" target is safe**: curl_cffi / rnet only publish a new target
  when the on-the-wire fingerprint actually changes, so picking the highest
  available major ``<=`` the real one reproduces a valid fingerprint.
* For **grok** the replayed ``cf_clearance`` is bound to the *issuing* browser
  (CloakBrowser's bundled Chromium), so the grok major derives from
  :func:`cloakbrowser_binary_major`, NOT the user's local Chrome.

Everything here is pure/­defensive: detection failures fall back to a sane floor
so a flaky probe never breaks a request path.
"""

from __future__ import annotations

import functools
import re
import subprocess
import sys
from pathlib import Path

# Safe floors used when runtime detection fails. Chosen to match what the
# bundled deps currently ship (curl_cffi 0.15 → chrome146; CloakBrowser 0.3.28
# binary → Chromium 145; installed rnet → Emulation.Chrome145).
FALLBACK_LOCAL_MAJOR = 146
FALLBACK_CLOAKBROWSER_MAJOR = 145

# Chrome majors curl_cffi can impersonate (descending). Captured 2026-06 from
# curl_cffi 0.15.x; ``pick_curl_cffi_target`` selects the nearest <= target so
# unknown-but-higher local Chromes degrade gracefully to the newest available.
CURL_CFFI_CHROME_TARGETS: tuple[int, ...] = (
    146, 145, 142, 136, 133, 131, 124, 123, 120, 119, 116, 110, 107, 104, 101, 100, 99,
)


# --------------------------------------------------------------------------- #
# Version parsing (pure)
# --------------------------------------------------------------------------- #
def parse_major(version_text: str | None) -> int | None:
    """Extract the leading Chrome major from a version string.

    Accepts ``"148.0.7778.215"``, ``"Google Chrome 148.0.7778.215"``,
    ``"Chromium 145.0.7632.109.2"`` etc. Returns ``None`` when no
    ``<major>.<minor>.<build>`` pattern is present.
    """
    if not version_text:
        return None
    m = re.search(r"(\d+)\.\d+\.\d+", version_text)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# Local Chrome detection (cached per process)
# --------------------------------------------------------------------------- #
def _detect_chrome_version_text() -> str | None:
    """Return the raw Chrome version string for the current OS, or None."""
    try:
        if sys.platform == "darwin":
            # Prefer the cheap "Last Version" marker file (no process spawn);
            # fall back to invoking the binary with --version.
            marker = (
                Path.home()
                / "Library/Application Support/Google/Chrome/Last Version"
            )
            if marker.is_file():
                txt = marker.read_text(errors="ignore").strip()
                if parse_major(txt):
                    return txt
            binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if Path(binary).exists():
                return subprocess.check_output(
                    [binary, "--version"], stderr=subprocess.DEVNULL, text=True, timeout=5
                )
        elif sys.platform.startswith("linux"):
            for cmd in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
                try:
                    return subprocess.check_output(
                        [cmd, "--version"], stderr=subprocess.DEVNULL, text=True, timeout=5
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
        elif sys.platform == "win32":
            import winreg  # type: ignore

            for hive, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
                ),
            ):
                try:
                    key = winreg.OpenKey(hive, sub)
                    name = "version" if "BLBeacon" in sub else "DisplayVersion"
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    continue
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


@functools.lru_cache(maxsize=1)
def detect_chrome_major() -> int | None:
    """Best-effort local Chrome major version (cached for the process)."""
    return parse_major(_detect_chrome_version_text())


@functools.lru_cache(maxsize=1)
def cloakbrowser_binary_major() -> int | None:
    """Major version of the Chromium binary CloakBrowser actually runs.

    grok's replayed ``cf_clearance`` is bound to *this* browser's UA + TLS, so
    the grok impersonation must follow it (not the user's local Chrome).
    """
    try:
        import cloakbrowser  # type: ignore

        info = cloakbrowser.binary_info()
        return parse_major(info.get("version")) or parse_major(
            getattr(cloakbrowser, "CHROMIUM_VERSION", None)
        )
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Target pickers (pure — nearest available <= major)
# --------------------------------------------------------------------------- #
def pick_curl_cffi_target(major: int | None, available: tuple[int, ...] | None = None) -> str:
    """Return the curl_cffi ``impersonate=`` string for ``major``.

    Picks the highest supported major ``<=`` ``major`` (nearest-lower is a valid
    fingerprint); falls back to the newest available when ``major`` is unknown
    or older than everything supported.
    """
    targets = tuple(sorted(available or CURL_CFFI_CHROME_TARGETS, reverse=True))
    if major is not None:
        for v in targets:
            if major >= v:
                return f"chrome{v}"
    return f"chrome{targets[0]}"


def _available_rnet_majors() -> list[int]:
    try:
        import rnet  # type: ignore

        out = []
        for name in dir(rnet.Emulation):
            if name.startswith("Chrome"):
                try:
                    out.append(int(name[len("Chrome"):]))
                except ValueError:
                    continue
        return sorted(out)
    except Exception:
        return []


def pick_rnet_emulation_name(major: int | None, available_majors: list[int] | None = None) -> str:
    """Return the ``rnet.Emulation`` attribute name nearest-lower to ``major``."""
    majors = sorted(available_majors if available_majors is not None else _available_rnet_majors())
    if not majors:
        # No rnet introspection (e.g. unit test) — echo the request so the
        # caller's getattr fallback decides.
        return f"Chrome{major or FALLBACK_CLOAKBROWSER_MAJOR}"
    if major is None:
        return f"Chrome{majors[-1]}"  # unknown local Chrome → newest available
    le = [v for v in majors if v <= major]
    return f"Chrome{max(le) if le else min(majors)}"


def get_rnet_emulation(major: int | None):
    """Resolve the actual ``rnet.Emulation`` member nearest-lower to ``major``.

    Returns ``None`` if rnet is unavailable so callers keep their own fallback.
    """
    try:
        import rnet  # type: ignore

        name = pick_rnet_emulation_name(major, _available_rnet_majors())
        return getattr(rnet.Emulation, name, None)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Header construction (pure — major MUST match the impersonation target)
# --------------------------------------------------------------------------- #
def _platform_ua_token() -> tuple[str, str]:
    """(os_token, sec_ch_ua_platform) for the current OS."""
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64", '"Windows"'
    if sys.platform.startswith("linux"):
        return "X11; Linux x86_64", '"Linux"'
    return "Macintosh; Intel Mac OS X 10_15_7", '"macOS"'


def build_ua(major: int) -> str:
    """Chrome desktop UA string for ``major`` on the current OS."""
    os_token, _ = _platform_ua_token()
    return (
        f"Mozilla/5.0 ({os_token}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )


def build_sec_ch_ua(major: int) -> str:
    """``sec-ch-ua`` value for ``major`` (must match the UA + TLS target)."""
    return f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not?A_Brand";v="99"'


def sec_ch_ua_platform() -> str:
    return _platform_ua_token()[1]


# --------------------------------------------------------------------------- #
# Convenience composers (detection + pick + safe floor)
# --------------------------------------------------------------------------- #
def perplexity_cloak() -> dict[str, str]:
    """Aligned ``{impersonate, user_agent, sec_ch_ua, sec_ch_ua_platform}`` for
    the Perplexity (curl_cffi) path, derived from the local Chrome."""
    target = pick_curl_cffi_target(detect_chrome_major() or FALLBACK_LOCAL_MAJOR)
    major = int(target.removeprefix("chrome"))
    return {
        "impersonate": target,
        "user_agent": build_ua(major),
        "sec_ch_ua": build_sec_ch_ua(major),
        "sec_ch_ua_platform": sec_ch_ua_platform(),
    }


def gemini_cloak() -> dict[str, str]:
    """Aligned cloak for the Gemini (curl_cffi) path.

    Gemini rides the same curl_cffi local-Chrome transport as Perplexity, so it
    shares the identical fingerprint set — UA = ``sec-ch-ua`` = TLS impersonation
    target, all derived from the locally installed Chrome. This replaces the old
    hardcoded ``IMPERSONATE_TARGET=chrome146`` + ``UA=Chrome/148`` mismatch.
    """
    return perplexity_cloak()


def grok_major() -> int:
    """The Chrome major grok must impersonate (follows CloakBrowser's binary)."""
    return cloakbrowser_binary_major() or FALLBACK_CLOAKBROWSER_MAJOR


# --------------------------------------------------------------------------- #
# Cloudflare-challenge detection (pure predicate, shared by both clients)
# --------------------------------------------------------------------------- #
# Unambiguous Cloudflare challenge identifiers — script / cookie / URL tokens
# that never appear in normal prose or answer text, so they are safe to match on
# any non-success body.
_CF_STRICT_MARKERS = re.compile(
    r"__cf_chl"
    r"|cf_chl_opt"
    r"|challenges\.cloudflare\.com"
    r"|cdn-cgi/challenge-platform",
    re.IGNORECASE,
)
# Human-readable interstitial phrases — these CAN appear in ordinary text, so
# they only count alongside a Cloudflare server header (``is_cf``).
_CF_PROSE_MARKERS = re.compile(
    r"Just a moment\.\.\."
    r"|Enable JavaScript and cookies to continue"
    r"|Checking your browser before accessing",
    re.IGNORECASE,
)


def is_cloudflare_challenge(status: int, headers: dict | None = None, text: str = "") -> bool:
    """True iff a response is a Cloudflare challenge/block (not a real answer).

    Confidence order (research.md §4): ``cf-mitigated: challenge`` header is
    definitive; then 503 behind Cloudflare; then unambiguous CF challenge body
    tokens; then a prose interstitial *with* a Cloudflare server header; finally
    the hidden 200 interstitial.

    A clean ``200`` with no Cloudflare server header is NEVER a challenge — this
    guards against false positives when the answer's own text mentions
    Cloudflare (e.g. a Grok reply ABOUT Cloudflare, returned as 200 NDJSON). A
    bare ``403``/``429`` with Cloudflare server headers but NO ``cf-mitigated``
    and no challenge body tokens is treated as a normal app auth/rate failure
    (perplexity.ai and grok.com both sit fully behind Cloudflare, so a genuine
    auth-403 also carries ``cf-ray`` — flagging it as a challenge would misroute
    real auth failures into the browser-solve path).
    """
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}

    if h.get("cf-mitigated", "").lower() == "challenge":
        return True

    is_cf = "cloudflare" in h.get("server", "").lower() or "cf-ray" in h

    # 503 behind Cloudflare is the classic "I'm Under Attack" interstitial.
    if status == 503 and is_cf:
        return True

    # A normal successful 200 with no Cloudflare markers is a real app response —
    # do NOT scan its body (the answer may legitimately mention Cloudflare).
    if status == 200 and not is_cf:
        return False

    if text and _CF_STRICT_MARKERS.search(text):
        return True
    if is_cf and text and _CF_PROSE_MARKERS.search(text):
        return True
    if (
        status == 200
        and is_cf
        and text
        and len(text) < 10_000
        and "<title>" in text.lower()
        and "cloudflare" in text.lower()
    ):
        return True
    return False
