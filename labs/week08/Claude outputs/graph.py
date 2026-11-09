"""The pipeline as a graph, with one gated step. TODO 3 to 5.

Four nodes. Three of them execute automatically and one stops and asks a
human, and which one is a decision about consequence rather than about
confidence.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from faults import ContractDrift, FaultPlan
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from retry import StepPolicy, call_with_policy

import tools


def append(a: list, b: list) -> list:
    return a + b


class CaseState(TypedDict):
    case_id: str
    topic: str
    passages: list[str]
    fee: dict
    draft: str
    submitted: bool
    decision: str
    degraded: bool
    missing: Annotated[list[str], append]
    events: Annotated[list[str], append]
    side_effects: Annotated[list[str], append]


SEARCH_POLICY = StepPolicy(attempts=3, base_delay=0.05, jitter=True,
                           max_elapsed=3.0, on_exhausted="degrade")
FEES_POLICY = StepPolicy(attempts=3, base_delay=0.05, jitter=True,
                         max_elapsed=3.0, on_exhausted="degrade")

# What `missing` is allowed to contain. These strings end up in the text the
# user reads, so they are written for the user, not for the log.
MISSING_PASSAGES = "the handbook passage for this topic"
MISSING_FEE = "the fee"


def validate_fee(value) -> None:
    """TODO 4. Where contract drift is caught.

    Drift is the fault no retry fixes, because the call succeeded. The only
    thing that catches it is a check on the SHAPE of what came back, run on
    the success path. If you have no validation, a renamed field flows all
    the way to the answer and the run reports success.
    """
    # An empty result is a well formed "I have nothing for this topic". It is
    # not a contract breach, so it is not this function's business: `price`
    # decides what to do with it, explicitly, which is decision 3 in
    # DECISIONS.md. Raising here would collapse two different faults
    # (`empty` and `drift`) into one indistinguishable outcome.
    if value == {}:
        return

    if not isinstance(value, dict):
        # `malformed`: a 200 whose body is an HTML error page.
        raise ContractDrift(
            f"fees returned {type(value).__name__}, expected a dict")

    if "fee_eur" not in value:
        # `drift`: this is the whole fault. The call succeeded, the body
        # parses, and the key we asked for is now called something else.
        # Naming the keys we DID get is what makes the log actionable.
        raise ContractDrift(
            f"fees returned keys {sorted(value)}, no 'fee_eur' "
            f"(contract drift: the call succeeded, the field was renamed)")

    amount = value["fee_eur"]
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ContractDrift(
            f"fees returned fee_eur={amount!r}, not a number")

    if "period" not in value:
        raise ContractDrift(
            f"fees returned fee_eur without a period: {sorted(value)}")


def validate_passages(value) -> None:
    """The same check, at the other boundary.

    `search` promises a list of strings. The `malformed` fault returns an
    HTML error page with a 200, which is a contract failure, not a transport
    one: no retry fixes it, and the fallback is the rung that does. An empty
    list is valid here for the same reason {} is valid above.
    """
    if not isinstance(value, list):
        raise ContractDrift(
            f"search returned {type(value).__name__}, expected a list")
    if any(not isinstance(p, str) for p in value):
        raise ContractDrift("search returned a list with non-string items")


# --------------------------------------------------------------------------
# TODO 3. The nodes, each with its own policy.
# --------------------------------------------------------------------------

def gather(state: CaseState, plan: FaultPlan) -> dict:
    """TODO 3a. Search, with retries and a fallback.

    Three cases, and the middle one is the interesting one:

      the call failed after everything    -> degraded, say search is down
      the call SUCCEEDED and returned []  -> decide, and be able to defend it
      the call succeeded with passages    -> note if the fallback was used

    An empty result is not an error and it is not a success either. It is
    the tool saying it does not cover this. Treating it as a success is how
    a pipeline answers a question from nothing.

    Record what is absent in `missing` so `draft` can say it out loud, and
    append to `events` so the checkpoint has something to count.
    """
    res = call_with_policy(tools.search, plan, state["topic"],
                           policy=SEARCH_POLICY,
                           fallback=tools.keyword_fallback,
                           validate=validate_passages)

    events = [f"search:{res.outcome}:tries={res.tries}"]
    if res.attempts and res.attempts[-1].error:
        events.append(f"search:last_error={res.attempts[-1].error}")

    # Case 1: the ladder is exhausted, retries and the fallback included.
    # Nothing was retrieved, and the answer has to say so rather than be
    # assembled from nothing.
    if not res.ok:
        return {"passages": [], "degraded": True,
                "missing": [MISSING_PASSAGES],
                "events": events + ["search:unavailable"]}

    # Case 2: a 200 with nothing in it. THE DECISION: an empty search result
    # is treated as a MISSING INPUT, not as a search that found nothing to
    # say. The handbook not covering a topic and the index being misbuilt
    # look identical from here, so the honest answer is the same in both
    # cases: say the passage is missing and let the reader decide. The cost
    # is that a genuinely uncovered topic is reported as degraded; the thing
    # that cost buys is that the pipeline never writes a confident answer
    # with no source under it.
    if not res.value:
        return {"passages": [], "degraded": True,
                "missing": [MISSING_PASSAGES],
                "events": events + ["search:empty->treated_as_missing"]}

    # Case 3: passages, possibly from the cheaper index. The fallback is
    # recorded because it is otherwise invisible: the answer looks identical
    # and its source is not.
    if res.used_fallback:
        events.append("search:served_from_cached_index")
    return {"passages": list(res.value), "events": events}


def price(state: CaseState, plan: FaultPlan) -> dict:
    """TODO 3b. The fee lookup, passing `validate_fee` to the policy.

    This is the step contract drift hits. Without a validator the renamed
    field flows into the answer and the run reports success.
    """
    res = call_with_policy(tools.fees, plan, state["topic"],
                           policy=FEES_POLICY,
                           validate=validate_fee)

    events = [f"fees:{res.outcome}:tries={res.tries}"]
    if res.attempts and res.attempts[-1].error:
        events.append(f"fees:last_error={res.attempts[-1].error}")

    # No fallback here on purpose, and that is a decision: there is no
    # cheaper source of truth for a legal fee. A stale or guessed amount is
    # worse than no amount, because the reader cannot tell it is wrong.
    # So this step has exactly two outcomes: the real figure, or an admitted
    # gap.
    if not res.ok:
        return {"fee": {}, "degraded": True, "missing": [MISSING_FEE],
                "events": events + ["fees:unavailable"]}

    if not res.value:
        return {"fee": {}, "degraded": True, "missing": [MISSING_FEE],
                "events": events + ["fees:empty->treated_as_missing"]}

    return {"fee": dict(res.value), "events": events}


def draft(state: CaseState) -> dict:
    """TODO 5. The goal predicate, and what a partial answer says.

    A degraded answer must name what is missing IN THE TEXT THE USER READS.
    An answer that quietly omits the fee is indistinguishable from one where
    there was no fee, and the reader has no way to know which they got.

    A degrade path that returns an empty string is technically graceful and
    completely useless.
    """
    passages = list(state.get("passages") or [])
    fee = dict(state.get("fee") or {})
    missing = sorted(set(state.get("missing") or []))
    events = list(state.get("events") or [])
    cached = "search:served_from_cached_index" in events

    # The goal predicate, stated once, in one place: this answer is complete
    # when it has a source AND a figure AND nothing was recorded as missing.
    # Note what is NOT in it: "a tool returned something". Three nodes can
    # all report success and still leave the goal unmet.
    complete = bool(passages) and fee.get("fee_eur") is not None \
        and not missing

    lines = [f"Case {state['case_id']}: {state['topic']}"]

    if passages:
        lines.append("Handbook: " + " ".join(passages))
        if cached:
            lines.append("Source: the cached keyword index, not the live "
                         "handbook, so it may be out of date.")
    if fee.get("fee_eur") is not None:
        lines.append(f"Fee: {fee['fee_eur']:.2f} EUR per "
                     f"{fee.get('period', 'unknown period')}.")

    if not complete:
        # The part that is not optional. The reader has to be able to tell a
        # gap from a zero, and "missing" has to appear in the prose, not only
        # in `events`.
        lines.append("INCOMPLETE ANSWER. Missing: "
                     + (", ".join(missing) if missing
                        else "one or more required inputs") + ".")
        lines.append("What is missing above was NOT retrieved. Do not read "
                     "it as nothing to pay or nothing on record.")
        if not passages and fee.get("fee_eur") is None:
            lines.append("Nothing at all was retrieved for this case, so "
                         "this is not an answer. It needs a human.")
        lines.append("Next step: check the source by hand before this is "
                     "sent to the citizen.")

    return {"draft": "\n".join(lines),
            "degraded": not complete,
            "events": [f"draft:{'complete' if complete else 'degraded'}"
                       f":missing={len(missing)}"]}


def submit(state: CaseState) -> dict:
    """The gated step. Exactly one, chosen by consequence.

    Everything above the interrupt runs AGAIN on resume, because the node
    re-executes from its first line. Put nothing here that writes.

    And the part the state will not show you: the first execution never
    returns, so its return value is discarded while whatever it did to the
    outside world is not. A write above this line happens twice and appears
    once. `02_gate.py` demonstrates it.
    """
    decision = interrupt({
        "action": "submit_case",
        "case_id": state["case_id"],
        # The exact arguments, not a summary the model wrote. The model
        # whose judgment you are checking would also be writing the account
        # of it.
        "arguments": {"topic": state["topic"], "fee": state.get("fee", {})},
        "evidence": state.get("passages", []),
        "degraded": state.get("degraded", False),
        "missing": sorted(set(state.get("missing", []))),
    })

    verdict = decision.get("verdict")
    if verdict == "approve":
        return {"submitted": True, "decision": "approve",
                "side_effects": [f"SUBMITTED {state['case_id']}"],
                "events": [f"gate:approve:{decision.get('by', '?')}"]}
    if verdict == "edit":
        edited = decision.get("arguments", {})
        return {"submitted": True, "decision": "edit",
                "fee": edited.get("fee", state.get("fee", {})),
                "side_effects": [f"SUBMITTED {state['case_id']} (edited)"],
                "events": [f"gate:edit:{decision.get('by', '?')}"]}
    return {"submitted": False, "decision": verdict or "reject",
            "events": [f"gate:{verdict or 'reject'}:"
                       f"{decision.get('by', '?')}"]}


def build(plan: FaultPlan, saver):
    graph = StateGraph(CaseState)
    graph.add_node("gather", lambda s: gather(s, plan))
    graph.add_node("price", lambda s: price(s, plan))
    graph.add_node("draft", draft)
    graph.add_node("submit", submit)
    graph.add_edge(START, "gather")
    graph.add_edge("gather", "price")
    graph.add_edge("price", "draft")
    graph.add_edge("draft", "submit")
    graph.add_edge("submit", END)
    return graph.compile(checkpointer=saver)


def initial(case_id: str, topic: str) -> CaseState:
    return {"case_id": case_id, "topic": topic, "passages": [], "fee": {},
            "draft": "", "submitted": False, "decision": "",
            "degraded": False, "missing": [], "events": [],
            "side_effects": []}
