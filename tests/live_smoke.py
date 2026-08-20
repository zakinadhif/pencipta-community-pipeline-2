"""Explicit, billable live smoke checks; not collected by the unit-test suite."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.agents.onboarding import OnboardingInterviewer, OnboardingSession
from src.agents.profile_compiler import ProfileCompiler


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your-api-key":
        raise SystemExit("OPENAI_API_KEY is not configured; live smoke tests were not run.")

    session = OnboardingSession()
    session.add_user_answer(
        "I build small Python tools for student communities, can help with basic automation, "
        "and want advice from someone experienced in volunteer retention. I live in Bandung."
    )
    turn = OnboardingInterviewer(api_key).next_turn(session, max_output_tokens=300)
    assert any(event["name"] == "getOnboardingState" for event in turn["tool_events"])
    assert turn["traces"] and turn["message"]

    draft, raw, trace = ProfileCompiler(api_key).compile_with_trace(session.transcript())
    assert draft.headline and raw.get("id") and trace.response_id
    print("live onboarding tools: passed")
    print("live profile structured output: passed")


if __name__ == "__main__":
    main()
