"""Block 3. The gate, and what the state will not tell you. TODO 7.

Run it as TWO separate invocations. That is the whole exercise: if the pause
only survives inside one script, it is a session variable with extra steps.

    python 02_gate.py start
    python 02_gate.py resume approve      # or reject, or edit

The written answer is at the bottom, and the second half of it is the part
that is not on any slide.
"""

from __future__ import annotations

import sys
from pathlib import Path

from faults import FaultPlan
from graph import build, initial
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from project.trace import repo_root, write_json

DB = repo_root() / "artifacts" / "week08_runs.sqlite"
CASE = "RB-2026-0042"


def show(graph, cfg) -> None:
    snap = graph.get_state(cfg)
    print(f"    next node:     {snap.next}")
    print(f"    side effects:  {snap.values.get('side_effects')}")
    print(f"    events:        {snap.values.get('events')}")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    verdict = sys.argv[2] if len(sys.argv) > 2 else "approve"
    cfg = {"configurable": {"thread_id": CASE}}
    plan = FaultPlan.parse("")          # no faults, the gate is the subject

    DB.parent.mkdir(parents=True, exist_ok=True)
    if mode == "start":
        DB.unlink(missing_ok=True)

    with SqliteSaver.from_conn_string(str(DB)) as saver:
        graph = build(plan, saver)

        if mode == "start":
            out = graph.invoke(initial(CASE, "parking vignette"), cfg)
            payload = out["__interrupt__"][0].value
            print("  the run has PAUSED at the gate\n")
            print(f"    action:    {payload['action']}")
            print(f"    arguments: {payload['arguments']}")
            print(f"    evidence:  {payload['evidence']}")
            print(f"    degraded:  {payload['degraded']}")
            show(graph, cfg)
            print("\n  This process can now exit, or be killed. Then run:")
            print("    python 02_gate.py resume approve")
            return 0

        before = graph.get_state(cfg)
        if not before.next:
            raise SystemExit("Nothing is paused. Run `start` first.")
        print(f"  resuming a run this process did not create")
        print(f"    it was paused before: {before.next}\n")

        resume = {"verdict": verdict, "by": "a.muller"}
        if verdict == "edit":
            # The approver's most common response is neither approve nor
            # reject: it is approve with one field changed. A gate with no
            # edit path throws away correct work and trains the approver to
            # approve rather than to correct.
            resume["arguments"] = {"fee": {"fee_eur": 55.0, "period": "year"}}

        out = graph.invoke(Command(resume=resume), cfg)
        print(f"    submitted: {out.get('submitted')}")
        print(f"    decision:  {out.get('decision')}")
        print(f"    fee now:   {out.get('fee')}")
        show(graph, cfg)

        record = {"case_id": CASE, "verdict": verdict,
                  "by": "a.muller", "submitted": out.get("submitted"),
                  "decision": out.get("decision"),
                  "arguments": out.get("fee"),
                  "evidence": out.get("passages"),
                  "events": out.get("events")}
        write_json("artifacts/week08_approval.json", record)
        print("\n  decision record written to artifacts/week08_approval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

WRITTEN_ANSWER = """
PART 1, the gate.

The gated step is `submit`, and it is the only one. The criterion is
consequence, not confidence: `submit` is the only node whose effect leaves
the system and cannot be undone. It files a case with the administration, and
downstream of that case a citizen receives a letter with an amount on it. A
model that is very confident about a wrong figure is exactly the case the
gate exists for, so gating by confidence would skip precisely the cases where
it is needed.

Why the other three are not gated:

  gather   an idempotent read with no external effect. When it fails it
           fails downward: no passage, rather than an invented passage.
           Retry plus fallback already cover its failure modes, and a human
           in front of a search adds no information the search did not have.
  price    the same, and its worst failure (drift) is not visible to the
           eye: a renamed payload looks correct to a person reading it. The
           right defence there is validation, not someone's attention.
  draft    a pure function of the state. It calls nothing and writes
           nothing, and its output is inside the payload the approver reads
           at the gate anyway.

The underlying reason there is exactly one: the approver's attention is the
scarcest resource in the system. Four prompts for one case teach them to
click through, and an approver who clicks through is worse than no gate,
because it produces a signature on something unread. You spend it once, at
the irreversible step.

The payload carries the exact arguments, the evidence, the `degraded` flag
and the `missing` list. It deliberately does NOT carry a summary written by a
model: the component whose judgment is being checked would also be writing
the account of itself, and the approver would be approving the account rather
than the action.

All three paths are implemented and demonstrated across two separate
processes, thread_id RB-2026-0042, SqliteSaver on
artifacts/week08_runs.sqlite:

  approve   submitted True,  decision approve, side effect SUBMITTED
  reject    submitted False, decision reject,  no side effect
  edit      submitted True,  decision edit,    fee 60.00 -> 55.00, and the
            EDITED amount is what gets filed, not the original

The `edit` path is not an extra. The most frequent response from a real
approver is neither approve nor reject, it is "approve with one field
changed". A gate without an edit path forces correct work to be thrown away
over one wrong field, and so teaches the approver to approve rather than to
correct.

An approval left unanswered past the timeout: default to NOT filing, with the
verdict recorded as "timeout" and no identity in the record, because nobody
decided. That protects the citizen and the administration, not the run's
completion rate. It is also the default the unattended batch in week 10 will
use: request_approval(payload, unattended=True) returns it instead of
waiting.

PART 2, the part that is not on any slide.

On resume the interrupted node restarts from its FIRST line, so everything
above interrupt() executes twice. That much is in the lecture. What is not:
the recorded state will not show you the duplicate. The first execution never
returns, it raises to persist the interrupt, so its return value is discarded
while whatever it did to the outside world is not.

Measured with interrupt_smoke_test.py: the side effect above the interrupt
prints in BOTH processes, and `side_effects` in the state contains it once.
In the paused state it does not appear at all. Executed twice, recorded once.

So the failure mode is not "the state gets messy". It is a case filed twice,
or an email sent twice, or a payment taken twice, on a run that looks clean
afterwards. The only record you have is the one that does not show the
duplicate.

The rule that follows is narrow and absolute: above an interrupt, read only.
Everything that writes goes below, in the branch that has already seen the
verdict. Two constraints follow for my project: the gated node is the only
place a write happens, and the write is idempotent on case_id, so a replay is
detectable rather than invisible.
"""