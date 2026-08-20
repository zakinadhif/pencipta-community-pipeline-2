import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Evaluation Laboratory")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo

    queries = json.loads((Path(__file__).parent / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    return mo, queries


@app.cell
def _(mo, queries):
    mo.md("""
    # 06 — Evaluation

    This lab holds the fixed query set used to compare retrieval, judge, cost, and latency experiments.
    """)
    mo.ui.table(queries, selection=None)
    return


if __name__ == "__main__":
    app.run()
