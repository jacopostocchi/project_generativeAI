"""The retry ladder. TODO 1 and 2.

Four responses to a failing step, and the lecture's instruction is to choose
one per step IN ADVANCE, by consequence, and to record which one fired:

    retry     the same call again, because the failure looks transient
    fallback  a different, worse call that is more likely to work
    degrade   answer partially, and say what is missing
    escalate  stop and ask a human

The policy is data, not control flow. That is what lets the same pipeline
run with one attempt in a fast test and three in the lab, and it is what
makes the policy reviewable. A try and except at every call site is the
thing this replaces, and finding fourteen of them later is the reason.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from faults import ContractDrift, RateLimited, ServerError, ToolTimeout


@dataclass
class StepPolicy:
    attempts: int = 3
    base_delay: float = 0.05
    jitter: bool = True
    max_elapsed: float = 5.0
    on_exhausted: str = "degrade"       # or "escalate"


@dataclass
class Attempt:
    n: int
    error: str | None
    slept: float = 0.0


@dataclass
class StepResult:
    value: object = None
    ok: bool = False
    attempts: list[Attempt] = field(default_factory=list)
    used_fallback: bool = False
    outcome: str = "ok"                 # ok | fallback | degraded | escalated

    @property
    def tries(self) -> int:
        return len(self.attempts)


# --------------------------------------------------------------------------
# TODO 1. Which errors deserve a second call?
# --------------------------------------------------------------------------

# The line is drawn as an ALLOWLIST, not a blocklist, so the default answer
# for an exception nobody has classified yet is "do not retry". A blocklist
# gets the new exception wrong silently; an allowlist gets it wrong loudly,
# once, and then you classify it.
#
# These three all mean "the upstream is having a moment", which is exactly
# what a second call buys:
RETRYABLE: tuple[type[BaseException], ...] = (
    ToolTimeout,        # no answer inside the deadline
    RateLimited,        # 429, it is asking us to slow down
    ServerError,        # 500, someone else's service is broken
)

# Deliberately absent, and this is the decision the session exists to catch:
#
#   ContractDrift  the call SUCCEEDED. A 200, a parseable body, and a field
#                  renamed from fee_eur to amount_eur. Retrying produces the
#                  same valid, wrong response as fast as the network allows,
#                  and then reports an exhausted ladder for a failure that
#                  never happened. Only validation catches it, and only a
#                  fallback or a degrade gets past it.
#
#   AuthError 401  not in this lab, same side of the line: a broken
#                  credential retried three times is a slow broken
#                  credential, and on some upstreams a locked account.
#
# The common test is not "which layer did this come from" but "will calling
# again plausibly give a different answer".


def is_retryable(exc: BaseException) -> bool:
    """TODO 1. Draw a line you can defend.

    Three of the exceptions in faults.py say "the upstream is having a
    moment", and a moment is exactly what a retry buys. One of them does
    not, and putting it on the wrong side of this line is the mistake this
    session exists to catch: the call SUCCEEDED, the response was valid, and
    a field had been renamed. Retrying that produces the same valid, wrong
    response as fast as the network allows, and then reports a timeout that
    never happened.

    Record in DECISIONS.md which one you excluded and why. Then consider a
    401, which is not in this lab: retrying an authentication failure turns
    a broken credential into a slow broken credential, and on some upstreams
    into a locked account.
    """
    return isinstance(exc, RETRYABLE)


# --------------------------------------------------------------------------
# TODO 2. Backoff with jitter, capped twice.
# --------------------------------------------------------------------------

def call_with_policy(fn, *args, policy: StepPolicy, fallback=None,
                     validate=None, **kwargs) -> StepResult:
    """TODO 2. Call `fn`, retrying by policy, then falling back, then degrading.

    Fill in a StepResult as you go: every attempt with its error, whether
    the fallback was used, and the final outcome. You report those counts at
    the checkpoint, and "it retried a few times" is not a count.

    Four things to get right.

    Two caps, not one. `attempts` bounds how many times you try and
    `max_elapsed` bounds how long the whole ladder may take. Without the
    second, three attempts with exponential backoff can still block a user
    for a minute.

    Exponential backoff: the delay doubles each time.

    Jitter, and it is not decoration. Ask what happens when thirty laptops
    in a room retry a rate limited endpoint at exactly the same interval.
    They re-collide, in lockstep, every time.

    `validate` runs on SUCCESS and is how contract drift is caught. It
    raises ContractDrift, which your `is_retryable` should refuse, so the
    ladder skips past retrying straight to the fallback. If you find
    yourself retrying a drifted response, TODO 1 is wrong.
    """
    result = StepResult()
    started = time.monotonic()
    delay = max(0.0, policy.base_delay)
    attempts = max(1, policy.attempts)

    for n in range(1, attempts + 1):
        try:
            value = fn(*args, **kwargs)
            # Validation runs ON THE SUCCESS PATH. This is the only place
            # contract drift can be caught, because nothing about the call
            # failed.
            if validate is not None:
                validate(value)
        except Exception as exc:                       # noqa: BLE001
            result.attempts.append(
                Attempt(n=n, error=f"{type(exc).__name__}: {exc}"))

            # Cap 1: attempts. Cap 2: the wall clock for the whole ladder.
            elapsed = time.monotonic() - started
            remaining = policy.max_elapsed - elapsed
            if not is_retryable(exc) or n == attempts or remaining <= 0:
                break

            # Exponential backoff with full jitter: sleep somewhere in
            # [0, delay) instead of exactly `delay`, so thirty clients that
            # collided on call 1 do not collide again on call 2.
            wait = random.uniform(0.0, delay) if policy.jitter else delay
            wait = min(wait, remaining)                # never overrun cap 2
            if wait > 0:
                time.sleep(wait)
            result.attempts[-1].slept = wait
            delay *= 2                                 # the doubling
            continue
        else:
            result.value = value
            result.ok = True
            result.outcome = "ok"
            result.attempts.append(Attempt(n=n, error=None))
            return result

    # The ladder is exhausted. Rung three: a different, worse call that is
    # more likely to work. It is validated too, because a fallback is a
    # dependency like any other.
    if fallback is not None:
        try:
            value = fallback(*args, **kwargs)
            if validate is not None:
                validate(value)
        except Exception as exc:                       # noqa: BLE001
            result.attempts.append(
                Attempt(n=result.tries + 1,
                        error=f"fallback {type(exc).__name__}: {exc}"))
        else:
            result.value = value
            result.ok = True
            result.used_fallback = True
            result.outcome = "fallback"
            return result

    # Rung four, chosen in advance by the policy rather than here: answer
    # partially and say what is missing, or stop and ask a human. Either way
    # the value is None, so no caller can mistake a failure for a result.
    result.value = None
    result.ok = False
    result.outcome = "degraded" if policy.on_exhausted == "degrade" \
        else "escalated"
    return result
