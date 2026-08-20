import marimo


__generated_with = "0.18.3"
app = marimo.App(width="medium", app_title="Agentic AI Chat Prototype")


@app.cell
def _():
    import json
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import marimo as mo
    from openai import OpenAI

    return OpenAI, ZoneInfo, datetime, json, mo, os


@app.cell
def _(mo):
    mo.md("""
    # Agentic AI chat prototype

    A small tool-using chat loop built for quick experimentation. The model can
    calculate expressions and look up the current time; every tool call is shown
    below the response.
    """)
    return


@app.cell
def _(mo):
    api_key_input = mo.ui.text(
        label="OpenAI API key (optional if OPENAI_API_KEY is set)",
        kind="password",
        placeholder="sk-...",
        full_width=True,
    )
    model_input = mo.ui.text(label="Model", value="gpt-4.1-mini", full_width=True)
    system_prompt_input = mo.ui.text_area(
        label="System prompt",
        value=(
            "You are a helpful AI assistant. Use tools when they make the answer "
            "more accurate. Briefly explain what you did."
        ),
        full_width=True,
    )
    mo.vstack([api_key_input, model_input, system_prompt_input])
    return api_key_input, model_input, system_prompt_input


@app.cell
def _(mo):
    user_message = mo.ui.text_area(
        label="Message",
        placeholder="Try: What time is it in Asia/Jakarta, and what is 17 * 29?",
        full_width=True,
    )
    send = mo.ui.run_button(label="Send to agent", kind="success")
    mo.vstack([user_message, send])
    return send, user_message


@app.cell
def _(ZoneInfo, datetime, json):
    tool_definitions = [
        {
            "type": "function",
            "name": "calculate",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_current_time",
            "description": "Get the current time in an IANA time zone, such as Asia/Jakarta.",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "required": ["timezone"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]

    def call_tool(name, arguments):
        if name == "calculate":
            expression = arguments["expression"]
            # A deliberately narrow calculator: only digits, arithmetic operators,
            # parentheses, decimal points, and whitespace are accepted.
            allowed = set("0123456789+-*/(). %")
            if not expression or any(char not in allowed for char in expression):
                return {"error": "Only basic arithmetic expressions are allowed."}
            try:
                return {"expression": expression, "result": eval(expression, {"__builtins__": {}}, {})}
            except Exception as exc:
                return {"error": f"Could not calculate expression: {exc}"}

        if name == "get_current_time":
            timezone = arguments["timezone"]
            try:
                now = datetime.now(ZoneInfo(timezone))
                return {"timezone": timezone, "time": now.isoformat()}
            except Exception:
                return {"error": f"Unknown time zone: {timezone}"}

        return {"error": f"Unknown tool: {name}"}

    def run_agent(client, model, system_prompt, message):
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=message,
            tools=tool_definitions,
        )
        trace = []

        # Continue until the model has no more tool calls to make.
        while function_calls := [item for item in response.output if item.type == "function_call"]:
            tool_outputs = []
            for call in function_calls:
                arguments = json.loads(call.arguments)
                result = call_tool(call.name, arguments)
                trace.append({"tool": call.name, "arguments": arguments, "result": result})
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    }
                )

            response = client.responses.create(
                model=model,
                instructions=system_prompt,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=tool_definitions,
            )

        return response.output_text, trace

    return run_agent


@app.cell
def _(OpenAI, api_key_input, mo, model_input, os, run_agent, send, system_prompt_input, user_message):
    mo.stop(not send.value)

    message = user_message.value.strip()
    mo.stop(not message, mo.callout("Enter a message first.", kind="warn"))

    api_key = api_key_input.value.strip() or os.getenv("OPENAI_API_KEY")
    mo.stop(
        not api_key,
        mo.callout("Set `OPENAI_API_KEY` or enter a key above before sending a message.", kind="warn"),
    )

    with mo.status.spinner(title="Agent is thinking..."):
        try:
            answer, trace = run_agent(
                OpenAI(api_key=api_key),
                model_input.value.strip(),
                system_prompt_input.value.strip(),
                message,
            )
        except Exception as exc:
            error = str(exc)
        else:
            error = None

    if error:
        result_view = mo.callout(f"Agent request failed: `{error}`", kind="danger")
    else:
        output = [mo.md("## Response"), mo.md(answer)]
        if trace:
            output.extend([mo.md("## Tool trace"), mo.ui.table(trace, selection=None)])
        result_view = mo.vstack(output)
    result_view
    return


if __name__ == "__main__":
    app.run()
