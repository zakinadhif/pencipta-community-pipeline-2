import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Profile Compiler Laboratory")


@app.cell
def _():
    import json
    import os

    import marimo as mo
    from dotenv import load_dotenv

    from src.harness.profile_compiler import ProfileCompiler

    load_dotenv()
    return ProfileCompiler, json, mo, os


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
    api_key = mo.ui.text(label="OpenAI API key (or OPENAI_API_KEY)", kind="password", full_width=True)
    transcript = mo.ui.text_area(
        label="Completed onboarding transcript JSON", full_width=True, rows=16,
        value='[{"role":"user","content":"I am learning web development. I have made small personal sites with HTML and CSS, enjoy startups, and can help other beginners practice basic frontend work. I want a patient senior developer mentor and am open to mentoring or collaborating."}]',
    )
    compile_profile = mo.ui.run_button(label="Compile profile draft", kind="success")
    mo.vstack([mo.hstack([model, reasoning]), api_key, transcript, compile_profile])
    return api_key, compile_profile, model, reasoning, transcript


@app.cell
def _(ProfileCompiler, api_key, compile_profile, json, mo, model, os, reasoning, transcript):
    mo.stop(not compile_profile.value)
    secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(not secret, mo.callout("Set OPENAI_API_KEY or enter a key to compile a profile.", kind="warn"))
    try:
        source = json.loads(transcript.value)
        draft, raw_response = ProfileCompiler(secret).compile(source, model=model.value.strip(), reasoning_effort=reasoning.value)
        view = mo.vstack([
            mo.md("## Source conversation"),
            mo.code_editor(json.dumps(source, indent=2), language="json", disabled=True),
            mo.md("## Parsed, validated draft — edit before acceptance"),
            mo.code_editor(json.dumps(draft.to_dict(), indent=2), language="json"),
            mo.accordion({"Raw model response": mo.json_output(raw_response)}),
        ])
    except Exception as exc:
        view = mo.callout(f"Profile compilation failed: `{type(exc).__name__}: {exc}`", kind="danger")
    view
    return


if __name__ == "__main__":
    app.run()
