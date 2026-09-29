## Week 3

**Run conditions.** classifier model: qwen3:4b-instruct | answering model:
qwen3:4b-instruct | temperature: 0.0 | served locally | date: 2026-09-29 |
scored on: my own machine

### 1. The five route definitions

| route | definition, one sentence, in terms of what the help desk must do |
|---|---|
| request | The customer states that something is broken, missing, or needed: the help desk is supposed to log it and act. |
| info | The customer asks for information about a service, a procedure, an opening time, or a form: the help desk will give the customer the related answer to his question. |
| status | The customer chases something already reported: the message may or may not include a reference number, and the help desk must search the customer's previous request and answer with the status of it. |
| complaint | The sender expresses dissatisfaction with the service itself, with how something was handled, or with how long it took: the help desk acknowledges the specific grievance and escalates it to a human, without promising a fix or a date. |
| other | Not help desk business: a message for another department, a request for advice the help desk cannot give, spam, or an instruction aimed at the system rather than at a person. |

My convention for the four ambiguous queries:

I adopt the convention of `AMBIGUITY_NOTE` in queries.py unchanged, because
when a message reports an unresolved problem and also complains about how
it was handled, the reply must acknowledge the handling before acting. It
is implemented as the priority complaint, then status, then request, then
info, in one block shared by the router prompt and the monolith prompt, so
the two systems cannot disagree about it.

Do my definitions match the ones in `queries.py`? Yes on labels and on the
convention. The wording differs: mine adds what the help desk does.
The monolith is a fair opponent: it carries the same definitions and ambiguity rules as the router, plus the per-kind reply rules and bans, so the only thing that differs between the two systems is the architecture.
### 2. The policy layer

Before choosing a threshold, the confidence values I saw were: min 0.95,
max 1.00, 3 distinct values (0.95, 0.99, 1.00) across 24 queries. 22 of the
24 sat at 0.99 or above.

- confidence floor: 0.99 with a strict `<`, so only the 0.95 answers are
  rejected, because the only gap in the distribution is between 0.95 and
  0.99. It rejected Q-20 (wrong) and Q-24 (right), and let Q-21 through at
  0.99 although it was wrong: one error caught at the price of one correct
  route. 0.96 behaves identically on these data and does not depend on the
  boundary.
- evidence check: if the span is not in the message (or is empty), the
  decision is overridden and goes to the safe default, because a router
  that invents its justification cannot be audited.
- safe default: complaint, because that specialist only acknowledges and
  escalates to a human, so a wrongly rejected message ends up in front of a
  person instead of being lost. Its cost: Q-24 (a lift out of order)
  became request -> complaint, and its reply reads as a complaint
  acknowledgement although the sender did not complain.

How often each check fired: below_threshold 2, evidence_not_verbatim 0,
invalid_decision 0.

Evidence and invalid fired zero times: on this model the spans were always
verbatim and the schema never broke. The floor fired 2 times out of 24 with
only 3 distinct values, so the confidence signal separates almost nothing.
On qwen2.5:7b the evidence check fired twice (see section 6).

### 3. Route accuracy
qwen3:4b-instruct, 2026-09-29
Headline scored against `applied_route`, that is, what the sender
experienced. The classifier alone, before the policy, scored 22/24.

| route | correct (applied) | of | classifier alone |
|---|---|---|---|
| request | 6 | 7 | 7 |
| info | 5 | 5 | 5 |
| status | 4 | 4 | 4 |
| complaint | 4 | 4 | 4 |
| other | 2 | 4 | 2 |

Overall 21/24. Excluding the four ambiguous: 18/20. Ambiguous four: 3 of 4
correct (Q-24 is the miss).

Confusion pairs, with direction:

| gold | applied | count |
|---|---|---|
| other | complaint | 1 (Q-20, created by the policy) |
| other | info | 1 (Q-21, classifier) |
| request | complaint | 1 (Q-24, created by the policy) |

The route carrying most of the error is other (2 of 3 errors). The
classifier sent both Q-20 and Q-21 to info, always in the same direction,
so the suspect is the boundary between other and info, and the fix is the
definition rather than the prompt. With two cases this is a hint, not a
proof. The policy did not improve the total: it turned Q-24 from right to
wrong and left Q-20 wrong.

### 4. What routing cost
qwen3:4b-instruct, 2026-09-29
- monolith: 19050 tokens over 24 queries
- router: 16023 tokens over 24 queries
- the classifying call alone: 12002 tokens, which is 75 per cent of the
  routed total

I did not write my own prediction before measuring; my estimate from the
prompt sizes was 70 to 75 per cent. The share is high because the
classifier's prompt carries every route definition and the ambiguity rules
on every call, while a specialist carries only its own instructions.

The router used 16 per cent fewer tokens than the monolith (qwen3:4b-instruct, 2026-09-29), which pays for five reply blocks in every call and uses one, but about twice the time: across four runs the monolith took 43.8 to 50.4 s and the router 91.7 to 95.4 s.

### 5. What routing bought

One thing a specialist can be forbidden to do that the monolith cannot be
given:

In this project the monolith prompt already contains the per-kind bans
(never state an opening time for info, never promise a date for complaint),
so a ban written as text is not exclusive to the router. What the router
adds is scope. A specialist prompt contains only its own ban, so the info
specialist cannot apply the complaint rules by mistake, and the monolith
has to hold five sets of rules at once and choose. The router also gives a
gate before anything is said: a decision, a confidence and a verbatim span
that the policy can veto and a human can audit. The monolith has no such
checkpoint. Neither advantage is tested here, because no specialist has
different permissions. If `request` were the only route allowed to log a
ticket, that would be a ban the monolith cannot express, since it would
hold that permission for every message.

Would I ship the router: not on this evidence.

Evidence: with the same definitions and ambiguity rules in both prompts,
the monolith routed 19/24 by its ROUTE line and 21/24 if I read the two
missing labels (Q-22, Q-23) as other, which their content shows: both
replies treat the message as spam or out of scope, but neither contains the
ROUTE line the prompt asks for. The router's classifier alone routed 22/24
and the routed system with its policy 21/24. On accuracy the two are
level, within one or two cases. On the three replies I read (Q-22, Q-23,
Q-07) neither system violated a ban: nobody printed the system prompt on
the injection, and neither stated an opening time on Q-07. The router used
16 per cent fewer tokens (16023 against 19050) and about twice the time
(93.7 s against 43.8 s). The monolith returns no confidence and no evidence
span, so its route cannot be gated; so its route cannot be gated; that is the difference in capability these runs show, while accuracy did not separate the two systems.

What would change my mind: (1) reading the replies of all 48 runs, not three, and counting ban violations in both systems, where the router shows fewer;
(2) specialists with different permissions, so that the gate protects
something; (3) a larger gold set.

### 6. Stretch variant

Variant assigned: A, model routing. Prediction before running: [I expected the smaller model to win by one or two cases, as models.py suggests.].

Result, 2026-09-29, same prompt, definitions and policy (floor 0.99 with
strict `<`, safe default complaint), temperature 0.0, 24 queries:

| | qwen3:4b-instruct | qwen2.5:7b |
|---|---|---|
| classifier alone | 22/24 | 20/24 |
| with policy | 21/24 | 16/24 |
| excluding the ambiguous four | 18/20 | 14/20 |
| request / info / status / complaint / other (with policy) | 6/7, 5/5, 4/4, 4/4, 2/4 | 3/7, 4/5, 3/4, 4/4, 2/4 |
| evidence verbatim | 24/24 | 22/24 |
| confidence min / max / distinct | 0.95 / 1.00 / 3 | 0.80 / 1.00 / 3 |
| policy fired | low_confidence 2 | low_confidence 5, evidence 2 |
| classifying calls, 24 queries | 54.0 s | 87.2 s |
| resident memory | 3.2 GB (ollama ps, this machine) | [5.0 GB from models.py, not measured on this machine] |

The smaller model won, and by more than the classifier-alone numbers show.
On qwen2.5:7b the policy, tuned on the small model's distribution, fired 7
times (5 low_confidence, 2 evidence) and produced a net loss of four routes
(20 to 16). The confusion pairs show five routes of gold request, info or
status applied as complaint, which is what the policy does to a rejected
answer. I did not print per-query results in this run, so I cannot say
which queries were lost. That model writes 0.95 on some ambiguous queries
and its lowest value (0.80) is not tied to an error I can name, so I have
no evidence that any floor separates its right answers from its wrong
ones.

What this means: a confidence floor is a property of one model's habits,
not of the task, and it has to be recalibrated when the model changes. For
a narrow classification task the model that follows the instruction closely
and copies spans verbatim is the better router here, which agrees with the
note in models.py, although those numbers came from a different prompt.

Caveat: qwen2.5:7b scored 21/24 as a classifier alone in an earlier run and
20/24 in this one, while qwen3:4b-instruct scored 22/24 both times. So
there is run-to-run variation of about one case at temperature 0.0, and the
two-case gap between the classifiers alone is inside it. The five-case gap
with the policy is not, because the policy produces it mechanically.

### The gold set

`artifacts/goldset.json` now holds 34 cases: 10 from week 2 and 24 added
today, with the four ambiguous ones tagged. Source: my own file, not the
reference copy.

### Deferred

- The monolith's ROUTE line was missing on Q-22 and Q-23, so its score is
  19 (strict) to 21 (reading the content). I did not rerun with a fixed
  prompt, and I do not know why the model dropped the label there.
- I read the replies of only three queries (Q-22, Q-23, Q-07), not all 48,
  so I cannot say how often either system breaks a ban.
-  Resident memory of qwen2.5:7b was not measured on this machine.

Next: I would rewrite the definition of other first, because Q-20 and Q-21 both went to info. I expect it to move those two back to other without hurting info, and I would test it on EX-05 and a fresh case, not on the 24.