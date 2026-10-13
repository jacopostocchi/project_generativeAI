# Week 5: a planner, an executor, and a second agent

Copy this into your `DECISIONS.md` and fill it in.

---

## Week 5

**Run conditions.** model: [ qwen2.5:7b] | framework: Pydantic AI [v2.55.0] |
runs per architecture: [3 ] | served locally | date: [2026-10-13] |
table from: [the recording (recorded 2026-10-13)]

### 1. The plan schema

What I tried first, and what happened:

A nested list of Step objects (tool, argument, why). It was valid in 1 of 3 tries. The two failures ended after three retries with Invalid JSON: the model answered in prose instead of JSON. The brief says this fails every time; it did not.

What I shipped, and why it is shaped that way:

goal: str, steps: list[str], suspect_file: str. It is the shallowest schema that carries what the validator checks, and the constraints live in the planner's prompt, not in field descriptions. It was still invalid in 8 of 14 planner calls (4 of 8 with descriptions, 4 of 6 without), so depth was not the only cost. The final prompt, which asks for a JSON object explicitly, was not measured.

### 2. The validator

| check | what it catches |
| step count between 2 and 6| 	an empty plan, or a plan that thrashes|
| suspect_file is one of the four source files|a file that does not exist|
| some step runs the tests|a plan that cannot verify itself |
|no step edits a test file (by path) | a plan that edits tests/|

On a failed check my system repairs once, then refuses, because the problems are specific enough to feed back, and a second failure means the plan is not usable, so refusing costs nothing.

### 3. The three-way table

| architecture | green | tokens (mean) | seconds (mean) |
| A baseline |0 /3 |10470 | 40.1|
| B planner | 2/3 | 1752| 15.0|
| C planner + reviewer | 0/3 |3441 |29.0|

### 4. Why the baseline fails

The baseline has to find, read and edit through an open-ended tool loop, while B makes one structured proposal that apply_fix checks, so the width of the action space is what changed, not the model or the prompt; in my own live runs it went green 2 of 6 times, so it is unreliable rather than incapable.

### 5. The reviewer
Verdicts across my runs: 0 approve, 3 reject (recording). My own live runs: 0 valid verdicts out of 4 fixes shown.

Would I ship it: no. Extra cost: 1689 tokens, 14.1 seconds per run.

The case where it would earn its cost:

When no free deterministic verifier covers the behaviour, for example a change that turns the failing test green by special-casing the hour or lowering OFF_PEAK_FROM_HOUR to 19; and only if it sees the whole file, not a one-line diff.

### 6. What my verifier cannot catch

pricing.discount_summary repeats the rule as start_hour > 20. No test covers it, because exactly one test fails on a clean checkout, so the correct fix in discounts.py makes the suite green while the summary still omits the off-peak label at 20:00. In the same way, or booking.start_hour == OFF_PEAK_FROM_HOUR in off_peak_discount passes the suite while is_off_peak(20) stays false.

### Deferred

