"""Checkpoint 2 numbers, from the file 01_compare.py writes.

    python 02_summary.py [artifacts/week05_architectures.json]

Prints: the table, why attempts never reached a fix, every proposed fix in
full, the reviewer's verdicts (and how many were valid), and its extra cost.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

NO_VERDICT = "reviewer produced no valid verdict"

path = Path(sys.argv[1] if len(sys.argv) > 1
            else "artifacts/week05_architectures.json")
rows = json.loads(path.read_text(encoding="utf-8"))["rows"]

by_arch: dict[str, list[dict]] = {}
for row in rows:
    by_arch.setdefault(row["architecture"], []).append(row)


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


print(f"{'architecture':<22}{'green':>8}{'no fix':>8}{'tokens':>10}{'seconds':>9}")
print("-" * 57)
for arch, group in by_arch.items():
    green = sum(bool(r["green"]) for r in group)
    nofix = ("-" if arch.startswith("A")
             else str(sum(1 for r in group if not r.get("fix"))))
    print(f"{arch:<22}{green:>4}/{len(group):<3}{nofix:>8}"
          f"{mean([r['tokens'] for r in group]):>10.0f}"
          f"{mean([r['seconds'] for r in group]):>9.1f}")
print("tokens: calls that failed validation are not counted. seconds: they are.")

baseline = by_arch.get("A baseline", [])
if baseline:
    print("\nbaseline tool calls per run:",
          [r.get("tool_calls") for r in baseline],
          "(0 can mean the run raised before the count)")
    for i, r in enumerate(baseline, 1):
        if r.get("sequence"):
            print(f"  run {i}: {r['refused']} refused by apply_fix: "
                  f"{r['sequence']}")

planned = [r for r in rows if r["architecture"].startswith(("B", "C"))]
failed = [r for r in planned if not r.get("fix")]
print(f"\nattempts that never reached a fix: {len(failed)} of {len(planned)}")
for reason, n in Counter(r.get("applied") for r in failed).items():
    print(f"  {n} x {reason}")
for r in failed:
    if r.get("failure_detail"):
        print(f"  {r['architecture']}: {r['failure_detail'][:200]}")

print("\nevery proposed fix, in full:")
for r in planned:
    if r.get("fix"):
        state = "green" if r["green"] else "RED  "
        print(f"  [{state}] {r['architecture']}: {r['fix']}")

print("\nwhat each run actually changed (a green run can still be wrong):")
for r in rows:
    if "changed" in r:
        state = "green" if r["green"] else "RED  "
        print(f"  [{state}] {r['architecture']}: "
              f"{r.get('changed') or '(nothing)'}")

reviewed = by_arch.get("C planner+reviewer", [])
judged = [r for r in reviewed if r.get("fix")]
valid = [r for r in judged
         if r.get("verdict") and r.get("verdict_reason") != NO_VERDICT]
print(f"\nreviewer: {len(valid)} valid verdicts out of {len(judged)} fixes shown")
for i, r in enumerate(judged, 1):
    print(f"  fix {i}: {r.get('verdict')}: {r.get('verdict_reason')}")
    if r.get("review_error"):
        print(f"          why no verdict: {r['review_error'][:200]}")

print("\nextra cost of the reviewer, per measured call:")
if any("review_tokens" in r for r in reviewed):
    measured = [r for r in judged if r.get("review_tokens")]
    for i, r in enumerate(measured, 1):
        print(f"  call {i}: {r['review_tokens']} tokens, {r['review_seconds']} s")
    if measured:
        print(f"  mean : {mean([r['review_tokens'] for r in measured]):.0f} "
              f"tokens, {mean([r['review_seconds'] for r in measured]):.1f} s")
    else:
        print("  no reviewer call produced a valid verdict: cost not measured")
else:
    b = by_arch.get("B planner", [])
    if b and reviewed:
        print("  (no review_tokens in these rows: C minus B, two independent "
              "samples, so it is noisy)")
        print(f"  {mean([r['tokens'] for r in reviewed]) - mean([r['tokens'] for r in b]):.0f} tokens, "
              f"{mean([r['seconds'] for r in reviewed]) - mean([r['seconds'] for r in b]):.1f} s")