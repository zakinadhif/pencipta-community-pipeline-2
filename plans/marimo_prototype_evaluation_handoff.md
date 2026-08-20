# Marimo Prototype & Evaluation Harness — Handoff

## 1. Purpose

This document describes how to prototype and evaluate the AI collaboration/matching pipeline before building the full product UI.

The prototype is not intended to impersonate the final social network.

Its purpose is to make the entire AI pipeline inspectable:

- step by step
- model call by model call
- streamed output by streamed output
- token usage by token usage
- latency by latency
- cost by cost
- candidate by candidate
- prompt version by prompt version

The primary goal is to answer:

> Does the matching system actually produce useful people, and what does each successful search cost?

---

# 2. Tool Choice

Use **marimo** for this phase.

Why marimo fits:

- reactive notebook model
- easy to expose intermediate pipeline state
- suitable for parameter controls and experiments
- notebooks are stored as normal Python files
- good fit for comparing prompts/models/configurations
- easier to reason about experimental dependencies than a script that reruns top-to-bottom
- can still be served as an interactive app when teammates need to try it

Do **not** use Streamlit as the main experimental harness.

Streamlit is more appropriate later if the goal becomes:

> Build a quick app-like shell for external users to experience the product flow.

For now, marimo is the better fit because the prototype should function as an **AI/algorithm laboratory**.

---

# 3. Prototype Philosophy

The notebooks should expose the system rather than hide it.

For every run, we should be able to see:

1. original input
2. exact prompt/configuration
3. raw model output
4. parsed structured output
5. retrieval queries
6. retrieved candidates
7. embedding similarity scores
8. prescoring calculations
9. final judge context
10. judge output
11. final explanation
12. token usage
13. latency
14. estimated cost
15. human evaluation

The notebook should make it easy to answer questions such as:

- Why did this person rank #1?
- What happens if candidate count changes from 10 to 20?
- Is the stronger model actually better here?
- Does medium reasoning meaningfully improve match quality?
- Is the expensive match judge worth the additional cost?
- How much does each stage contribute to total latency?
- How much does each stage contribute to total spend?
- Which prompt version performs best?
- Which retrieval weights produce better candidates?
- How many candidates need LLM reranking?
- Are embeddings or reranking causing bad results?

---

# 4. Repository Structure

Recommended structure:

```text
/ (workspace root)
  01_onboarding.py
  02_profile_compiler.py
  03_retrieval.py
  04_matching.py
  05_end_to_end.py
  06_evals.py

  src/
    agents/
      onboarding.py
      profile_compiler.py
      need_interpreter.py
      match_judge.py
      introduction.py

    retrieval/
      embeddings.py
      search.py
      prescore.py

    tracing/
      trace.py
      storage.py

    costs/
      pricing.py
      calculator.py

    schemas/
      profile.py
      search.py
      matching.py
      traces.py

  data/
    synthetic_profiles.json
    eval_queries.json

  runs.duckdb
```

Important rule:

> Core pipeline logic belongs under `src/`, not directly inside notebook cells.

The notebooks should be interactive views and experiment drivers over reusable application logic.

This makes the eventual production implementation easier to port or reuse.

---

# 5. Notebook Breakdown

## `01_onboarding.py`

Purpose:

- test conversational onboarding
- inspect every model turn
- inspect how many turns are needed
- inspect token growth across turns
- compare prompt variants
- evaluate whether the conversation gathers enough useful information

Controls:

```text
model
reasoning effort
system prompt version
synthetic persona / manual user input
max onboarding turns
```

Display:

```text
conversation
raw streaming output
per-turn token usage
per-turn cost
cumulative cost
latency
final conversation transcript
```

Useful evaluation questions:

- Does onboarding feel natural?
- Does it ask unnecessary questions?
- Does it distinguish interest from experience?
- Does it discover canHelpWith and lookingFor?
- Does it stop at the right point?
- How expensive is one onboarding session?

---

## `02_profile_compiler.py`

Purpose:

- turn onboarding transcripts into structured profiles
- compare compiler prompts
- inspect profile quality
- test edits and recompilation

Inputs:

```text
onboarding transcript
existing profile (optional)
compiler prompt version
model
```

Display side by side:

```text
SOURCE CONVERSATION

↓

RAW MODEL OUTPUT

↓

PARSED PROFILE

headline
summary
knowledge[]
experience[]
interests[]
canHelpWith[]
lookingFor[]
openTo[]
projects[]
location
```

Add an editable JSON/profile panel to manually inspect or correct output.

Evaluation questions:

- Did the compiler invent anything?
- Did it collapse interest into expertise?
- Is the profile concise enough?
- Is important matching information lost?
- Are entries too vague?
- Would another human understand the person at a glance?

---

## `03_retrieval.py`

Purpose:

- inspect semantic retrieval independently from LLM ranking
- understand whether the embedding representation is producing good candidate pools

Inputs:

```text
requester
query
Need Interpreter output
retrieval weights
candidate count
```

Display:

```text
interpreted need

offers retrieval query
interests retrieval query
needs retrieval query

↓

candidate table
```

Suggested candidate table:

| Rank | Person | Offers Sim | Interest Sim | Reciprocal Sim | Interaction Fit | Prescore |
|---|---|---:|---:|---:|---:|---:|

Allow expansion of each row to inspect:

```text
headline
summary
knowledge
experience
interests
canHelpWith
lookingFor
openTo
```

Evaluation questions:

- Is the right person even reaching the shortlist?
- Are similar beginners incorrectly outranking useful experts?
- Is reciprocity helping or hurting retrieval?
- What candidate pool size is sufficient?
- How much does each embedding dimension contribute?

---

## `04_matching.py`

Purpose:

- isolate the expensive mutual-match judge
- compare models, prompts, reasoning effort and shortlist sizes

Controls:

```text
judge model
reasoning effort
prompt version
candidate count
include / exclude requester profile
include / exclude prescore
```

Display:

```text
EXACT JUDGE INPUT

request
interpreted need
requester profile
candidate profiles

↓

RAW STREAM

↓

STRUCTURED MATCHES
```

Suggested result view:

| Rank | Candidate | Judge Score | Prescore | Reason |
|---|---|---:|---:|---|

Then provide human rating controls:

```text
Good
Okay
Bad
```

Evaluation questions:

- Does the model actually improve ranking over prescore?
- How often does a cheaper model choose the same top candidates?
- Is medium reasoning better than low reasoning?
- Does increasing shortlist size improve quality enough to justify cost?
- Does the judge understand complementarity?
- Does it correctly penalize interaction mismatch?

---

## `05_end_to_end.py`

Purpose:

Run the actual MVP discovery loop exactly as production would.

Flow:

```text
query
  ↓
Need Interpreter
  ↓
embedding retrieval
  ↓
prescore
  ↓
shortlist
  ↓
Mutual Match Judge
  ↓
Introduction Agent
  ↓
final results
```

This notebook should be the main demonstration harness.

Top controls:

```text
Requester:
[ select profile ]

Query:
[____________________________________________]

Need model:
[ Luna ]

Judge model:
[ Terra ]

Judge reasoning:
[ medium ]

Retrieval candidates:
[ 30 ]

Judge shortlist:
[ 12 ]

[ Run Pipeline ]
```

Then display each stage in order.

---

# 6. Recommended End-to-End Layout

Conceptual notebook view:

```text
┌─────────────────────────────────────────────┐
│ INPUT                                       │
│                                             │
│ requester profile                           │
│ natural-language query                      │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 1. NEED INTERPRETER                         │
│                                             │
│ prompt                                      │
│ streamed output                             │
│ parsed structured output                    │
│ model / latency / tokens / cost             │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 2. EMBEDDING + RETRIEVAL                    │
│                                             │
│ generated retrieval queries                 │
│ similarity values                           │
│ retrieved candidates                        │
│ retrieval latency / embedding cost          │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 3. PRESCORING                               │
│                                             │
│ offer score                                 │
│ interest score                              │
│ reciprocal score                            │
│ final heuristic score                       │
│ shortlist                                   │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 4. MATCH JUDGE                              │
│                                             │
│ exact context sent to model                 │
│ streamed output                             │
│ final structured ranking                    │
│ tokens / latency / cost                     │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│ 5. INTRODUCTION                             │
│                                             │
│ why this person                             │
│ why you                                     │
│ possible opener                             │
│ tokens / latency / cost                     │
└─────────────────────────────────────────────┘
```

At the top or bottom, always display aggregate run metrics.

---

# 7. Standard Trace Object

Every LLM call should emit the same trace structure.

Suggested Python type:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class LLMTrace:
    run_id: str
    call_id: str
    stage: str

    model: str
    reasoning_effort: str | None

    prompt_version: str

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int

    time_to_first_delta_ms: float | None
    total_latency_ms: float

    estimated_cost_usd: float

    request: Any
    response: Any
```

Useful additional fields:

```python
created_at
error
retry_count
response_id
```

The exact schema can evolve, but all model calls must be observable through one common interface.

---

# 8. Streaming Instrumentation

Do not assume each streaming delta corresponds to exactly one tokenizer token.

Capture stream events with timestamps:

```text
0 ms       request sent
483 ms     first output delta
497 ms     next delta
512 ms     next delta
...
2381 ms    response completed
```

Then store authoritative final usage from the completed response.

Metrics:

```text
time to first output
total generation latency
input tokens
cached input tokens
output tokens
reasoning tokens
total tokens
estimated cost
```

Optional derived metric:

```text
output throughput
≈ output_tokens / generation_seconds
```

The notebook may display the generated text live, but final token counts must come from the API usage object rather than assuming stream chunks equal tokens.

---

# 9. Cost Tracking

Centralize model pricing.

Do not scatter hardcoded prices through notebooks.

Suggested:

```text
src/costs/pricing.py
```

Conceptual structure:

```python
MODEL_PRICING = {
    "model-name": {
        "input_per_million": ...,
        "cached_input_per_million": ...,
        "output_per_million": ...,
    }
}
```

Then:

```python
estimate_cost(usage, model)
```

If reasoning tokens are billed as output tokens for the selected model/API semantics, handle that centrally in the calculator.

The exact pricing table should be easy to update.

---

# 10. Per-Run Metrics

For each pipeline run, show something like:

```text
PIPELINE TOTAL

LLM calls                 3
Embedding calls           2

Input tokens          10,411
Cached input tokens    1,820
Output tokens            712
Reasoning tokens          621

TTFT                     483 ms
Total latency            6.2 s

Estimated API cost     $0.0xxx
```

Also show cost by stage:

| Stage | Model | Input | Output | Reasoning | Latency | Cost |
|---|---|---:|---:|---:|---:|---:|
| Need Interpreter | Luna | ... | ... | ... | ... | ... |
| Embeddings | embedding model | ... | — | — | ... | ... |
| Match Judge | Terra | ... | ... | ... | ... | ... |
| Introduction | Luna | ... | ... | ... | ... | ... |

This should be generated automatically from traces.

---

# 11. Persistent Experiment Storage

Do not keep evaluation data only in notebook memory.

Use **DuckDB** for the prototype.

Recommended tables:

```text
runs
llm_calls
retrieval_results
candidate_scores
match_results
human_evaluations
```

Suggested `runs`:

```text
id
requester_id
query
config_json
created_at
total_latency_ms
total_cost_usd
```

Suggested `llm_calls`:

```text
id
run_id
stage

model
reasoning_effort
prompt_version

input_tokens
cached_input_tokens
output_tokens
reasoning_tokens

ttft_ms
latency_ms
cost_usd

request_json
response_json

created_at
```

Suggested `retrieval_results`:

```text
run_id
candidate_id

offers_similarity
interests_similarity
reciprocal_similarity
interaction_score
prescore
retrieval_rank
```

Suggested `match_results`:

```text
run_id
candidate_id

judge_rank
judge_score
judge_reason

shown
```

Suggested `human_evaluations`:

```text
run_id
candidate_id

rating
notes
created_at
```

---

# 12. Prompt Versioning

Every prompt must have an explicit version.

Examples:

```text
need_interpreter_v1
need_interpreter_v2

match_judge_v1
match_judge_v2
```

Store prompt version with every run.

Prefer prompt source files under:

```text
src/agents/prompts/
```

For example:

```text
src/agents/prompts/
  onboarding_v1.txt
  profile_compiler_v1.txt
  need_interpreter_v1.txt
  match_judge_v1.txt
  introduction_v1.txt
```

Do not silently edit a production experiment prompt while keeping the same version string.

The purpose is to make questions such as this answerable:

> Did match judge v7 actually perform better than v6?

---

# 13. Human Evaluation Panel

Human evaluation should be part of the prototype from the start.

For each returned candidate:

```text
#1 Sarah

Why:
Has previously run a student organization and is open to helping
other student leaders with volunteer retention.

[ Good ] [ Okay ] [ Bad ]

Optional notes:
[_________________________________________]
```

Store each evaluation.

Do not rely only on the model's own score.

---

# 14. Evaluation Dataset

Create:

```text
data/eval_queries.json
```

Use intentionally specific queries.

Examples:

```text
someone who has deployed an AT Protocol PDS themselves

a senior developer who actually enjoys teaching beginners

someone who started a student organization and knows how to keep
volunteers motivated

a designer who likes brutalist interfaces and wants side projects

someone who has travelled to Japan as a Muslim and can help me plan

someone who understands accounting but wants help learning programming
```

For controlled evaluation, maintain a synthetic or curated profile dataset where expected useful matches can be manually reasoned about.

Start with:

```text
100–500 profiles
```

Profiles do not need to be real users during early pipeline development.

---

# 15. Evaluation Metrics

Do not optimize for embedding similarity alone.

Useful prototype metrics:

## Ranking quality

```text
Good@1
Good@3
Good@5

AnyGood@3
AnyGood@5
```

Example:

```text
Good@3 =
percentage of top-3 returned results manually rated "Good"
```

## Search usefulness

```text
percentage of queries with at least one Good result
```

This may be the most important early metric.

## Cost

```text
average cost / search
p50 cost / search
p95 cost / search

average cost / onboarding
```

## Latency

```text
p50 search latency
p95 search latency
time to first visible output
```

## Retrieval recall proxy

For manually evaluated test cases:

```text
Was a known-good candidate present in the retrieval shortlist?
```

This distinguishes:

```text
retrieval failure
```

from:

```text
ranking failure
```

That distinction is extremely important.

---

# 16. Experiment Comparison

The harness should make it easy to run the same evaluation set with different configurations.

Example:

```text
Experiment A
judge = Luna
reasoning = low
shortlist = 10

Experiment B
judge = Terra
reasoning = low
shortlist = 10

Experiment C
judge = Terra
reasoning = medium
shortlist = 10

Experiment D
judge = Terra
reasoning = medium
shortlist = 20
```

Then produce a comparison table:

| Configuration | Any Good @ 3 | Good @ 3 | Avg Cost/Search | P50 Latency |
|---|---:|---:|---:|---:|
| Luna / low / 10 | ... | ... | ... | ... |
| Terra / low / 10 | ... | ... | ... | ... |
| Terra / medium / 10 | ... | ... | ... | ... |
| Terra / medium / 20 | ... | ... | ... | ... |

Model choice should eventually be justified by these measurements rather than intuition.

---

# 17. Retrieval Experiment Controls

Expose these as notebook controls:

```text
offers weight
interests weight
reciprocity weight
interaction compatibility weight

initial retrieval count
judge shortlist count
```

Starting prescore:

```text
score =
    0.45 * offer_match
  + 0.20 * interest_match
  + 0.20 * reciprocal_need_match
  + 0.15 * interaction_compatibility
```

These weights are only initial heuristics.

Do not overfit them before enough evaluations exist.

---

# 18. Agent Experiment Controls

Expose:

```text
model
reasoning effort
prompt version
temperature / sampling parameters where supported/relevant
max output
shortlist size
```

Do not expose dozens of meaningless knobs.

Prioritize parameters that materially affect:

- quality
- cost
- latency

---

# 19. Error Inspection

Every pipeline stage should preserve failed runs.

Do not discard them.

Capture:

```text
schema validation failures
API errors
retries
empty retrieval
invalid structured output
judge returning no matches
judge returning malformed IDs
embedding errors
```

The notebook should make failed stages inspectable.

A pipeline harness is useful precisely because broken behavior should be visible.

---

# 20. Reproducibility

For each run, persist:

```text
input
requester profile snapshot
candidate profile snapshots or stable IDs + version
model
prompt version
reasoning effort
retrieval weights
candidate counts
structured intermediate outputs
timestamps
```

If practical, also persist the raw API response IDs.

A run should be reproducible enough that the team can understand why an old result occurred.

---

# 21. Recommended End-to-End Run Object

Conceptually:

```python
@dataclass
class PipelineRun:
    run_id: str

    requester_id: str
    query: str

    config: dict

    need_interpretation: dict

    retrieval_results: list
    prescored_candidates: list

    final_matches: list
    introductions: list

    llm_traces: list[LLMTrace]

    total_latency_ms: float
    total_cost_usd: float
```

This can later map directly into stored DB records.

---

# 22. Streamlit Decision

Do not build both Streamlit and marimo simultaneously.

Use:

```text
marimo
   ↓
prove pipeline quality
   ↓
freeze initial interfaces
   ↓
build actual product
```

Streamlit is optional later.

Use Streamlit only if there is a concrete need for a disposable app-like user test shell before the actual JS/TS application exists.

Otherwise skip it.

Marimo itself can provide enough interactivity for internal and teammate evaluation.

---

# 23. Prototype Non-Goals

The marimo prototype does **not** need:

- polished visual design
- production auth
- production messaging
- social feed
- push notifications
- mobile responsiveness
- real-time presence
- sophisticated permissions
- production observability platform
- production-scale infrastructure
- autonomous agents
- final frontend architecture

It exists to evaluate the intelligence layer.

---

# 24. Success Criteria for the Harness

The harness is successful when the team can answer these questions with data:

### Matching

- Does the system consistently surface genuinely useful people?
- Are failures caused by retrieval or ranking?
- Does reciprocity improve results?
- Does complementarity work better than plain similarity?

### Models

- Does the stronger judge model materially outperform the cheaper one?
- Is medium reasoning worth its cost?
- What is the cheapest model configuration that preserves acceptable quality?

### Retrieval

- How many candidates must be retrieved?
- How many should reach the judge?
- Which embedding representation contributes the most?

### Cost

- What does one onboarding session cost?
- What does one search cost?
- Which stage dominates spend?

### Latency

- What is the end-to-end search latency?
- Which stage dominates latency?
- How quickly can the user see useful progressive output?

### Prompts

- Which prompt versions perform better on the same evaluation set?

---

# 25. Core Principle

> Do not use the prototype merely to prove that the pipeline runs.

Use it to determine whether each expensive piece of intelligence earns its place.

The ideal progression is:

```text
simple retrieval
      ↓
measure

+ deterministic prescore
      ↓
measure

+ cheap judge
      ↓
measure

+ stronger judge
      ↓
measure

+ more reasoning
      ↓
measure
```

Every additional AI capability should have an observable quality benefit relative to its cost and latency.

---

# 26. One-Sentence Handoff Summary

> Build a marimo-based experimental harness around reusable pipeline code, persist every intermediate result and model trace in DuckDB, expose the important model/retrieval controls interactively, stream model output for inspection, use authoritative API usage data for token and cost accounting, and evaluate configurations against human-rated matching quality rather than relying on model scores alone.
