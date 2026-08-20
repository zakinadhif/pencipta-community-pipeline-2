import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Profile Compiler Laboratory")


@app.cell
def _():
    import json
    import os
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.agents.profile_compiler import ProfileCompiler
    from src.schemas.profile import ProfileDraft
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    return ExperimentStore, ProfileCompiler, ProfileDraft, json, mo, os, store


@app.cell
def _(mo):
    mo.md("""
    # 02 — Profile compiler

    The compiler produces a validated **draft**, never a database write. Review or edit this result before any later acceptance and embedding step.
    """)
    return


@app.cell
def _(mo):
    model = mo.ui.text(label="Model", value="gpt-5.6-luna")
    reasoning = mo.ui.dropdown(label="Reasoning", options=["none", "low", "medium", "high"], value="low")
    prompt_version = mo.ui.dropdown(label="Prompt version", options=["profile_compiler_v1"], value="profile_compiler_v1")
    max_output = mo.ui.number(label="Maximum output tokens", start=128, stop=4000, value=1200)
    api_key = mo.ui.text(label="OpenAI API key (or OPENAI_API_KEY)", kind="password", full_width=True)
    transcript = mo.ui.text_area(
        label="Completed onboarding transcript JSON", full_width=True, rows=16,
        value='[{"role":"user","content":"I am learning web development. I have made small personal sites with HTML and CSS, enjoy startups, and can help other beginners practice basic frontend work. I want a patient senior developer mentor and am open to mentoring or collaborating."}]',
    )
    existing_profile = mo.ui.text_area(label="Existing profile JSON (optional)", full_width=True, rows=8, value="")
    compile_profile = mo.ui.run_button(label="Compile profile draft", kind="success")
    mo.vstack([mo.hstack([model, reasoning, prompt_version, max_output]), api_key, transcript, existing_profile, compile_profile])
    return api_key, compile_profile, existing_profile, max_output, model, prompt_version, reasoning, transcript


@app.cell
def _(ProfileCompiler, api_key, compile_profile, existing_profile, json, max_output, mo, model, os, prompt_version, reasoning, store, transcript):
    mo.stop(not compile_profile.value)
    secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(not secret, mo.callout("Set OPENAI_API_KEY or enter a key to compile a profile.", kind="warn"))
    try:
        source = json.loads(transcript.value)
        prior = json.loads(existing_profile.value) if existing_profile.value.strip() else None
        compiler_input = source + ([{"role": "user", "content": f"Existing profile to update:\n{json.dumps(prior)}"}] if prior else [])
        draft, raw_response, trace = ProfileCompiler(secret).compile_with_trace(compiler_input, model=model.value.strip(), reasoning_effort=reasoning.value, max_output_tokens=int(max_output.value))
        run_id = store.new_run({"id": "profile-compiler-lab"}, "profile compilation", {"model": model.value, "reasoning_effort": reasoning.value, "prompt_version": prompt_version.value})
        store.add_call(run_id, trace)
        store.finish_run(run_id, need=None, status="completed", error=None, latency_ms=trace.latency_ms, estimated_cost=trace.estimated_cost_usd)
        compiled = {"source": source, "existing_profile": prior, "draft": draft.to_dict(), "raw_response": raw_response, "trace": trace.to_dict(), "run_id": run_id}
    except Exception as exc:
        compiled = {"error": f"{type(exc).__name__}: {exc}"}
    return (compiled,)


@app.cell
def _(compiled, json, mo):
    mo.stop("error" in compiled, mo.callout(f"Profile compilation failed: `{compiled['error']}`", kind="danger"))
    draft_editor = mo.ui.code_editor(json.dumps(compiled["draft"], indent=2), language="json")
    accept = mo.ui.run_button(label="Validate and accept edited draft", kind="success")
    mo.vstack([
        mo.md("## Source conversation"),
        mo.code_editor(json.dumps(compiled["source"], indent=2), language="json", disabled=True),
        mo.md("## Parsed profile — directly editable before acceptance"),
        draft_editor,
        accept,
        mo.accordion({
            "Exact API request": mo.json_output(compiled["trace"]["request"]),
            "Raw model response": mo.json_output(compiled["raw_response"]),
            "Standard trace": mo.json_output(compiled["trace"]),
        }),
        mo.md(f"Tokens: input `{compiled['trace']['input_tokens']}`, output `{compiled['trace']['output_tokens']}`, reasoning `{compiled['trace']['reasoning_tokens']}` · latency `{compiled['trace']['latency_ms']:.1f} ms` · estimated cost `${compiled['trace']['estimated_cost_usd']:.6f}`"),
    ])
    return accept, draft_editor


@app.cell
def _(ProfileDraft, accept, draft_editor, json, mo):
    mo.stop(not accept.value)
    try:
        accepted = ProfileDraft.from_dict(json.loads(draft_editor.value)).to_dict()
        acceptance_view = mo.vstack([mo.callout("Edited profile is valid and accepted for the next explicit persistence/embedding step.", kind="success"), mo.json_output(accepted)])
    except Exception as exc:
        acceptance_view = mo.callout(f"Edited profile is invalid: `{type(exc).__name__}: {exc}`", kind="danger")
    acceptance_view
    return


if __name__ == "__main__":
    app.run()
