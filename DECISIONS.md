# Decisions
**Run conditions.** Everything below was produced on:

- machine: [Mac, M2, 8GB]
- model: [qwen2.5:7b]
- served by: Ollama, one request at a time, locally
- date: [2026-09-16]
### 1. Machine and model set
I am running the [required plus optional] model set.

### 2. The first call
| finish reason |stop|
if my programme came back with a truncation it would have came back
with finish reason "length"

| prompt tokens |24|
| completion tokens |45 |
| elapsed |7.642590584000573|

### 3. Variance

| cell | distinct (recording) | distinct (mine) | median latency |
| closed_short, t=0.0 | 1/12 | 10|0.17 |
| closed_short, t=1.0 | 1/12 |10 | 0.17|
| open_list, t=0.0 | 1/12 |189 |1.10 |
| open_list, t=1.0 | 11/12 | 178|1.14 |

Which cell still returns a single answer at temperature 1.0, and why that one: closed_short at t=1.0, because the question has only one correct, one-word answer — so even with more random sampling, the model keeps converging on the same output.


Which cells a test asserting exact string equality would pass on, and what
that tells me about testing this system: A test asserting exact string equality only passes on deterministic cells (temperature 0, or a closed question with a single correct answer). It fails on any open-ended cell at higher temperature, even when the model's answers are all equally correct in meaning.



**The sentence that carries into week 10.** [One sentence about when you can
and cannot rely on repeating an output. Week 10 will ask you to find this
again. It should not say "the model is random", because your own table shows
otherwise in most cells.]
 
You can rely on an output repeating exactly when the question has a small answer space (short factual questions, or anything at temperature 0); you cannot rely on it for open-ended prompts at nonzero temperature, where many wordings are equally correct — so testing those requires judging meaning, not exact text.

## Week 2

**Run conditions.** model: [qwen3:4b-instruct ] | temperature: 0.0 | prompt version: [ week02-zero-shot-v1] |
served locally | date: [2026-09-27] | scored on: [ my own
machine]

### 1. The output contract

The conventions I chose, and why:

- due_date, when the message states no date: [`None` (Python `date | None`). This keeps the type honest]
- due_date, when the message states only a relative expression: [resolve it to an absolute ISO date if the reference point is clear from context (e.g. "before the end of the month" relative to a known date); otherwise `None`. The prompt states this explicitly so the model isn't left guessing.]
- quote, and what "verbatim" means in my scorer: [an exact substring match (`in document_text`), no lowercasing, no stripping punctuation, no whitespace normalization. The moment the check is relaxed it stops measuring copying and starts measuring approximate copying.]
- what my scorer does with a record that failed validation: [counts it as `invalid`, and marks every one of the four fields wrong for that record.]

[A scorer that skips records it could not parse reports a number that improves every time the model gets worse — the invalid count has to be counted, not hidden, or the metric rewards failure.]

### 2. Zero-shot, per field

| field | correct | of |
| category | 8| 10 |
| urgency | 10| 10 |
| due_date |7 | 10 |
| quote | 9| 10 |
| invalid records | 0| 10 |

My prediction, written before block 3: examples will help most on [due_date ] because [the zero-shot prompt already stated the null convention explicitly in words and the model still invented dates 3 times out of 10 — a concrete example showing message-with-no-deadline → `due_date: null` gives the model a pattern to imitate rather than an abstract instruction it apparently doesn't follow reliably].

### 3. Few-shot

Examples chosen, and the job each one does:

| example | why it is in the block | field it should move |
| EX-02 (fr, facilities/urgent, no date)|shows the facilities boundary and reinforces `due_date: null` with a concrete case| category, due_date|
| EX-03 (de, hardware/standard, with date)|contrasts directly with EX-02 (same "something broken" framing, different category) and shows the non-null date case| category|
|EX-04 (en, other/info, no date)|covers the `other` label, and a second reinforcement of `due_date: null`|category, due_date|
| EX-05 (fr, billing/standard, with date, DD/MM European format) | covers a non-English example with a numeric date, so the block isn't all-English | quote (language diversity), due_date format |


| field | zero-shot | few-shot | move |
| category |8/10|8/10 | +0|
| urgency |10/10 | 10/10| +0|
| due_date |7/10 | 9/10| +2|
| quote |9/10 |10/10 | +1|

### 4. What got worse

[Nothing got worse on the raw counts — `category` stayed flat at 8/10, and `due_date` and `quote` both improved. But the flat `category` number hides a real change: in zero-shot, the only category error was REQ-08 (`facilities` instead of `hardware`). In few-shot, REQ-08 is still wrong the same way, but a new error appeared on REQ-09 (`facilities` instead of `other`, which was correct in zero-shot). So the count is unchanged, but a working case broke while a broken case stayed broken . Both new and old category errors were mislabeled toward `facilities`, which suggests the examples I picked for the facilities/hardware boundary (EX-02, EX-03) may have nudged the model toward `facilities` generally rather than sharpening the boundary as intended.

On `due_date`: two of the three original errors (REQ-01, REQ-05) genuinely disappeared — correct `null` now, not just a different wrong date. REQ-10 persists with the exact same invented date (2024-12-31) as in zero-shot]

### 5. What the examples cost

- extra input tokens per call: [ 347]
- per thousand calls: [347,000 ]
- estimated euros per thousand calls on the small tier: [0.10–0.14€], against the price list dated [2026-08-10 ]. Estimate, not a measurement.

### 6. Ship it or not

[I would ship the few-shot variant. The gain (+2 due_date, +1 quote, nothing worse in aggregate) moves in the direction predicted before running the experiment, which is stronger evidence than a number alone — and due_date was the most concerning zero-shot failure (the model inventing plausible dates, which could trigger wrong actions downstream). The token cost (347 extra input tokens/call) is real but modest in absolute terms. Caveat: ten records means one flipped answer is 10 percentage points, so +2 on due_date could be noise rather than a stable improvement — and the category substitution (REQ-08 stays wrong, REQ-09 newly wrong) shows the few-shot examples aren't purely beneficial even where the aggregate count doesn't show it. What would change my mind: running the same comparison on a larger gold set (week 10's 200 cases) and seeing the due_date gain disappear.]

### Sensitivity variant

Variant assigned: [role]. What I changed: [prepended "You are a senior service desk analyst." to the few-shot prompt from block 3, changing nothing else]. What moved: [category improved by +1 (8/10 → 9/10); urgency, due_date, and quote were unchanged].

### The gold set

Ten cases written to `artifacts/goldset.json`, tagged by language.

One thing my scorer cannot currently detect:

[the scorer cannot distinguish a `category`/`urgency` misclassification caused by genuine ambiguity in the source message from one caused by the model failing to read a clearly stated fact — it only reports "wrong", not "wrong because the message itself was ambiguous." That distinction matters for deciding whether more prompting can fix an error or whether the task itself needs a clearer label taxonomy.]

### Deferred

[Anything you did not get to, and why.]
