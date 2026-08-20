import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Onboarding Interviewer Laboratory")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.agents.onboarding import OnboardingInterviewer, OnboardingSession

    load_dotenv(Path(__file__).parent / ".env")
    return OnboardingInterviewer, OnboardingSession, mo, os


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
def _(mo):
    get_finished, set_finished = mo.state(False)
    get_tool_events, set_tool_events = mo.state([])
    return get_finished, get_tool_events, set_finished, set_tool_events


@app.cell
def _(OnboardingInterviewer, OnboardingSession, mo, os, set_finished, set_tool_events):
    api_key = os.getenv("OPENAI_API_KEY")
    mo.stop(not api_key, mo.callout("`OPENAI_API_KEY` is missing. Add it to the repository `.env`, then restart this notebook.", kind="warn"))
    interviewer = OnboardingInterviewer(api_key)

    def onboarding_model(messages, config):
        session = OnboardingSession.from_messages(messages)
        events = []
        result = interviewer.next_turn(
            session,
            max_output_tokens=config.max_tokens,
            on_tool_event=events.append,
        )
        set_tool_events(events)
        set_finished(result["finished"])
        return result["message"]

    chat = mo.ui.chat(
        onboarding_model,
        prompts=["Start my onboarding"],
        config={"max_tokens": 300, "temperature": 1},
        max_height=600,
    )
    chat
    return (chat,)


@app.cell
def _(get_finished, get_tool_events, mo):
    events = get_tool_events()
    status = (
        mo.callout("Onboarding is complete.", kind="success")
        if get_finished()
        else mo.callout("Onboarding is still in progress.", kind="info")
    )
    mo.vstack(
        [
            status,
            mo.accordion(
                {
                    f"Agent tools used on the latest turn ({len(events)})": mo.json_output(events)
                }
            ),
        ]
    )
    return


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
