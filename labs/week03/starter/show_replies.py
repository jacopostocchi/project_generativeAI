import json
import sys
from pathlib import Path

PATH = Path("../../../artifacts/traces.jsonl")
wanted = sys.argv[1:] or ["Q-22", "Q-23", "Q-07"]

latest = {}   # (case_id, kind) -> record, the last one wins
for line in PATH.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    if r.get("week") != 3:
        continue
    names = [s["name"] for s in r.get("steps", [])]
    kind = "router" if any(n.endswith(":respond") for n in names) else "monolith"
    latest[(r["case_id"], kind)] = r

for cid in wanted:
    print("=" * 72)
    for kind in ("monolith", "router"):
        r = latest.get((cid, kind))
        if not r:
            print(f"[{cid}] {kind}: no record")
            continue
        print(f"[{cid}] {kind}  started {r['started_at']}")
        if kind == "router":
            print(f"  notes: {r.get('notes')}")
        print("  input :", r["input"][:120].replace("\n", " "))
        print("  output:")
        for out_line in (r.get("output") or "").splitlines():
            print("    " + out_line)
        print()
