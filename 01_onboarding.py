import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Onboarding Interviewer Laboratory")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.harness.onboarding import ONBOARDING_PROMPT

    load_dotenv(Path(__file__).parent / ".env")
    return ONBOARDING_PROMPT, mo, os


@app.cell
def _(mo):
    mo.md("""
    # 01 — Onboarding interviewer

    This laboratory records a short conversation before any profile is generated.
    The interviewer asks one question at a time; it never writes a profile or commits user data.
    The transcript below is the source record for the profile compiler.
    """)
    return


@app.cell
def _(ONBOARDING_PROMPT, mo, os):
    api_key = os.getenv("OPENAI_API_KEY")
    mo.stop(not api_key, mo.callout("`OPENAI_API_KEY` is missing. Add it to the repository `.env`, then restart this notebook.", kind="warn"))
    chat = mo.ui.chat(
        mo.ai.llm.openai(
            "gpt-5.6-terra",
            api_key=api_key,
            system_message=ONBOARDING_PROMPT,
        ),
        prompts=["Start my onboarding"],
        # This model accepts only its default temperature (1); Marimo's chat
        # component otherwise supplies 0.5 by default.
        config={"max_tokens": 300, "temperature": 1},
        max_height=600,
    )
    chat
    return (chat,)


@app.cell
def _(chat, mo):
    transcript = [
        {"role": message.role, "content": message.content}
        for message in chat.value
        if message.role in {"user", "assistant"} and isinstance(message.content, str)
    ]
    mo.accordion({"Transcript for profile compilation": mo.json_output(transcript)})
    return (transcript,)


if __name__ == "__main__":
    app.run()
