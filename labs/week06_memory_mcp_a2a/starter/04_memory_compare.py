"""Memory off against memory on: tokens and turns for the same task.

    cd starter
    python 04_memory_compare.py            # 3 runs per mode
    RUNS=5 python 04_memory_compare.py

Needs Ollama running with the course model (LARGE, qwen2.5:7b), ideally with
OLLAMA_CONTEXT_LENGTH=8192.

The task: plan how to contact one resident about a change in waste
collection. The agent must establish three things: channel, time of day,
language. Both modes have `ask_resident`, which costs a turn per question.
Memory on adds `recall`, which returns stored facts about that resident.
Memory off has to ask.

The resident is simulated by rules, not by a second model, so every token
counted belongs to the agent under test.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory import MemoryStore                       # noqa: E402
from project.models import LARGE, client_for, model_name  # noqa: E402

SUBJECT = "A. Muller"
STORE_PATH = Path("artifacts/compare_store.json")
MAX_TURNS = 10
RUNS = int(os.environ.get("RUNS", "3"))

FACTS = [
    ("contact_channel", "Prefers phone calls, never email."),
    ("contact_time", "Best reached in the morning."),
    ("language", "Speaks Luxembourgish and German, not French."),
]

SYSTEM = (
    "You are a municipal service agent. Plan how to contact resident "
    f"{SUBJECT!r} about a change in the waste collection schedule. You must "
    "determine three things: the contact channel, the time of day, and the "
    "language. Use the tools to find them out; never guess. As soon as you "
    "know all three, call `finish`."
)

ASK = {"type": "function", "function": {
    "name": "ask_resident",
    "description": "Ask the resident ONE question and get their answer. "
                   "Each question is a separate exchange with the resident.",
    "parameters": {"type": "object", "properties": {
        "question": {"type": "string"}}, "required": ["question"]}}}

RECALL = {"type": "function", "function": {
    "name": "recall",
    "description": "Return up to 3 stored facts about this resident that "
                   "match the query, as '[kind] text'. An empty list means "
                   "nothing relevant is stored.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string"}}, "required": ["query"]}}}

FINISH = {"type": "function", "function": {
    "name": "finish",
    "description": "Submit the contact plan. Call once, when all three "
                   "values are known.",
    "parameters": {"type": "object", "properties": {
        "channel": {"type": "string"},
        "time_of_day": {"type": "string"},
        "language": {"type": "string"}},
        "required": ["channel", "time_of_day", "language"]}}}


def resident_answers(question: str) -> str:
    """Rule-based resident. Answers one topic per question."""
    q = question.lower()
    if any(w in q for w in ("language", "speak", "french", "german")):
        return "I speak Luxembourgish and German. Not French, please."
    if any(w in q for w in ("time", "when", "morning", "afternoon",
                            "evening", "hour")):
        return "Mornings are best for me."
    if any(w in q for w in ("contact", "reach", "phone", "email", "call",
                            "channel", "prefer")):
        return "Please phone me. I never read email."
    return "Sorry, could you ask more specifically?"


def correct(plan: dict) -> bool:
    return ("phone" in plan.get("channel", "").lower()
            and "morning" in plan.get("time_of_day", "").lower()
            and any(l in plan.get("language", "").lower()
                    for l in ("luxembourg", "german")))


def seed_store() -> MemoryStore:
    if STORE_PATH.exists():
        STORE_PATH.unlink()
    store = MemoryStore.load(STORE_PATH)
    for kind, text in FACTS:
        store.write(SUBJECT, kind, text)
    return store


def run_once(memory_on: bool, store: MemoryStore) -> dict:
    client = client_for(LARGE)
    tools = [ASK, FINISH] + ([RECALL] if memory_on else [])
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Plan the contact."}]
    tokens = turns = 0
    plan: dict | None = None

    while turns < MAX_TURNS and plan is None:
        resp = client.chat.completions.create(
            model=model_name(LARGE), messages=messages, tools=tools,
            temperature=0)
        turns += 1
        if resp.usage:
            tokens += resp.usage.prompt_tokens + resp.usage.completion_tokens
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in calls] or None})
        if not calls:
            messages.append({"role": "user", "content":
                             "Use a tool, or call `finish` if you know all "
                             "three values."})
            continue
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if c.function.name == "finish":
                plan = args
                out = "submitted"
            elif c.function.name == "recall" and memory_on:
                out = json.dumps(store.search(SUBJECT, args.get("query", ""),
                                              k=3))
            elif c.function.name == "ask_resident":
                out = resident_answers(args.get("question", ""))
            else:
                out = f"unknown tool {c.function.name}"
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": out})

    return {"tokens": tokens, "turns": turns,
            "finished": plan is not None,
            "correct": bool(plan) and correct(plan)}


def main() -> int:
    store = seed_store()
    results = {}
    for memory_on in (False, True):
        label = "memory on" if memory_on else "memory off"
        runs = [run_once(memory_on, store) for _ in range(RUNS)]
        results[label] = runs
        for i, r in enumerate(runs, 1):
            print(f"{label:<11} run {i}: tokens={r['tokens']:>5} "
                  f"turns={r['turns']:>2} correct={r['correct']}")

    print(f"\nmodel {model_name(LARGE)}, {RUNS} runs per mode, "
          f"median shown\n")
    print("| | tokens | turns to finish | correct |")
    print("|---|---|---|---|")
    for label, runs in results.items():
        med_tok = statistics.median(r["tokens"] for r in runs)
        med_turn = statistics.median(r["turns"] for r in runs)
        ok = sum(r["correct"] for r in runs)
        print(f"| {label} | {med_tok:.0f} | {med_turn:.0f} | "
              f"{ok}/{len(runs)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
