# Handoff Consistency Audit and Remediation Log

Status: in progress  
Created: 2026-08-20  
Source of truth:

- `plans/ai_collaboration_social_network_mvp_handoff.md` (all 1,349 lines reviewed)
- `plans/marimo_prototype_evaluation_handoff.md` (all 1,220 lines reviewed)

This file is intentionally kept as a durable, uncommitted execution artifact until the remediation is complete and explicitly committed by the user.

## Rules that must remain true

- Keep the five agent prompts verbatim and retain explicit prompt versions.
- Keep the six Marimo notebooks at the repository root.
- Use `gpt-5.6-terra`/low for onboarding, `gpt-5.6-luna`/low for profile and need work, `gpt-5.6-terra`/medium for judging, and `gpt-5.6-luna`/low for introductions.
- Preserve directional matching: requester needs → candidate offers, shared interests, requester offers → candidate needs.
- Never expose unrestricted mutation, SQL, messaging, browsing, or autonomous-contact tools to agents.
- Keep reusable logic under `src/`; notebooks are interactive experiment drivers.
- Do not commit or push this remediation without an explicit user request.

## Remediation checklist

### A. Runtime correctness

- [x] Fix `PROFILE_SCHEMA` so every strict Structured Outputs property is required; represent optional project fields as nullable.
- [x] Add a live-compatible regression test for all strict schemas.
- [x] Make interaction filtering fall back to interpreted interaction types when `hardFilters.interactionTypes` is empty.
- [x] Consume the Need Interpreter's `retrievalQueries.needs` field or remove the dead field without breaking directional reciprocity.
- [x] Persist onboarding completion across Marimo chat turns and prevent post-completion reopening.
- [x] Detect and preserve empty retrieval, malformed judge IDs, and other stage failures instead of silently discarding them.

### B. Shared observability and cost accounting

- [x] Implement a standard `LLMTrace` contract under `src/tracing/`.
- [x] Route onboarding, profile compilation, pipeline responses, and embeddings through observable result/trace objects.
- [x] Persist authoritative final usage, stream timestamps, TTFT, latency, errors, request, response, response ID, and prompt version.
- [x] Trace embedding calls and include their latency/usage where available.
- [x] Centralize updateable model pricing in `src/costs/pricing.py`; remove notebook-entered per-token rates.
- [x] Generate per-run totals and per-stage metrics from stored traces.

### C. Marimo laboratories

- [x] `01_onboarding.py`: expose model, reasoning, prompt version, max turns/output; show tool events, raw/turn traces, tokens, latency, cost, cumulative totals, and final transcript.
- [x] `02_profile_compiler.py`: show exact request, raw response, parsed profile, trace metrics, prompt version, optional existing profile, and an editable accepted draft.
- [x] `03_retrieval.py`: implement requester/query/need controls, weights/count controls, directional queries, similarity/prescore table, and candidate detail inspection.
- [x] `04_matching.py`: implement isolated judge controls, exact judge input, raw stream, structured matches, prescore comparison, and saved human ratings.
- [ ] `05_end_to_end.py`: show exact inputs and each stage in order, trace tables, aggregate metrics, failures, and visible progressive stream state.
- [x] `06_evals.py`: implement evaluation runs/comparison views and Good@K, AnyGood@K, latency/cost, and retrieval-recall proxy metrics.

### D. Dataset and documentation

- [ ] Expand the synthetic dataset toward the handoff's 100-profile minimum while keeping it inspectable and deterministic.
- [x] Include all six canonical specific evaluation queries from the MVP handoff.
- [x] Correct README paths and describe every root notebook accurately.
- [x] Ensure DuckDB location and documentation agree.

### E. Verification

- [x] Unit tests cover strict schemas, interaction filtering, directional retrieval, onboarding completion, tracing/costs, metrics, and malformed judge output.
- [x] All tests pass.
- [x] All six notebooks pass `marimo check`.
- [ ] Targeted live API smoke tests pass for onboarding tools and profile structured output.
- [x] `git diff --check` passes.
- [x] Working tree contains only deliberate, uncommitted remediation changes.

## Initial evidence

- All five prompt constants are verbatim substrings of the MVP handoff.
- Live profile compilation failed with HTTP 400 because project `name` and `status` were properties omitted from `required`.
- A candidate with `openTo=[]` passed a mentoring search when `hardFilters.interactionTypes=[]`.
- `03_retrieval.py`, `04_matching.py`, and `06_evals.py` were placeholders.
- `src/schemas/search.py`, `src/schemas/matching.py`, and `src/schemas/traces.py` were empty.
- `src/costs/pricing.py` was empty and notebook-entered rates defaulted cost estimates to zero.
- The dataset contained 8 profiles and 4 evaluation queries.

## Execution log

- 2026-08-20: Audit completed; all source handoff lines loaded and reviewed.
- 2026-08-20: Previous onboarding-tool fix committed separately as `a82cc2e` before remediation began.
- 2026-08-20: Remediation artifact created; implementation started.
- 2026-08-20: Continued remediation; completed evaluation metrics/lab and canonical query coverage, corrected README, and fixed a Marimo cross-cell definition error.
- 2026-08-20: Verification snapshot: 12 tests passed, all six notebooks passed `marimo check`, and `git diff --check` passed. Live API smoke tests and dataset expansion remain outstanding.
