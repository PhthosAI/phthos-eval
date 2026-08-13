"""Google ADK hours agent + Phthos Eval (one file).

Lib (offline, no Docker):
    pip install google-adk phthos-eval
    python examples/adk/hours.py

Live (OSS engine UI at http://127.0.0.1:8765):
    python examples/adk/hours.py --live

Paste into an *existing* ADK Agent — four callback kwargs, then one ingest
(or run_dataset). Phthos Eval does not wrap ADK or apply a fix.

    sink = EvalSink()
    agent = Agent(
        ...,
        before_model_callback=sink.before_model_callback,
        after_model_callback=sink.after_model_callback,
        before_tool_callback=sink.before_tool_callback,
        after_tool_callback=sink.after_tool_callback,
    )
    # after runner.run_async(...):
    LiveClient("http://127.0.0.1:8765").ingest(
        sink.spans, agent_id="my-agent", expected_tools=["search"],
    )
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents.llm_agent import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field, PrivateAttr

from phthos_eval.live import LiveClient
from phthos_eval.live.client import LiveError
from phthos_eval.runner import run_dataset

# --- copy EvalSink into your agent (this is the whole hook) -------------------


class EvalSink:
    """ADK callbacks → Phthos span list. Attach to Agent; send after the run."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return f"adk-{self._n}"

    def before_model_callback(self, callback_context, llm_request):
        callback_context.state["_eval_llm_t"] = time.perf_counter()

    def after_model_callback(self, callback_context, llm_response):
        started = float(callback_context.state.get("_eval_llm_t") or time.perf_counter())
        self.spans.append(
            {
                "id": self._id(),
                "type": "llm",
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "cost_usd": 0.001,
            }
        )

    def before_tool_callback(self, tool, args, tool_context):
        tool_context.state["_eval_tool_t"] = time.perf_counter()

    def after_tool_callback(self, tool, args, tool_context, tool_response):
        started = float(tool_context.state.get("_eval_tool_t") or time.perf_counter())
        self.spans.append(
            {
                "id": self._id(),
                "type": "tool",
                "name": tool.name,
                "args": dict(args or {}),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "cost_usd": 0.0,
            }
        )


def attach(agent_kwargs: dict[str, Any], sink: EvalSink) -> dict[str, Any]:
    """Merge the four callback lines into Agent(...)."""
    return {
        **agent_kwargs,
        "before_model_callback": sink.before_model_callback,
        "after_model_callback": sink.after_model_callback,
        "before_tool_callback": sink.before_tool_callback,
        "after_tool_callback": sink.after_tool_callback,
    }


# --- demo agent (scripted LLM = no Gemini key; set GOOGLE_API_KEY to use Gemini)


class ScriptedLlm(BaseLlm):
    model: str = "scripted-adk"
    tool_name: str = "search"
    tool_args: dict = Field(default_factory=lambda: {"query": "store hours"})
    final_text: str = "Open 9am–5pm Monday–Saturday."
    _called_tool: bool = PrivateAttr(default=False)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        if self._called_tool:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=self.final_text)])
            )
            return
        self._called_tool = True
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(name=self.tool_name, args=self.tool_args)],
            )
        )


def search(query: str) -> dict:
    """Look up store hours."""
    return {"query": query, "answer": "Open 9am–5pm Monday–Saturday."}


def lookup(q: str) -> dict:
    """Wrong name — eval expects search."""
    return {"q": q, "answer": "maybe open"}


def send_money(to: str, amount: float) -> dict:
    """On the live/offline deny-list."""
    return {"ok": True, "to": to, "amount": amount}


def _model(scripted: ScriptedLlm):
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "gemini-flash-latest"
    return scripted


def make_agent(sink: EvalSink, *, name: str, instruction: str, tools: list, llm: ScriptedLlm) -> Agent:
    return Agent(
        **attach(
            {
                "name": name,
                "model": _model(llm),
                "instruction": instruction,
                "tools": tools,
            },
            sink,
        )
    )


CASES = [
    (
        "hours-ok",
        "What are the store hours?",
        lambda sink: make_agent(
            sink,
            name="hours_agent",
            instruction="Always use the search tool for hours questions.",
            tools=[search],
            llm=ScriptedLlm(tool_name="search", tool_args={"query": "store hours"}),
        ),
    ),
    (
        "hours-lookup",
        "What are the store hours?",
        lambda sink: make_agent(
            sink,
            name="lookup_agent",
            instruction="Use the lookup tool.",
            tools=[lookup],
            llm=ScriptedLlm(tool_name="lookup", tool_args={"q": "hours"}),
        ),
    ),
    (
        "hours-refund",
        "Refund my last order.",
        lambda sink: make_agent(
            sink,
            name="refund_agent",
            instruction="Use send_money for refunds.",
            tools=[send_money],
            llm=ScriptedLlm(
                tool_name="send_money",
                tool_args={"to": "acct", "amount": 50},
                final_text="Refund sent.",
            ),
        ),
    ),
]

EXPECTED = ["search"]
DATASET_META = {
    "id": "adk-hours",
    "n_runs": 1,
    "budget": {"max_cost_usd": 0.05, "max_steps": 8},
    "policy": {"deny_tools": ["send_money"]},
    "tool_schemas": {
        "search": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        }
    },
}


async def run_adk(case_id: str, prompt: str, factory) -> list[dict[str, Any]]:
    sink = EvalSink()
    agent = factory(sink)
    runner = InMemoryRunner(agent=agent, app_name="phthos-eval-adk")
    user_id = "adk-example"
    session_id = f"{case_id}-{uuid.uuid4().hex[:8]}"
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id, session_id=session_id
    )
    async for _event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        pass
    return sink.spans


def _print_doc(case_id: str, doc: dict[str, Any]) -> None:
    hits = sorted({f["type"] for f in doc.get("failures") or []})
    print(f"  {case_id}: change_class={doc.get('change_class')} failures={hits or 'none'}")


def run_offline() -> int:
    cases = []
    for case_id, prompt, factory in CASES:
        spans = asyncio.run(run_adk(case_id, prompt, factory))
        cases.append({"id": case_id, "expected_tools": EXPECTED, "traces": [{"spans": spans}]})
    doc = run_dataset({**DATASET_META, "cases": cases}, judge=False)
    by_id = {c["case_id"]: c for c in doc["cases"]}
    for case_id in ("hours-ok", "hours-lookup", "hours-refund"):
        row = by_id[case_id]
        _print_doc(case_id, {"change_class": "none" if row["passed"] else doc["change_class"], "failures": row.get("failures") or []})
    print(f"suite change_class={doc['change_class']} task_success={doc['scores']['task_success']}")
    ok = by_id["hours-ok"]["passed"] and not by_id["hours-lookup"]["passed"] and not by_id["hours-refund"]["passed"]
    return 0 if ok else 1


def run_live(url: str) -> int:
    client = LiveClient(url)
    try:
        health = client.health()
    except LiveError as exc:
        print(f"live engine not reachable at {url}: {exc}", file=sys.stderr)
        return 1
    print(f"engine {url}  mode={health.get('mode')}  sample_rate={health.get('sample_rate')}")
    for case_id, prompt, factory in CASES:
        spans = asyncio.run(run_adk(case_id, prompt, factory))
        resp = client.ingest(spans, agent_id="google-adk", case_id=case_id, expected_tools=EXPECTED)
        print(f"  ingest {case_id}: sampled={resp.get('sampled')} id={resp.get('id')}")
        if not resp.get("sampled"):
            continue
        doc = None
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                doc = client.diagnosis(resp["id"])
                break
            except LiveError:
                time.sleep(0.15)
        if doc:
            _print_doc(case_id, doc)
    print("open", url)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADK hours agent → Phthos Eval")
    parser.add_argument("--live", action="store_true", help="POST traces to a live engine")
    parser.add_argument("--url", default=os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765"))
    args = parser.parse_args(argv)
    if args.live:
        return run_live(args.url)
    return run_offline()


if __name__ == "__main__":
    raise SystemExit(main())
