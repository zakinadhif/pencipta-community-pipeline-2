"""Faithfully convert an onboarding transcript into a user-editable profile draft."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .profiles import ProfileDraft, ProfileValidationError


PROFILE_COMPILER_VERSION = "profile_compiler_v1"
PROFILE_COMPILER_PROMPT = """Turn the supplied onboarding conversation into a structured social-profile draft.
Faithfully represent only what the user said about themselves; do not invent or verify facts. Preserve the distinction between interests, knowledge, experience, willingness to help, and what the user is looking for. Keep descriptions concise and concrete, without promotional labels.

Return JSON only with exactly: headline, summary, knowledge, experience, interests, canHelpWith, lookingFor, openTo, projects, location. Each field must be present. Use empty arrays for unknown list fields and null for an unknown location. openTo values may only be collaboration, mentoring, being_mentored, cofounding, friendship, advice, recommendations, hiring, being_hired, or meeting_people. Each project has a required description and optional name and status."""


class ProfileCompiler:
    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)

    def compile(self, transcript: list[dict[str, str]], *, model: str = "gpt-5.6-luna", reasoning_effort: str = "low") -> tuple[ProfileDraft, dict[str, Any]]:
        if not transcript:
            raise ValueError("A transcript is required before compiling a profile.")
        request: dict[str, Any] = {"model": model, "instructions": PROFILE_COMPILER_PROMPT, "input": json.dumps({"transcript": transcript})}
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        response = self.client.responses.create(**request)
        try:
            raw = json.loads(response.output_text)
            draft = ProfileDraft.from_dict(raw)
        except (json.JSONDecodeError, ProfileValidationError) as exc:
            raise RuntimeError(f"Profile compiler returned an invalid draft: {exc}") from exc
        return draft, response.model_dump()
