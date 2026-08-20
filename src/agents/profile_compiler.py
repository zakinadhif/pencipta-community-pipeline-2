"""Faithfully convert an onboarding transcript into a user-editable profile draft."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from ..schemas.profile import ProfileDraft, ProfileValidationError


PROFILE_COMPILER_VERSION = "profile_compiler_v1"
PROFILE_COMPILER_PROMPT = """You turn a conversation with a user into a structured social profile.

Your job is to faithfully represent what the user has communicated about
themselves in a form useful for matching them with other people.

Extract:

- knowledge
- experience
- interests
- things they can help others with
- things they are looking for
- current projects
- kinds of interactions they are open to
- location, when relevant and explicitly provided

IMPORTANT:

Do not invent information.

Preserve the distinction between:

INTEREST
"I want to learn cybersecurity"

KNOWLEDGE
"I know web security"

EXPERIENCE
"I've competed in CTFs for three years"

CAN HELP WITH
"I can help beginners learn web exploitation"

LOOKING FOR
"I'd like someone experienced with binary exploitation"

Do not treat one category as another unless the user's statement supports it.

Do not attempt to independently verify the user's statements.

The profile represents how the user has described themselves.

Write concise, concrete descriptions.

Avoid promotional language and generic labels.

Bad:
"passionate technology enthusiast"

Good:
"interested in offensive security and CTFs"

Bad:
"experienced entrepreneur"

Good:
"previously ran a student marketplace"

Generate a short human-readable profile and structured fields.
"""

PROFILE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo", "projects", "location"], "properties": {"headline": {"type": "string"}, "summary": {"type": "string"}, "knowledge": {"type": "array", "items": {"type": "string"}}, "experience": {"type": "array", "items": {"type": "string"}}, "interests": {"type": "array", "items": {"type": "string"}}, "canHelpWith": {"type": "array", "items": {"type": "string"}}, "lookingFor": {"type": "array", "items": {"type": "string"}}, "openTo": {"type": "array", "items": {"type": "string"}}, "projects": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["description"], "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "string"}}}}, "location": {"type": ["string", "null"]}}}


class ProfileCompiler:
    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)

    def compile(self, transcript: list[dict[str, str]], *, model: str = "gpt-5.6-luna", reasoning_effort: str = "low") -> tuple[ProfileDraft, dict[str, Any]]:
        if not transcript:
            raise ValueError("A transcript is required before compiling a profile.")
        request: dict[str, Any] = {"model": model, "instructions": PROFILE_COMPILER_PROMPT, "input": json.dumps({"transcript": transcript}), "text": {"format": {"type": "json_schema", "name": "profile_draft", "schema": PROFILE_SCHEMA, "strict": True}}}
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        response = self.client.responses.create(**request)
        try:
            draft = ProfileDraft.from_dict(json.loads(response.output_text))
        except (json.JSONDecodeError, ProfileValidationError) as exc:
            raise RuntimeError(f"Profile compiler returned an invalid draft: {exc}") from exc
        return draft, response.model_dump()
