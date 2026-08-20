# Matching-pipeline experiment harness

This repository is a Marimo laboratory for an AI-assisted people-matching
pipeline. The notebook is a driver; reusable pipeline, storage, prompting, and
cost-accounting code lives in `src/harness/`.

## Start

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Then replace the placeholder in .env with your key.
marimo edit experimental_harness.py
```

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
marimo check experimental_harness.py
marimo run experimental_harness.py
```

No API key is written to DuckDB or source control.
