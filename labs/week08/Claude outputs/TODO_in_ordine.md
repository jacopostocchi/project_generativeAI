# I TODO in ordine, 1 -> 7

Ordine di esecuzione consigliato: 1 e 2 in `retry.py`, 3-5 in `graph.py`,
6 e 7 sono le risposte scritte in fondo ai due script. Dentro `graph.py` il
TODO 4 sta FISICAMENTE sopra il TODO 3 nel file: scrivilo prima, perche' 3a
e 3b lo usano.

---

## TODO 1 — `retry.py`, `is_retryable`

Quali errori meritano una seconda chiamata. Allowlist, non blocklist.

```python
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
```

---

## TODO 2 — `retry.py`, `call_with_policy`

La scala: retry con backoff esponenziale + jitter e due cap, poi fallback, poi degrade/escalate.

```python
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
```

---

## TODO 3a — `graph.py`, `gather`

Search con retry e fallback, e la decisione sul risultato vuoto.

```python
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
```

---

## TODO 3b — `graph.py`, `price`

Lookup della tariffa, con `validate_fee` passato alla policy. Nessun fallback, di proposito.

```python
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
```

---

## TODO 4 — `graph.py`, `validate_fee` (+ `validate_passages`)

Dove si prende il contract drift: un controllo sulla FORMA, sul percorso di successo.

```python
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


```

---

## TODO 5 — `graph.py`, `draft`

Il goal predicate, e cosa dice una risposta parziale nel testo che legge l'utente.

```python
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
```

---

## TODO 6 — risposta scritta in fondo a `starter/01_survive.py`

La matrice dei fault e cosa ha comprato l'hardening. Testo completo in `TODO_6_7_risposte_scritte.md`.

---

## TODO 7 — risposta scritta in fondo a `starter/02_gate.py`

Quale step e' gated e perche' gli altri no, piu' il duplicato che lo stato non mostra. Testo completo in `TODO_6_7_risposte_scritte.md`.
