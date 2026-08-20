"""Precomputed per-profile embedding index persisted in DuckDB."""
from __future__ import annotations

from typing import Any

from ..tracing.storage import ExperimentStore
from .embeddings import OpenAIEmbedder, profile_vectors


class EmbeddingIndex:
    """Three directional vectors per profile, keyed {kind: {profile_id: vector}}."""

    def __init__(self, vectors: dict[str, dict[str, list[float]]], texts: dict[tuple[str, str], str] | None = None) -> None:
        self.vectors = vectors
        self.texts = texts or {}

    @classmethod
    def rebuild(cls, store: ExperimentStore, profiles: list[dict[str, Any]], embedder: Any) -> "EmbeddingIndex":
        store.create_vector_table()
        rows, doc_to_key = [], {}
        for profile in profiles:
            vectors = profile_vectors(profile)
            for kind in ("offers", "interests", "needs"):
                text = getattr(vectors, kind)
                if text.strip():
                    doc_to_key[(profile["id"], kind)] = text
        texts = list(doc_to_key.values())
        embeddings = embedder.embed(texts)
        for (profile_id, kind), text in doc_to_key.items():
            rows.append({"profile_id": profile_id, "kind": kind, "vector": embeddings[len(rows)], "text": text})
        store.upsert_vector_rows(rows)
        return cls.load(store)

    @classmethod
    def load(cls, store: ExperimentStore) -> "EmbeddingIndex":
        vectors: dict[str, dict[str, list[float]]] = {"offers": {}, "interests": {}, "needs": {}}
        texts: dict[tuple[str, str], str] = {}
        for row in store.load_vector_rows():
            vectors.setdefault(row["kind"], {})[row["profile_id"]] = row["vector"]
            texts[(row["profile_id"], row["kind"])] = row["text"]
        return cls(vectors, texts)


def rebuild_index(store: ExperimentStore, profiles: list[dict[str, Any]], client: Any) -> EmbeddingIndex:
    return EmbeddingIndex.rebuild(store, profiles, OpenAIEmbedder(client))
