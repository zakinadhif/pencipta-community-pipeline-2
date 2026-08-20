# Matching-pipeline experiment harness

This repository is a Marimo laboratory for an AI-assisted people-matching
pipeline. The notebook is a driver; reusable pipeline, storage, prompting, and
cost-accounting code lives in `src/harness/`.

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
marimo edit 05_end_to_end.py  # current end-to-end matching laboratory
```

`01_onboarding.py` and `02_profile_compiler.py` produce inspectable,
user-editable records and drafts only. They never commit a profile or generate
embeddings automatically.

Live runs persist every intermediate result in `data/runs.duckdb`. The bundled
synthetic profiles and evaluation queries can be inspected without an API key;
executing the model stages requires one.

## What is persisted

- immutable run configuration and profile snapshots
- raw streamed events, final API responses, API usage, latency, and errors
- retrieval similarities, prescores, final matches, and human ratings
- optional organization Costs API buckets (requires `OPENAI_ADMIN_KEY`)

Per-call token counts come from the final API usage object. Per-call dollar
values are clearly marked **estimates** based on rates entered in the notebook;
the organization Costs API is the financial source of truth and is stored
separately because it is aggregate rather than attributable to one request.

## Useful commands

```powershell
marimo check 05_end_to_end.py
marimo run 05_end_to_end.py
```

No API key is written to DuckDB or source control.
