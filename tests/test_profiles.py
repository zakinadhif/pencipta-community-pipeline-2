import json
from pathlib import Path

import pytest

from src.schemas.profile import ProfileDraft, ProfileValidationError


def test_synthetic_profiles_conform_to_profile_ontology():
    profiles = json.loads((Path(__file__).parents[1] / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    for profile in profiles:
        draft = ProfileDraft.from_dict({
            **profile,
            "projects": profile.get("projects", []),
            "location": profile.get("location"),
        })
        assert draft.headline == profile["headline"]


def test_rejects_invalid_interaction_type():
    with pytest.raises(ProfileValidationError, match="unsupported interaction"):
        ProfileDraft.from_dict({
            "headline": "A", "summary": "B", "knowledge": [], "experience": [], "interests": [],
            "canHelpWith": [], "lookingFor": [], "openTo": ["coffee"], "projects": [], "location": None,
        })
