# Agent integration examples

One folder per framework, then **lib** (offline) and **live** (engine). Same wrap call for every stack. Eval does not apply a fix.

```text
agent_integration_examples/
  <framework>/
    requirements.txt
    lib/     wrap → run → diagnose
    live/    wrap → run → ingest
```

```python
from phthos_eval import TraceSink

sink = TraceSink()
agent = sink.wrap(agent)  # framework still runs the agent
# run as usual
doc = sink.diagnose(expected_tools=["search"])           # lib
sink.ingest(client, agent_id="my-agent", expected_tools=["search"])  # live
```

`TraceSink.frameworks` is the adapter list. Unknown stack: `sink.add_llm` / `sink.add_tool`, or OpenTelemetry OpenInference to `POST /v1/otel/traces`.
