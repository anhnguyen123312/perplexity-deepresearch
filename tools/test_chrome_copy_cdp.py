"""
Windows-only POC: extract perplexity.ai cookies from a COPIED Chrome profile
by launching the user's REAL chrome.exe with --remote-debugging-port (CDP) and
calling Network.getAllCookies.

Theory: Chrome 136+ blocks --remote-debugging-port for the DEFAULT user-data-dir.
But if we copy User Data to a temp dir, that becomes a NON-default dir → CDP
should be allowed. And since we use the real chrome.exe (in Program Files),
ABE elevation_service path validation passes.

Open question (the test): when chrome.exe launches with a copied user-data-dir,
will it still decrypt the v20-encrypted cookies that were originally encrypted
with the user's master key? Or is the app_bound_encrypted_key in Local State
bound to the original directory path and unreadable from the copy?

Run on Windows:
    python tools\\test_chrome_copy_cdp.py

Expected outcomes:
    A) Prints cookies including "__Secure-next-auth.session-token"
       → SUCCESS. The copy + real-chrome + CDP path works. Integrate it.
    B) Prints cookies but session-token is empty/garbled
       → ABE rejected, copy approach dead, fall back to login-once.
    C) chrome.exe refuses to launch / CDP port never opens
       → Chrome 136+ block tighter than expected.
    D) DevToolsActivePort never written
       → Same as C.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


CHROME_EXE_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def find_chrome_exe() -> Path:
    for p in CHROME_EXE_CANDIDATES:
        if p.exists():
            return p
    raise RuntimeError(
        f"chrome.exe not found in any of: {CHROME_EXE_CANDIDATES}"
    )


def _enable_backup_privilege() -> None:
    """Enable SeBackupPrivilege so CreateFile with FILE_FLAG_BACKUP_SEMANTICS bypasses ACL/sharing locks."""
    import win32api
    import win32con
    import win32security
    try:
        h = win32api.GetCurrentProcess()
        token = win32security.OpenProcessToken(
            h, win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY
        )
        luid = win32security.LookupPrivilegeValue(None, "SeBackupPrivilege")
        win32security.AdjustTokenPrivileges(
            token, False, [(luid, win32con.SE_PRIVILEGE_ENABLED)]
        )
    except Exception as e:
        print(f"[!] Could not enable SeBackupPrivilege: {e}", file=sys.stderr)


def _shared_copy(src: Path, dst: Path) -> None:
    """Copy locked SQLite file using FILE_FLAG_BACKUP_SEMANTICS + SeBackupPrivilege."""
    import win32con
    import win32file
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    try:
        h = win32file.CreateFile(
            str(src),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
    except Exception:
        # Fall back to robocopy /B (also backup-read but as a process)
        rc = subprocess.run(
            [
                "robocopy",
                str(src.parent),
                str(dst.parent),
                src.name,
                "/B",
                "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
                "/R:1", "/W:1",
            ],
            capture_output=True,
        )
        # robocopy returns 1 (success with copies) or 0 (no work). >=8 = error.
        if rc.returncode >= 8:
            raise RuntimeError(
                f"robocopy failed for {src}: rc={rc.returncode}\n"
                f"stdout={rc.stdout.decode(errors='ignore')}\n"
                f"stderr={rc.stderr.decode(errors='ignore')}"
            )
        return
    try:
        with open(dst, "wb") as out:
            while True:
                rc, data = win32file.ReadFile(h, 1024 * 1024)
                if rc != 0 or not data:
                    break
                out.write(data)
    finally:
        h.close()


def copy_profile(src_root: Path, dst_root: Path) -> None:
    """Copy minimum files needed for cookies + ABE master key."""
    _enable_backup_privilege()
    if dst_root.exists():
        shutil.rmtree(dst_root, ignore_errors=True)
    dst_root.mkdir(parents=True)

    # Local State (has os_crypt.app_bound_encrypted_key) — REQUIRED
    _shared_copy(src_root / "Local State", dst_root / "Local State")

    # Default profile — Cookies live here
    src_default = src_root / "Default"
    dst_default = dst_root / "Default"
    dst_default.mkdir()
    for name in ("Cookies", "Login Data", "Preferences"):
        s = src_default / name
        if s.exists():
            _shared_copy(s, dst_default / name)
    # Network/Cookies (newer Chrome) — this one Chrome holds with exclusive lock
    src_network = src_default / "Network"
    if src_network.exists():
        dst_network = dst_default / "Network"
        dst_network.mkdir(exist_ok=True)
        for name in ("Cookies",):
            s = src_network / name
            if s.exists():
                try:
                    _shared_copy(s, dst_network / name)
                    print(f"[+] Network/{name} copied")
                except Exception as e:
                    print(f"[!] Network/{name} skipped (locked): {e}")


def wait_for_devtools_port(profile_dir: Path, timeout: float = 30.0) -> int:
    """Chrome writes DevToolsActivePort file with the actual port (when --remote-debugging-port=0)."""
    f = profile_dir / "DevToolsActivePort"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if f.exists():
            try:
                content = f.read_text().strip().splitlines()
                if content:
                    return int(content[0])
            except Exception:
                pass
        time.sleep(0.2)
    raise TimeoutError(f"DevToolsActivePort not written within {timeout}s at {f}")


def get_cookies_via_cdp(port: int, url: str) -> list[dict]:
    """Use CDP HTTP /json + WebSocket to call Network.getAllCookies."""
    try:
        import websocket  # type: ignore
    except ImportError:
        print("[!] websocket-client not installed. pip install websocket-client",
              file=sys.stderr)
        sys.exit(2)

    # 1. Get the BROWSER-level WebSocket so we can spawn targets
    ver = json.loads(
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5).read()
    )
    browser_ws = ver["webSocketDebuggerUrl"]

    bws = websocket.create_connection(browser_ws, timeout=10)
    msg_id = [0]
    def call(method, params=None):
        msg_id[0] += 1
        bws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
        while True:
            r = json.loads(bws.recv())
            if r.get("id") == msg_id[0]:
                return r

    # Spawn a target navigating to perplexity (so cookies for that domain load)
    res = call("Target.createTarget", {"url": url})
    target_id = res["result"]["targetId"]
    res = call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
    session_id = res["result"]["sessionId"]
    bws.close()

    # 2. Connect to the page WebSocket directly
    targets = json.loads(
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5).read()
    )
    page_target = next((t for t in targets if t.get("id") == target_id), None)
    if page_target is None:
        raise RuntimeError(f"could not find target {target_id} in /json")
    ws_url = page_target["webSocketDebuggerUrl"]

    # 2. WebSocket call Network.getAllCookies on the page session
    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        # Wait for navigation/load
        time.sleep(3)
        # Drain any pending messages
        ws.settimeout(0.5)
        try:
            while True:
                ws.recv()
        except Exception:
            pass
        ws.settimeout(10)

        ws.send(json.dumps({"id": 99, "method": "Network.getAllCookies"}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 99:
                return msg.get("result", {}).get("cookies", [])
    finally:
        ws.close()


def main() -> int:
    if sys.platform != "win32":
        print("This POC is Windows-only.")
        return 1

    kill_chrome = "--kill-chrome" in sys.argv

    chrome_exe = find_chrome_exe()
    print(f"[*] chrome.exe: {chrome_exe}")

    src = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    dst = Path(os.environ["TEMP"]) / "pdr-chrome-copy"

    if kill_chrome:
        print("[*] Killing chrome.exe processes briefly...")
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                       capture_output=True)
        time.sleep(1.5)

    print(f"[*] Copy {src} -> {dst}")
    copy_profile(src, dst)

    args = [
        str(chrome_exe),
        f"--user-data-dir={dst}",
        "--remote-debugging-port=0",  # let Chrome pick free port
        "--remote-allow-origins=*",   # required since Chrome 111
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-background-networking",
        "--disable-default-apps",
        "--mute-audio",
    ]
    print(f"[*] Launch: {' '.join(args)}")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        port = wait_for_devtools_port(dst)
        print(f"[*] CDP port = {port}")
        cookies = get_cookies_via_cdp(port, "https://www.perplexity.ai/")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"[*] Got {len(cookies)} cookies")
    perplexity = [c for c in cookies if "perplexity" in c.get("domain", "")]
    print(f"[*] perplexity.ai cookies: {len(perplexity)}")
    for c in perplexity:
        v = c.get("value", "")
        v_preview = (v[:30] + "...") if len(v) > 30 else v
        print(f"    {c['name']:<48} {v_preview}")

    session_token = next(
        (c for c in perplexity
         if c["name"] in ("__Secure-next-auth.session-token",
                          "next-auth.session-token")),
        None,
    )
    if session_token and session_token.get("value"):
        print()
        print("[+] SUCCESS: session-token found")
        print(f"    name  = {session_token['name']}")
        print(f"    len   = {len(session_token['value'])}")
        return 0
    else:
        print()
        print("[-] FAIL: no session-token / empty value")
        print("    -> ABE likely refused decryption from copied dir")
        print("    -> fall back to login-once approach")
        return 1


if __name__ == "__main__":
    sys.exit(main())
