import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Matching Laboratory")


@app.cell
def _():
    import marimo as mo

    return mo,


@app.cell
def _(mo):
    mo.md("""
    # 04 — Mutual matching

    This lab will isolate the judge and match-explanation stages after retrieval is validated.
    The reusable prompt contracts already live under `src/agents/`; the complete composed flow remains in `05_end_to_end.py`.
    """)
    return


if __name__ == "__main__":
    app.run()
