import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Retrieval Laboratory")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo

    profiles = json.loads((Path(__file__).parent / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    return mo, profiles


@app.cell
def _(mo, profiles):
    mo.md("""
    # 03 — Retrieval

    Inspect candidate pools, directional similarity, and deterministic prescores here.
    Embedding generation is the next implementation milestone; the current lexical baseline lives in `src/retrieval/`.
    """)
    mo.ui.table(profiles, selection=None)
    return


if __name__ == "__main__":
    app.run()
