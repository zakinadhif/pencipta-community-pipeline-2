import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Matching Laboratory")


@app.cell
def _():
    import json
    import os
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.pipeline import Pipeline, PipelineConfig
    from src.retrieval.prescore import weighted_prescore
    from src.retrieval.search import search_people
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    profiles = json.loads((workspace / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    def json_view(value):
        return mo.md(f"```json\n{json.dumps(value, indent=2, default=str, ensure_ascii=False)}\n```")

    return ExperimentStore, Pipeline, PipelineConfig, json, json_view, mo, os, profiles, search_people, store, weighted_prescore


@app.cell
def _(mo):
    mo.md("""
    # 04 — Mutual matching

    Isolate the expensive mutual-match judge, inspect its exact context and raw stream, and compare its ranking with deterministic prescores.
    """)
    return


@app.cell
def _(json, mo, profiles):
    options = {f"{profile['name']} — {profile['headline']}": profile["id"] for profile in profiles}
    requester = mo.ui.dropdown(label="Requester", options=options, value=next(iter(options)))
    query = mo.ui.text_area(label="Request", value="I need someone experienced in campus distribution who can advise me.", full_width=True)
    need = mo.ui.text_area(label="Interpreted need JSON", rows=12, full_width=True, value=json.dumps({"goal": "learn campus distribution", "interactionType": ["advice"], "target": {"knowledge": ["campus distribution"], "experience": ["launching a student product"], "interests": ["student entrepreneurship"]}, "hardFilters": {"location": None, "interactionTypes": []}, "softPreferences": [], "retrievalQueries": {"offers": "campus distribution and student product launch", "interests": "student entrepreneurship", "needs": "product feedback"}, "avoidMatchingOn": []}, indent=2))
    model = mo.ui.text(label="Judge model", value="gpt-5.6-terra")
    reasoning = mo.ui.dropdown(label="Reasoning", options=["none", "low", "medium", "high"], value="medium")
    prompt_version = mo.ui.dropdown(label="Prompt version", options=["match_judge_v1"], value="match_judge_v1")
    count = mo.ui.number(label="Candidate count", start=1, stop=25, value=8)
    include_requester = mo.ui.switch(label="Include requester profile", value=True)
    include_prescore = mo.ui.switch(label="Include prescore", value=True)
    max_output = mo.ui.number(label="Maximum output tokens", start=128, stop=4000, value=1600)
    api_key = mo.ui.text(label="OpenAI API key (or OPENAI_API_KEY)", kind="password", full_width=True)
    run = mo.ui.run_button(label="Run isolated judge", kind="success")
    mo.vstack([requester, query, need, mo.hstack([model, reasoning, prompt_version, count, include_requester, include_prescore, max_output]), api_key, run])
    return api_key, count, include_prescore, include_requester, max_output, model, need, prompt_version, query, reasoning, requester, run


@app.cell
def _(Pipeline, PipelineConfig, api_key, count, include_prescore, include_requester, json, max_output, mo, model, need, os, profiles, query, reasoning, requester, run, search_people, store, weighted_prescore):
    mo.stop(not run.value)
    secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(not secret, mo.callout("Set OPENAI_API_KEY to run the isolated judge.", kind="warn"))
    interpreted = json.loads(need.value)
    requester_profile = next(profile for profile in profiles if profile["id"] == requester.value)
    config = PipelineConfig(judge_model=model.value, judge_reasoning_effort=reasoning.value, judge_shortlist=int(count.value), max_output_tokens=int(max_output.value))
    candidates = search_people(profiles=profiles, requester=requester_profile, queries=interpreted["retrievalQueries"], filters=interpreted["hardFilters"], interaction_types=interpreted["interactionType"], limit=len(profiles))
    for row in candidates:
        row["interaction_score"] = float(bool(set(interpreted["interactionType"]) & set(row["candidate"].get("openTo", []))))
        row["prescore"] = weighted_prescore(row["offers_similarity"], row["interests_similarity"], row["reciprocal_similarity"], row["interaction_score"], config)
    candidates.sort(key=lambda row: row["prescore"], reverse=True)
    streamed = []
    result = Pipeline(store, profiles, secret).run_judge_experiment(requester.value, query.value, interpreted, candidates, config, include_requester=include_requester.value, include_prescore=include_prescore.value, on_delta=streamed.append)
    result["streamed_text"] = "".join(streamed)
    result["candidate_rows"] = candidates[:int(count.value)]
    return (result,)


@app.cell
def _(json_view, mo, result):
    traces = []
    mo.stop(result["status"] != "completed", mo.callout(f"Judge failed: `{result['error']}`", kind="danger"))
    prescores = {row["candidate"]["id"]: row["prescore"] for row in result["candidate_rows"]}
    mo.vstack([
        mo.md("## Exact judge input"), json_view(result["input"]),
        mo.md("## Raw stream"), mo.md(f"```json\n{result['streamed_text']}\n```"),
        mo.md("## Structured matches"),
        mo.ui.table([{"rank": rank, "candidate": match["userId"], "judge_score": match["score"], "prescore": round(prescores.get(match["userId"], 0), 3), "reason": match["reason"]} for rank, match in enumerate(result["matches"], 1)], selection=None),
        mo.md(f"Latency `{result['latency_ms']:.1f} ms` · estimated cost `${result['estimated_cost_usd']:.6f}`"),
    ])
    return


@app.cell
def _(mo, result):
    mo.stop(not result["matches"])
    candidate = mo.ui.dropdown(label="Candidate", options=[match["userId"] for match in result["matches"]])
    rating = mo.ui.dropdown(label="Human rating", options=["good", "okay", "bad"], value="good")
    notes = mo.ui.text_area(label="Notes", full_width=True)
    save = mo.ui.run_button(label="Save rating")
    mo.vstack([mo.md("## Human evaluation"), candidate, rating, notes, save])
    return candidate, notes, rating, save


@app.cell
def _(candidate, mo, notes, rating, result, save, store):
    mo.stop(not save.value)
    store.add_evaluation(result["run_id"], candidate.value, rating.value, notes.value)
    mo.callout("Rating saved to DuckDB.", kind="success")
    return


if __name__ == "__main__":
    app.run()
