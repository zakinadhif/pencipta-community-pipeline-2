# Matching-pipeline experiment harness

This repository is a Marimo laboratory for an AI-assisted people-matching
pipeline. The notebooks are experiment drivers; reusable pipeline, storage,
prompting, evaluation, and cost-accounting code lives in `src/`.

## Start

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Then replace the placeholder in .env with your key.
marimo edit 05_end_to_end.py
```

The work follows the handoffs in `plans/` in order. Begin with the profile
vertical slice, then move into matching:

```powershell
marimo edit 01_onboarding.py
marimo edit 02_profile_compiler.py
marimo edit 03_retrieval.py
marimo edit 04_matching.py
marimo edit 05_end_to_end.py
marimo edit 06_evals.py
```

The six root notebooks cover onboarding, editable profile compilation,
directional retrieval, isolated judging, the complete pipeline, and persisted
evaluation comparisons respectively. The first two produce inspectable,
user-editable records and drafts only; they never commit a profile or generate
embeddings automatically.

Live runs persist every intermediate result in `data/runs.duckdb`. The bundled
synthetic profiles and evaluation queries can be inspected without an API key;
executing the model stages requires one.

The 100-profile fixture is deterministic. Regenerate it after editing the eight
canonical anchor profiles with `python data/generate_synthetic_profiles.py`.

## What is persisted

- immutable run configuration and profile snapshots
- raw streamed events, final API responses, API usage, latency, and errors
- retrieval similarities, prescores, final matches, and human ratings
- optional organization Costs API buckets (requires `OPENAI_ADMIN_KEY`)

Per-call token counts come from the final API usage object. Per-call dollar
values are clearly marked **estimates** based on centralized rates in
`src/costs/pricing.py`;
the organization Costs API is the financial source of truth and is stored
separately because it is aggregate rather than attributable to one request.

## Useful commands

```powershell
marimo check 01_onboarding.py 02_profile_compiler.py 03_retrieval.py 04_matching.py 05_end_to_end.py 06_evals.py
marimo run 05_end_to_end.py
python -m tests.live_smoke  # explicit, billable API smoke checks
```

No API key is written to DuckDB or source control.
