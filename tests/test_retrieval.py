import json
from pathlib import Path

from src.retrieval.embeddings import profile_vectors
from src.retrieval.search import search_people


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
