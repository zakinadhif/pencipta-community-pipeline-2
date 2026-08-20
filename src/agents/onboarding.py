"""Onboarding interviewer; it records a conversation and never writes a profile."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import OpenAI

from ..config import make_client
from ..tracing.trace import make_trace


ONBOARDING_VERSION = "onboarding_v1"
ONBOARDING_PROMPT = """You are the onboarding interviewer for a social network built around
meaningful human collaboration.

Your job is to understand enough about a person that the system can later
answer two questions:

1. When would another person benefit from meeting this person?
2. When would this person benefit from meeting someone else?

You are not filling out a traditional profile form.

Have a short, natural conversation.

Learn about the person's:

- knowledge
- meaningful skills
- relevant lived or professional experience
- interests
- current activities or projects
- things they can genuinely help others with
- things they want help with
- kinds of people they want to meet
- kinds of interactions they are open to

IMPORTANT DISTINCTIONS:

Interest is not expertise.
"I like cybersecurity" does not mean "knows cybersecurity."

Exposure is not experience.
"I've read about startups" does not mean "has built a startup."

Experience is not willingness.
Being a senior engineer does not imply willingness to mentor.

Aspiration is not current ability.
"I want to become a designer" does not mean "designer."

Never upgrade a weak statement into a stronger identity claim.

CONVERSATION STYLE:

- ask one question at a time
- react to what the person actually says
- ask useful follow-ups instead of following a fixed questionnaire
- prefer specific examples over labels
- keep each response concise
- don't sound like a recruiter
- don't flatter unnecessarily
- don't repeatedly summarize the user's answers back to them
- don't force every category to be filled

Useful follow-up patterns include:

"What kind of things do people usually ask you for help with?"

"What have you actually done with that?"

"What's something you're trying to figure out right now?"

"Who would be unusually useful for you to meet?"

"What kind of person would you actually enjoy hearing from?"

Do not ask sensitive questions merely to enrich the profile.

Aim to finish in roughly 5–8 meaningful user answers, but continue when
there is an obvious important ambiguity.

Finish when you have enough information to produce a useful profile,
not when every possible field has been discussed.

When enough information has been collected, call finishOnboarding.
"""
ONBOARDING_CHAT_PROMPT = ONBOARDING_PROMPT

ONBOARDING_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "getOnboardingState",
        "description": "Return the current onboarding transcript, progress, and completion state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "finishOnboarding",
        "description": "Mark onboarding complete once enough useful information has been collected.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

_NON_ANSWERS = {
    "hello",
    "hi",
    "hey",
    "start",
    "start my onboarding",
    "let's start",
    "lets start",
}


@dataclass(frozen=True)
class Turn:
    role: str
    content: str


@dataclass
class OnboardingSession:
    turns: list[Turn] = field(default_factory=list)
    finished: bool = False

    def add_user_answer(self, answer: str) -> None:
        if self.finished:
            raise RuntimeError("This onboarding session is already complete.")
        if not (answer := answer.strip()):
            raise ValueError("An onboarding answer cannot be empty.")
        self.turns.append(Turn("user", answer))

    def transcript(self) -> list[dict[str, str]]:
        return [{"role": turn.role, "content": turn.content} for turn in self.turns]

    def meaningful_answer_count(self) -> int:
        return sum(
            turn.role == "user" and turn.content.strip().lower() not in _NON_ANSWERS
            for turn in self.turns
        )

    def state(self) -> dict[str, Any]:
        return {
            "meaningfulUserAnswers": self.meaningful_answer_count(),
            "finished": self.finished,
            "transcript": self.transcript(),
        }

    @classmethod
    def from_messages(cls, messages: list[Any], *, finished: bool = False) -> OnboardingSession:
        turns: list[Turn] = []
        for message in messages:
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)
            if role in {"user", "assistant"} and isinstance(content, str):
                turns.append(Turn(role, content))
        return cls(turns=turns, finished=finished)


class OnboardingInterviewer:
    """Tool-enabled Responses API driver shared by Marimo and programmatic callers."""

    def __init__(self, api_key: str | None = None, *, client: Any | None = None) -> None:
        self.client = client or make_client(api_key=api_key) or OpenAI(api_key=api_key)

    def next_turn(
        self,
        session: OnboardingSession,
        *,
        model: str = "gpt-5.6-terra",
        reasoning_effort: str = "low",
        max_output_tokens: int = 300,
        on_tool_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        input_items: list[Any] = session.transcript()
        request: dict[str, Any] = {
            "model": model,
            "instructions": ONBOARDING_PROMPT,
            "input": input_items,
            "tools": ONBOARDING_TOOLS,
            "tool_choice": {"type": "function", "name": "getOnboardingState"},
            "max_output_tokens": max_output_tokens,
        }
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}

        tool_events: list[dict[str, Any]] = []
        traces = []
        started = time.perf_counter()
        response = self.client.responses.create(**request)
        traces.append(make_trace(stage="onboarding", model=model, reasoning_effort=reasoning_effort, prompt_version=ONBOARDING_VERSION, request=request, response=response, latency_ms=(time.perf_counter() - started) * 1000))
        for _ in range(8):
            tool_calls = [item for item in response.output if item.type == "function_call"]
            if not tool_calls:
                break

            input_items += response.output
            for tool_call in tool_calls:
                arguments = json.loads(tool_call.arguments or "{}")
                result = self._execute_tool(tool_call.name, arguments, session)
                event = {
                    "name": tool_call.name,
                    "arguments": arguments,
                    "result": result,
                    "call_id": tool_call.call_id,
                }
                tool_events.append(event)
                if on_tool_event is not None:
                    on_tool_event(event)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(result),
                    }
                )

            follow_up = {**request, "input": input_items, "tool_choice": "auto"}
            started = time.perf_counter()
            response = self.client.responses.create(**follow_up)
            traces.append(make_trace(stage="onboarding", model=model, reasoning_effort=reasoning_effort, prompt_version=ONBOARDING_VERSION, request=follow_up, response=response, latency_ms=(time.perf_counter() - started) * 1000))
        else:
            raise RuntimeError("Onboarding interviewer exceeded the tool-call limit.")

        message = response.output_text.strip()
        if not message:
            message = "Thanks — I have enough to complete your onboarding." if session.finished else "What would you like me to know about you?"
        session.turns.append(Turn("assistant", message))
        return {
            "message": message,
            "finished": session.finished,
            "tool_events": tool_events,
            "traces": traces,
            "response": response.model_dump(),
        }

    @staticmethod
    def _execute_tool(name: str, arguments: dict[str, Any], session: OnboardingSession) -> dict[str, Any]:
        if arguments:
            return {"ok": False, "error": f"{name} does not accept arguments."}
        if name == "getOnboardingState":
            return session.state()
        if name == "finishOnboarding":
            session.finished = True
            return {"ok": True, "finished": True}
        return {"ok": False, "error": f"Unknown onboarding tool: {name}"}
