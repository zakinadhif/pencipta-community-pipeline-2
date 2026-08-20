import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Retrieval Laboratory")


@app.cell
def _():
    import json
    import os
    from pathlib import Path
    from types import SimpleNamespace

    import marimo as mo
    from dotenv import load_dotenv
    from openai import OpenAI

    from src.pipeline import PipelineConfig
    from src.retrieval.embeddings import OpenAIEmbedder
    from src.retrieval.index import EmbeddingIndex, rebuild_index
    from src.retrieval.search import search_people
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    profiles = json.loads((workspace / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    def json_view(value):
        return mo.md(f"```json\n{json.dumps(value, indent=2, default=str, ensure_ascii=False)}\n```")

    return EmbeddingIndex, ExperimentStore, OpenAI, OpenAIEmbedder, PipelineConfig, SimpleNamespace, json, json_view, mo, os, profiles, rebuild_index, search_people, store


@app.cell
def _(mo, profiles):
    mo.md("""
    # 03 — Retrieval

    Inspect candidate pools, directional similarity, and deterministic prescores here.
    Run directional retrieval independently from the judge. Leave the API key empty for the lexical baseline, or use the configured key for `text-embedding-3-large`.
    """)
    return


@app.cell
def _(json, mo, profiles):
    options = {f"{profile['name']} — {profile['headline']}": profile["id"] for profile in profiles}
    requester = mo.ui.dropdown(label="Requester", options=options, value=next(iter(options)))
    query = mo.ui.text_area(label="Original query", value="I need a senior developer who enjoys teaching beginners.", full_width=True)
    need_json = mo.ui.text_area(label="Need Interpreter output", rows=14, full_width=True, value=json.dumps({"goal": "learn software development from an experienced mentor", "interactionType": ["being_mentored"], "target": {"knowledge": ["software development"], "experience": ["senior developer"], "interests": ["teaching beginners"]}, "hardFilters": {"location": None, "interactionTypes": []}, "softPreferences": [], "retrievalQueries": {"offers": "senior software developer who teaches beginners", "interests": "software education and mentoring beginners", "needs": "beginner offering enthusiasm and consistent practice"}, "avoidMatchingOn": ["other beginners seeking mentors"]}, indent=2))
    api_key = mo.ui.text(label="OpenAI API key (optional; otherwise lexical)", kind="password", full_width=True)
    count = mo.ui.number(label="Candidate count", start=1, stop=100, value=30)
    per_dimension = mo.ui.number(label="Top-N per dimension", start=5, stop=200, value=50)
    offers = mo.ui.number(label="Offers weight", start=0, stop=1, step=0.05, value=0.45)
    interests = mo.ui.number(label="Interests weight", start=0, stop=1, step=0.05, value=0.20)
    reciprocity = mo.ui.number(label="Reciprocity weight", start=0, stop=1, step=0.05, value=0.20)
    interaction = mo.ui.number(label="Interaction weight", start=0, stop=1, step=0.05, value=0.15)
    rebuild = mo.ui.run_button(label="Rebuild index")
    run = mo.ui.run_button(label="Run retrieval", kind="success")
    mo.vstack([requester, query, need_json, api_key, mo.hstack([count, per_dimension, offers, interests, reciprocity, interaction]), mo.hstack([rebuild, run])])
    return api_key, count, interaction, interests, need_json, offers, per_dimension, query, rebuild, reciprocity, requester, run


@app.cell
def _(OpenAI, OpenAIEmbedder, PipelineConfig, api_key, count, interaction, interests, json, mo, need_json, offers, os, per_dimension, profiles, query, rebuild, reciprocity, requester, run, search_people, store):
    mo.stop(not run.value)
    need = json.loads(need_json.value)
    requester_profile = next(profile for profile in profiles if profile["id"] == requester.value)
    secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    if rebuild.value:
        mo.stop(not secret, mo.callout("An API key is required to rebuild the embedding index.", kind="warn"))
        index = rebuild_index(store, profiles, OpenAI(api_key=secret))
        mode = "indexed (rebuilt)"
    else:
        index = EmbeddingIndex.load(store) if secret else None
        has_vectors = bool(index and index.vectors.get("offers"))
        if has_vectors:
            mode = "indexed"
        else:
            index = None
            mode = "lexical" if not secret else "all-candidate (dev)"
    embedder = OpenAIEmbedder(OpenAI(api_key=secret)) if secret else None
    config = PipelineConfig(retrieval_count=int(count.value), offers_weight=float(offers.value), interests_weight=float(interests.value), reciprocity_weight=float(reciprocity.value), interaction_weight=float(interaction.value))
    rows = search_people(profiles=profiles, requester=requester_profile, queries=need["retrievalQueries"], filters=need["hardFilters"], interaction_types=need["interactionType"], limit=int(count.value), index=index, embedder=embedder, per_dimension_count=int(per_dimension.value), weights=config)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    run_id = store.new_run(requester_profile, query.value, {"experiment": "retrieval", "weights": {"offers": offers.value, "interests": interests.value, "reciprocity": reciprocity.value, "interaction": interaction.value}, "count": count.value, "mode": mode})
    if embedder and embedder.last_trace:
        store.add_call(run_id, embedder.last_trace)
    store.add_retrieval(run_id, rows)
    cost = embedder.last_trace.estimated_cost_usd if embedder and embedder.last_trace else 0.0
    latency = embedder.last_trace.latency_ms if embedder and embedder.last_trace else 0.0
    store.finish_run(run_id, need=need, status="completed", error=None, latency_ms=latency, estimated_cost=cost)
    retrieval_result = {"run_id": run_id, "need": need, "rows": rows, "mode": mode, "embedding_trace": embedder.last_trace.to_dict() if embedder and embedder.last_trace else None}
    return (retrieval_result,)


@app.cell
def _(json_view, mo, retrieval_result):
    selected_need = retrieval_result["need"]
    mo.vstack([
        mo.md(f"## Interpreted need and directional queries — **mode: `{retrieval_result['mode']}`**"),
        json_view(selected_need),
        mo.ui.table([{"rank": row["rank"], "person": row["candidate"]["name"], "offers": round(row["offers_similarity"], 3), "interests": round(row["interests_similarity"], 3), "reciprocal": round(row["reciprocal_similarity"], 3), "interaction": row["interaction_score"], "prescore": round(row["prescore"], 3)} for row in retrieval_result["rows"]], selection=None),
        mo.accordion({f"#{row['rank']} {row['candidate']['name']}": json_view({key: row["candidate"].get(key) for key in ("headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo")}) for row in retrieval_result["rows"]}),
        mo.accordion({"Embedding trace": json_view(retrieval_result["embedding_trace"] or {"mode": "lexical baseline"})}),
    ])
    return


if __name__ == "__main__":
    app.run()
