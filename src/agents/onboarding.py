"""Onboarding interviewer; it records a conversation and never writes a profile."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


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


class OnboardingInterviewer:
    """Programmatic driver; Marimo's chat component uses the same base prompt."""

    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)

    def next_turn(self, session: OnboardingSession, *, model: str = "gpt-5.6-terra", reasoning_effort: str = "low") -> dict[str, Any]:
        request: dict[str, Any] = {"model": model, "instructions": ONBOARDING_PROMPT, "input": json.dumps({"transcript": session.transcript()})}
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        response = self.client.responses.create(**request)
        message = response.output_text.strip()
        if not message:
            raise RuntimeError("Onboarding interviewer returned an empty message.")
        session.turns.append(Turn("assistant", message))
        return {"message": message, "finished": False, "response": response.model_dump()}
