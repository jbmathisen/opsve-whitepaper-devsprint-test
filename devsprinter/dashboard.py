"""Dashboard: the sprint board as a self-contained web page (one HTML file, no dependencies).

Two modes from one renderer:
- Static (`python dashboard.py state.json --out site/index.html`, or `board.py --html …`):
  a read-only page for GitHub Pages or a local file. It reloads itself every minute.
- Interactive (`render(data, app={...})`, used by serve.py on localhost): adds "My work",
  a Start button on every free task that is ready, Release on your own tasks, and a Setup page
  (`render_setup`) with a health check, personal settings and the team's settings.

The page shows each task's state, plan, milestone (25/50/75/100 %) and how long it has been
going, the free tasks and a timeline of the latest events. Everything from GitHub is
HTML-escaped.
"""
import argparse
import html
import json
import statistics
import sys
from pathlib import Path

import config
from board import EVENT_TEXT, event_text, thresholds
from context import span

LABEL = {"active": "Active", "claimed": "Claimed", "quiet": "Quiet", "assigned": "Assigned",
         "waiting": "Waiting", "review": "In review", "changes": "Changes asked", "stale": "Stale",
         "done": "Done"}
ORDER = ["active", "claimed", "quiet", "assigned", "waiting", "review", "changes", "stale", "done"]
PRESET_TEXT = {"short": "Short tasks", "mixed": "Mixed", "long": "Long tasks"}
VIEWS_DOC = "https://github.com/jbmathisen/devsprinter/blob/main/docs/views.md"
CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;
--active:#1f8a4c;--claimed:#1f8a4c;--quiet:#b7791f;--assigned:#7a7a74;--waiting:#b7791f;
--review:#2563eb;--changes:#b7791f;--stale:#c0392b;--done:#6b4fbb;--accent:#2563eb;
--btn:#1d1d1b;--btn-text:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151514;--card:#1f1f1d;
--text:#ecebe6;--muted:#a3a29b;--line:#33332f;--active:#4cc27f;--claimed:#4cc27f;--quiet:#e0a43a;
--assigned:#a3a29b;--waiting:#e0a43a;--review:#6ea0ff;--changes:#e0a43a;
--stale:#ef6b5b;--done:#a58cf0;--accent:#6ea0ff;--btn:#ecebe6;--btn-text:#151514}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:16px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:28px 0 10px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}
.meta{color:var(--muted);font-size:13px}a{color:var(--accent)}
nav{margin-left:auto;display:flex;gap:4px}
nav a{padding:4px 12px;border-radius:999px;text-decoration:none;color:var(--text);font-size:14px}
nav a[aria-current]{background:var(--card);border:1px solid var(--line);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 8px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13px}
.chip b{font-variant-numeric:tabular-nums}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:1px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);
border-radius:10px;padding:12px 14px;min-width:0}
.card .top{display:flex;justify-content:space-between;gap:8px;font-size:13px;color:var(--muted)}
.card .title{font-weight:600;margin:4px 0 6px;overflow-wrap:anywhere}
.pct{font-weight:600;font-variant-numeric:tabular-nums}
.bar{position:relative;height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:6px 0}
.bar i{display:block;height:100%;background:var(--c)}
.bar b{position:absolute;top:0;bottom:0;width:2px;background:var(--card)}
.now{font-size:13px;overflow-wrap:anywhere}.now span{color:var(--muted)}
ul{margin:0;padding:0;list-style:none}
.free li,.events li,.checks li{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:8px 12px;margin-bottom:6px;overflow-wrap:anywhere}
.free li,.checks li{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.free .t,.checks .t{flex:1;min-width:180px}
.tag{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 8px}
.events time{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:8px;font-size:13px}
.empty{color:var(--muted);font-style:italic}
button{font:inherit;font-size:13px;font-weight:600;border-radius:8px;padding:6px 14px;cursor:pointer;
border:1px solid var(--btn);background:var(--btn);color:var(--btn-text)}
button.ghost{background:transparent;color:var(--text);border-color:var(--line)}
button:disabled{opacity:.5;cursor:default}
.card .actions{margin-top:10px}
#msg{display:none;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);
border-radius:10px;padding:12px 14px;margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}
#msg.err{border-left-color:var(--stale)}#msg code{display:block;margin-top:8px;font-size:13px}
.mark{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:13px;font-weight:700;color:#fff;flex:none}
.ok .mark{background:var(--active)}.bad .mark{background:var(--stale)}.info .mark{background:var(--assigned)}
.checks small,.panel small,.hint{color:var(--muted);font-size:13px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;padding:8px 0;border-bottom:1px solid var(--line)}
.row:last-of-type{border-bottom:0}.row>.k{width:220px;max-width:100%;font-weight:600}
.row label{display:inline-flex;align-items:center;gap:6px}
input[type=text],input[type=number]{font:inherit;color:var(--text);background:var(--bg);
border:1px solid var(--line);border-radius:6px;padding:5px 8px;max-width:100%}
input[type=number]{width:96px}input[type=text]{width:320px}
.presets{display:flex;flex-wrap:wrap;gap:8px}
.report{background:var(--bg);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:14px}
.save{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:12px}
pre{background:var(--bg);border-radius:8px;padding:10px 12px;overflow:auto;font-size:13px}
footer{margin-top:32px;color:var(--muted);font-size:12px}
"""
# Interactive mode only. No inline handlers: one listener, a nonce'd script, the token from the URL.
APP_JS = """
const T = new URLSearchParams(location.search).get('t') || '';
document.querySelectorAll('a[data-nav]').forEach(a => { a.href = a.dataset.nav + '?t=' + encodeURIComponent(T); });
let busy = false;
function show(j){const m=document.getElementById('msg');m.className=j.ok?'':'err';m.textContent=j.message||'';
 if(j.command){const c=document.createElement('code');c.textContent=j.command;m.appendChild(c);}
 m.style.display='block';m.scrollIntoView({block:'nearest'});}
function payload(b){
 if (b.dataset.n) return {n: Number(b.dataset.n)};
 const f = b.closest('form'), o = {}; if (!f) return o;
 for (const el of f.elements) { if (!el.name) continue;
  if (el.type === 'checkbox') o[el.name] = el.checked;
  else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
  else if (el.type === 'number') o[el.name] = Number(el.value);
  else o[el.name] = el.value; }
 return o;
}
const BUSY = {start:'Starting…', release:'Releasing…', label:'Creating…'};
document.addEventListener('click', async (ev) => {
 const p = ev.target.closest('button[data-preset]');
 if (p) { const f = p.closest('form'); f.elements.quiet_minutes.value = p.dataset.quiet;
  f.elements.stale_minutes.value = p.dataset.stale; return; }
 const b = ev.target.closest('button[data-act]'); if(!b) return;
 if (b.dataset.confirm && !confirm(b.dataset.confirm)) return;
 busy = true; b.disabled = true; const label = b.textContent;
 b.textContent = BUSY[b.dataset.act] || 'Saving…';
 let j; try { const r = await fetch('/api/' + b.dataset.act, {method:'POST',
   headers:{'Content-Type':'application/json','X-Devsprinter-Token':T},
   body: JSON.stringify(payload(b))}); j = await r.json(); }
 catch (e) { j = {ok:false, message:'No answer from the local Devsprinter server. Is it still running?'}; }
 show(j); b.textContent = label;
 if (j.ok) { setTimeout(() => location.reload(), 2500); } else { b.disabled = false; busy = false; }
});
if (document.body.dataset.page === 'board') {
 setInterval(() => { if (!busy && document.getElementById('msg').style.display !== 'block') location.reload(); }, 30000);
}
"""


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def bar(pct: int) -> str:
    marks = "".join(f'<b style="left:{m}%"></b>' for m in (25, 50, 75))
    return f'<div class="bar"><i style="width:{pct}%"></i>{marks}</div>'


def took_text(r: dict) -> str:
    took = r.get("took")
    if not took or took == "–":
        return ""
    return f"Done in {took}" if r["state"] == "done" else f"Going for {took}"


def card(r: dict, repo: str, action: str = "") -> str:
    pct = r.get("pct")
    if pct is None:  # older state files
        pct = round(100 * r["done"] / r["total"]) if r.get("total") else 0
    link = f"https://github.com/{repo}/issues/{r['n']}"
    has_plan = bool(r.get("total"))
    plan = f'<div class="now"><span>Plan:</span> {esc(r["plan"])}' + \
        (f' · <span class="pct">{pct} %</span>' if has_plan else "") + "</div>"
    now = f'<div class="now"><span>Now:</span> {esc(r["now"])}</div>' if r.get("now") not in (None, "–") else ""
    took = f'<div class="now"><span>Time:</span> {esc(took_text(r))}</div>' if took_text(r) else ""
    return (f'<article class="card" style="--c:var(--{r["state"]})">'
            f'<div class="top"><span><span class="dot" style="background:var(--{r["state"]})"></span>'
            f'{LABEL[r["state"]]} · @{esc(r["who"])}</span><span>{esc(r["when"])}</span></div>'
            f'<div class="title"><a href="{esc(link)}">#{r["n"]}</a> {esc(r["title"])}</div>'
            f'{plan}{bar(pct) if has_plan else ""}{now}{took}{action}</article>')


def is_ready(f: dict, ready_label: str) -> bool:
    if not ready_label:
        return True
    return ready_label.lower() in (lb.lower() for lb in f.get("labels") or [])


def free_item(f: dict, repo: str, app: dict | None) -> str:
    tags = "".join(f'<span class="tag">{esc(lb)}</span>' for lb in f.get("labels") or [])
    link = f'<a href="https://github.com/{esc(repo)}/issues/{f["n"]}">#{f["n"]}</a>'
    action = ""
    if app is not None:
        if is_ready(f, app.get("ready_label", "")):
            action = f'<button data-act="start" data-n="{f["n"]}">Start</button>'
        else:
            action = f'<span class="tag" title="Add the label {esc(app.get("ready_label"))} to make it startable">not ready</span>'
    return f'<li><span class="t">{link} {esc(f["title"])}</span>{tags}{action}</li>'


def page(title: str, body: str, app: dict | None, current: str, repo: str, meta: str) -> str:
    """The shell around both pages: head, header with navigation (interactive only), script."""
    if app is None:
        refresh, script, nav = '<meta http-equiv="refresh" content="60">', "", ""
    else:
        refresh = ""
        script = f'<script nonce="{esc(app.get("nonce", ""))}">{APP_JS}</script>'
        nav = "<nav>" + "".join(
            f'<a data-nav="{path}"' + (' aria-current="page"' if key == current else "") + f">{name}</a>"
            for key, path, name in (("board", "/", "Board"), ("setup", "/setup", "Setup"))) + "</nav>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>{esc(title)}</title><style>{CSS}</style></head>
<body data-page="{current}"><main>
<header><h1>Devsprinter</h1><span class="meta"><a href="https://github.com/{esc(repo)}">{esc(repo)}</a>
{meta}</span>{nav}</header>
{body}
</main>{script}</body></html>
"""


def render(data: dict, app: dict | None = None) -> str:
    """The board page. `app` (interactive mode): {"me": login, "ready_label": str, "nonce": str}."""
    repo = data.get("repo") or ""
    rows = sorted(data.get("rows") or [], key=lambda r: (ORDER.index(r["state"]), r.get("secs") or 0))
    free = data.get("free") or []
    events = list(reversed(data.get("events") or []))[:50]
    counts = {k: sum(r["state"] == k for r in rows) for k in ORDER}
    chips = "".join(f'<span class="chip"><span class="dot" style="background:var(--{k})"></span>'
                    f'{LABEL[k]} <b>{counts[k]}</b></span>' for k in ORDER if counts[k])
    chips += f'<span class="chip">Free <b>{len(free)}</b></span>'
    me = (app or {}).get("me", "").lower()
    mine = [r for r in rows if app is not None and r["who"].lower() == me]
    team = [r for r in rows if r not in mine]
    release = '<div class="actions"><button class="ghost" data-act="release" data-n="{n}">Release</button></div>'
    mine_html = "".join(card(r, repo, release.format(n=r["n"])) for r in mine) or \
        '<p class="empty">You have no task. Pick one under Free and press Start.</p>'
    cards = "".join(card(r, repo) for r in team) or '<p class="empty">Nobody is working on anything right now.</p>'
    free_html = "".join(free_item(f, repo, app) for f in free) or '<li class="empty">Nothing.</li>'
    ev_html = "".join(f'<li><time datetime="{esc(e["ts"])}">{esc(e["ts"][5:16].replace("T", " "))}</time>'
                      f'{esc(event_text(e))}</li>' for e in events if e.get("type") in EVENT_TEXT) \
        or '<li class="empty">No events yet. They appear after the next change.</li>'
    gen = esc((data.get("generated") or "").replace("T", " ").replace("Z", " UTC"))
    if app is None:
        sections = ""
        team_title, foot = "In progress", ("the page reloads itself every minute · "
                                           "take a task with <code>/devsprinter:claim N</code>")
    else:
        sections = f'<div id="msg" role="status"></div><h2>My work (@{esc(app.get("me"))})</h2><div class="grid">{mine_html}</div>'
        team_title = "Team"
        ready = app.get("ready_label")
        foot = ("local dashboard, only reachable from this computer · Start claims the issue, "
                "creates a worktree and opens Claude Code there"
                + (f" · only issues labelled <code>{esc(ready)}</code> can be started" if ready else ""))
    body = f"""<div class="chips">{chips}</div>
{sections}
<h2>{team_title}</h2><div class="grid">{cards}</div>
<h2>Free</h2><ul class="free">{free_html}</ul>
<h2>Recent events</h2><ul class="events">{ev_html}</ul>
<footer>Devsprinter · {esc(thresholds(data.get("team")))} · progress is shown at 25/50/75/100 % · {foot}</footer>"""
    return page(f"Devsprinter · {repo}", body, app, "board", repo, f"· updated {gen}")


# ---------- Setup page ----------

def duration_report(events: list[dict]) -> dict | None:
    """How long finished tasks took, from the done events, and the preset that fits them.

    Stale counts time WITHOUT any signal, not task length: a working agent sends one at least
    every 15 minutes. Long tasks still deserve a longer stale time, because people pause them
    for reviews and meetings; short tasks can be called stale much sooner."""
    took = sorted(e["took_s"] for e in events or []
                  if e.get("type") == "done" and isinstance(e.get("took_s"), (int, float)))
    if not took:
        return None
    median = statistics.median(took)
    preset = "short" if median <= 30 * 60 else "mixed" if median <= 3 * 3600 else "long"
    return {"count": len(took), "median": span(median), "shortest": span(took[0]),
            "longest": span(took[-1]), "preset": preset}


def check_item(c: dict) -> str:
    mark = {True: ("ok", "✓"), False: ("bad", "!"), None: ("info", "i")}[c.get("ok")]
    action = ""
    if c.get("act"):
        a = c["act"]
        action = (f'<button class="ghost" data-act="{esc(a["act"])}" data-confirm="{esc(a.get("confirm", ""))}">'
                  f'{esc(a["label"])}</button>')
    elif c.get("link"):
        href, text = c["link"]
        action = f'<a href="{esc(href)}">{esc(text)}</a>'
    return (f'<li class="{mark[0]}"><span class="mark">{mark[1]}</span>'
            f'<span class="t"><b>{esc(c["title"])}</b><br><small>{esc(c.get("detail", ""))}</small></span>'
            f'{action}</li>')


def radio(name: str, value: str, current: str, text: str) -> str:
    on = " checked" if value == current else ""
    return f'<label><input type="radio" name="{name}" value="{esc(value)}"{on}> {esc(text)}</label>'


def checkbox(name: str, on: bool, text: str) -> str:
    return f'<label><input type="checkbox" name="{name}"{" checked" if on else ""}> {esc(text)}</label>'


def env_note(info: dict, name: str) -> str:
    var = (info.get("overrides") or {}).get(name)
    return f'<small>Set by {esc(var)} in your environment, which wins over this.</small>' if var else ""


def render_setup(info: dict, app: dict) -> str:
    """The Setup page. `info` comes from serve.App.setup_info()."""
    repo = info.get("repo") or ""
    local = config.clean_local(info.get("local"))
    team = config.clean_team(info.get("team"))
    checks = "".join(check_item(c) for c in info.get("checks") or [])

    mine = f"""<form class="panel" id="local">
<div class="row"><span class="k">Progress updates</span>
{radio("signal", "milestones", local["signal"], "At 25, 50, 75 and 100 %")}
{radio("signal", "steps", local["signal"], "On every step")}{env_note(info, "signal")}</div>
<div class="row"><span class="k">Share my progress</span>
{checkbox("push", local["push"], "Send my progress to the issue on GitHub")}{env_note(info, "push")}</div>
<div class="row"><span class="k">Collision warnings</span>
{checkbox("context", local["context"], "Tell my agent when a task is already taken")}{env_note(info, "context")}</div>
<div class="row"><span class="k">Start opens</span>
{radio("launch", "auto", local["launch"], "A terminal with Claude Code")}
{radio("launch", "none", local["launch"], "Nothing, just show the command")}</div>
<div class="row"><span class="k">Worktrees folder</span>
<input type="text" name="worktrees" value="{esc(local["worktrees"])}" placeholder="{esc(info.get("worktrees_default", ""))}">
<small>Empty = next to your clone</small></div>
<div class="save"><button type="button" data-act="settings">Save my settings</button>
<small>Saved in ~/.devsprinter/config.json on this computer only. Your hooks use it from their next run.</small></div>
</form>"""

    report = info.get("report")
    if report:
        suggested = config.PRESETS[report["preset"]]
        report_html = (f'<div class="report"><b>How long your tasks take:</b> {report["count"]} finished, '
                       f'median {esc(report["median"])}, shortest {esc(report["shortest"])}, '
                       f'longest {esc(report["longest"])}. Suggested: <b>{PRESET_TEXT[report["preset"]]}</b> '
                       f'(quiet {span(suggested[0] * 60)}, stale {span(suggested[1] * 60)}).</div>')
    else:
        report_html = ('<div class="report">No finished tasks yet. Once a few are done, this shows how '
                       'long they took and suggests the times that fit.</div>')
    presets = "".join(
        f'<button type="button" class="ghost" data-preset="{key}" data-quiet="{q}" data-stale="{s}">'
        f'{PRESET_TEXT[key]} · quiet {span(q * 60)}, stale {span(s * 60)}</button>'
        for key, (q, s) in config.PRESETS.items())
    source = (f"Now read from <code>{config.TEAM_FILE}</code> in {esc(repo)}." if info.get("team_found")
              else f"No <code>{config.TEAM_FILE}</code> in {esc(repo)} yet, so the defaults apply.")
    label_note = ""
    if info.get("ready_label_source") not in (None, "team"):
        label_note = (f'<small>This dashboard currently uses the label <code>{esc(info.get("ready_label"))}</code> '
                      f'from {esc(info["ready_label_source"])}.</small>')
    confirm = (f"Commit {config.TEAM_FILE} to the default branch of {repo} with your GitHub login? "
               "Everyone on the team gets these times.")
    team_html = f"""<form class="panel" id="team">
<p class="hint">Quiet and stale count the time since the agent's last signal, not how long the task is.
A working agent signals at every milestone and at least every 15 minutes, so a long task is not
marked stale while it runs. Pick shorter times if your tasks are small and a silent agent means
someone has left; longer ones if people often pause tasks for reviews or meetings.</p>
{report_html}
<div class="row"><span class="k">Presets</span><div class="presets">{presets}</div></div>
<div class="row"><span class="k">Quiet after</span>
<input type="number" name="quiet_minutes" min="1" max="{config.MAX_MINUTES - 1}" value="{team["quiet_minutes"]}"> minutes</div>
<div class="row"><span class="k">Stale after</span>
<input type="number" name="stale_minutes" min="2" max="{config.MAX_MINUTES}" value="{team["stale_minutes"]}"> minutes</div>
<div class="row"><span class="k">Ready label</span>
<input type="text" name="ready_label" value="{esc(team["ready_label"])}" placeholder="empty = any free issue">
{label_note}</div>
<div class="save"><button type="button" data-act="team" data-confirm="{esc(confirm)}">Save to repo</button>
<small>{source} Needs write access to the repo.</small></div>
<details><summary class="hint">Or add the file yourself</summary>
<pre>{esc(config.team_text(team))}</pre></details>
</form>"""

    views = f"""<ul class="checks">
<li class="info"><span class="mark">i</span><span class="t"><b>Feed to Discord or Slack</b><br>
<small>Add the secret DEVSPRINTER_DISCORD_WEBHOOK or DEVSPRINTER_SLACK_WEBHOOK to the repo. Webhooks are
never entered here.</small></span><a href="https://github.com/{esc(repo)}/settings/secrets/actions">Repo secrets</a></li>
<li class="info"><span class="mark">i</span><span class="t"><b>GitHub Projects board and a public page</b><br>
<small>Set the variables DEVSPRINTER_PROJECT or DEVSPRINTER_PAGES. See the guide.</small></span>
<a href="https://github.com/{esc(repo)}/settings/variables/actions">Repo variables</a>
<a href="{VIEWS_DOC}">Guide</a></li></ul>"""

    body = f"""<div id="msg" role="status"></div>
<h2>Health check</h2><ul class="checks">{checks}</ul>
<h2>My settings</h2>{mine}
<h2>Team settings</h2>{team_html}
<h2>Optional views</h2>{views}
<footer>Devsprinter · signed in to GitHub as @{esc(app.get("me"))} · settings for {esc(repo)}</footer>"""
    return page(f"Devsprinter setup · {repo}", body, app, "setup", repo, "· setup")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", help="the file from board.py --state-out")
    ap.add_argument("--out", default="site/index.html")
    args = ap.parse_args()
    data = json.loads(Path(args.state).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"Dashboard: {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
