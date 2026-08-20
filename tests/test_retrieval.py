import json
from pathlib import Path

from src.retrieval.embeddings import profile_vectors
from src.retrieval.prescore import interaction_score, weighted_prescore
from src.retrieval.search import search_people


def test_interaction_score_graded_below_two_overlaps():
    assert interaction_score(["advice", "mentoring"], ["advice", "mentoring"]) == 1.0
    assert interaction_score(["advice", "mentoring"], ["advice"]) == 0.5
    assert interaction_score(["advice", "mentoring"], ["cofounding"]) == 0.0
    assert interaction_score([], ["advice"]) == 0.0


class _Weights:
    offers_weight = 0.45
    interests_weight = 0.20
    reciprocity_weight = 0.20
    interaction_weight = 0.15


def test_weighted_prescore_preserves_ordering_and_clamps():
    low = weighted_prescore(0.0, 0.0, 0.0, 0.0, _Weights())
    high = weighted_prescore(0.9, 0.5, 0.4, 1.0, _Weights())
    assert 0.0 <= low <= high <= 1.0


def _profiles():
    return json.loads((Path(__file__).parents[1] / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))


def test_profile_vectors_keep_offers_interests_and_needs_directional():
    maya = next(profile for profile in _profiles() if profile["id"] == "maya")
    vectors = profile_vectors(maya)
    assert "campus distribution" in vectors.offers
    assert "student entrepreneurship" in vectors.interests
    assert "design feedback" in vectors.needs


def test_retrieval_excludes_requester_and_applies_hard_location_filter():
    profiles = _profiles()
    requester = next(profile for profile in profiles if profile["id"] == "adi")
    results = search_people(
        profiles=profiles,
        requester=requester,
        queries={"offers": "student organization operations", "interests": "community", "needs": ""},
        filters={"location": "Bandung", "interactionTypes": []},
        interaction_types=[],
        limit=30,
    )
    assert results
    assert all(row["candidate"]["id"] != "adi" for row in results)
    assert all(row["candidate"]["location"] == "Bandung" for row in results)


def test_interpreted_interaction_types_apply_when_hard_filter_list_is_empty():
    requester = {
        "id": "requester", "knowledge": [], "experience": [], "interests": [],
        "canHelpWith": ["Python"], "lookingFor": ["mentoring"], "openTo": [], "projects": [],
    }
    incompatible = {
        "id": "incompatible", "knowledge": [], "experience": [], "interests": [],
        "canHelpWith": ["mentoring"], "lookingFor": [], "openTo": [], "projects": [],
    }
    compatible = {
        **incompatible, "id": "compatible", "openTo": ["mentoring"],
    }
    rows = search_people(
        profiles=[requester, incompatible, compatible], requester=requester,
        queries={"offers": "mentoring", "interests": "", "needs": "Python help"},
        filters={"location": None, "interactionTypes": []}, interaction_types=["mentoring"],
        limit=10,
    )
    assert [row["candidate"]["id"] for row in rows] == ["compatible"]


class RecordingEmbedder:
    def __init__(self):
        self.texts = []

    def embed(self, texts):
        self.texts = texts
        return [[1.0, 0.0] for _ in texts]


def test_reciprocal_query_uses_need_interpreter_output():
    requester = {
        "id": "requester", "knowledge": [], "experience": [], "interests": [],
        "canHelpWith": ["Python"], "lookingFor": ["mentoring"], "openTo": [], "projects": [],
    }
    candidate = {
        "id": "candidate", "knowledge": [], "experience": [], "interests": [],
        "canHelpWith": ["mentoring"], "lookingFor": ["Python help"],
        "openTo": ["mentoring"], "projects": [],
    }
    embedder = RecordingEmbedder()
    search_people(
        profiles=[requester, candidate], requester=requester,
        queries={"offers": "mentor", "interests": "", "needs": "custom reciprocal query"},
        filters={"location": None, "interactionTypes": []}, interaction_types=["mentoring"],
        limit=10, embedder=embedder,
    )
    assert embedder.texts[2] == "custom reciprocal query"
