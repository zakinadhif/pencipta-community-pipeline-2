"""Profile contract and validation for the collaboration-matching MVP.

The compiler produces a draft only. Persisting or embedding that draft remains a
separate, explicit user-acceptance action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


INTERACTION_TYPES = frozenset({
    "collaboration", "mentoring", "being_mentored", "cofounding", "friendship",
    "advice", "recommendations", "hiring", "being_hired", "meeting_people",
})


class ProfileValidationError(ValueError):
    """Raised when an AI-generated profile does not satisfy the product contract."""


def _strings(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ProfileValidationError(f"{field_name} must be a list of non-empty strings.")
    return [item.strip() for item in value]


def _projects(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ProfileValidationError("projects must be a list.")
    cleaned: list[dict[str, str]] = []
    for project in value:
        if not isinstance(project, dict) or not isinstance(project.get("description"), str) or not project["description"].strip():
            raise ProfileValidationError("each project needs a non-empty description.")
        item = {"description": project["description"].strip()}
        for key in ("name", "status"):
            if key in project and project[key] is not None:
                if not isinstance(project[key], str) or not project[key].strip():
                    raise ProfileValidationError(f"project {key} must be a non-empty string when provided.")
                item[key] = project[key].strip()
        cleaned.append(item)
    return cleaned


@dataclass(frozen=True)
class ProfileDraft:
    headline: str
    summary: str
    knowledge: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    canHelpWith: list[str] = field(default_factory=list)
    lookingFor: list[str] = field(default_factory=list)
    openTo: list[str] = field(default_factory=list)
    projects: list[dict[str, str]] = field(default_factory=list)
    location: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProfileDraft":
        if not isinstance(value, dict):
            raise ProfileValidationError("profile must be an object.")
        required = {"headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo", "projects", "location"}
        missing = required - value.keys()
        if missing:
            raise ProfileValidationError(f"profile is missing fields: {', '.join(sorted(missing))}.")
        for field_name in ("headline", "summary"):
            if not isinstance(value[field_name], str) or not value[field_name].strip():
                raise ProfileValidationError(f"{field_name} must be a non-empty string.")
        open_to = _strings(value["openTo"], "openTo")
        unsupported = set(open_to) - INTERACTION_TYPES
        if unsupported:
            raise ProfileValidationError(f"unsupported interaction types: {', '.join(sorted(unsupported))}.")
        location = value["location"]
        if location is not None and (not isinstance(location, str) or not location.strip()):
            raise ProfileValidationError("location must be a non-empty string or null.")
        return cls(
            headline=value["headline"].strip(), summary=value["summary"].strip(),
            knowledge=_strings(value["knowledge"], "knowledge"),
            experience=_strings(value["experience"], "experience"),
            interests=_strings(value["interests"], "interests"),
            canHelpWith=_strings(value["canHelpWith"], "canHelpWith"),
            lookingFor=_strings(value["lookingFor"], "lookingFor"), openTo=open_to,
            projects=_projects(value["projects"]), location=location.strip() if location else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
