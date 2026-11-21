"""Sprint board: an overview of all open issues, kept in one pinned issue.

`python board.py --repo owner/repo` reads all open issues with assignees, labels and
Devsprinter comments (one GraphQL call) and writes a table into the issue "Sprint board"
(recognised by the marker <!-- devsprinter-board --> in its body). If it does not exist it is
created and pinned. `--dry-run` only prints the table.

State per row: active, quiet (no signal for the team's quiet time, default 30 min), stale
(no signal for the stale time, default 4 h), done (all steps done), assigned (an assignee but
no Devsprinter signal yet). Free issues are listed separately. The times come from
.github/devsprinter.json (config.py). Each row also says how long the task has been going,
and a done task how long it took.

The board also keeps the previous snapshot and the latest events in a hidden line
(<!-- devsprinter-state {...} -->). Each run compares with the previous one and creates events
(claimed, milestone, released, done, stale ...). They feed the views:
feed.py (Discord/Slack), projects.py (GitHub Projects), dashboard.py (web page) and serve.py
(the interactive local dashboard). `--state-out file.json` writes the state and new events.

Run by a GitHub Action (.github/workflows/devsprinter-board.yml) or locally with `gh`.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import config
from context import ago, elapsed, pulses, span
from emit import milestone, short

BOARD_MARKER = "<!-- devsprinter-board -->"
BOARD_TITLE = "Sprint board"
STATE_RE = re.compile(r"<!-- devsprinter-state (\{.*?\}) -->", re.S)
MAX_EVENTS = 100
QUERY = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
issues(states:OPEN,first:100,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{
id number title body isPinned assignees(first:10){nodes{login}} labels(first:20){nodes{name}}
comments(last:50){nodes{author{login} body}}}}}}"""
STATE_LABEL = {"active": "🟢 active", "quiet": "🟡 quiet", "stale": "🔴 stale", "done": "✅ done",
               "assigned": "⚪ assigned"}
ORDER = ["active", "quiet", "assigned", "stale", "done"]
# Event types and how they read. `started` and `replanned` are shown on the board and the
# dashboard but are not sent to the feed by default (feed.py).
EVENT_TEXT = {
    "claimed": "🙋 {who} took #{n} {title}",
    "started": "▶️ {who} started on #{n} {title} ({plan})",
    "milestone": "📍 {who} reached {pct} % on #{n} {title} ({plan})",
    "replanned": "📝 #{n} {title}: new plan {plan}",
    "done": "✅ {who} finished #{n} {title}{took} ({plan})",
    "stale": "🔴 #{n} {title} is stale ({who}, no recent activity)",
    "back": "🟢 {who} is back on #{n} {title}",
    "released": "↩️ {who} released #{n} {title}",
    "closed": "🔒 #{n} {title} was closed",
}


def gh(*args: str, body: str | None = None) -> str | None:
    cmd = ["gh", *args] + (["--body-file", "-"] if body is not None else [])
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60,
                             input=body.encode("utf-8") if body is not None else None)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", errors="replace").strip() if out.returncode == 0 else None


def fetch(repo: str) -> list[dict]:
    owner, name = repo.split("/", 1)
    out = gh("api", "graphql", "-f", f"query={QUERY}", "-F", f"owner={owner}", "-F", f"name={name}")
    if out is None:
        raise SystemExit(f"Could not read the issues of {repo} (is gh logged in?).")
    return json.loads(out)["data"]["repository"]["issues"]["nodes"]


def cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def is_board(issue: dict) -> bool:
    return (issue.get("body") or "").startswith(BOARD_MARKER)


def labels_of(issue: dict) -> list[str]:
    return [lb["name"] for lb in (issue.get("labels") or {}).get("nodes") or [] if lb.get("name")]


def rows_for(issue: dict, team: dict | None = None) -> list[dict]:
    team = config.clean_team(team)
    base = {"n": issue["number"], "title": issue["title"], "id": issue.get("id")}
    rows = []
    for p in pulses(issue):
        when, secs = ago(p["ts"])
        finished = p["type"] == "done" or (p["total"] and p["done"] == p["total"])
        if finished:
            state = "done"
        elif secs is None or secs > team["stale_minutes"] * 60:
            state = "stale"
        elif secs > team["quiet_minutes"] * 60:
            state = "quiet"
        else:
            state = "active"
        # How long the task has been going (until the last signal once it is done or stale)
        took_s = elapsed(p["since"], p["ts"] if finished or state == "stale" else None)
        done, total = p["done"] or 0, p["total"] or 0
        plan = f"v{p['plan_rev']} · {done}/{total}" if total else "–"
        rows.append({**base, "state": state, "who": p["actor"], "plan": plan,
                     "rev": p["plan_rev"] or 0, "done": done, "total": total,
                     "pct": milestone(done, total),
                     "now": short(p["current"]) if p["current"] else "–",
                     "when": when if secs is not None else "–", "secs": secs or 0,
                     "ts": p["ts"] if secs is not None else None,
                     "took_s": round(took_s) if took_s is not None else None,
                     "took": span(took_s) if took_s is not None else "–"})
    with_pulse = {r["who"].lower() for r in rows}
    for a in (issue.get("assignees") or {}).get("nodes") or []:
        if a["login"].lower() not in with_pulse:
            rows.append({**base, "state": "assigned", "who": a["login"], "plan": "–", "rev": 0,
                         "done": 0, "total": 0, "pct": 0, "now": "–", "when": "–", "secs": 0,
                         "ts": None, "took_s": None, "took": "–"})
    return rows


def compute(issues: list[dict], team: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(rows, free issues), without the board issue itself."""
    rows, free = [], []
    for i in issues:
        if is_board(i):
            continue
        r = rows_for(i, team)
        rows += r
        if not r:
            free.append({"n": i["number"], "title": i["title"], "id": i.get("id"),
                         "labels": labels_of(i)})
    rows.sort(key=lambda r: (ORDER.index(r["state"]), r["secs"], r["n"]))
    return rows, free


# ---------- events ----------

def key(row: dict) -> str:
    return f"{row['n']}:{row['who'].lower()}"


def snapshot(rows: list[dict]) -> dict:
    return {key(r): {k: r.get(k) for k in ("n", "title", "who", "state", "rev", "done", "total", "plan")}
            for r in rows}


def read_state(issues: list[dict]) -> dict | None:
    board = next((i for i in issues if is_board(i)), None)
    m = STATE_RE.search((board or {}).get("body") or "")
    if not m:
        return None
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return None
    return state if isinstance(state, dict) and isinstance(state.get("rows"), dict) else None


def diff(prev: dict | None, rows: list[dict], open_numbers: set[int], now_ts: str) -> list[dict]:
    """Events between the previous snapshot and now. No previous = first run = no events."""
    if prev is None:
        return []
    old = prev.get("rows") or {}
    events = []

    def ev(kind: str, r: dict) -> None:
        e = {"ts": now_ts, "type": kind, "n": r["n"], "title": short(r["title"]),
             "who": r["who"], "plan": r.get("plan") or "–",
             "pct": milestone(r.get("done"), r.get("total"))}
        if kind == "done" and r.get("took_s") is not None:
            e["took_s"], e["took"] = r["took_s"], r["took"]  # for the "how long tasks take" report
        events.append(e)

    for r in rows:
        o = old.get(key(r))
        if o is None:
            ev("done" if r["state"] == "done" else "claimed", r)
            continue
        if r["state"] != o["state"]:
            if r["state"] == "done":
                ev("done", r)
                continue
            if r["state"] == "stale":
                ev("stale", r)
            elif r["state"] == "active" and o["state"] == "stale":
                ev("back", r)
            elif r["state"] == "active" and o["state"] == "assigned":
                ev("started", r)
                continue
        old_rev = o.get("rev") or 0
        if r["rev"] > old_rev > 0:
            ev("replanned", r)
        elif r["state"] != "done" and r["rev"] == old_rev and \
                milestone(r["done"], r["total"]) > milestone(o.get("done"), o.get("total")):
            ev("milestone", r)
    now_keys = {key(r) for r in rows}
    closed = set()
    for k, o in old.items():
        if k in now_keys:
            continue
        if o["n"] in open_numbers:
            ev("released", o)
        elif o["n"] not in closed:
            closed.add(o["n"])
            ev("closed", o)
    return events


def event_text(e: dict, at: bool = True) -> str:
    who = ("@" if at else "") + str(e.get("who") or "?")
    values = {"pct": milestone(e.get("done"), e.get("total")), **e, "who": who,
              "took": f" in {e['took']}" if e.get("took") else ""}
    return EVENT_TEXT.get(e["type"], "{type} #{n}").format(**values)


# ---------- the markdown board ----------

def thresholds(team: dict | None) -> str:
    team = config.clean_team(team)
    return (f"quiet after {span(team['quiet_minutes'] * 60)}, "
            f"stale after {span(team['stale_minutes'] * 60)}")


def render(issues: list[dict], now: datetime.datetime | None = None,
           state: dict | None = None, team: dict | None = None) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rows, free = compute(issues, team)
    counts = {k: sum(r["state"] == k for r in rows) for k in ORDER}
    lines = [BOARD_MARKER, f"## {BOARD_TITLE}",
             " · ".join([f"{STATE_LABEL[k]} {counts[k]}" for k in ORDER if counts[k]] + [f"free {len(free)}"]),
             ""]
    if rows:
        lines += ["| State | Task | Who | Plan | Now | Time | Last |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            plan = f"{r['plan']} ({r['pct']} %)" if r["total"] else r["plan"]
            took = r.get("took") or "–"
            took = f"done in {took}" if r["state"] == "done" and took != "–" else took
            lines.append(f"| {STATE_LABEL[r['state']]} | #{r['n']} {cell(r['title'])[:50]} | @{r['who']} "
                         f"| {plan} | {cell(r['now'])} | {took} | {r['when']} |")
    else:
        lines.append("_Nobody is working on anything right now._")
    lines += ["", f"### Free ({len(free)})"]
    lines += [f"- #{i['n']} {cell(i['title'])}" for i in free] or ["_Nothing._"]
    recent = list(reversed((state or {}).get("events") or []))[:8]
    if recent:
        lines += ["", "### Recent events"]
        lines += [f"- `{e['ts'][11:16]}` {cell(event_text(e, at=False))}" for e in recent]
    lines += ["", f"<sub>Updated {now.strftime('%Y-%m-%d %H:%M')} UTC by Devsprinter · "
                  f"{thresholds(team)} · take a task with <code>/devsprinter:claim N</code></sub>"]
    if state is not None:
        # < and > are escaped, so a title containing "-->" cannot end the HTML comment
        blob = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        lines.insert(1, "<!-- devsprinter-state " + blob.replace("<", "\\u003c").replace(">", "\\u003e") + " -->")
    return "\n".join(lines)


def build(issues: list[dict], now: datetime.datetime | None = None,
          fallback: dict | None = None, team: dict | None = None) -> tuple[str, dict, list[dict]]:
    """(board text, new saved state, new events). `fallback` is used when the board issue has
    no saved state yet, e.g. the local dashboard's own previous snapshot."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    now_ts = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows, _ = compute(issues, team)
    prev = read_state(issues) or fallback
    new = diff(prev, rows, {i["number"] for i in issues if not is_board(i)}, now_ts)
    events = ((prev or {}).get("events") or []) + new
    state = {"v": 1, "rows": snapshot(rows), "events": events[-MAX_EVENTS:]}
    return render(issues, now, state, team), state, new


def publish(repo: str, issues: list[dict], body: str) -> str:
    board = next((i for i in issues if is_board(i)), None)
    if board:
        if gh("issue", "edit", str(board["number"]), "--repo", repo, body=body) is None:
            raise SystemExit("Could not update the Sprint board issue.")
        if not board.get("isPinned"):
            gh("issue", "pin", str(board["number"]), "--repo", repo)
        return f"Updated #{board['number']}."
    url = gh("issue", "create", "--repo", repo, "--title", BOARD_TITLE, body=body)
    if url is None:
        raise SystemExit("Could not create the Sprint board issue.")
    gh("issue", "pin", url.rsplit("/", 1)[-1], "--repo", repo)
    return f"Created and pinned {url}."


def export(repo: str, issues: list[dict], state: dict, new: list[dict],
           now: datetime.datetime | None = None, team: dict | None = None) -> dict:
    """The state that feed.py, projects.py, dashboard.py and serve.py read."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rows, free = compute(issues, team)
    return {"v": 1, "repo": repo, "generated": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "rows": rows, "free": free, "events": state["events"], "new_events": new,
            "team": config.clean_team(team)}


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--dry-run", action="store_true", help="only print the table, save nothing")
    ap.add_argument("--state-out", help="write the state and new events as JSON here")
    ap.add_argument("--html", help="write the static dashboard (one HTML file) here")
    ap.add_argument("--config", default=config.TEAM_FILE,
                    help="team settings file (default: .github/devsprinter.json in this folder)")
    args = ap.parse_args()
    team = config.team_at(".") if args.config == config.TEAM_FILE else \
        config.team_from_text(Path(args.config).read_text(encoding="utf-8"))
    issues = fetch(args.repo)
    body, state, new = build(issues, team=team)
    print(STATE_RE.sub("", body).replace("\n\n## ", "\n## ", 1) if args.dry_run
          else publish(args.repo, issues, body))
    if args.state_out or args.html:
        data = export(args.repo, issues, state, new, team=team)
        if args.state_out:
            Path(args.state_out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.html:
            import dashboard
            Path(args.html).parent.mkdir(parents=True, exist_ok=True)
            Path(args.html).write_text(dashboard.render(data), encoding="utf-8")
            print(f"Dashboard: {Path(args.html).resolve()}")


if __name__ == "__main__":
    main()
