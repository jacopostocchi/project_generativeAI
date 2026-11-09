"""The project's entry point. Week 7 puts retrieval behind the memory store."""

from __future__ import annotations

import argparse

from .memory import MemoryStore


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.run")
    ap.add_argument("query")
    ap.add_argument("--subject", required=True)
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()

    store = MemoryStore.load()
    hits = store.search(args.subject, args.query, k=args.k)
    print(f"memory.search subject={args.subject!r} k={args.k}: {len(hits)} hits")
    for position, hit in enumerate(hits, start=1):
        print(f"  {position}. {hit[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
