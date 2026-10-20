
## Week 6

**Run conditions.** MCP SDK version: mcp==2.0.0rc1 | specification revision:
2026-07-28 | model: qwen2.5:7b (memory comparison only; blocks 1–3 run without a model) | served locally | date: 2026-10-20

### 1. The handle

Format I chose: `fact-` + 16 hex chars from `secrets.token_hex(8)` (64 random bits), e.g. `fact-f4b562cdb55d4fff`; cases use the same scheme, `case-` + 12 hex.

A guessable handle would expose: how many facts exist, and the neighbouring handles (`fact-0006` next to `fact-0007`), so anyone holding one handle could enumerate and read other residents' facts.


### 2. Conflict and retention

- A write that contradicts an older fact: overwrite, per (subject, kind), because `recall` then never returns two contradictory facts to the model; the cost is losing the previous value, only `written_at` of the current one survives.
- How long a record lives: 90 days from `written_at`, hard-deleted on the next write or search, because keeping residents' data forever has no justification and an unpurged record is still held data.


[Nothing expires by default. If you kept it that way, say so explicitly
rather than leaving it unsaid. An undeclared retention policy is still a
retention policy.]

### 3. What k costs

k = [3 ]. Tokens added per call: [ ~15 per fact (`[kind] text`), so ~45–50 per call; linear in k, independent of store size.].

At four hundred facts in the store, this design costs the same tokens per call (k caps the output), but scans all facts on every call (O(n), reduced by the subject filter) and keyword overlap returns more false positives and misses synonyms: the reason week 7 moves `search` to embeddings.

### 4. Memory off against memory on

| | tokens | turns to finish |
|---|---|---|
| memory off | 1642 | 4 |
| memory on | 1349 | 3 |

Measured with `starter/04_memory_compare.py`: qwen2.5:7b, temperature 0, 3 runs per mode (identical, so this is one deterministic run, not a variance estimate), task = establish channel, time and language for one resident; both modes can ask the (rule-simulated) resident, memory on also has `recall`. Correct 3/3 in both.

Memory costs more per call (~450 vs ~410 tokens: the recalled facts sit in every later prompt) and saves a whole call, so the total drops by ~18%. Here it was a win because the facts were already stored and one `recall` replaced several questions; on a task where nothing relevant is stored, `recall` is a pure extra call and memory on would cost more.


### 5. The protocol, at the wire

| server mode | status | Mcp-Session-Id | answered |
| stateless_http=True | 200 | none | yes |
| stateless_http=False | 400 | cae2132458a9424c9052831f8e5ec1b5 | no |

The error the session-mode server returned, quoted exactly:

`{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Bad Request: Missing session ID"}}`

Why the two-server handle demonstration does not prove this on its own:

It passes identically in session mode: the state lives in a shared file and every call opens its own connection, so the handle resolving on :8001 only shows that a file is a file. Only the identical raw request, answered by one mode and refused by the other, fails when statelessness is switched off.


### 6. What forget does not reach
Anything already copied into a running conversation's messages, logs or traces, and any backup of the store. Deleting the fact does not un-say it: the model can still repeat it until that conversation ends. A resident's deletion request is therefore not fulfilled by `forget` alone; the active conversation and logs must be handled too.

### Deferred

