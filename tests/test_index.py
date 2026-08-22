import pytest

from src.retrieval.embeddings import profile_vectors
from src.retrieval.index import EmbeddingIndex, rebuild_index
from src.tracing.storage import ExperimentStore


class FakeEmbedder:
    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[float(i) for i in range(self.dim)] for _ in texts]


def _profiles():
    return [
        {"id": "a", "knowledge": ["python"], "experience": [], "interests": ["data"], "canHelpWith": [], "lookingFor": ["mentor"], "openTo": [], "projects": []},
        {"id": "b", "knowledge": ["rust"], "experience": [], "interests": ["systems"], "canHelpWith": [], "lookingFor": ["collaborator"], "openTo": [], "projects": []},
    ]


def test_rebuild_embeds_every_profile_vector_and_persists(tmp_path):
    store = ExperimentStore(tmp_path / "runs.duckdb")
    embedder = FakeEmbedder()
    index = EmbeddingIndex.rebuild(store, _profiles(), embedder)
    assert embedder.calls == 1
    assert set(index.vectors["offers"]) == {"a", "b"}
    rows = store.load_vector_rows()
    assert len(rows) == 6


def test_load_reads_back_persisted_vectors(tmp_path):
    store = ExperimentStore(tmp_path / "runs.duckdb")
    store.upsert_vector_rows([
        {"profile_id": "a", "kind": "offers", "vector": [1.0, 2.0], "text": "x"},
        {"profile_id": "a", "kind": "interests", "vector": [3.0, 4.0], "text": "y"},
        {"profile_id": "a", "kind": "needs", "vector": [5.0, 6.0], "text": "z"},
    ])
    index = EmbeddingIndex.load(store)
    assert index.vectors["offers"]["a"] == [1.0, 2.0]


def test_rebuild_index_wrapper_returns_populated_index(tmp_path, monkeypatch):
    store = ExperimentStore(tmp_path / "runs.duckdb")
    client = object()
    monkeypatch.setattr("src.retrieval.index.OpenAIEmbedder", lambda client_: FakeEmbedder())
    index = rebuild_index(store, _profiles(), client)
    assert "a" in index.vectors["offers"]
    assert "b" in index.vectors["interests"]
