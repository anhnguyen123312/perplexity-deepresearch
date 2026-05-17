"""Inspect the SQLite cookies copy to see if perplexity rows exist (encrypted)."""
import os
import sqlite3
from pathlib import Path

p = Path(os.environ["TEMP"]) / "pdr-chrome-copy" / "Default" / "Network" / "Cookies"
print("file:", p, "exists=", p.exists(), "size=", p.stat().st_size if p.exists() else "-")

con = sqlite3.connect(str(p))
total = con.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
print("total rows:", total)

rows = con.execute(
    "SELECT host_key, name, length(encrypted_value), hex(substr(encrypted_value,1,3)) "
    "FROM cookies WHERE host_key LIKE ? ORDER BY host_key, name",
    ("%perplexity%",),
).fetchall()
print(f"perplexity rows: {len(rows)}")
for host, name, enc_len, prefix_hex in rows:
    prefix = bytes.fromhex(prefix_hex).decode("ascii", errors="replace")
    print(f"  {host:<30} {name:<50} len={enc_len:<5} prefix={prefix!r}")
