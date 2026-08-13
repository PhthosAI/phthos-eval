from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "agent_integration_examples"


def test_google_adk_examples_are_wrap_only() -> None:
    adk = EXAMPLES / "google_adk"
    req = (adk / "requirements.txt").read_text(encoding="utf-8")
    assert "google-adk" in req and "ddgs" in req and "phthos-eval" in req
    lib = (adk / "lib" / "agent.py").read_text(encoding="utf-8")
    live = (adk / "live" / "agent.py").read_text(encoding="utf-8")
    for src in (lib, live):
        assert "sink.wrap(" in src
        assert "class EvalSink" not in src
        assert "tool_schemas" not in src
        assert "requirements.txt" in src
        assert src.count("\n") < 80


def test_each_framework_folder_has_lib_live_and_requirements() -> None:
    folders = sorted(p for p in EXAMPLES.iterdir() if p.is_dir())
    assert {p.name for p in folders} >= {
        "google_adk",
        "langchain",
        "langgraph",
        "crewai",
        "openai_agents",
        "llama_index",
        "pydantic_ai",
        "autogen",
        "microsoft_agent_framework",
        "semantic_kernel",
        "smolagents",
        "agno",
        "haystack",
        "dspy",
        "camel",
        "strands",
        "langroid",
        "letta",
        "atomic_agents",
        "beeai",
        "livekit_agents",
    }
    for folder in folders:
        req = folder / "requirements.txt"
        lib = folder / "lib" / "agent.py"
        live = folder / "live" / "agent.py"
        readme = folder / "README.md"
        assert req.is_file(), folder
        assert "phthos-eval" in req.read_text(encoding="utf-8")
        assert lib.is_file() and live.is_file() and readme.is_file()
        for src in (lib.read_text(encoding="utf-8"), live.read_text(encoding="utf-8")):
            assert "sink.wrap(" in src
            assert "class EvalSink" not in src
            assert "requirements.txt" in src
        assert "pip install -r" in readme.read_text(encoding="utf-8")
