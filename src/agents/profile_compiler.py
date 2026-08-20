"""Faithfully convert an onboarding transcript into a user-editable profile draft."""
from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI

from ..schemas.profile import INTERACTION_TYPES, ProfileDraft, ProfileValidationError
from ..tracing.trace import make_trace


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

For `openTo`, use only these interaction types:
advice, being_hired, being_mentored, cofounding, collaboration, friendship,
hiring, meeting_people, mentoring, recommendations.

`openTo` describes the broad social interaction, not the activity or topic.
Put activities and preferences such as photo walks, drawing together, quiet
time outdoors, or discussing nature in `interests` and `lookingFor`. For
example, someone seeking a peer for photo walks may be open to `friendship`,
`meeting_people`, and/or `collaboration`; never put "photo walks" in `openTo`.
"""

PROFILE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo", "projects", "location"], "properties": {"headline": {"type": "string"}, "summary": {"type": "string"}, "knowledge": {"type": "array", "items": {"type": "string"}}, "experience": {"type": "array", "items": {"type": "string"}}, "interests": {"type": "array", "items": {"type": "string"}}, "canHelpWith": {"type": "array", "items": {"type": "string"}}, "lookingFor": {"type": "array", "items": {"type": "string"}}, "openTo": {"type": "array", "items": {"type": "string", "enum": sorted(INTERACTION_TYPES)}}, "projects": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["name", "description", "status"], "properties": {"name": {"type": ["string", "null"]}, "description": {"type": "string"}, "status": {"type": ["string", "null"]}}}}, "location": {"type": ["string", "null"]}}}


class ProfileCompiler:
    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)

    def compile(self, transcript: list[dict[str, str]], *, model: str = "gpt-5.6-luna", reasoning_effort: str = "low") -> tuple[ProfileDraft, dict[str, Any]]:
        draft, raw_response, _ = self.compile_with_trace(
            transcript, model=model, reasoning_effort=reasoning_effort
        )
        return draft, raw_response

    def compile_with_trace(self, transcript: list[dict[str, str]], *, model: str = "gpt-5.6-luna", reasoning_effort: str = "low", max_output_tokens: int = 1200):
        if not transcript:
            raise ValueError("A transcript is required before compiling a profile.")
        request: dict[str, Any] = {"model": model, "instructions": PROFILE_COMPILER_PROMPT, "input": json.dumps({"transcript": transcript}), "max_output_tokens": max_output_tokens, "text": {"format": {"type": "json_schema", "name": "profile_draft", "schema": PROFILE_SCHEMA, "strict": True}}}
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        started = time.perf_counter()
        response = None
        try:
            response = self.client.responses.create(**request)
        except Exception as exc:
            trace = make_trace(stage="profile_compiler", model=model, reasoning_effort=reasoning_effort, prompt_version=PROFILE_COMPILER_VERSION, request=request, response=response, latency_ms=(time.perf_counter() - started) * 1000, error=f"{type(exc).__name__}: {exc}")
            setattr(exc, "llm_trace", trace)
            raise
        try:
            draft = ProfileDraft.from_dict(json.loads(response.output_text))
        except (json.JSONDecodeError, ProfileValidationError) as exc:
            raise RuntimeError(f"Profile compiler returned an invalid draft: {exc}") from exc
        trace = make_trace(stage="profile_compiler", model=model, reasoning_effort=reasoning_effort, prompt_version=PROFILE_COMPILER_VERSION, request=request, response=response, latency_ms=(time.perf_counter() - started) * 1000)
        return draft, response.model_dump(), trace
