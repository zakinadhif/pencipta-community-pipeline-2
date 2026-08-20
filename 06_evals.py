import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Evaluation Laboratory")


@app.cell
def _():
    import json
    from pathlib import Path
    import marimo as mo
    from src.evaluation.metrics import aggregate_metrics, ranking_metrics
    from src.tracing.storage import ExperimentStore
    root = Path(__file__).parent
    queries = json.loads((root / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    store = ExperimentStore(root / "data" / "runs.duckdb")
    return aggregate_metrics, mo, queries, ranking_metrics, store


@app.cell
def _(mo, queries):
    mo.md("""
    # 06 — Evaluation laboratory

    Compare persisted configurations using human ratings, retrieval recall proxies,
    latency, and estimated cost. Model judge scores are never ground truth.
    """)
    query_table = mo.ui.table(queries, selection=None, label="Fixed evaluation queries")
    refresh = mo.ui.run_button(label="Refresh persisted evaluations")
    mo.vstack([query_table, refresh])
    return (refresh,)


@app.cell
def _(aggregate_metrics, mo, queries, ranking_metrics, refresh, store):
    mo.stop(not refresh.value)
    _runs_df = store.dataframe("select id, query, config_json, status, error, total_latency_ms, estimated_cost_usd, created_at from runs order by created_at desc")
    _evals_df = store.dataframe("select run_id, candidate_id, rating, notes, created_at from human_evaluations order by created_at desc")
    _retrieval_df = store.dataframe("select run_id, candidate_id, retrieval_rank, prescore from retrieval_results order by run_id, retrieval_rank")
    _runs = _runs_df.to_dict("records")
    summary = aggregate_metrics(_runs)
    _rating_rows = []
    if not _evals_df.empty:
        for _run_id, _group in _evals_df.groupby("run_id"):
            _ordered = _group.merge(_retrieval_df, how="left", on=["run_id", "candidate_id"]).sort_values("retrieval_rank", na_position="last")
            _rating_rows.append({"run_id": _run_id} | ranking_metrics(_ordered["rating"].tolist()))
    _known_good = {item["query"]: set(item.get("known_good_candidate_ids", [])) for item in queries}
    _recall_rows = []
    for _run in _runs:
        _expected = _known_good.get(_run["query"], set())
        _retrieved = set(_retrieval_df.loc[_retrieval_df["run_id"] == _run["id"], "candidate_id"].tolist())
        _recall_rows.append({"run_id": _run["id"], "query": _run["query"], "known_good_count": len(_expected), "retrieved_known_good": len(_expected & _retrieved), "retrieval_recall_proxy": len(_expected & _retrieved) / len(_expected) if _expected else None})
    mo.vstack([
        mo.md("## Aggregate run metrics"), mo.json_output(summary),
        mo.md("## Good@K and AnyGood@K from saved human ratings"), mo.ui.table(_rating_rows, selection=None),
        mo.md("## Known-good retrieval recall proxy"), mo.ui.table(_recall_rows, selection=None),
        mo.md("## Run comparison"), mo.ui.table(_runs, selection=None),
        mo.md("## Saved human ratings"), mo.ui.table(_evals_df.to_dict("records"), selection=None),
    ])
    return


if __name__ == "__main__":
    app.run()
