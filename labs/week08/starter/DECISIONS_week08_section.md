# Week 8: retries, recovery, and a human approval gate

Copy this into your `DECISIONS.md` and fill it in.

---

## Week 8

**Run conditions.** fault seed: 42 | attempts: 3 | base delay: 0.02 (01_survive HARDENED), 0.05 (SEARCH_POLICY / FEES_POLICY) | max elapsed: 3.0 | LangGraph 1.2.20 | date: 2026-11-09

### 1. Which errors are retryable

Retryable: [ ToolTimeout, RateLimited, ServerError.]

Deliberately NOT retryable: Deliberately NOT retryable: ContractDrift, because the call succeeded. A 200, a body that parses, and a field renamed from fee_eur to amount_eur.

Retrying a call that succeeded returns the same valid, wrong response as fast as the network allows, and then reports an exhausted ladder for a failure that never happened: three times the cost, no new information, and a log that blames the transport for a contract problem.

The line is an allowlist (RETRYABLE), not a blocklist, so the default answer for an exception nobody has classified yet is "do not retry". A 401 falls outside it for free, which is what I want: a broken credential retried three times is a slow broken credential, and on some upstreams a locked account.

### 2. The fault matrix

| | correct | WRONG | degraded | failed |
| baseline | 1|0 |2 | 5|
| hardened | 2|0| 5| 1|

What hardening actually bought:

Four of the five outright failures became degraded answers that say what is missing. Not more correct answers: the one extra correct is flaky, the control case, and the only row where a retry is genuinely the right response. empty stays failed, and that is correct: nothing was retrieved, so there is nothing to degrade to. WRONG is 0 in both rows only because the drift fault renames the key, so the wrong answer gives itself away. A drift that changed the value instead would fill the baseline's WRONG column, and could not fill the hardened one, where validation rejects the shape before anyone reads the number.

The proof that this is a ladder and not a retry wrapper: on drift and on malformed, the fees step reports one attempt, not three.

### 3. The empty result

An empty result is not an error. My pipeline treats it as a missing input rather than as a search that succeeded and found nothing, because a handbook that does not cover the topic and an index that was built wrong look identical from inside the pipeline. Treating it as a success is how a pipeline answers a question from nothing. The cost I accept is that a genuinely uncovered topic is reported as degraded; what that cost buys is that no confident answer ever leaves with no source under it. The same holds for fees, where a {} becomes missing: ["the fee"] instead of an amount that is silently absent.

### 4. The gate

Gated step: submit. The others are not gated because gather and price are idempotent reads with no external effect, already covered by retry, fallback and validation, and draft is a pure function of the state whose output ends up inside the payload the approver reads anyway. submit is the only node whose effect leaves the system and cannot be undone. The criterion is consequence, not confidence: gating everything teaches the approver to click through, and a signature on something unread is worse than no gate at all.

An unanswered approval after the timeout: it does not submit. The verdict is recorded as timeout with no identity in the record, because nobody decided. That protects the citizen and the administration, not the run's completion rate. It is also the default the unattended batch in week 10 will use.

The approval payload carries the exact arguments, the evidence, the degraded flag and the missing list, and deliberately does not carry a summary written by a model: the component whose judgment is under review would otherwise be writing the account of itself.

### 5. The duplicate the state does not show

I put a side effect above the interrupt. It executed 2 times. The recorded state showed it 1 time.

What that means for anything my gated node does before it asks:

The first execution never returns, it raises to persist the interrupt, so its return value is discarded while whatever it did to the outside world is not. In the paused state WROTE_ABOVE_INTERRUPT did not appear at all, and in the final state it appears exactly once. So the failure mode is not "the state gets messy": it is a case filed twice on a run that looks clean afterwards, and the only record I have is the one that does not show the duplicate. The rule: above an interrupt, read only. Two constraints follow for my project: the gated node is the only place a write happens, and that write is idempotent on case_id, so a replay is detectable rather than invisible.
