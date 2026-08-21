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
    return (
        Pipeline,
        PipelineConfig,
        eval_queries,
        mo,
        os,
        per_requester_tokens,
        per_run_tokens,
        profiles,
        store,
        time,
    )


@app.cell
def _(mo):
    mo.md("""
    # 07 — Live pipeline test

    Jalankan pipeline end-to-end terhadap query yang kamu ketik sendiri, atau
    terhadap semua eval query. Hasil match, retrieval, dan konsumsi token
    per-run + per-requester dibaca dari DuckDB.

    **Alur:** query (input kamu) → Need Interpreter → retrieval (lexical jika
    tidak ada embeddings) → prescore → match judge → introduction → semua
    disimpan ke `data/runs.duckdb`.

    - Tanpa embeddings → retrieval memakai lexical fallback otomatis.
    - Streaming SDK diblokir → fallback non-stream (HTTP langsung).
    - Output model yang tidak mengikuti schema → dinormalisasi adaptif.
    """)
    return


@app.cell
def _(mo, profiles):
    name_by_id = {p["id"]: p for p in profiles}
    # Tampilkan hanya profil kanonik sebagai requester (biar dropdown ringan & cepat);
    # query tetap dijalankan atas seluruh 2.000 profil kandidat.
    requester_ids = [p["id"] for p in profiles if not p["id"].startswith("synthetic-")]
    profile_options = {f"{name_by_id[i]['name']} — {name_by_id[i]['headline']}": i for i in requester_ids}
    default_label = next(label for label, pid in profile_options.items() if pid == "adi")
    requester = mo.ui.dropdown(label="Requester", options=profile_options, value=default_label)
    custom_query = mo.ui.text_area(
        label="Query kustom (ketik kebutuhan orang yang kamu cari)",
        value="I need a senior developer who genuinely enjoys teaching beginners.",
        full_width=True,
    )
    judge_reasoning = mo.ui.dropdown(label="Judge reasoning", options=["none", "low", "medium"], value="low")
    retrieval_count = mo.ui.number(label="Retrieval count", start=5, stop=50, value=15)
    judge_shortlist = mo.ui.number(label="Judge shortlist", start=3, stop=20, value=6)
    max_output = mo.ui.number(label="Max output tokens", start=200, stop=2000, value=800)
    return (
        custom_query,
        judge_reasoning,
        judge_shortlist,
        max_output,
        requester,
        retrieval_count,
    )


@app.cell
def _(mo):
    run_single = mo.ui.run_button(label="▶ Run query kustom ini")
    run_all = mo.ui.run_button(label="Run all eval queries")
    mo.hstack([run_single, run_all])
    return run_all, run_single


@app.cell
def _(
    Pipeline,
    PipelineConfig,
    custom_query,
    eval_queries,
    judge_reasoning,
    judge_shortlist,
    max_output,
    mo,
    os,
    profiles,
    requester,
    retrieval_count,
    run_all,
    run_single,
    store,
    time,
):
    batch_trigger = run_all.value
    single_trigger = (run_single.value or os.getenv("LIVE_TEST") == "1")
    mo.stop(not (batch_trigger or single_trigger))
    config = PipelineConfig(judge_reasoning_effort=judge_reasoning.value, retrieval_count=int(retrieval_count.value), judge_shortlist=int(judge_shortlist.value), max_output_tokens=int(max_output.value))
    requester_label = requester.value
    requester_id = next(profile["id"] for profile in profiles if profile["id"] == requester_label or f"{profile['name']} — {profile['headline']}" == requester_label)
    pipeline = Pipeline(store, profiles, os.getenv("OPENAI_API_KEY"))

    queries = eval_queries if batch_trigger else [{"query": custom_query.value.strip(), "known_good_candidate_ids": []}]
    if not queries[0]["query"]:
        queries = [{"query": "I need someone who can help me get started.", "known_good_candidate_ids": []}]

    results = []
    for item in queries:
        query = item["query"]
        start = time.perf_counter()
        try:
            result = pipeline.run(requester_id, query, config)
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
                "new_run_id": result.get("run_id"),
            })
        except Exception as exc:
            results.append({"query": query, "known_good": item.get("known_good_candidate_ids", []), "status": "failed", "error": f"{type(exc).__name__}: {exc}", "matches": 0, "retrieval": 0, "top_candidates": [], "latency_ms": 0, "cost_usd": 0, "new_run_id": None})
    test_output = {"run_time": time.strftime("%Y-%m-%d %H:%M:%S"), "config": config.__dict__, "results": results}
    return (test_output,)


@app.cell
def _(mo, test_output):
    mo.md("## Hasil")
    rows = [{"query": r["query"][:60], "status": r["status"], "error": (r.get("error") or "")[:40], "interactionType": r.get("interactionType"), "retrieval": r.get("retrieval"), "matches": r.get("matches"), "top": ",".join(r.get("top_candidates", [])), "latency_ms": r.get("latency_ms"), "cost_usd": r.get("cost_usd"), "run_id": (r.get("new_run_id") or "")[:8]} for r in test_output["results"]]
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
    _runs = per_run_tokens(store, min_tokens=1)
    mo.hstack([
        mo.ui.table(_runs, selection=None),
        mo.ui.table(per_requester_tokens(store), selection=None),
    ], justify="start")
    return


if __name__ == "__main__":
    app.run()
