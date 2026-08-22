"""(Re)build the precomputed profile vector index into data/runs.duckdb."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import make_client
from src.retrieval.index import rebuild_index
from src.tracing.storage import ExperimentStore


def main() -> None:
    load_dotenv(ROOT / ".env")
    profiles = json.loads((ROOT / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY required to rebuild the embedding index.")
    client = make_client(api_key=api_key)
    store = ExperimentStore(ROOT / "data" / "runs.duckdb")
    index = rebuild_index(store, profiles, client)
    counts = {kind: len(vectors) for kind, vectors in index.vectors.items()}
    print(f"Index rebuilt: {counts}")


if __name__ == "__main__":
    main()
