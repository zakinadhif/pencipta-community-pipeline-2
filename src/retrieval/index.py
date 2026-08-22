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
    def rebuild(cls, store: ExperimentStore, profiles: list[dict[str, Any]], embedder: Any, *, batch_size: int = 256) -> "EmbeddingIndex":
        store.create_vector_table()
        rows, doc_to_key = [], {}
        for profile in profiles:
            vectors = profile_vectors(profile)
            for kind in ("offers", "interests", "needs"):
                text = getattr(vectors, kind)
                if text.strip():
                    doc_to_key[(profile["id"], kind)] = text
        keys = list(doc_to_key.keys())
        # Embed in batches: many providers cap request input length (e.g. 2048).
        for start in range(0, len(keys), batch_size):
            chunk = keys[start:start + batch_size]
            texts = [doc_to_key[key] for key in chunk]
            embeddings = embedder.embed(texts)
            for key, vector in zip(chunk, embeddings):
                rows.append({"profile_id": key[0], "kind": key[1], "vector": vector, "text": doc_to_key[key]})
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
