"""Capture llm/tool spans from an existing agent. No framework import required.

    from phthos_eval import TraceSink

    sink = TraceSink()
    agent = sink.wrap(agent)
    doc = sink.diagnose(expected_tools=["search"])
"""

from __future__ import annotations

from typing import Any

from phthos_eval.runner import run_dataset
from phthos_eval.wrap import FRAMEWORKS, wrap_agent


def instrument(agent: Any, *, sink: TraceSink | None = None) -> tuple[Any, TraceSink]:
    """Attach a sink and return ``(agent, sink)``."""
    s = sink or TraceSink()
    return s.wrap(agent), s


class TraceSink:
    """In-process span buffer. ``wrap`` attaches collectors; you still run the agent."""

    frameworks = FRAMEWORKS

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self._n = 0

    def reset(self) -> None:
        self.spans = []
        self._n = 0

    def wrap(self, agent: Any) -> Any:
        """Attach collectors for the detected framework and return the agent (or configured copy)."""
        return wrap_agent(self, agent)

    def add_llm(
        self,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        tokens: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        span: dict[str, Any] = {
            "id": self._id(),
            "type": "llm",
            "latency_ms": round(float(latency_ms), 3),
            "cost_usd": float(cost_usd),
            **extra,
        }
        if tokens is not None:
            span["tokens"] = tokens
        self.spans.append(span)
        return span

    def add_tool(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        **extra: Any,
    ) -> dict[str, Any]:
        span: dict[str, Any] = {
            "id": self._id(),
            "type": "tool",
            "name": name,
            "args": dict(args or {}),
            "latency_ms": round(float(latency_ms), 3),
            "cost_usd": float(cost_usd),
            **extra,
        }
        self.spans.append(span)
        return span

    def diagnose(
        self,
        *,
        expected_tools: list[str] | None = None,
        budget: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        tool_schemas: dict[str, Any] | None = None,
        case_id: str = "run",
        dataset_id: str = "trace-sink",
        judge: bool = False,
    ) -> dict[str, Any]:
        """Score the captured spans with the same offline runner."""
        return run_dataset(
            {
                "id": dataset_id,
                "n_runs": 1,
                "budget": budget or {"max_cost_usd": 1e9, "max_steps": 10_000},
                "policy": policy or {"deny_tools": []},
                "tool_schemas": tool_schemas or {},
                "cases": [
                    {
                        "id": case_id,
                        "expected_tools": expected_tools or [],
                        "traces": [{"spans": list(self.spans)}],
                    }
                ],
            },
            judge=judge,
        )

    def ingest(self, client: Any, **kwargs: Any) -> Any:
        """POST spans through a ``LiveClient`` (or anything with ``ingest(spans, **kw)``)."""
        return client.ingest(self.spans, **kwargs)

    def _id(self) -> str:
        self._n += 1
        return f"s{self._n}"
