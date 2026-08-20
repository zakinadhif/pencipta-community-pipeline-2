import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Live Pipeline Test")


@app.cell
def _():
    import json
    import os
    import time
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.evaluation.reporting import per_requester_tokens, per_run_tokens
    from src.pipeline import Pipeline, PipelineConfig
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    profiles = json.loads((workspace / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    eval_queries = json.loads((workspace / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    return eval_queries, json, mo, os, profiles, store, time, per_requester_tokens, per_run_tokens, Pipeline, PipelineConfig, Path


@app.cell
def _(mo):
    mo.md("""
    # 07 — Live pipeline test

    Menjalankan pipeline end-to-end terhadap setiap evaluation query pada
    provider yang dikonfigurasi di `.env`, lalu menampilkan hasil match,
    retrieval, dan konsumsi token per-run + per-requester dari DuckDB.

    - Tanpa embeddings (provider tanpa endpoint embeddings) → retrieval memakai
      lexical fallback secara otomatis.
    - Streaming SDK diblokir → fallback non-stream (HTTP langsung).
    - Output model yang tidak mengikuti schema ketat → dinormalisasi adaptif.
    """)
    return


@app.cell
def _(mo, PipelineConfig):
    judge_reasoning = mo.ui.dropdown(label="Judge reasoning", options=["none", "low", "medium"], value="low")
    retrieval_count = mo.ui.number(label="Retrieval count", start=5, stop=50, value=15)
    judge_shortlist = mo.ui.number(label="Judge shortlist", start=3, stop=20, value=6)
    max_output = mo.ui.number(label="Max output tokens", start=200, stop=2000, value=800)
    run_all = mo.ui.run_button(label="Run all eval queries", kind="success")
    mo.vstack([
        mo.hstack([judge_reasoning, retrieval_count, judge_shortlist, max_output], justify="start"),
        run_all,
    ])
    return judge_reasoning, max_output, retrieval_count, judge_shortlist, run_all


@app.cell
def _(Pipeline, PipelineConfig, eval_queries, json, mo, os, profiles, retrieval_count, judge_reasoning, judge_shortlist, max_output, run_all, store):
    live_trigger = run_all.value or os.getenv("LIVE_TEST") == "1"
    mo.stop(not live_trigger)
    config = PipelineConfig(judge_reasoning_effort=judge_reasoning.value, retrieval_count=int(retrieval_count.value), judge_shortlist=int(judge_shortlist.value), max_output_tokens=int(max_output.value))
    requester_id = "adi"
    results = []
    for item in eval_queries:
        query = item["query"]
        start = time.perf_counter()
        try:
            result = Pipeline(store, profiles, os.getenv("OPENAI_API_KEY")).run(requester_id, query, config)
            results.append({
                "query": query,
                "known_good": item.get("known_good_candidate_ids", []),
                "status": result["status"],
                "error": result["error"],
                "need_goal": (result.get("need") or {}).get("goal"),
                "interactionType": (result.get("need") or {}).get("interactionType"),
                "retrieval": len(result.get("retrieval", [])),
                "matches": len(result.get("matches", [])),
                "top_candidates": [m["candidate_id"] for m in result.get("matches", [])[:3]],
                "latency_ms": round(result.get("total_latency_ms", 0), 0),
                "cost_usd": round(result.get("estimated_cost_usd", 0), 6),
            })
        except Exception as exc:
            results.append({"query": query, "known_good": item.get("known_good_candidate_ids", []), "status": "failed", "error": f"{type(exc).__name__}: {exc}", "matches": 0, "retrieval": 0, "top_candidates": [], "latency_ms": 0, "cost_usd": 0})
    test_output = {"run_time": time.strftime("%Y-%m-%d %H:%M:%S"), "config": config.__dict__, "results": results}
    return (test_output,)


@app.cell
def _(mo, test_output):
    mo.md("## Hasil per eval query")
    rows = [{"query": r["query"][:60], "status": r["status"], "error": (r.get("error") or "")[:40], "interactionType": r.get("interactionType"), "retrieval": r.get("retrieval"), "matches": r.get("matches"), "top": ",".join(r.get("top_candidates", [])), "latency_ms": r.get("latency_ms"), "cost_usd": r.get("cost_usd")} for r in test_output["results"]]
    mo.ui.table(rows, selection=None)
    return


@app.cell
def _(mo, test_output):
    mo.md("## Detail lengkap")
    mo.vstack([mo.md(f"Run: `{test_output['run_time']}` · config: `{test_output['config']}`")])
    for r in test_output["results"]:
        mo.md(f"**{r['query'][:70]}** — `{r['status']}`")
        if r["status"] == "completed":
            mo.md(f"- goal: {r.get('need_goal')}\n- interactionType: {r.get('interactionType')}\n- retrieval: {r.get('retrieval')} · matches: {r.get('matches')} · top: {r.get('top_candidates')} · latency: {r.get('latency_ms')} ms · cost: ${r.get('cost_usd')}")
        else:
            mo.md(f"- error: `{r.get('error')}`")
    return


@app.cell
def _(mo, per_requester_tokens, per_run_tokens, store):
    mo.md("## Konsumsi token AI (dari DuckDB)")
    mo.hstack([
        mo.ui.table(per_run_tokens(store), selection=None),
        mo.ui.table(per_requester_tokens(store), selection=None),
    ], justify="start")
    return


if __name__ == "__main__":
    app.run()
