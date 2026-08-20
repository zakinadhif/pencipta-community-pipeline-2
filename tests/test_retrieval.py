import json
from pathlib import Path

import pytest

from src.retrieval.embeddings import profile_vectors
from src.retrieval.index import EmbeddingIndex
from src.retrieval.prescore import interaction_score, weighted_prescore
from src.retrieval.search import search_people
from src.tracing.storage import ExperimentStore


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


class FixedEmbedder:
    def __init__(self):
        self.vectors = {"query-offers": [1, 0, 0], "query-interests": [0, 1, 0], "query-needs": [0, 0, 1]}
        self.texts = []

    def embed(self, texts):
        self.texts = list(texts)
        return [self.vectors.get(text, [1, 1, 0]) for text in texts]


def _fixture_profiles():
    return [
        {"id": "req", "knowledge": ["python"], "experience": [], "interests": ["ai"], "canHelpWith": ["mentoring"], "lookingFor": ["feedback"], "openTo": ["advice"], "projects": [], "location": "Bandung"},
        {"id": "c1", "knowledge": ["react"], "experience": [], "interests": ["ai"], "canHelpWith": ["design"], "lookingFor": ["partner"], "openTo": ["advice"], "projects": [], "location": "Bandung"},
        {"id": "c2", "knowledge": ["react"], "experience": [], "interests": ["ai"], "canHelpWith": ["design"], "lookingFor": ["partner"], "openTo": ["advice"], "projects": [], "location": "Jakarta"},
    ]


def _query_dict():
    return {"offers": "query-offers", "interests": "query-interests", "needs": "query-needs"}


def test_search_with_index_embeds_only_queries():
    store = ExperimentStore("/tmp/opencode/test_search_index.duckdb")
    store.upsert_vector_rows([
        {"profile_id": "c1", "kind": "offers", "vector": [1, 0, 0], "text": "react"},
        {"profile_id": "c1", "kind": "interests", "vector": [0, 1, 0], "text": "ai"},
        {"profile_id": "c1", "kind": "needs", "vector": [0, 0, 1], "text": "partner"},
        {"profile_id": "c2", "kind": "offers", "vector": [1, 0, 0], "text": "react"},
        {"profile_id": "c2", "kind": "interests", "vector": [0, 1, 0], "text": "ai"},
        {"profile_id": "c2", "kind": "needs", "vector": [0, 0, 1], "text": "partner"},
    ])
    index = EmbeddingIndex.load(store)
    embedder = FixedEmbedder()
    profiles = _fixture_profiles()
    rows = search_people(profiles=profiles, requester=profiles[0], queries=_query_dict(),
                         filters={"location": None, "interactionTypes": []}, interaction_types=["advice"],
                         limit=10, index=index, embedder=embedder)
    assert embedder.texts == ["query-offers", "query-interests", "query-needs"]
    assert len(rows) == 2
    assert rows[0]["rank"] == 1


def test_search_embeds_candidates_when_no_index():
    embedder = FixedEmbedder()
    profiles = _fixture_profiles()
    rows = search_people(profiles=profiles, requester=profiles[0], queries=_query_dict(),
                         filters={"location": None, "interactionTypes": []}, interaction_types=["advice"],
                         limit=10, embedder=embedder)
    assert len(rows) == 2
    assert embedder.texts[0:3] == ["query-offers", "query-interests", "query-needs"]


def test_search_excludes_requester_and_applies_location_filter():
    profiles = _fixture_profiles()
    rows = search_people(profiles=profiles, requester=profiles[0], queries=_query_dict(),
                         filters={"location": "Bandung", "interactionTypes": []}, interaction_types=["advice"],
                         limit=10)
    ids = [row["candidate"]["id"] for row in rows]
    assert "req" not in ids and ids == ["c1"]


def test_min_prescore_filters_rows():
    profiles = _fixture_profiles()
    rows = search_people(profiles=profiles, requester=profiles[0], queries=_query_dict(),
                         filters={"location": None, "interactionTypes": []}, interaction_types=["advice"],
                         limit=10, min_prescore=0.9)
    assert all(row["prescore"] >= 0.9 for row in rows)


def test_per_dimension_union_keeps_candidates_strong_in_one_dimension():
    candidates = [
        {"id": f"c{i}", "knowledge": ["react"], "experience": [], "interests": ["ai"], "canHelpWith": [], "lookingFor": [], "openTo": ["advice"], "projects": [], "location": "Bandung"}
        for i in range(6)
    ]
    store = ExperimentStore("/tmp/opencode/test_union.duckdb")
    vectors = {"c0": {"offers": [1, 0, 0], "interests": [0, 0, 1], "needs": [0, 1, 0]},
               "c1": {"offers": [0, 1, 0], "interests": [1, 0, 0], "needs": [0, 1, 0]},
               "c2": {"offers": [0, 1, 0], "interests": [0, 1, 0], "needs": [0, 1, 0]},
               "c3": {"offers": [0, 0, 1], "interests": [0, 1, 0], "needs": [0, 1, 0]},
               "c4": {"offers": [0, 0, 1], "interests": [0, 0, 1], "needs": [0, 1, 0]},
               "c5": {"offers": [0, 0, 1], "interests": [0, 0, 1], "needs": [0, 0, 1]}}
    store.upsert_vector_rows([{"profile_id": pid, "kind": kind, "vector": vec, "text": ""}
                              for pid, kinds in vectors.items() for kind, vec in kinds.items()])
    index = EmbeddingIndex.load(store)

    class _E:
        def embed(self, texts):
            return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    profiles = [{"id": "req", "knowledge": [], "experience": [], "interests": [], "canHelpWith": [], "lookingFor": [], "openTo": [], "projects": [], "location": "Bandung"}] + candidates
    rows = search_people(profiles=profiles, requester=profiles[0], queries=_query_dict(),
                         filters={"location": None, "interactionTypes": []}, interaction_types=["advice"],
                         limit=10, index=index, embedder=_E(), per_dimension_count=2)
    ids = [row["candidate"]["id"] for row in rows]
    assert "c5" in ids
    assert set(ids) <= {f"c{i}" for i in range(6)}
