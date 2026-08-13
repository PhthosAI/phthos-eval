"""Minimal live UI — pass rate, cost, policy hits, diagnosis JSON. No editor."""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Phthos Eval — live</title>
  <style>
    :root { color-scheme: light dark; --fg: CanvasText; --muted: gray; --line: color-mix(in srgb, CanvasText 18%, Canvas); --acc: #0b6; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 15px/1.45 system-ui, sans-serif; color: var(--fg); background: Canvas; }
    header { padding: 1.25rem 1.5rem 0.75rem; border-bottom: 1px solid var(--line); }
    h1 { font-size: 1.15rem; font-weight: 650; margin: 0 0 0.25rem; }
    .sub { color: var(--muted); font-size: 0.9rem; }
    main { display: grid; grid-template-columns: minmax(16rem, 22rem) 1fr; min-height: calc(100vh - 4.5rem); }
    .stats { display: flex; gap: 1.25rem; flex-wrap: wrap; padding: 1rem 1.5rem; border-bottom: 1px solid var(--line); }
    .stat b { display: block; font-size: 1.35rem; font-variant-numeric: tabular-nums; }
    .stat span { color: var(--muted); font-size: 0.8rem; }
    aside { border-right: 1px solid var(--line); overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--line); }
    tr { cursor: pointer; }
    tr.active { outline: 2px solid var(--acc); outline-offset: -2px; }
    .fail { color: #c40; }
    .pass { color: var(--acc); }
    section { padding: 1rem 1.25rem; overflow: auto; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; }
    button { font: inherit; padding: 0.35rem 0.7rem; cursor: pointer; }
    .row { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.75rem; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Phthos Eval — live</h1>
    <p class="sub">Sampled production scores on this machine. No prompt editor. No auto-fix.</p>
  </header>
  <div class="stats" id="stats"></div>
  <main>
    <aside>
      <table>
        <thead><tr><th>Run</th><th>Pass</th><th>Class</th></tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </aside>
    <section>
      <div class="row">
        <strong id="title">Pick a sampled run</strong>
        <button type="button" id="export" hidden>Save to offline dataset</button>
      </div>
      <pre id="json"></pre>
    </section>
  </main>
  <script>
    let selected = null;
    async function load() {
      const s = await (await fetch("/v1/scores")).json();
      const pct = s.pass_rate == null ? "—" : Math.round(s.pass_rate * 100) + "%";
      document.getElementById("stats").innerHTML = [
        ["Pass rate", pct],
        ["Cost (USD)", (s.cost || 0).toFixed(4)],
        ["Policy hits", String(s.policy_hits || 0)],
        ["Sampled / received", (s.sampled || 0) + " / " + (s.received || 0)],
        ["Sample rate", Math.round((s.sample_rate || 0) * 100) + "%"],
        ["Judge", s.judge || "off"],
      ].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
      const tb = document.getElementById("rows");
      tb.innerHTML = (s.runs || []).map(r =>
        `<tr data-id="${r.id}" class="${r.id===selected?"active":""}">
          <td>${r.id.slice(0,8)}</td>
          <td class="${r.passed?"pass":"fail"}">${r.passed?"yes":"no"}</td>
          <td>${r.change_class || ""}</td>
        </tr>`
      ).join("");
      tb.querySelectorAll("tr").forEach(tr => tr.onclick = () => openRun(tr.dataset.id));
    }
    async function openRun(id) {
      selected = id;
      const doc = await (await fetch("/v1/diagnoses/" + id)).json();
      document.getElementById("title").textContent = id;
      document.getElementById("json").textContent = JSON.stringify(doc, null, 2);
      const btn = document.getElementById("export");
      btn.hidden = false;
      btn.onclick = async () => {
        const r = await fetch("/v1/diagnoses/" + id + "/export", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
        const body = await r.json();
        btn.textContent = r.ok ? "Saved " + body.path : "Export failed";
      };
      load();
    }
    load();
    setInterval(load, 3000);
  </script>
</body>
</html>
"""
