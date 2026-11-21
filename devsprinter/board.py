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

Open sprints: people and any LLM also join with comment commands (/claim, /join, /done,
/waiting ..., see commands.py), and an open PR that says "Fixes #N" puts #N in review, waiting
on the sprintmaster. With `--act` (the Action) the board also carries out the commands once:
assigns or unassigns the commenter, adds the ready label, or answers a refused command. The
comment ids it has handled are kept in the saved state.

Run by a GitHub Action (.github/workflows/devsprinter-board.yml) or locally with `gh`.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import commands
import config
from context import ago, elapsed, pulses, span
from emit import milestone, short

BOARD_MARKER = "<!-- devsprinter-board -->"
BOARD_TITLE = "Sprint board"
STATE_RE = re.compile(r"<!-- devsprinter-state (\{.*?\}) -->", re.S)
MAX_EVENTS = 100
MAX_SEEN = 300
REPLY_MARKER = "<!-- devsprinter-reply -->"
QUERY = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
issues(states:OPEN,first:100,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{
id number title body isPinned assignees(first:10){nodes{login}} labels(first:20){nodes{name}}
comments(last:50){nodes{id createdAt authorAssociation author{__typename login} body}}}}
pullRequests(states:OPEN,first:50,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{
number title url isDraft reviewDecision author{login} closingIssuesReferences(first:10){nodes{number}}}}}}"""
STATE_LABEL = {"active": "🟢 active", "claimed": "🙋 claimed", "quiet": "🟡 quiet",
               "assigned": "⚪ assigned", "waiting": "⏳ waiting", "review": "👀 in review",
               "changes": "✏️ changes asked", "stale": "🔴 stale", "done": "✅ done"}
ORDER = ["active", "claimed", "quiet", "assigned", "waiting", "review", "changes", "stale", "done"]
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
    return fetch_all(repo)[0]


def fetch_all(repo: str) -> tuple[list[dict], list[dict]]:
    """(open issues with their linked PRs attached, all open PRs)."""
    owner, name = repo.split("/", 1)
    out = gh("api", "graphql", "-f", f"query={QUERY}", "-F", f"owner={owner}", "-F", f"name={name}")
    if out is None:
        raise SystemExit(f"Could not read the issues of {repo} (is gh logged in?).")
    data = json.loads(out)["data"]["repository"]
    issues = data["issues"]["nodes"]
    prs = (data.get("pullRequests") or {}).get("nodes") or []
    link_prs(issues, prs)
    return issues, prs


def link_prs(issues: list[dict], prs: list[dict]) -> None:
    """Attach each open PR to the issues it closes ("Fixes #N"), as issue["prs"]."""
    by_n = {i["number"]: i for i in issues}
    for pr in prs:
        for ref in (pr.get("closingIssuesReferences") or {}).get("nodes") or []:
            i = by_n.get(ref.get("number"))
            if i is not None:
                i.setdefault("prs", []).append(pr)


def cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def is_board(issue: dict) -> bool:
    return (issue.get("body") or "").startswith(BOARD_MARKER)


def labels_of(issue: dict) -> list[str]:
    return [lb["name"] for lb in (issue.get("labels") or {}).get("nodes") or [] if lb.get("name")]


def blank(base: dict, state: str, who: str, **extra) -> dict:
    row = {**base, "state": state, "who": who, "plan": "–", "rev": 0, "done": 0, "total": 0,
           "pct": 0, "now": "–", "when": "–", "secs": 0, "ts": None, "took_s": None, "took": "–"}
    row.update(extra)
    return row


def waits_text(w: dict | None) -> str:
    if not w:
        return ""
    if "user" in w:
        return "@" + w["user"]
    if "issue" in w:
        return f"#{w['issue']}"
    return w.get("text") or "someone"


def rows_for(issue: dict, team: dict | None = None, masters: list[str] | None = None,
             open_numbers: set[int] | None = None) -> list[dict]:
    team = config.clean_team(team)
    masters = masters if masters is not None else team["sprintmasters"]
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
    covered = {r["who"].lower() for r in rows}
    # Open PRs that close this issue: the author's work is in review (or needs changes)
    for pr in issue.get("prs") or []:
        author = (pr.get("author") or {}).get("login") or ""
        if not author or author.lower() in covered:
            continue
        covered.add(author.lower())
        now = f"PR #{pr['number']}"
        if pr.get("isDraft"):
            rows.append(blank(base, "claimed", author, now=f"draft {now}"))
        elif pr.get("reviewDecision") == "CHANGES_REQUESTED":
            rows.append(blank(base, "changes", author, now=f"{now} · waiting on @{author}",
                              waits="@" + author))
        else:
            sm = " ".join("@" + m for m in masters) or "the sprintmaster"
            rows.append(blank(base, "review", author, now=f"{now} · waiting on {sm}", waits=sm))
    # People who joined with a comment command (no plugin, no PR yet)
    folded = commands.fold(issue, masters, team["who_can_claim"], team["ready_label"])
    for low, p in folded["people"].items():
        if low in covered:
            continue
        covered.add(low)
        when, secs = ago(p["last"])
        took_s = elapsed(p["since"], p["last"] if p["done"] else None)
        took = {"took_s": round(took_s) if took_s is not None else None,
                "took": span(took_s) if took_s is not None else "–"}
        seen = {"when": when if secs is not None else "–", "secs": secs or 0, "ts": p["last"]}
        w = p.get("waiting")
        if w and "issue" in w and open_numbers is not None and w["issue"] not in open_numbers:
            w = None  # the issue it waited on is closed
        joined = "joined" if p["role"] == "join" else "claimed"
        if p["done"]:
            rows.append(blank(base, "done", p["who"], now="done, waiting for approval", **seen, **took))
        elif w:
            rows.append(blank(base, "waiting", p["who"], now=f"waiting on {waits_text(w)}",
                              waits=waits_text(w), **seen, **took))
        elif secs is None or secs > team["claim_stale_hours"] * 3600:
            rows.append(blank(base, "stale", p["who"], now=joined, **seen, **took))
        else:
            rows.append(blank(base, "claimed", p["who"], now=joined, **seen, **took))
    for a in (issue.get("assignees") or {}).get("nodes") or []:
        if a["login"].lower() not in covered:
            rows.append(blank(base, "assigned", a["login"]))
    return rows


def compute(issues: list[dict], team: dict | None = None,
            masters: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(rows, free issues), without the board issue itself. A free issue has "group":
    ready (anyone may take it), waiting (a waiting label, e.g. a decision) or open."""
    team = config.clean_team(team)
    open_numbers = {i["number"] for i in issues if not is_board(i)}
    waiting = {k.lower(): v for k, v in team["waiting_labels"].items()}
    ready = team["ready_label"].lower()
    rows, free = [], []
    for i in issues:
        if is_board(i):
            continue
        r = rows_for(i, team, masters, open_numbers)
        rows += r
        if not r:
            labels = labels_of(i)
            on = next((waiting[lb.lower()] for lb in labels if lb.lower() in waiting), None)
            group = "waiting" if on else \
                "ready" if ready and ready in (lb.lower() for lb in labels) else "open"
            free.append({"n": i["number"], "title": i["title"], "id": i.get("id"),
                         "labels": labels, "group": group, **({"waits": on} if on else {})})
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
           state: dict | None = None, team: dict | None = None,
           masters: list[str] | None = None) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rows, free = compute(issues, team, masters)
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
    groups = {g: [i for i in free if i.get("group", "open") == g] for g in ("ready", "open", "waiting")}
    titles = {"ready": "Free to take", "open": "Not ready yet" if groups["ready"] else "Free",
              "waiting": "Waiting on a decision"}
    if not free:
        lines += ["", "### Free (0)", "_Nothing._"]
    for g, items in groups.items():
        if items:
            lines += ["", f"### {titles[g]} ({len(items)})"]
            lines += [f"- #{i['n']} {cell(i['title'])}"
                      + (f" · waiting on {cell(i['waits'])}" if i.get("waits") else "") for i in items]
    recent = list(reversed((state or {}).get("events") or []))[:8]
    if recent:
        lines += ["", "### Recent events"]
        lines += [f"- `{e['ts'][11:16]}` {cell(event_text(e, at=False))}" for e in recent]
    lines += ["", f"<sub>Updated {now.strftime('%Y-%m-%d %H:%M')} UTC by Devsprinter · "
                  f"{thresholds(team)} · take a task: write <code>/claim</code> in the issue, "
                  f"or <code>/devsprinter:claim N</code> in Claude Code</sub>"]
    if state is not None:
        # < and > are escaped, so a title containing "-->" cannot end the HTML comment
        blob = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        lines.insert(1, "<!-- devsprinter-state " + blob.replace("<", "\\u003c").replace(">", "\\u003e") + " -->")
    return "\n".join(lines)


# ---------- comment commands: what the Action does ----------

def command_actions(issues: list[dict], team: dict | None = None,
                    masters: list[str] | None = None) -> list[tuple[int, dict]]:
    """[(issue number, action)] for every command in the fetched comments."""
    team = config.clean_team(team)
    masters = masters if masters is not None else team["sprintmasters"]
    out = []
    for i in issues:
        if is_board(i):
            continue
        for a in commands.fold(i, masters, team["who_can_claim"], team["ready_label"])["actions"]:
            out.append((i["number"], a))
    return out


def todo(issues: list[dict], team: dict | None = None, masters: list[str] | None = None,
         prev: dict | None = None) -> list[tuple[int, dict]]:
    """The actions not carried out yet. With no record of handled comments (first run, or a
    board from before commands existed) nothing is done: old comments are not replayed."""
    prev = prev if prev is not None else read_state(issues)
    if not prev or not isinstance(prev.get("seen"), list):
        return []
    seen = set(prev["seen"])
    return [(n, a) for n, a in command_actions(issues, team, masters) if a["comment"] not in seen]


def act(repo: str, actions: list[tuple[int, dict]], masters: list[str]) -> list[str]:
    """Carry out the actions with gh. Returns one line per action for the log."""
    log = []
    for n, a in actions:
        do, who = a["do"], a.get("who") or ""
        if do == "assign":
            ok = gh("issue", "edit", str(n), "--repo", repo, "--add-assignee", who) is not None
        elif do == "unassign":
            ok = gh("issue", "edit", str(n), "--repo", repo, "--remove-assignee", who) is not None
        elif do == "label":
            ok = gh("issue", "edit", str(n), "--repo", repo, "--add-label", a["label"]) is not None
        elif do == "reply":
            text = commands.reply_text(a, masters)
            ok = bool(text) and gh("issue", "comment", str(n), "--repo", repo,
                                   body=REPLY_MARKER + "\n" + text) is not None
        else:
            continue
        log.append(f"#{n} {do} {who}".strip() + ("" if ok else " (failed)"))
    return log


def build(issues: list[dict], now: datetime.datetime | None = None,
          fallback: dict | None = None, team: dict | None = None,
          masters: list[str] | None = None) -> tuple[str, dict, list[dict]]:
    """(board text, new saved state, new events). `fallback` is used when the board issue has
    no saved state yet, e.g. the local dashboard's own previous snapshot."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    now_ts = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows, _ = compute(issues, team, masters)
    prev = read_state(issues) or fallback
    new = diff(prev, rows, {i["number"] for i in issues if not is_board(i)}, now_ts)
    events = ((prev or {}).get("events") or []) + new
    # Every command comment seen so far, handled or not, so it is never carried out twice
    seen = list((prev or {}).get("seen") or [])
    known = set(seen)
    seen += [a["comment"] for _, a in command_actions(issues, team, masters)
             if a["comment"] and a["comment"] not in known and not known.add(a["comment"])]
    state = {"v": 1, "rows": snapshot(rows), "events": events[-MAX_EVENTS:], "seen": seen[-MAX_SEEN:]}
    return render(issues, now, state, team, masters), state, new


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
           now: datetime.datetime | None = None, team: dict | None = None,
           masters: list[str] | None = None) -> dict:
    """The state that feed.py, projects.py, dashboard.py and serve.py read."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rows, free = compute(issues, team, masters)
    return {"v": 1, "repo": repo, "generated": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "rows": rows, "free": free, "events": state["events"], "new_events": new,
            "team": config.clean_team(team)}


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--dry-run", action="store_true", help="only print the table, save nothing")
    ap.add_argument("--act", action="store_true",
                    help="carry out new comment commands (assign, reply, label); the Action uses this")
    ap.add_argument("--state-out", help="write the state and new events as JSON here")
    ap.add_argument("--html", help="write the static dashboard (one HTML file) here")
    ap.add_argument("--config", default=config.TEAM_FILE,
                    help="team settings file (default: .github/devsprinter.json in this folder)")
    args = ap.parse_args()
    team = config.team_at(".") if args.config == config.TEAM_FILE else \
        config.team_from_text(Path(args.config).read_text(encoding="utf-8"))
    masters = config.sprintmasters(team, args.repo)
    issues = fetch(args.repo)
    actions = todo(issues, team, masters)
    if args.dry_run:
        for n, a in actions:
            print(f"Would do: #{n} {a['do']} {a.get('who') or a.get('label') or ''}".rstrip())
    elif args.act and actions:
        for line in act(args.repo, actions, masters):
            print(line)
        # Changes made with the Action's own token start no new run, so show them now
        by_n = {i["number"]: i for i in issues}
        for n, a in actions:
            if a["do"] == "label" and n in by_n:
                by_n[n].setdefault("labels", {}).setdefault("nodes", []).append({"name": a["label"]})
    body, state, new = build(issues, team=team, masters=masters)
    print(STATE_RE.sub("", body).replace("\n\n## ", "\n## ", 1) if args.dry_run
          else publish(args.repo, issues, body))
    if args.state_out or args.html:
        data = export(args.repo, issues, state, new, team=team, masters=masters)
        if args.state_out:
            Path(args.state_out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.html:
            import dashboard
            Path(args.html).parent.mkdir(parents=True, exist_ok=True)
            Path(args.html).write_text(dashboard.render(data), encoding="utf-8")
            print(f"Dashboard: {Path(args.html).resolve()}")


if __name__ == "__main__":
    main()
