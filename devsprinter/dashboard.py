"""Dashboard: the sprint board as a self-contained web page (one HTML file, no dependencies).

Two modes from one renderer:
- Static (`python dashboard.py state.json --out site/index.html`, `board.py --html …`, or
  `sprint.py dashboard` for a local snapshot): a read-only page. Except as a snapshot it reloads
  itself every minute.
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
:root{--ground:#f4f3ef;--surface:#fff;--ink:#17191c;--muted:#5d6168;--line:#e2e0da;--soft:#efede8;
--shell:#15233b;--shell-ink:#f3f1ea;--shell-muted:#aeb7c6;--shell-line:#2a3a56;
--free:#2f7d4f;--progress:#2a5bd7;--waiting:#a86a12;--review:#0f7a86;--done:#6b7280;--stale:#c0392b;
--accent:#2a5bd7;--btn:#15233b;--btn-text:#fff;--focus:#2a5bd7;
--active:var(--progress);--claimed:var(--progress);--quiet:var(--waiting);--assigned:var(--done);
--changes:var(--waiting);--card:var(--surface);--text:var(--ink);--bg:var(--ground)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ground:#111317;--surface:#1a1d22;
--ink:#e9e7e1;--muted:#a3a7ae;--line:#2b2f36;--soft:#22262c;--shell:#0c1422;--shell-ink:#eef0f3;
--shell-muted:#8d99ad;--shell-line:#1f2b40;--free:#5cb985;--progress:#7aa2ff;--waiting:#e0a548;
--review:#4fc1cc;--done:#9aa1ab;--stale:#ef7466;--accent:#7aa2ff;--btn:#e9e7e1;--btn-text:#111317;--focus:#7aa2ff}}
*{box-sizing:border-box}
html{scrollbar-color:var(--line) transparent}
body{margin:0;background:var(--ground);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
min-height:100dvh;display:flex;flex-direction:column}
::selection{background:color-mix(in srgb,var(--accent) 25%,transparent)}
a{color:var(--accent);text-underline-offset:2px}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}
.num,.count,time,.pct,.when{font-variant-numeric:tabular-nums}
ul{margin:0;padding:0;list-style:none}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* shell */
.shell{background:var(--shell);color:var(--shell-ink)}
.shell-in{max-width:1600px;margin:0 auto;padding:14px 20px 0}
.brand{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px}
.brand h1{font-size:17px;margin:0;letter-spacing:-.01em}
.brand .meta{color:var(--shell-muted);font-size:13px}.brand .meta a{color:var(--shell-ink)}
nav.pages{margin-left:auto;display:flex;gap:4px}
nav.pages a{padding:4px 12px;border-radius:999px;text-decoration:none;color:var(--shell-muted);font-size:13px}
nav.pages a[aria-current]{background:var(--shell-line);color:var(--shell-ink);font-weight:600}

/* the flow strip: the sprint as a flow, and on a phone the lane tabs */
.flow{display:flex;gap:2px;margin-top:14px;overflow-x:auto;scrollbar-width:none}
.flow label{flex:1 1 0;min-width:96px;display:flex;flex-direction:column;gap:2px;padding:8px 12px 10px;
color:var(--shell-muted);cursor:default;border-radius:8px 8px 0 0;position:relative}
.flow label b{font-size:22px;line-height:1.1;color:var(--shell-ink);font-weight:650}
.flow label span{font-size:12.5px;display:flex;align-items:center;gap:6px;white-space:nowrap}
.flow label::after{content:"";position:absolute;left:12px;right:12px;bottom:0;height:3px;border-radius:3px 3px 0 0;background:var(--c)}
.flow label+label::before{content:"";position:absolute;left:-5px;top:20px;width:7px;height:7px;
border-top:1.5px solid var(--shell-line);border-right:1.5px solid var(--shell-line);transform:rotate(45deg)}
.mix{display:flex;height:4px;background:var(--shell-line)}
.mix i{display:block;height:100%;background:var(--c)}

/* layout */
main{flex:1;min-height:0;width:100%;max-width:1600px;margin:0 auto;padding:16px 20px 12px;display:flex;flex-direction:column;gap:14px}
.layout{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px}
.board{display:grid;grid-template-columns:repeat(5,minmax(180px,1fr));gap:12px;min-height:0;overflow-x:auto}
.lane{display:flex;flex-direction:column;min-height:0;background:var(--soft);border-radius:12px}
.lane>header{display:flex;align-items:center;gap:8px;padding:10px 12px 8px;font-weight:600;font-size:13.5px}
.lane>header .count{margin-left:auto;color:var(--muted);font-weight:500}
.lane .items{flex:1;min-height:0;overflow-y:auto;padding:0 8px 10px;display:flex;flex-direction:column;gap:8px;
scrollbar-width:thin}
.dot{width:8px;height:8px;border-radius:50%;background:var(--c);flex:none;display:inline-block}

.item{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0;
display:flex;flex-direction:column;gap:6px;transition:border-color .15s,box-shadow .15s}
.item:hover{border-color:color-mix(in srgb,var(--c) 45%,var(--line));box-shadow:0 2px 8px -4px rgb(0 0 0/.18)}
.item .top{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted)}
.item .top .num{color:var(--muted);text-decoration:none;font-weight:600}
.item .top .when{margin-left:auto}
.item .title{color:var(--ink);text-decoration:none;font-weight:600;line-height:1.35;overflow-wrap:anywhere}
.item .title:hover{text-decoration:underline}
.item .note{font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
.item .note b{color:var(--ink);font-weight:600}
.who{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink)}
.av{width:20px;height:20px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:9.5px;font-weight:700;font-style:normal;color:#fff;background:hsl(var(--h) 45% 42%);flex:none;letter-spacing:.02em}
.badge{font-size:11.5px;font-weight:600;padding:1px 7px;border-radius:999px;color:var(--c);
background:color-mix(in srgb,var(--c) 12%,transparent)}
.tags{display:flex;flex-wrap:wrap;gap:4px}
.tag{font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:0 7px}
.bar{position:relative;height:6px;background:var(--soft);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--c)}
.bar b{position:absolute;top:0;bottom:0;width:2px;background:var(--surface)}
.pct{font-weight:600;color:var(--ink)}
.empty{color:var(--muted);font-size:13px;padding:6px 4px}
details.later{margin-top:4px}
details.later summary{cursor:pointer;color:var(--muted);font-size:12.5px;padding:4px 4px;list-style-position:inside}
details.later .items{padding:6px 0 0;overflow:visible}

/* rail */
.rail{display:flex;flex-direction:column;gap:14px;min-height:0;overflow-y:auto;scrollbar-width:thin}
.rail section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.rail h2{font-size:13.5px;margin:0 0 8px;display:flex;align-items:center;gap:8px}
.rail h2 .count{margin-left:auto;color:var(--muted);font-weight:500}
.rail li{display:flex;gap:8px;align-items:baseline;padding:6px 0;border-top:1px solid var(--line);font-size:13px;overflow-wrap:anywhere}
.rail li:first-child{border-top:0}
.rail li .num{color:var(--muted);text-decoration:none;font-weight:600;flex:none}
.rail li .t{flex:1;min-width:0}
.rail .sub{display:block;color:var(--muted);font-size:12px}
.events time{color:var(--muted);font-size:12px;flex:none;min-width:74px}
.events .dot{align-self:center}

/* my work (local, interactive) */
.mine{display:flex;flex-direction:column;gap:8px}
.mine h2{font-size:13.5px;margin:0}
.mine .row-items{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}
.actions{display:flex;gap:8px;margin-top:2px}
button{font:inherit;font-size:12.5px;font-weight:600;border-radius:8px;padding:5px 12px;cursor:pointer;
border:1px solid var(--btn);background:var(--btn);color:var(--btn-text)}
button.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
button:disabled{opacity:.5;cursor:default}
#msg{display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
white-space:pre-wrap;overflow-wrap:anywhere}
#msg.err{border-color:var(--stale)}#msg code{display:block;margin-top:8px;font-size:13px}
footer{color:var(--muted);font-size:12px;padding:0 2px}
footer code{font-size:11.5px}

/* setup page (shares the shell) */
body[data-page=setup] main{max-width:1040px;display:block}
body[data-page=setup] h2{font-size:14px;margin:28px 0 10px}
.checks li{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin-bottom:6px;
display:flex;align-items:center;gap:10px;flex-wrap:wrap;overflow-wrap:anywhere}
.checks .t{flex:1;min-width:180px}
.mark{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:13px;font-weight:700;color:#fff;flex:none}
.ok .mark{background:var(--free)}.bad .mark{background:var(--stale)}.info .mark{background:var(--done)}
.checks small,.panel small,.hint{color:var(--muted);font-size:13px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;padding:8px 0;border-bottom:1px solid var(--line)}
.row:last-of-type{border-bottom:0}.row>.k{width:220px;max-width:100%;font-weight:600}
.row label{display:inline-flex;align-items:center;gap:6px}
input[type=text],input[type=number]{font:inherit;color:var(--ink);background:var(--ground);
border:1px solid var(--line);border-radius:6px;padding:5px 8px;max-width:100%}
input[type=number]{width:96px}input[type=text]{width:320px}
.presets{display:flex;flex-wrap:wrap;gap:8px}
.report{background:var(--ground);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:14px}
.save{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:12px}
pre{background:var(--ground);border-radius:8px;padding:10px 12px;overflow:auto;font-size:13px}

@media (max-width:1399px){.layout{grid-template-columns:minmax(0,1fr) 260px}}
/* fits one screen on a desktop: the lanes scroll, not the page */
@media (min-width:1100px) and (min-height:620px){body[data-page=board]{height:100dvh;overflow:hidden}
body[data-page=board] .rail,body[data-page=board] .lane{max-height:100%}}
@media (max-width:1099px){.layout{grid-template-columns:1fr}.board{grid-auto-flow:column;grid-template-columns:none;
grid-auto-columns:minmax(260px,78%);scroll-snap-type:x mandatory}.lane{scroll-snap-align:start;max-height:70vh}}
/* phone: the flow strip is the tab bar, one lane at a time */
@media (max-width:719px){
.shell-in{padding:12px 16px 0}main{padding:12px 16px}
.flow label{cursor:pointer;flex:none;min-width:0;padding:6px 12px 9px}.flow label b{font-size:19px}
.flow label+label::before{display:none}
.board{display:block;overflow:visible}.lane{display:none;max-height:none}
#lane-free:checked~.shell label[for=lane-free],#lane-progress:checked~.shell label[for=lane-progress],
#lane-waiting:checked~.shell label[for=lane-waiting],#lane-review:checked~.shell label[for=lane-review],
#lane-done:checked~.shell label[for=lane-done]{background:var(--shell-line);color:var(--shell-ink)}
#lane-free:checked~main .lane-free,#lane-progress:checked~main .lane-progress,#lane-waiting:checked~main .lane-waiting,
#lane-review:checked~main .lane-review,#lane-done:checked~main .lane-done{display:flex}
#lane-free:focus-visible~.shell label[for=lane-free],#lane-progress:focus-visible~.shell label[for=lane-progress],
#lane-waiting:focus-visible~.shell label[for=lane-waiting],#lane-review:focus-visible~.shell label[for=lane-review],
#lane-done:focus-visible~.shell label[for=lane-done]{outline:2px solid var(--shell-ink);outline-offset:-2px}
.lane .items{overflow:visible}button{min-height:44px;padding:8px 14px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
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
    return f'<div class="bar" aria-hidden="true"><i style="width:{pct}%"></i>{marks}</div>'


def took_text(r: dict) -> str:
    took = r.get("took")
    if not took or took == "–":
        return ""
    return f"Done in {took}" if r["state"] == "done" else f"Going for {took}"


# The board's lanes, left to right, and which row states go in each
LANES = [("free", "Free to take"), ("progress", "In progress"), ("waiting", "Waiting"),
         ("review", "In review"), ("done", "Done")]
LANE_OF = {"active": "progress", "claimed": "progress", "quiet": "progress", "assigned": "progress",
           "stale": "progress", "waiting": "waiting", "changes": "waiting", "review": "review", "done": "done"}
BADGE = {"quiet": ("quiet", "waiting"), "stale": ("stale", "stale"), "assigned": ("assigned", "done"),
         "changes": ("changes asked", "waiting")}
EMPTY = {"free": "Nothing free right now.", "progress": "Nobody is working on anything right now.",
         "waiting": "Nobody is waiting.", "review": "Nothing to review.", "done": "Nothing finished yet."}
EVENT_COLOR = {"claimed": "progress", "started": "progress", "milestone": "progress", "replanned": "progress",
               "back": "progress", "done": "free", "stale": "stale", "released": "done", "closed": "done"}
PR_STATE = {"review": "waiting for review", "changes": "changes asked", "approved": "approved", "draft": "draft"}


def hue(login: str) -> int:
    return sum(ord(ch) * (i + 7) for i, ch in enumerate(login.lower())) % 360


def initials(login: str) -> str:
    parts = [p for p in login.replace("_", "-").split("-") if p]
    letters = (parts[0][:1] + parts[1][:1]) if len(parts) > 1 else login[:2]
    return esc(letters.upper() or "?")


def person(login: str) -> str:
    return (f'<span class="who"><i class="av" style="--h:{hue(login)}" aria-hidden="true">{initials(login)}</i>'
            f'@{esc(login)}</span>')


def issue_link(repo: str, n) -> str:
    return f"https://github.com/{esc(repo)}/issues/{int(n)}"


def item(r: dict, repo: str, action: str = "") -> str:
    """One task someone is on, in its lane."""
    lane = LANE_OF.get(r["state"], "progress")
    pct = r.get("pct")
    if pct is None:  # older state files
        pct = round(100 * r["done"] / r["total"]) if r.get("total") else 0
    link = issue_link(repo, r["n"])
    badge = BADGE.get(r["state"])
    badge_html = f'<span class="badge" style="--c:var(--{badge[1]})">{badge[0]}</span>' if badge else ""
    when = f'<span class="when">{esc(r["when"])}</span>' if r.get("when") not in (None, "–") else ""
    plan = ""
    if r.get("total"):
        plan = (f'<div class="note">Plan {esc(r["plan"])} · <span class="pct">{pct} %</span></div>{bar(pct)}')
    notes = [esc(r["now"])] if r.get("now") not in (None, "–") else []
    if took_text(r):
        notes.append(esc(took_text(r)))
    note = f'<div class="note">{" · ".join(notes)}</div>' if notes else ""
    return (f'<article class="item" style="--c:var(--{"stale" if r["state"] == "stale" else lane})">'
            f'<div class="top"><a class="num" href="{link}">#{r["n"]}</a>{badge_html}{when}</div>'
            f'<a class="title" href="{link}">{esc(r["title"])}</a>{plan}{note}{person(r["who"])}{action}</article>')


def is_ready(f: dict, ready_label: str) -> bool:
    if not ready_label:
        return True
    return ready_label.lower() in (lb.lower() for lb in f.get("labels") or [])


def free_item(f: dict, repo: str, app: dict | None, ready_label: str = "") -> str:
    """A task nobody has yet."""
    link = issue_link(repo, f["n"])
    labels = [lb for lb in f.get("labels") or [] if lb.lower() != (ready_label or "").lower()]
    tags = "".join(f'<span class="tag">{esc(lb)}</span>' for lb in labels)
    waits = f'<div class="note">Waiting on <b>{esc(f["waits"])}</b></div>' if f.get("waits") else ""
    action = ""
    if app is not None:
        if is_ready(f, app.get("ready_label", "")):
            action = f'<div class="actions"><button data-act="start" data-n="{int(f["n"])}">Start</button></div>'
        else:
            action = (f'<div class="tags"><span class="tag" title="Add the label {esc(app.get("ready_label"))} '
                      f'to make it startable">not ready</span></div>')
    return (f'<article class="item" style="--c:var(--free)"><div class="top"><a class="num" href="{link}">'
            f'#{int(f["n"])}</a></div><a class="title" href="{link}">{esc(f["title"])}</a>{waits}'
            + (f'<div class="tags">{tags}</div>' if tags else "") + f"{action}</article>")


def group_of(f: dict, ready_label: str) -> str:
    return f.get("group") or ("ready" if is_ready(f, ready_label) else "open")


def lane_html(key: str, name: str, items: list[str], extra: str = "", count: int | None = None) -> str:
    body = "".join(items) or f'<p class="empty">{EMPTY[key]}</p>'
    n = len(items) if count is None else count
    return (f'<section class="lane lane-{key}" style="--c:var(--{key})" aria-label="{name}">'
            f'<header><span class="dot" aria-hidden="true"></span>{name}<span class="count">{n}</span></header>'
            f'<div class="items">{body}{extra}</div></section>')


def plain_event(e: dict) -> str:
    """The event's text without its leading emoji: the page draws a coloured dot instead."""
    text = event_text(e)
    first, _, rest = text.partition(" ")
    return rest if first and not first[0].isalnum() and first[0] not in "@#" else text


def page(title: str, body: str, app: dict | None, current: str, repo: str, meta: str,
         snapshot: bool = False, flow: str = "", before: str = "") -> str:
    """The shell around both pages: head, header with navigation (interactive only), script.
    `flow` goes inside the header (the board's flow strip); `before` comes first in <body>
    (the lane switches the flow strip controls on a phone)."""
    if app is None:
        refresh = "" if snapshot else '<meta http-equiv="refresh" content="60">'
        script, nav = "", ""
    else:
        refresh = ""
        script = f'<script nonce="{esc(app.get("nonce", ""))}">{APP_JS}</script>'
        nav = '<nav class="pages">' + "".join(
            f'<a data-nav="{path}"' + (' aria-current="page"' if key == current else "") + f">{name}</a>"
            for key, path, name in (("board", "/", "Board"), ("setup", "/setup", "Setup"))) + "</nav>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>{esc(title)}</title><style>{CSS}</style></head>
<body data-page="{current}">{before}
<header class="shell"><div class="shell-in"><div class="brand"><h1>Devsprinter</h1>
<span class="meta"><a href="https://github.com/{esc(repo)}">{esc(repo)}</a> {meta}</span>{nav}</div>{flow}</div></header>
<main>
{body}
</main>{script}</body></html>
"""


def render(data: dict, app: dict | None = None, snapshot: bool = False) -> str:
    """The board page. `app` (interactive mode): {"me": login, "ready_label": str, "nonce": str}.
    `snapshot`: a file someone opened locally (no reload; the footer says how to refresh it).

    Layout: a flow strip in the header (how many tasks at each step, and the mix), five lanes
    (free to take, in progress, waiting, in review, done) that scroll on their own, and a rail
    with decisions, pull requests and activity. On a desktop it fits one screen; on a phone the
    flow strip switches lanes (CSS only, so it also works as a local file without scripts)."""
    repo = data.get("repo") or ""
    team = config.clean_team(data.get("team"))
    ready_label = (app or {}).get("ready_label", team["ready_label"]) if app is not None else team["ready_label"]
    rows = sorted(data.get("rows") or [], key=lambda r: (ORDER.index(r["state"]), r.get("secs") or 0))
    free = data.get("free") or []
    events = list(reversed(data.get("events") or []))[:40]
    prs = data.get("prs") or []
    groups = {g: [f for f in free if group_of(f, ready_label) == g] for g in ("ready", "open", "waiting")}

    lanes = {k: [r for r in rows if LANE_OF.get(r["state"]) == k] for k, _ in LANES if k != "free"}
    counts = {"free": len(groups["ready"]), **{k: len(v) for k, v in lanes.items()}}
    default = "progress" if counts["progress"] else "free"
    before = "".join(f'<input type="radio" name="lane" id="lane-{k}" class="sr"'
                     + (" checked" if k == default else "") + f' aria-label="Show {name}">' for k, name in LANES)
    total = sum(counts.values()) or 1
    flow = ('<div class="flow" role="list">'
            + "".join(f'<label for="lane-{k}" role="listitem" style="--c:var(--{k})"><b>{counts[k]}</b>'
                      f'<span><i class="dot" aria-hidden="true"></i>{name}</span></label>' for k, name in LANES)
            + '</div><div class="mix" aria-hidden="true">'
            + "".join(f'<i style="--c:var(--{k});width:{100 * counts[k] / total:.2f}%"></i>' for k, _ in LANES if counts[k])
            + "</div>")

    later = ""
    if groups["open"]:
        later = (f'<details class="later"><summary>Not ready yet ({len(groups["open"])})</summary><div class="items">'
                 + "".join(free_item(f, repo, app, ready_label) for f in groups["open"]) + "</div></details>")
    board_html = lane_html("free", "Free to take", [free_item(f, repo, app, ready_label) for f in groups["ready"]], later)
    for k, name in LANES[1:]:
        board_html += lane_html(k, name, [item(r, repo) for r in lanes[k]])

    rail = ""
    if groups["waiting"]:
        rail += (f'<section><h2><span class="dot" style="--c:var(--waiting)" aria-hidden="true"></span>'
                 f'Waiting on a decision<span class="count">{len(groups["waiting"])}</span></h2><ul>'
                 + "".join(f'<li><a class="num" href="{issue_link(repo, f["n"])}">#{int(f["n"])}</a><span class="t">'
                           f'<a href="{issue_link(repo, f["n"])}" style="color:inherit;text-decoration:none">{esc(f["title"])}</a>'
                           + (f'<span class="sub">waiting on {esc(f["waits"])}</span>' if f.get("waits") else "")
                           + "</span></li>" for f in groups["waiting"]) + "</ul></section>")
    if prs:
        rail += (f'<section><h2><span class="dot" style="--c:var(--review)" aria-hidden="true"></span>'
                 f'Pull requests<span class="count">{len(prs)}</span></h2><ul>'
                 + "".join(f'<li><a class="num" href="https://github.com/{esc(repo)}/pull/{int(p["n"])}">#{int(p["n"])}</a>'
                           f'<span class="t">{esc(p["title"])}<span class="sub">@{esc(p["who"])} · '
                           f'{esc(PR_STATE.get(p.get("state"), p.get("state")))}'
                           + "".join(f" · fixes #{int(n)}" for n in p.get("fixes") or [] if isinstance(n, int))
                           + "</span></span></li>" for p in prs) + "</ul></section>")
    ev_html = "".join(f'<li><span class="dot" style="--c:var(--{EVENT_COLOR.get(e["type"], "done")})" aria-hidden="true">'
                      f'</span><time datetime="{esc(e["ts"])}">{esc(e["ts"][5:16].replace("T", " "))}</time>'
                      f'<span class="t">{esc(plain_event(e))}</span></li>'
                      for e in events if e.get("type") in EVENT_TEXT) \
        or '<li><span class="empty">No events yet. They appear after the next change.</span></li>'
    rail += f'<section><h2>Activity</h2><ul class="events">{ev_html}</ul></section>'

    gen = esc((data.get("generated") or "").replace("T", " ").replace("Z", " UTC"))
    mine_html = ""
    if app is None and snapshot:
        foot = ("A snapshot: ask your AI to show the dashboard again, or run "
                "<code>python devsprinter/sprint.py dashboard</code>, for fresh data. "
                "To join, ask your AI <i>what can I do?</i>")
    elif app is None:
        foot = ("Reloads every minute. To join, ask your AI <i>what can I do?</i> "
                "or write <code>/claim</code> in an issue.")
    else:
        me = (app.get("me") or "").lower()
        mine = [r for r in rows if r["who"].lower() == me]
        release = '<div class="actions"><button class="ghost" data-act="release" data-n="{n}">Release</button></div>'
        mine_items = "".join(item(r, repo, release.format(n=int(r["n"]))) for r in mine) or \
            '<p class="empty">You have no task. Pick one under Free to take and press Start.</p>'
        mine_html = (f'<div id="msg" role="status"></div><section class="mine" aria-label="My work">'
                     f'<h2>My work (@{esc(app.get("me"))})</h2><div class="row-items">{mine_items}</div></section>')
        foot = ("Local dashboard, only reachable from this computer. Start claims the issue, "
                "creates a worktree and opens Claude Code there"
                + (f"; only issues labelled <code>{esc(ready_label)}</code> can be started." if ready_label else "."))
    body = (f'{mine_html}<div class="layout"><div class="board">{board_html}</div>'
            f'<aside class="rail">{rail}</aside></div>'
            f'<footer>{foot} Quiet and stale: {esc(thresholds(data.get("team")))}. '
            f'Agents report progress at 25, 50, 75 and 100 %.</footer>')
    return page(f"Devsprinter · {repo}", body, app, "board", repo, f"· updated {gen}", snapshot, flow, before)


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
