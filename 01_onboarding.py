import marimo


__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Onboarding Interviewer Laboratory")


@app.cell
def _():
    import os
    import uuid
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.agents.onboarding import OnboardingInterviewer, OnboardingSession
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    return ExperimentStore, OnboardingInterviewer, OnboardingSession, mo, os, store, uuid


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
    model = mo.ui.text(label="Model", value="gpt-5.6-terra")
    reasoning = mo.ui.dropdown(label="Reasoning", options=["none", "low", "medium", "high"], value="low")
    prompt_version = mo.ui.dropdown(label="Prompt version", options=["onboarding_v1"], value="onboarding_v1")
    max_turns = mo.ui.number(label="Maximum meaningful answers", start=1, stop=20, value=8)
    max_output = mo.ui.number(label="Maximum output tokens", start=64, stop=2000, value=300)
    mo.hstack([model, reasoning, prompt_version, max_turns, max_output], justify="start")
    return max_output, max_turns, model, prompt_version, reasoning


@app.cell
def _(mo):
    get_finished, set_finished = mo.state(False)
    get_tool_events, set_tool_events = mo.state([])
    get_traces, set_traces = mo.state([])
    return get_finished, get_tool_events, get_traces, set_finished, set_tool_events, set_traces


@app.cell
def _(OnboardingInterviewer, OnboardingSession, max_output, max_turns, mo, model, os, prompt_version, reasoning, set_finished, set_tool_events, set_traces, store, uuid):
    api_key = os.getenv("OPENAI_API_KEY")
    mo.stop(not api_key, mo.callout("`OPENAI_API_KEY` is missing. Add it to the repository `.env`, then restart this notebook.", kind="warn"))
    interviewer = OnboardingInterviewer(api_key)
    session_state = {"finished": False, "run_id": None, "traces": []}

    def onboarding_model(messages, config):
        if session_state["finished"]:
            return "Your onboarding is already complete. The transcript is ready for profile compilation."
        session = OnboardingSession.from_messages(messages, finished=session_state["finished"])
        if session.meaningful_answer_count() >= int(max_turns.value):
            session_state["finished"] = True
            set_finished(True)
            return "Thanks — the configured onboarding turn limit has been reached. Your transcript is ready for profile compilation."
        if session_state["run_id"] is None:
            session_state["run_id"] = store.new_run(
                {"id": f"onboarding-{uuid.uuid4()}"},
                "onboarding session",
                {"model": model.value, "reasoning_effort": reasoning.value, "prompt_version": prompt_version.value, "max_turns": int(max_turns.value), "max_output_tokens": int(max_output.value)},
            )
        events = []
        result = interviewer.next_turn(
            session,
            model=model.value,
            reasoning_effort=reasoning.value,
            max_output_tokens=int(max_output.value),
            on_tool_event=events.append,
        )
        for trace in result["traces"]:
            store.add_call(session_state["run_id"], trace)
            session_state["traces"].append(trace.to_dict())
        set_tool_events(events)
        set_traces(list(session_state["traces"]))
        session_state["finished"] = result["finished"]
        set_finished(session_state["finished"])
        if session_state["finished"]:
            total_cost = sum(trace["estimated_cost_usd"] for trace in session_state["traces"])
            store.finish_run(session_state["run_id"], need=None, status="completed", error=None, latency_ms=sum(trace["latency_ms"] for trace in session_state["traces"]), estimated_cost=total_cost)
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
def _(get_finished, get_tool_events, get_traces, mo):
    events = get_tool_events()
    traces = get_traces()
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
                    f"Agent tools used on the latest turn ({len(events)})": mo.json_output(events),
                    f"Raw model-call traces ({len(traces)})": mo.json_output(traces),
                }
            ),
            mo.ui.table(
                [
                    {
                        "call": index,
                        "model": trace["model"],
                        "input": trace["input_tokens"],
                        "output": trace["output_tokens"],
                        "reasoning": trace["reasoning_tokens"],
                        "latency_ms": round(trace["latency_ms"], 1),
                        "cost_usd": round(trace["estimated_cost_usd"], 6),
                    }
                    for index, trace in enumerate(traces, 1)
                ],
                selection=None,
            ),
            mo.md(f"**Cumulative estimated cost:** `${sum(trace['estimated_cost_usd'] for trace in traces):.6f}`"),
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
