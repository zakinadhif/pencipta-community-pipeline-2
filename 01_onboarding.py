import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Onboarding Interviewer Laboratory")


@app.cell
def _():
    import json
    import os

    import marimo as mo
    from dotenv import load_dotenv

    from src.harness.onboarding import OnboardingInterviewer, OnboardingSession, Turn

    load_dotenv()
    return OnboardingInterviewer, OnboardingSession, Turn, json, mo, os


@app.cell
def _(mo):
    mo.md("""
    # 01 — Onboarding interviewer

    This laboratory records a short conversation before any profile is generated.
    The interviewer asks one question at a time; it never writes a profile or commits user data.
    Keep the transcript editable so every model turn is inspectable.
    """)
    return


@app.cell
def _(mo):
    model = mo.ui.text(label="Model", value="gpt-5.6-terra")
    reasoning = mo.ui.dropdown(label="Reasoning", options=["none", "low", "medium", "high"], value="low")
    api_key = mo.ui.text(label="OpenAI API key (or OPENAI_API_KEY)", kind="password", full_width=True)
    transcript = mo.ui.text_area(
        label="Transcript JSON", full_width=True, rows=14,
        value='[{"role":"user","content":"I am a student learning web development and I enjoy helping friends with basic HTML and CSS."}]',
    )
    ask = mo.ui.run_button(label="Ask next onboarding question", kind="success")
    mo.vstack([mo.hstack([model, reasoning]), api_key, transcript, ask])
    return api_key, ask, model, reasoning, transcript


@app.cell
def _(OnboardingInterviewer, OnboardingSession, Turn, api_key, ask, json, mo, model, os, reasoning, transcript):
    mo.stop(not ask.value)
    secret = api_key.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(not secret, mo.callout("Set OPENAI_API_KEY or enter a key to ask a live onboarding question.", kind="warn"))
    try:
        turns = json.loads(transcript.value)
        if not isinstance(turns, list) or any(turn.get("role") not in {"user", "assistant"} or not isinstance(turn.get("content"), str) for turn in turns):
            raise ValueError("each turn needs a user/assistant role and string content")
        session = OnboardingSession([Turn(turn["role"], turn["content"]) for turn in turns])
        result = OnboardingInterviewer(secret).next_turn(session, model=model.value.strip(), reasoning_effort=reasoning.value)
        updated_transcript = session.transcript()
        view = mo.vstack([
            mo.callout("Append the returned assistant turn to the editable transcript, then add the person's next answer. Marked finished means it is ready for the compiler.", kind="success" if result["finished"] else "info"),
            mo.md(f"## Interviewer\n\n{result['message']}\n\n## Updated transcript"),
            mo.code_editor(json.dumps(updated_transcript, indent=2), language="json", disabled=True),
            mo.accordion({"Raw response": mo.json_output(result["response"])}),
        ])
    except Exception as exc:
        view = mo.callout(f"Onboarding turn failed: `{type(exc).__name__}: {exc}`", kind="danger")
    view
    return


if __name__ == "__main__":
    app.run()
