import marimo


__generated_with = "0.18.3"
app = marimo.App(width="full", app_title="Matching Pipeline Experiment Harness")


@app.cell
def _():
    import json
    import os
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.harness.pipeline import Pipeline, PipelineConfig, sync_authoritative_costs
    from src.harness.storage import ExperimentStore

    return ExperimentStore, Path, Pipeline, PipelineConfig, json, load_dotenv, mo, os, sync_authoritative_costs


@app.cell
def _(mo):
    mo.md("""
    # AI matching pipeline laboratory

    A controlled, inspectable end-to-end experiment: need interpretation →
    deterministic retrieval → prescoring → mutual-match judge → introduction.
    Every run, stream event, API usage record, retrieval score, and human rating
    is stored in DuckDB.

    Per-call dollars below are estimates from the token usage returned by the API.
    Use the **Sync authoritative costs** control to persist the organization Costs
    API's invoice-reconciling totals (an admin key is required).
    """)
    return


@app.cell
def _(ExperimentStore, Path, json, load_dotenv):
    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    profiles = json.loads((workspace / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    eval_queries = json.loads((workspace / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    return eval_queries, profiles, store, workspace


@app.cell
def _(mo, profiles):
    profile_options = {f"{profile['name']} — {profile['headline']}": profile["id"] for profile in profiles}
    requester = mo.ui.dropdown(label="Requester", options=profile_options, value=next(iter(profile_options.values())))
    query = mo.ui.text_area(
        label="Natural-language need",
        value="I want someone who has deployed an AT Protocol PDS themselves and can help me understand the setup.",
        full_width=True,
    )
    api_key = mo.ui.text(label="OpenAI project API key (or OPENAI_API_KEY)", kind="password", full_width=True)
    mo.vstack([requester, query, api_key])
    return api_key, query, requester


@app.cell
def _(mo):
    need_model = mo.ui.text(label="Need model", value="gpt-4.1-mini")
    judge_model = mo.ui.text(label="Judge model", value="gpt-4.1-mini")
    intro_model = mo.ui.text(label="Introduction model", value="gpt-4.1-mini")
    reasoning = mo.ui.dropdown(label="Judge reasoning", options=["none", "low", "medium", "high"], value="none")
    retrieval_count = mo.ui.number(label="Initial retrieval count", start=1, stop=50, value=15)
    shortlist = mo.ui.number(label="Judge shortlist", start=1, stop=25, value=8)
    offers_weight = mo.ui.number(label="Offers weight", start=0, stop=1, step=0.05, value=0.45)
    interests_weight = mo.ui.number(label="Interests weight", start=0, stop=1, step=0.05, value=0.20)
    reciprocity_weight = mo.ui.number(label="Reciprocity weight", start=0, stop=1, step=0.05, value=0.20)
    interaction_weight = mo.ui.number(label="Interaction weight", start=0, stop=1, step=0.05, value=0.15)
    mo.md("## Experiment controls")
    mo.hstack([need_model, judge_model, intro_model, reasoning, retrieval_count, shortlist], justify="start")
    mo.hstack([offers_weight, interests_weight, reciprocity_weight, interaction_weight], justify="start")
    return (intro_model, interaction_weight, interests_weight, judge_model, need_model,
            offers_weight, reasoning, reciprocity_weight, retrieval_count, shortlist)


@app.cell
def _(mo):
    mo.md("## Cost-estimate rates (USD per million tokens)")
    input_rate = mo.ui.number(label="Input", start=0, step=0.01, value=0.0)
    cached_rate = mo.ui.number(label="Cached input", start=0, step=0.01, value=0.0)
    output_rate = mo.ui.number(label="Output", start=0, step=0.01, value=0.0)
    run = mo.ui.run_button(label="Run live pipeline", kind="success")
    mo.hstack([input_rate, cached_rate, output_rate, run], justify="start")
    return cached_rate, input_rate, output_rate, run


@app.cell
def _(mo):
    mo.md("## Evaluation and accounting")
    admin_key = mo.ui.text(label="OpenAI admin key (or OPENAI_ADMIN_KEY)", kind="password", full_width=True)
    sync_costs = mo.ui.run_button(label="Sync authoritative costs")
    mo.hstack([admin_key, sync_costs], justify="start")
    return admin_key, sync_costs


@app.cell
def _(admin_key, mo, os, store, sync_authoritative_costs, sync_costs):
    mo.stop(not sync_costs.value)
    admin_secret = admin_key.value.strip() or os.getenv("OPENAI_ADMIN_KEY")
    mo.stop(not admin_secret, mo.callout("Set OPENAI_ADMIN_KEY or enter an admin key to sync organization-wide cost buckets.", kind="warn"))
    try:
        count = sync_authoritative_costs(store, admin_secret, 0)
        cost_sync_view = mo.callout(f"Stored {count} authoritative daily cost bucket(s).", kind="success")
    except Exception as exc:
        cost_sync_view = mo.callout(f"Cost sync failed and was not hidden: `{type(exc).__name__}: {exc}`", kind="danger")
    cost_sync_view
    return


@app.cell
def _(api_key, cached_rate, input_rate, interaction_weight, interests_weight, intro_model,
          judge_model, need_model, offers_weight, os, Pipeline, PipelineConfig, profiles,
          query, reasoning, reciprocity_weight, requester, retrieval_count, run, shortlist, store, mo):
    import time

    mo.stop(not run.value)
    selected_query = query.value.strip()
    mo.stop(not selected_query, mo.callout("Enter a matching need first.", kind="warn"))
    project_secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(not project_secret, mo.callout("Live mode requires OPENAI_API_KEY. The synthetic dataset remains available for inspection without it.", kind="warn"))
    config = PipelineConfig(
        need_model=need_model.value.strip(), judge_model=judge_model.value.strip(),
        introduction_model=intro_model.value.strip(), reasoning_effort=reasoning.value,
        retrieval_count=int(retrieval_count.value), judge_shortlist=int(shortlist.value),
        offers_weight=float(offers_weight.value), interests_weight=float(interests_weight.value),
        reciprocity_weight=float(reciprocity_weight.value), interaction_weight=float(interaction_weight.value),
        input_per_million=float(input_rate.value), cached_input_per_million=float(cached_rate.value),
        output_per_million=float(output_rate.value),
    )
    streamed = {"need": [], "judge": []}
    with mo.status.spinner(title="Running pipeline and recording stream events…"):
        result = Pipeline(store, profiles, project_secret).run(
            requester.value, selected_query, config,
            on_delta=lambda stage, delta: streamed[stage].append(delta),
        )
    result["streamed_text"] = {stage: "".join(chunks) for stage, chunks in streamed.items()}
    result["finished_at"] = time.time()
    return result,


@app.cell
def _(mo, result):
    mo.stop(not result)
    if result["status"] != "completed":
        mo.callout(f"Run `{result['run_id']}` failed and its partial trace is retained: `{result['error']}`", kind="danger")
    else:
        mo.callout(f"Run `{result['run_id']}` completed in {result['total_latency_ms']:.0f} ms; estimated per-call cost: ${result['estimated_cost_usd']:.6f}.", kind="success")
    mo.md("## Streamed model text (captured verbatim)")
    mo.accordion({"Need interpreter stream": mo.md(f"```text\n{result['streamed_text']['need']}\n```"), "Judge stream": mo.md(f"```text\n{result['streamed_text']['judge']}\n```")})
    return


@app.cell
def _(mo, result):
    mo.stop(not result or not result["need"])
    mo.md("## 1. Need interpretation")
    mo.json_output(result["need"])
    mo.md("## 2. Retrieval and deterministic prescoring")
    rows = [{"rank": row["rank"], "candidate": row["candidate"]["name"], "offers": round(row["offers_similarity"], 3), "interests": round(row["interests_similarity"], 3), "reciprocal": round(row["reciprocal_similarity"], 3), "interaction": row["interaction_score"], "prescore": round(row["prescore"], 3)} for row in result["retrieval"]]
    mo.ui.table(rows, selection=None)
    return


@app.cell
def _(mo, profiles, result):
    mo.stop(not result or not result["matches"])
    names = {profile["id"]: profile["name"] for profile in profiles}
    match_cards = []
    for rank, match in enumerate(result["matches"], 1):
        intro = match.get("introduction", {})
        match_cards.append(mo.md(f"""### #{rank} {names.get(match['candidate_id'], match['candidate_id'])}
Judge score: `{match.get('score', 'n/a')}`

{match.get('reason', '')}

**Why this person:** {intro.get('why_this_person', '')}

**Why you:** {intro.get('why_you', '')}

**Possible opener:** {intro.get('possible_opener', '')}"""))
    mo.vstack([mo.md("## 3. Judge and introductions"), *match_cards])
    return


@app.cell
def _(mo, result):
    mo.stop(not result or not result["matches"])
    rating = mo.ui.dropdown(label="Human rating", options=["good", "okay", "bad"], value="good")
    candidate = mo.ui.dropdown(label="Candidate", options={match["candidate_id"]: match["candidate_id"] for match in result["matches"]})
    notes = mo.ui.text_area(label="Rating notes", full_width=True)
    save_rating = mo.ui.run_button(label="Save human rating")
    mo.vstack([mo.md("## 4. Human evaluation (the quality signal)"), candidate, rating, notes, save_rating])
    return candidate, notes, rating, save_rating


@app.cell
def _(candidate, mo, notes, rating, result, save_rating, store):
    mo.stop(not save_rating.value)
    store.add_evaluation(result["run_id"], candidate.value, rating.value, notes.value)
    mo.callout("Human rating saved to DuckDB.", kind="success")
    return


@app.cell
def _(mo, store):
    mo.md("## Persistent experiment summary")
    metrics = store.dataframe("""
        select count(*) as runs,
               avg(estimated_cost_usd) as avg_estimated_cost,
               avg(total_latency_ms) as avg_latency_ms,
               count(*) filter (where status = 'failed') as failed_runs
        from runs
    """)
    ratings = store.dataframe("""
        select rating, count(*) as ratings
        from human_evaluations group by rating order by rating
    """)
    mo.hstack([mo.ui.table(metrics, selection=None), mo.ui.table(ratings, selection=None)], justify="start")
    return


if __name__ == "__main__":
    app.run()
