"""A short, traceable interviewer that creates conversation records, never profiles."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


ONBOARDING_VERSION = "onboarding_v1"
ONBOARDING_PROMPT = """You are the onboarding interviewer for a social network built around meaningful human collaboration.
Learn enough to answer when someone would benefit from meeting this person, and when this person would benefit from meeting another.

Have a short, natural conversation. Ask exactly one concise question at a time and react to the user's actual answer. Seek concrete examples where useful. Learn only what the person volunteers about knowledge, experience, interests, current projects, things they can help with, things they seek, and welcomed interaction types.

Interest is not expertise; exposure is not experience; experience is not willingness; aspiration is not current ability. Never upgrade a weak statement into a stronger identity claim. Do not ask sensitive questions merely to enrich a profile. Do not sound like a recruiter or repeatedly summarize the user.

Aim for five to eight meaningful answers. Mark finished only when there is enough information for a useful profile; do not force every category.

Return JSON only: {"message": string, "finished": boolean}."""


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
        answer = answer.strip()
        if not answer:
            raise ValueError("An onboarding answer cannot be empty.")
        self.turns.append(Turn("user", answer))

    def transcript(self) -> list[dict[str, str]]:
        return [{"role": turn.role, "content": turn.content} for turn in self.turns]


class OnboardingInterviewer:
    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)

    def next_turn(self, session: OnboardingSession, *, model: str = "gpt-5.6-terra", reasoning_effort: str = "low") -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model, "instructions": ONBOARDING_PROMPT,
            "input": json.dumps({"transcript": session.transcript()}),
        }
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        response = self.client.responses.create(**request)
        try:
            parsed = json.loads(response.output_text)
            message, finished = parsed["message"].strip(), bool(parsed["finished"])
        except (json.JSONDecodeError, KeyError, AttributeError) as exc:
            raise RuntimeError("Onboarding interviewer returned invalid JSON.") from exc
        if not message:
            raise RuntimeError("Onboarding interviewer returned an empty message.")
        session.turns.append(Turn("assistant", message))
        session.finished = finished
        return {"message": message, "finished": finished, "response": response.model_dump()}
