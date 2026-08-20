"""Persistent trace-record contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class LLMTrace:
    stage: str
    model: str
    reasoning_effort: str | None
    prompt_version: str
    request: Any
    response: Any
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    ttft_ms: float | None = None
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    stream_events: list[dict[str, Any]] = field(default_factory=list)
    response_id: str | None = None
    error: str | None = None
    call_type: str = "response"
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
