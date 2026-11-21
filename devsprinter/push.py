"""Sends a session's progress to GitHub as ONE sticky comment on the task's issue.

Started in the background by emit.py: `python push.py <session>`.
- Claimed tasks only: a local marker (claim.py) or the actor being an assignee on the issue.
  The assignee check is cached for 10 min. Without a claim nothing is sent.
- The issue, not the PR, because there is no PR when the work starts.
- Milestones, not every step (the default; set on the dashboard's Setup page or with
  DEVSPRINTER_SIGNAL): the comment is
  only rewritten when the plan crosses 25, 50, 75 or 100 %, when the agent replans, when the
  session pauses or finishes, or every 15 minutes as a heartbeat so "last active" stays true.
  DEVSPRINTER_SIGNAL=steps updates it on every step instead.
- Debounce: at most one write per 30 s and session. Whoever holds the push lock waits out the
  window and then sends the *latest* state. Other calls exit at once.
- Updates the comment marked <!-- devsprinter actor=<actor> --> or creates it.

By hand: `python push.py <session> --dry-run` prints the comment and the gh calls without
sending anything.
"""
import argparse
import datetime
import json
import subprocess
import sys
import time

import config
from emit import Lock, home, load_state, milestone, now_iso, progress, safe_id, save_state

DEBOUNCE_S = 30
HEARTBEAT_S = 15 * 60
ASSIGNEE_TTL_S = 600
ICON = {"done": "x", "doing": " ", "todo": " "}


def marker(actor: str) -> str:
    return f"<!-- devsprinter actor={actor} -->"


def signal_mode() -> str:
    return config.setting("signal")


def signature(state: dict) -> list:
    """What others need to know. The comment is rewritten only when this changes (or on heartbeat)."""
    done, total, _ = progress(state)
    finished = state.get("last_type") == "done" or (total and done == total)
    return [state.get("task"), state.get("plan_rev"), milestone(done, total), bool(finished),
            state.get("last_type") == "paused"]


def should_push(state: dict, now: float | None = None) -> bool:
    if signal_mode() == "steps":
        return True
    now = time.time() if now is None else now
    return (state.get("pushed_sig") != signature(state)
            or now - state.get("pushed_at", 0) >= HEARTBEAT_S)


def render(state: dict) -> str:
    steps = state["steps"]
    done, total, current = progress(state)
    pct = milestone(done, total)
    head = f"**@{state['actor']} is on {state['task']}**"
    if total:
        head += f" · plan v{state['plan_rev']} · {pct} % ({done}/{total} steps)"
        head += f" · now: *{current}*" if current else ""
    else:
        head += " · no plan yet"
    lines = [marker(state["actor"]), head, ""]
    if steps:
        lines += ["<details><summary>Plan</summary>", ""]
        for s in steps:
            title = f"**{s['title']}** ← now" if s["status"] == "doing" else s["title"]
            lines.append(f"- [{ICON[s['status']]}] {title}")
        lines += ["", "</details>"]
    last_ts = state.get("last_ts") or now_iso()
    ts = last_ts.replace("T", " ").replace("Z", " UTC")
    # A machine-readable line for collision protection (context.py). Hidden in GitHub's view.
    data = {"session": state["session"], "plan_rev": state["plan_rev"], "done": done,
            "total": total, "milestone": pct, "current": current, "ts": last_ts,
            "type": state.get("last_type"), "since": state.get("since")}
    # < and > are escaped, so a step title containing "-->" cannot end the HTML comment
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    lines.insert(1, f"<!-- devsprinter-data {blob} -->")
    lines += ["", f"<sub>Last signal: {state.get('last_type')} {ts} · session {state['session'][:8]}"
                  " · updated automatically by Devsprinter</sub>"]
    return "\n".join(lines)


def gh(state: dict, *args: str, body: str | None = None) -> str | None:
    cmd = ["gh", *args]
    if body is not None:
        cmd += ["-F", "body=@-"]
    try:
        # Bytes, not text mode: otherwise \n becomes \r\n in the comment on Windows
        out = subprocess.run(cmd, cwd=state.get("cwd") or None, capture_output=True, timeout=30,
                             input=body.encode("utf-8") if body is not None else None)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", errors="replace") if out.returncode == 0 else None


def find_target(state: dict) -> str | None:
    """repos/<owner>/<repo>/issues/<nr> for the task's issue."""
    if not (state.get("repo") and state.get("task")):
        return None
    return f"repos/{state['repo']}/issues/{state['task'].lstrip('#')}"


def is_claimed(state: dict) -> bool:
    """A local marker is enough. Otherwise: is the actor an assignee on the issue? (cached in state)"""
    if state.get("claimed"):
        return True
    cached = state.get("assignee_check") or {}
    if cached.get("task") == state["task"] and time.time() - cached.get("at", 0) < ASSIGNEE_TTL_S:
        return cached["ok"]
    out = gh(state, "issue", "view", state["task"].lstrip("#"), "--repo", state["repo"],
             "--json", "assignees", "--jq", ".assignees[].login")
    ok = out is not None and state["actor"].lower() in out.lower().split()
    with Lock(home() / f"{safe_id(state['session'])}.lock"):
        fresh = load_state(state["session"]) or state
        fresh["assignee_check"] = {"task": state["task"], "at": time.time(), "ok": ok}
        save_state(fresh)
    return ok


def upsert(state: dict, target: str, body: str) -> bool:
    """Update the existing sticky comment or create a new one."""
    listing = gh(state, "api", f"{target}/comments", "--paginate",
                 "--jq", f'.[] | select(.body | startswith("{marker(state["actor"])}")) | .id')
    if listing is None:
        return False
    ids = listing.split()
    repo = state["repo"]
    if ids:
        return gh(state, "api", "-X", "PATCH", f"repos/{repo}/issues/comments/{ids[0]}",
                  body=body) is not None
    return gh(state, "api", f"{target}/comments", body=body) is not None


def push(session: str, dry_run: bool = False) -> int:
    state = load_state(session)
    if not state or not state.get("task"):
        return 0
    if dry_run:
        print(render(state))
        print("\n--- would run:")
        claim = "local marker" if state.get("claimed") else "check assignee with gh issue view"
        print(f"claim: {claim}")
        print(f"signal: {signal_mode()} · would send now: {'yes' if should_push(state) else 'no'}")
        print(f"gh api {find_target(state) or '<no remote>'}/comments"
              "  (PATCH if the marker exists, otherwise POST)")
        return 0
    if not state.get("repo") or not should_push(state) or not is_claimed(state):
        return 0
    lock = Lock(home() / f"{safe_id(session)}.push.lock", wait=0, stale=DEBOUNCE_S * 3)
    with lock:
        if not lock.held:
            return 0  # someone else is already waiting and will send the latest state
        while True:
            state = load_state(session) or state
            wait = state.get("pushed_at", 0) + DEBOUNCE_S - time.time()
            if wait > 0:
                time.sleep(wait)
                state = load_state(session) or state
            if not should_push(state):
                return 0
            seq, sig = state["seq"], signature(state)
            target = find_target(state)
            if not target:
                return 0
            ok = upsert(state, target, render(state))
            with Lock(home() / f"{safe_id(session)}.lock"):
                fresh = load_state(session) or state
                fresh["pushed_at"] = time.time()
                if ok:
                    fresh["pushed_seq"], fresh["pushed_sig"] = seq, sig
                save_state(fresh)
            # New events while we were sending? Go round again after the next window.
            if not ok or fresh["seq"] == seq or not should_push(fresh):
                return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles are cp1252 otherwise; "←" breaks
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    push(args.session, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            with (home() / "errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} push: {exc!r}\n")
        except OSError:
            pass
    sys.exit(0)
