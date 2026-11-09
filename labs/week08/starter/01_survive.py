"""Blocks 1 and 2. Break it, then survive it. TODO 6.

    python 01_survive.py --baseline     # no policy at all, watch it die
    python 01_survive.py                # the full fault matrix, hardened

No model is called anywhere in this file. The tools are offline and the
faults are deterministic, so the whole block runs in about a second and the
same seed gives the same failures every time.

The written answer is at the bottom.
"""

from __future__ import annotations

import argparse

from faults import FAULTS, ContractDrift, FaultPlan
from retry import StepPolicy, call_with_policy

import tools
from graph import validate_fee

from project.trace import TraceRecorder, local_conditions, write_json

NO_POLICY = StepPolicy(attempts=1, base_delay=0.0, jitter=False,
                       on_exhausted="escalate")
HARDENED = StepPolicy(attempts=3, base_delay=0.02, jitter=True,
                      max_elapsed=3.0, on_exhausted="degrade")


def run_one(kind: str, hardened: bool) -> dict:
    """One fault, against search and against fees, with or without policy."""
    policy = HARDENED if hardened else NO_POLICY
    plan = FaultPlan.parse(f"search:{kind}@1.0,fees:{kind}@1.0", seed=42)

    rec = TraceRecorder(
        week=8, case_id=f"{kind}-{'hardened' if hardened else 'baseline'}",
        conditions=local_conditions("none (offline tools)", temperature=0.0,
                                    fault=kind, policy=policy.attempts),
        user_input=f"fault={kind}")

    with rec.step("tool", "search") as span:
        search = call_with_policy(
            tools.search, plan, "parking vignette", policy=policy,
            fallback=tools.keyword_fallback if hardened else None)
        span.ok = search.ok
        span.detail(tries=search.tries, outcome=search.outcome)

    with rec.step("tool", "fees") as span:
        fee = call_with_policy(
            tools.fees, plan, "parking vignette", policy=policy,
            validate=validate_fee if hardened else None)
        span.ok = fee.ok
        span.detail(tries=fee.tries, outcome=fee.outcome)

    # Classify the OUTCOME, not merely whether something came back.
    #
    # "Did it answer" is the obvious metric and it is a trap: it counts a
    # confidently wrong answer as a success, and so it rewards the pipeline
    # with no validation. Ask instead which of four things happened.
    TRUE_FEE = 60.0
    got_fee = fee.value.get("fee_eur") if isinstance(fee.value, dict) else None
    has_passage = bool(search.value)

    if has_passage and got_fee == TRUE_FEE:
        verdict = "correct"          # right answer, from good data
    elif has_passage and got_fee is not None:
        verdict = "WRONG"            # answered, and the number is not right
    elif not has_passage and not got_fee:
        verdict = "failed"           # nothing at all, and it said so
    else:
        verdict = "degraded"         # partial, and it names what is missing

    rec.finish(output=None,
               outcome={"correct": "ok", "WRONG": "error",
                        "degraded": "degraded", "failed": "error"}[verdict],
               fault=kind, hardened=hardened, verdict=verdict)

    return {"fault": kind, "hardened": hardened,
            "search_tries": search.tries, "search_outcome": search.outcome,
            "fees_tries": fee.tries, "fees_outcome": fee.outcome,
            "verdict": verdict}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true",
                    help="no retries, no fallback, no validation")
    args = ap.parse_args()
    hardened = not args.baseline

    print(f"{'fault':<14}{'search':>20}{'fees':>20}{'verdict':>12}")
    print("-" * 70)
    rows = []
    for kind in FAULTS:
        row = run_one(kind, hardened)
        rows.append(row)
        print(f"{kind:<14}"
              f"{row['search_outcome'] + ' x' + str(row['search_tries']):>20}"
              f"{row['fees_outcome'] + ' x' + str(row['fees_tries']):>20}"
              f"{row['verdict']:>12}")

    tally = {v: sum(1 for r in rows if r["verdict"] == v)
             for v in ("correct", "WRONG", "degraded", "failed")}
    label = "hardened" if hardened else "BASELINE, no policy"
    print(f"\n  {label}: correct {tally['correct']}, "
          f"WRONG {tally['WRONG']}, degraded {tally['degraded']}, "
          f"failed {tally['failed']}  (out of {len(rows)})")
    print("  The number that matters is WRONG: an answer that is confidently")
    print("  incorrect is worse than one that admits it is incomplete.")
    write_json(f"artifacts/week08_faults_"
               f"{'hardened' if hardened else 'baseline'}.json",
               {"rows": rows})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

WRITTEN_ANSWER = """
The seed is 42. The two configurations are NO_POLICY (one attempt, no
fallback, no validation) and HARDENED (three attempts, exponential backoff
with jitter, max_elapsed 3.0, a fallback on search, validate_fee on fees).

                correct   WRONG   degraded   failed
    baseline          1       0          2        5
    hardened          2       0          5        1

What hardening bought: not correct answers. It moved four of the five
outright failures into the degraded column, which is to say it turned silence
into a partial answer that says what is missing. The only extra `correct` is
`flaky`, the control case, where a single retry makes the fault disappear
entirely and where retrying is genuinely the right response. Concluding from
that one row that robustness means retry is exactly the mistake the row
exists to expose.

The `empty` row stays `failed` after hardening, and that is correct: nothing
was retrieved, so there is nothing to degrade to. A pipeline that answered
anyway on `empty` would gain a `correct` row by inventing the data. An honest
failure is the best result available there.

The attempt counts are the evidence that this is a ladder and not a retry
wrapper:

    timeout / rate_limit / server_error   search x3 then fallback, fees x3 then degrade
    malformed                             fees x1   validation, not retry
    drift                                 fees x1   the call SUCCEEDED
    flaky                                 x2        retry does its job
    slow / empty                          x1        no error to retry

On `drift` and `malformed` the counter reads one. If it read three,
`is_retryable` would have put a contract failure on the retryable side and
the policy would be paying three times for the same wrong answer.

On the WRONG column: it is 0 in both configurations, and in neither case is
that a safety property worth boasting about. It is 0 because the `drift` fault
renames the KEY, so fee.value.get("fee_eur") reads None instead of a plausible
number: the wrong answer gives itself away, policy or no policy. What
validation changes is who catches it and how early, not whether it is
catchable: validate_fee rejects the renamed shape on the first attempt, which
is why the fees step reports one try instead of three, and why the answer that
reaches the user says the fee is missing instead of dropping it in silence.

What neither column defends against is a fault that keeps the contract and
corrupts the content: fee_eur: 75.0, a float, under the right key, with the
right period. validate_fee passes it, and the row would read WRONG in the
hardened configuration too. That is the honest limit of this harness: it
reaches the transport and the contract layers, and the judgment layer is not
injectable from outside, because nothing about that response is an error.
Catching it needs a goldset and an expected value, which is week 10, not a
retry policy.
"""