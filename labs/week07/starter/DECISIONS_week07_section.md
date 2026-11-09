# Week 7: a RAG pipeline you can score

Copy this into your `DECISIONS.md` and fill it in.

---

## Week 7

**Run conditions.** embedding model: nomic-embed-text | dimensionality: 768 |
chunk size: 600 | overlap: 80 | k: 5 | store: Chroma | date: 2026-11-09 |
table from: my own index

### 1. The chunker

size 600, overlap 80, because 600 characters holds a short section whole and
keeps a fee or a deadline in the same chunk as the heading that names it,
while 80 characters is about one sentence, enough that a number landing on a
window boundary still appears intact in one of the two chunks that share it.

### 2. The index

84 chunks, 768 dimensions, 1.84 seconds for one full indexing run.

### 3. The table

| qid | dense rank | keyword rank | recall@5 | tags |
| --- | --- | --- | --- | --- |
| Q01 | 1 | 2 | 1.00 | distractor, superseded |
| Q02 | 1 | 1 | 1.00 | rare-token |
| Q03 | 1 | 1 | 1.00 | easy |
| Q04 | 1 | 1 | 1.00 | vocabulary |
| Q05 | 22 | 7 | 0.00 | multi-document |
| Q06 | 1 | 16 | 1.00 | negation |
| Q07 | 1 | 3 | 1.00 | easy |
| Q08 | 1 | 1 | 1.00 | numeric |
| Q09 | 1 | 2 | 1.00 | distractor |
| Q10 | 1 | 1 | 1.00 | easy |
| Q11 | 1 | 5 | 1.00 | easy |
| Q12 | unanswerable | – | – | unanswerable |

### 4. Good pipeline, or easy task?

Easy task: ten of the eleven answerable questions have a single gold section
in a corpus of 84 chunks where each of the ten documents covers a distinct
subject, so rank one measures the absence of competition in the corpus rather
than any quality of the retriever.

### 5. The question that fails on both

Question: Q05, "I have just moved to Remerbaach and I own a car. What do I
have to do at the commune?". Dense rank 22, keyword rank 7.

Why it fails:

Two mechanisms, neither of them granularity. First, the question asks what I
must do and the gold section RB-ARRIVEE::Deadline says by when; the query
never mentions time, so nothing in it points at a section headed Deadline.
The top five show the consequence: RB-ARRIVEE appears twice, at ranks 1 and 3,
both times in the wrong section (Who must declare, (intro)). The retriever
finds the right document and the wrong part of it. Second, "I own a car" sits
closer to a transport document than to a parking vignette, so
RB-VIGNETTE::How to apply loses ranks 2 and 4 to RB-TRANSPORT; the word
vignette is not in the query. Rank 5 is RB-HIVER::What the commune clears,
matched on the surface phrasing "what ... the commune".

Keyword's rank 7 is its only win over dense in the table, and it is a win on
rank that is not a win on usefulness: both retrievers leave recall@5 at 0.00.

A disagreement with the annotation, recorded and left standing. Dense's top
hit, RB-ARRIVEE::Who must declare, arguably does answer "what do I have to
do", and the annotation convention permits replacing it. I am not replacing
it: relabelling a gold section because it costs me recall is the habit this
session exists to break, and the correction in section 6 is a different kind
of thing, a claim about mechanism that measurement falsified rather than a
label that cost me points.

Would any chunk size fix it? No, and demonstrably rather than probably: the
chunker splits within each section and never joins two, so raising size can
only reduce the number of chunks per section, never merge Who must declare
with Deadline. The sweep below measures it: 30 at 300 characters, 22 at 600,
20 at 1200, monotone in the right direction and nowhere near the top five.
The failure is compositional, the answer being the union of two documents, and
it is addressed upstream or downstream of the chunker by query decomposition,
multi-query retrieval, or a higher k with reranking.

### The chunk sweep

300/40 gives 145 chunks, 600/80 gives 84, 1200/160 gives 57. Dense rank of the
first gold chunk, by question:

| qid | 300 | 600 | 1200 |
| --- | --- | --- | --- |
| Q01 | 1 | 1 | 1 |
| Q02 | 1 | 1 | 1 |
| Q03 | 1 | 1 | 1 |
| Q04 | 1 | 1 | 1 |
| Q05 | 30 | 22 | 20 |
| Q06 | 1 | 1 | 1 |
| Q07 | 1 | 1 | 1 |
| Q08 | 1 | 1 | 1 |
| Q09 | 1 | 1 | 1 |
| Q10 | 1 | 1 | 1 |
| Q11 | 1 | 1 | 1 |

Dense retrieval is invariant to chunk size here: rank one on ten of eleven
questions at every size tried. recall@5 does not move either, holding 1.00 on
those ten and 0.00 on Q05 across all three configurations, which makes it a
third metric that cannot vary on this data.

Q05 is the only question that responds, improving monotonically with size
(30, 22, 20) without ever reaching the top five. That is the empirical form of
section 5's answer: larger chunks help, because a bigger window around a gold
section catches more of the generic arrival language the query resembles, but
the ceiling is structural. The chunker splits within sections and never joins
them, so no size merges Who must declare with Deadline.

Keyword rank, by contrast, swings non-monotonically with size: Q06 goes
11/16/4, Q11 goes 18/5/6, Q02 goes 8/1/1. The dense-against-keyword gap is
therefore a property of the configuration as much as of the two retrievers,
and the divergence recorded in section 6 against WEEK07_FINDINGS.md is
explained by it: at 300 characters my keyword rank for Q02 is 8, moving toward
their 12.

Keeping 600/80. Nothing in the sweep argues for changing it: 1200 buys two
ranks on a question that fails anyway, and since the wire-in returns chunk
text to the caller, doubling the chunk size doubles the token cost of every
hit that MemoryStore.search hands back.

### Where meaning beats words

Q06, "Do I need to pay for the communal shuttle bus?": dense rank 1, keyword
rank 16, the widest gap in the table. The document says travel is free of
charge and the question asks about paying, so the two share no term on the
concept that decides the answer. Keyword search has only "communal shuttle
bus" to work with and spreads its score across every section of RB-TRANSPORT;
the embedding places free-of-charge next to pay and puts Fares first. Dense
retrieval earns its cost on the questions where the user's words and the
document's words name the same thing differently.

### 6. The gold-set correction

The note said: the string RB-1140b is rare, exact and semantically empty, so
dense retrieval is the wrong tool for Q02 and keyword search is the right one.

My measurement said: dense ranks the gold chunk first and keyword also ranks
it first, so dense is not the wrong tool and keyword is not needed. The query
is not semantically empty — "fill in form ... what is it for" aligns with the
section heading How to apply, which the chunker prepends to every chunk. The
superseded page's near-identical RB-1140a is a real distractor but a weak one:
RB-VIGNETTE-2024::How to apply takes rank 2 for dense, never rank 1.

The corrected note:

"The query carries the string RB-1140b: rare and exact. Measured, this is not
where dense retrieval loses. Both retrievers put the gold chunk first (dense
1, keyword 1), because the query is not semantically empty: 'fill in form ...
what is it for' aligns with the section heading 'How to apply', which the
chunker prepends to every chunk. The superseded page's near-identical RB-1140a
is a real distractor but a weak one, taking rank 2 for dense and never rank 1.
Testing the rare-token claim properly needs a query that is the token alone,
with no surrounding words."

Independent confirmation, and a divergence worth recording. The course's own
WEEK07_FINDINGS.md probed this corpus in August and reached the same
conclusion by a different route: it measured keyword at rank 12 on Q02, so
keyword is not merely unnecessary but worse. Its dense ranks agree with mine
on all eight questions it lists, including Q05 at 22; its keyword ranks differ
on four of them (Q02 1 vs 12, Q03 1 vs 3, Q05 7 vs 30, Q06 16 vs 7). The dense
half of the pipeline is reproducible because corpus and embedder fix it; the
keyword half is implementation-defined, and my scorer counts distinct query
terms without weighting rarity or normalising for length. The sweep above
shows how far configuration alone moves it. The falsified claim survives both
measurements; the numbers behind it belong to one implementation.

What it cost to find: one indexing run and one table, about five seconds of
compute. What it would have cost not to find: the hybrid-retrieval stretch is
built on the premise that keyword search rescues the rare-token question, so
the next session would have been spent making a true thing out of a false one.

### Wire-in

`MemoryStore.search(subject, query, k)` keeps its signature. Dense retrieval
over the corpus at 600/80 sits behind it in `app/memory.py`, with the index
built once per process. `app/` did not exist in this repository and was
created this session; `python -m app.run --subject "A. Muller" "How do I
register a new address?"` returns 3 hits.

Three things changed behind the unchanged signature, and a caller cannot see
any of them:

- `subject` no longer scopes the corpus half of the result. Week 6's facts are
  still subject-scoped, in `_search_facts`; the corpus is shared published
  material and is searched unscoped. Facts come first, the corpus fills the
  remainder of k.
- The token cost of k rose by an order of magnitude: ~15 tokens per fact in
  week 6, ~150 per corpus chunk now, so k=3 moved from ~45 tokens per call to
  ~450 when no stored fact matches.
- `search` acquired a network dependency. It raises when the embedder is
  unreachable rather than returning zero hits, because an empty recall and an
  unreachable embedder would otherwise be indistinguishable.

One defect the wire-in exposed and block 2 could not. The first query returned
RB-VIGNETTE-2024::How to apply at rank 3, carrying the obsolete form RB-1140a
next to the current RB-1140b. The annotation convention keeps that document in
the corpus precisely to measure what a retriever does with superseded content,
and the answer is that it returns it, in the same shape as the current page
and with no marker. Neither metric used today could have caught it: rank of
the first gold chunk and recall@5 both describe where the correct chunk landed
and say nothing about what else came back. The fix is a metadata filter at
query time, keyed either on a front-matter status field or on a doc id.

### What this measurement still cannot tell me

Nothing in rank-of-first-gold or recall@5 describes what came back beside the
gold chunk, which is why the superseded 2024 page reached rank 3 in the
wire-in without either number moving.
