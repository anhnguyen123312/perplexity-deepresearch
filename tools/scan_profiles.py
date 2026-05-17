"""Scan all Chrome profiles for perplexity cookies (encrypted)."""
import os
import sqlite3
import shutil
import subprocess
import time
from pathlib import Path


def shared_copy(src, dst):
    """robocopy /B with backup privilege - only works post-kill or for non-locked files."""
    rc = subprocess.run(
        ["robocopy", str(src.parent), str(dst.parent), src.name,
         "/B", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:0", "/W:0"],
        capture_output=True,
    )
    return rc.returncode < 8


def main():
    user_data = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    print(f"User Data: {user_data}")
    print()

    for sub in user_data.iterdir():
        if not sub.is_dir():
            continue
        cookies_path = sub / "Network" / "Cookies"
        if not cookies_path.exists():
            cookies_path = sub / "Cookies"
        if not cookies_path.exists():
            continue

        # Try copy to temp
        tmp = Path(os.environ["TEMP"]) / f"scan-{sub.name}.db"
        if tmp.exists():
            tmp.unlink()
        try:
            shutil.copy2(cookies_path, tmp)
            copied = "shutil"
        except PermissionError:
            ok = shared_copy(cookies_path, tmp.parent / tmp.name)
            if not ok:
                print(f"[{sub.name}] LOCKED - cannot copy")
                continue
            copied = "robocopy"

        try:
            con = sqlite3.connect(str(tmp))
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
            total = -1
            perp = []
            if "cookies" in tables:
                total = con.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
                perp = con.execute(
                    "SELECT host_key, name, length(encrypted_value), "
                    "hex(substr(encrypted_value,1,3)) "
                    "FROM cookies WHERE host_key LIKE ? OR host_key LIKE ?",
                    ("%perplexity%", "%grok.com%"),
                ).fetchall()
            print(f"[{sub.name:<20}] copy={copied:<8} tables={tables} "
                  f"total={total} perplexity_or_grok={len(perp)}")
            for host, name, enc_len, prefix_hex in perp[:5]:
                prefix = bytes.fromhex(prefix_hex).decode("ascii", errors="replace")
                print(f"    {host:<30} {name:<50} len={enc_len:<5} prefix={prefix!r}")
            con.close()
        except sqlite3.DatabaseError as e:
            print(f"[{sub.name}] sqlite error: {e}")
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
