from __future__ import annotations

from phthos_eval.live.client import LiveClient

# First trace of each fixtures/dataset.json case — kept here so live-demo
# works after pip install without the repo tree.
DEMO = [
    {
        "case_id": "pass-search",
        "expected_tools": ["search"],
        "spans": [
            {"id": "p0-s0", "type": "llm", "latency_ms": 80, "cost_usd": 0.001},
            {
                "id": "p0-s1",
                "type": "tool",
                "name": "search",
                "args": {"query": "store hours"},
                "latency_ms": 40,
                "cost_usd": 0.0,
            },
            {"id": "p0-s2", "type": "llm", "latency_ms": 60, "cost_usd": 0.001},
        ],
    },
    {
        "case_id": "fail-wrong-tool",
        "expected_tools": ["search"],
        "spans": [
            {
                "id": "w0-s0",
                "type": "tool",
                "name": "lookup",
                "args": {"q": "hours"},
                "latency_ms": 20,
                "cost_usd": 0.0,
            }
        ],
    },
    {
        "case_id": "fail-budget",
        "expected_tools": ["search"],
        "spans": [
            {
                "id": "b0-s0",
                "type": "tool",
                "name": "search",
                "args": {"query": "everything"},
                "latency_ms": 4000,
                "cost_usd": 0.8,
            }
        ],
    },
    {
        "case_id": "fail-policy",
        "expected_tools": ["search"],
        "spans": [
            {
                "id": "y0-s0",
                "type": "tool",
                "name": "send_money",
                "args": {"to": "acct", "amount": 50},
                "latency_ms": 15,
                "cost_usd": 0.0,
            }
        ],
    },
    {
        "case_id": "fail-loop",
        "expected_tools": ["search"],
        "spans": [
            {
                "id": "l0-s0",
                "type": "tool",
                "name": "search",
                "args": {"query": "x"},
                "latency_ms": 10,
                "cost_usd": 0.001,
            },
            {
                "id": "l0-s1",
                "type": "tool",
                "name": "search",
                "args": {"query": "x"},
                "latency_ms": 10,
                "cost_usd": 0.001,
            },
            {
                "id": "l0-s2",
                "type": "tool",
                "name": "search",
                "args": {"query": "x"},
                "latency_ms": 10,
                "cost_usd": 0.001,
            },
        ],
    },
]


def run_demo(url: str, api_key: str | None = None) -> int:
    client = LiveClient(url, api_key=api_key)
    health = client.health()
    print(f"engine {url}  sample_rate={health.get('sample_rate')}  judge={health.get('judge')}")
    for item in DEMO:
        resp = client.ingest(
            item["spans"],
            agent_id="demo",
            case_id=item["case_id"],
            expected_tools=item["expected_tools"],
        )
        print(f"  {item['case_id']}: accepted sampled={resp['sampled']} id={resp['id']}")
    print("poll GET /v1/scores  and  GET /v1/diagnoses/{id}")
    print("open", url)
    return 0
