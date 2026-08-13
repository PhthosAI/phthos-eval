"""Live UI — self-host scores view, plus hosted login and tenant dashboard. No editor."""

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
        ["Gold", s.gold_stale ? "stale" : "current"],
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

AUTH_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Phthos Eval — sign in</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; font: 15px/1.45 system-ui, sans-serif; display: grid; place-items: center; min-height: 100vh; }
    form { width: min(22rem, 92vw); display: grid; gap: 0.55rem; }
    h1 { font-size: 1.15rem; margin: 0 0 0.25rem; }
    .sub, .err { color: gray; font-size: 0.9rem; }
    .err { color: #c40; }
    input { font: inherit; padding: 0.45rem 0.55rem; }
    button { font: inherit; padding: 0.5rem 0.7rem; cursor: pointer; }
    a { color: inherit; }
  </style>
</head>
<body>
  <form id="f">
    <h1>Phthos Eval</h1>
    <p class="sub">Hosted live + offline eval. Same engine as OSS. No prompt editor. No auto-fix.</p>
    <input name="email" type="email" required placeholder="email" autocomplete="username"/>
    <input name="password" type="password" required minlength="8" placeholder="password (8+)" autocomplete="current-password"/>
    <input name="workspace" placeholder="workspace name (sign up only)"/>
    <button type="submit" id="login">Sign in</button>
    <button type="button" id="signup">Create workspace</button>
    <p class="err" id="err"></p>
    <p class="sub">Self-host without accounts: run <code>phthos-eval live</code> (omit <code>--hosted</code>).</p>
    <p class="sub"><a href="/sso/saml/login">Sign in with SSO (SAML)</a> — Pro cloud overlay.</p>
  </form>
  <script>
    const err = document.getElementById("err");
    async function post(path, body) {
      const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.status);
      return data;
    }
    document.getElementById("f").onsubmit = async (e) => {
      e.preventDefault();
      err.textContent = "";
      const fd = new FormData(e.target);
      try {
        await post("/v1/login", {email: fd.get("email"), password: fd.get("password")});
        location.href = "/";
      } catch (ex) { err.textContent = ex.message; }
    };
    document.getElementById("signup").onclick = async () => {
      err.textContent = "";
      const fd = new FormData(document.getElementById("f"));
      try {
        const data = await post("/v1/signup", {
          email: fd.get("email"), password: fd.get("password"),
          workspace_name: fd.get("workspace") || "workspace",
        });
        sessionStorage.setItem("phthos_api_key", data.api_key || "");
        location.href = "/";
      } catch (ex) { err.textContent = ex.message; }
    };
  </script>
</body>
</html>
"""

HOSTED_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Phthos Eval — hosted</title>
  <style>
    :root { color-scheme: light dark; --fg: CanvasText; --muted: gray; --line: color-mix(in srgb, CanvasText 18%, Canvas); --acc: #0b6; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 15px/1.45 system-ui, sans-serif; color: var(--fg); background: Canvas; }
    header { padding: 1rem 1.5rem; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
    h1 { font-size: 1.15rem; font-weight: 650; margin: 0; }
    .sub { color: var(--muted); font-size: 0.85rem; margin: 0.2rem 0 0; }
    nav { display: flex; gap: 0.5rem; padding: 0.6rem 1.5rem; border-bottom: 1px solid var(--line); }
    nav button { font: inherit; padding: 0.3rem 0.65rem; cursor: pointer; }
    nav button.on { outline: 2px solid var(--acc); }
    .stats { display: flex; gap: 1.25rem; flex-wrap: wrap; padding: 1rem 1.5rem; }
    .stat b { display: block; font-size: 1.35rem; font-variant-numeric: tabular-nums; }
    .stat span { color: var(--muted); font-size: 0.8rem; }
    main { display: grid; grid-template-columns: minmax(16rem, 24rem) 1fr; min-height: 50vh; }
    aside { border-right: 1px solid var(--line); overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--line); }
    tr { cursor: pointer; }
    tr.active { outline: 2px solid var(--acc); outline-offset: -2px; }
    .fail { color: #c40; } .pass { color: var(--acc); }
    section { padding: 1rem 1.25rem; overflow: auto; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; }
    button, input { font: inherit; padding: 0.35rem 0.7rem; }
    .row { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
    .panel { padding: 1rem 1.5rem; display: none; }
    .panel.on { display: block; }
    .warn { background: color-mix(in srgb, #0b6 12%, Canvas); padding: 0.6rem 0.8rem; margin: 0 1.5rem 1rem; }
    label { display: grid; gap: 0.2rem; margin-bottom: 0.6rem; max-width: 28rem; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Phthos Eval</h1>
      <p class="sub" id="who">Hosted tenant. Same scorers as OSS. No auto-fix.</p>
    </div>
    <div class="row">
      <button type="button" id="bundle">Export all</button>
      <button type="button" id="out">Sign out</button>
    </div>
  </header>
  <p class="warn" id="keybox" hidden></p>
  <nav>
    <button type="button" class="on" data-tab="live">Live</button>
    <button type="button" data-tab="history">History</button>
    <button type="button" data-tab="datasets">Datasets</button>
    <button type="button" data-tab="alerts">Alerts</button>
    <button type="button" data-tab="plan">Plan</button>
    <button type="button" data-tab="team">Team</button>
    <button type="button" data-tab="usage">Usage</button>
  </nav>
  <div class="stats" id="stats"></div>
  <div id="live" class="panel on">
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
  </div>
  <div id="history" class="panel">
    <table>
      <thead><tr><th>When</th><th>Run</th><th>Pass</th><th>Class</th><th>Cost</th></tr></thead>
      <tbody id="hist"></tbody>
    </table>
  </div>
  <div id="datasets" class="panel">
    <div class="row">
      <input type="file" id="dsfile" accept="application/json,.json"/>
      <input id="dsname" placeholder="name"/>
      <button type="button" id="dsup">Upload</button>
    </div>
    <table>
      <thead><tr><th>Name</th><th>Id</th><th></th></tr></thead>
      <tbody id="dslist"></tbody>
    </table>
    <pre id="dsout"></pre>
  </div>
  <div id="alerts" class="panel">
    <form id="af">
      <label>Webhook URL <input name="webhook_url" placeholder="https://…"/></label>
      <label>Alert email <input name="alert_email" type="email"/></label>
      <label>Min pass rate <input name="min_pass_rate" type="number" min="0" max="1" step="0.05" value="0.8"/></label>
      <button type="submit">Save alerts</button>
    </form>
    <p class="sub">Fires when pass rate crosses below the threshold. Email needs SMTP on the host. Eval still does not apply a fix.</p>
    <pre id="alog"></pre>
  </div>
  <div id="plan" class="panel">
    <p class="sub">Scorers and the diagnosis schema are free on every plan. Paid is ops: retention, SAML, hosted judges, seats.</p>
    <pre id="planout"></pre>
    <p><a href="/billing">Billing (cloud overlay)</a></p>
  </div>
  <div id="team" class="panel">
    <form id="inv">
      <label>Email <input name="email" type="email" required/></label>
      <label>Password <input name="password" type="password" minlength="8" required/></label>
      <label>Role
        <select name="role">
          <option value="viewer">viewer</option>
          <option value="member" selected>member</option>
          <option value="admin">admin</option>
        </select>
      </label>
      <button type="submit">Invite</button>
    </form>
    <pre id="teamout"></pre>
  </div>
  <div id="usage" class="panel">
    <pre id="usageout"></pre>
  </div>
  <script>
    let selected = null;
    const key = sessionStorage.getItem("phthos_api_key");
    if (key) {
      const box = document.getElementById("keybox");
      box.hidden = false;
      box.textContent = "API key (shown once): " + key + "  — send as Authorization: Bearer. Traces stay on this host; BYOK judge is optional and off by default.";
      sessionStorage.removeItem("phthos_api_key");
    }
    async function api(path, opts) {
      const r = await fetch(path, opts);
      if (r.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.status);
      return data;
    }
    document.querySelectorAll("nav button").forEach(btn => btn.onclick = () => {
      document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b===btn));
      document.querySelectorAll(".panel").forEach(p => p.classList.toggle("on", p.id===btn.dataset.tab));
    });
    async function load() {
      const me = await api("/v1/me");
      document.getElementById("who").textContent = (me.email || "") + " · " + (me.workspace_name || me.workspace_id);
      const s = await api("/v1/scores?limit=200");
      const pct = s.pass_rate == null ? "—" : Math.round(s.pass_rate * 100) + "%";
      document.getElementById("stats").innerHTML = [
        ["Pass rate", pct], ["Cost (USD)", (s.cost || 0).toFixed(4)],
        ["Policy hits", String(s.policy_hits || 0)],
        ["Sampled / received", (s.sampled || 0) + " / " + (s.received || 0)],
        ["Sample rate", Math.round((s.sample_rate || 0) * 100) + "%"],
        ["Judge", s.judge || "off"],
        ["Gold", s.gold_stale ? "stale" : "current"],
      ].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
      const tb = document.getElementById("rows");
      tb.innerHTML = (s.runs || []).map(r =>
        `<tr data-id="${r.id}" class="${r.id===selected?"active":""}">
          <td>${r.id.slice(0,8)}</td>
          <td class="${r.passed?"pass":"fail"}">${r.passed?"yes":"no"}</td>
          <td>${r.change_class || ""}</td>
        </tr>`).join("");
      tb.querySelectorAll("tr").forEach(tr => tr.onclick = () => openRun(tr.dataset.id));
      document.getElementById("hist").innerHTML = (s.runs || []).map(r =>
        `<tr><td>${(r.created_at||"").slice(0,19)}</td><td>${r.id.slice(0,8)}</td>
         <td class="${r.passed?"pass":"fail"}">${r.passed?"yes":"no"}</td>
         <td>${r.change_class||""}</td><td>${r.cost==null?"":r.cost}</td></tr>`).join("");
      const ds = await api("/v1/datasets");
      document.getElementById("dslist").innerHTML = (ds.datasets || []).map(d =>
        `<tr><td>${d.name}</td><td>${d.id.slice(0,8)}</td>
         <td><button data-run="${d.id}">Run</button> <button data-get="${d.id}">Download</button></td></tr>`).join("");
      document.querySelectorAll("[data-run]").forEach(b => b.onclick = () => runDs(b.dataset.run));
      document.querySelectorAll("[data-get]").forEach(b => b.onclick = () => getDs(b.dataset.get));
      const al = await api("/v1/alerts");
      const f = document.getElementById("af");
      f.webhook_url.value = al.webhook_url || "";
      f.alert_email.value = al.alert_email || "";
      f.min_pass_rate.value = al.min_pass_rate == null ? 0.8 : al.min_pass_rate;
      document.getElementById("alog").textContent = JSON.stringify(al.recent || [], null, 2);
      const plan = await api("/v1/plan");
      document.getElementById("planout").textContent = JSON.stringify(plan, null, 2);
      const mem = await api("/v1/members");
      document.getElementById("teamout").textContent = JSON.stringify(mem.members || [], null, 2);
      const usage = await api("/v1/usage");
      document.getElementById("usageout").textContent = JSON.stringify(usage, null, 2);
    }
    async function openRun(id) {
      selected = id;
      const doc = await api("/v1/diagnoses/" + id);
      document.getElementById("title").textContent = id;
      document.getElementById("json").textContent = JSON.stringify(doc, null, 2);
      const btn = document.getElementById("export");
      btn.hidden = false;
      btn.onclick = async () => {
        const body = await api("/v1/diagnoses/" + id + "/export", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
        btn.textContent = "Saved " + body.path;
      };
      load();
    }
    async function runDs(id) {
      const doc = await api("/v1/datasets/" + id + "/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
      document.getElementById("dsout").textContent = JSON.stringify(doc, null, 2);
      load();
    }
    async function getDs(id) {
      const doc = await api("/v1/datasets/" + id);
      const blob = new Blob([JSON.stringify(doc.body, null, 2)], {type:"application/json"});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (doc.name || "dataset") + ".json";
      a.click();
    }
    document.getElementById("dsup").onclick = async () => {
      const file = document.getElementById("dsfile").files[0];
      if (!file) return;
      const body = JSON.parse(await file.text());
      await api("/v1/datasets", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({name: document.getElementById("dsname").value || file.name, dataset: body})});
      load();
    };
    document.getElementById("af").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await api("/v1/alerts", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({
        webhook_url: fd.get("webhook_url"), alert_email: fd.get("alert_email"),
        min_pass_rate: Number(fd.get("min_pass_rate")),
      })});
      load();
    };
    document.getElementById("inv").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await api("/v1/members", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({
        email: fd.get("email"), password: fd.get("password"), role: fd.get("role"),
      })});
      load();
    };
    document.getElementById("bundle").onclick = async () => {
      const doc = await api("/v1/export");
      const blob = new Blob([JSON.stringify(doc, null, 2)], {type:"application/json"});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "phthos-eval-export.json";
      a.click();
    };
    document.getElementById("out").onclick = async () => {
      await fetch("/v1/logout", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
      location.href = "/login";
    };
    load();
    setInterval(load, 8000);
  </script>
</body>
</html>
"""
