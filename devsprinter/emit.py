"""Hook receiver: turns Claude Code hook JSON into Devsprinter events (schema v1).

Called by hooks (SessionStart, PostToolUse, Stop, SessionEnd) with hook JSON on stdin.
- Keeps state per session in ~/.devsprinter/<session>.json, because the plan tools only
  send one step or one delta at a time (see docs/architecture.md).
- Appends every event to ~/.devsprinter/events.jsonl.
- If the session belongs to a task, push.py is started in the background. push.py only
  sends anything if the task is claimed (local marker from claim.py, or issue assignee),
  and by default only when a milestone (25/50/75/100 %) is crossed.
Always exits with code 0, so the agent is never blocked.

Env: DEVSPRINTER_HOME (state folder), DEVSPRINTER_TASK, DEVSPRINTER_FEATURE,
DEVSPRINTER_ACTOR, DEVSPRINTER_NO_PUSH=1 (local log only).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import config

SCHEMA_VERSION = 1
TITLE_MAX = 60
PLAN_TOOLS = {"TaskCreate", "TaskUpdate", "TodoWrite", "mcp__ccd_turn__update_plan"}
# Plan tool statuses -> schema statuses
STATUS = {"pending": "todo", "in_progress": "doing", "completed": "done"}
CLAIM_FILE = "devsprinter-claim"
DOTFILE = ".devsprinter"


def home() -> Path:
    return Path(os.environ.get("DEVSPRINTER_HOME", Path.home() / ".devsprinter"))


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_id(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session)[:80] or "unknown"


def milestone(done: int | None, total: int | None) -> int:
    """The last milestone reached: 0, 25, 50, 75 or 100 (percent of the plan's steps done)."""
    if not total:
        return 0
    return 25 * (4 * min(done or 0, total) // total)


def state_path(session: str) -> Path:
    return home() / f"{safe_id(session)}.json"


def load_state(session: str) -> dict | None:
    try:
        return json.loads(state_path(session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(state: dict) -> None:
    path = state_path(state["session"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


class Lock:
    """A simple file lock per session, so parallel hooks do not overwrite each other's state."""

    def __init__(self, path: Path, wait: float = 2.0, stale: float = 10.0):
        self.path, self.wait, self.stale, self.held = path, wait, stale, False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.wait
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                self.held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    return self  # better a rare race than a hanging hook
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.held:
            try:
                self.path.unlink()
            except OSError:
                pass


# --- Linking a session to a task -------------------------------------------------

def run(cwd: str, *cmd: str) -> str | None:
    try:
        out = subprocess.run(cmd, cwd=cwd or None, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def git(cwd: str, *args: str) -> str | None:
    return run(cwd, "git", *args)


def parse_repo(url: str | None) -> str | None:
    """https://github.com/a/b.git or git@github.com:a/b.git -> a/b"""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url or "")
    return m.group(1) if m else None


def parse_task(branch: str | None) -> str | None:
    """api/33-parser -> #33, 33-x -> #33, feature/x-12 -> None (the number must start a segment)."""
    m = re.search(r"(?:^|/)(\d+)(?:[-_]|$)", branch or "")
    return f"#{m.group(1)}" if m else None


def read_dotfile(cwd: str) -> dict:
    """.devsprinter in the working folder: lines like 'task=33' and 'feature=login'."""
    try:
        text = (Path(cwd) / DOTFILE).read_text(encoding="utf-8")
    except OSError:
        return {}
    pairs = (line.split("=", 1) for line in text.splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def read_claim(git_dir: str | None) -> str | None:
    """Local claim marker in the .git folder (never committed, one per worktree). Written by claim.py."""
    if not git_dir:
        return None
    try:
        text = (Path(git_dir) / CLAIM_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return f"#{text.lstrip('#')}" if text.lstrip("#").isdigit() else None


def resolve_context(cwd: str) -> dict:
    dot = read_dotfile(cwd)
    branch = git(cwd, "symbolic-ref", "--short", "HEAD")  # works before the first commit too
    git_dir = git(cwd, "rev-parse", "--absolute-git-dir")
    claim = read_claim(git_dir)
    task = (claim or os.environ.get("DEVSPRINTER_TASK") or dot.get("task")
            or parse_task(branch))
    if task and not task.startswith("#"):
        task = f"#{task}"
    # GitHub handle: gh reads its local config (no network)
    actor = (os.environ.get("DEVSPRINTER_ACTOR") or git(cwd, "config", "github.user")
             or run(cwd, "gh", "config", "get", "-h", "github.com", "user")
             or git(cwd, "config", "user.name") or "unknown")
    return {
        "cwd": cwd,
        "branch": branch,
        "git_dir": git_dir,
        "claimed": bool(claim),
        "repo": parse_repo(git(cwd, "remote", "get-url", "origin")),
        "task": task,
        "feature": os.environ.get("DEVSPRINTER_FEATURE") or dot.get("feature"),
        "actor": actor,
    }


# --- Plan logic --------------------------------------------------------------------

def short(title) -> str:
    title = " ".join(str(title or "").split())
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1] + "…"


def new_state(session: str, cwd: str) -> dict:
    return {"session": session, "plan_rev": 0, "steps": [], "seq": 0,
            "started": now_iso(), "last_type": None, **resolve_context(cwd)}


def bump_rev(state: dict) -> None:
    """A new plan version when the plan changes after work has started (or for the first plan)."""
    if state["plan_rev"] == 0 or any(s["status"] != "todo" for s in state["steps"]):
        state["plan_rev"] += 1
        state["_rev_open"] = True


def replace_plan(state: dict, items: list, title_key: str) -> None:
    steps = [{"id": str(i + 1), "title": short(it.get(title_key)),
              "status": STATUS.get(it.get("status"), "todo")} for i, it in enumerate(items or [])]
    if [s["title"] for s in steps] != [s["title"] for s in state["steps"]]:
        bump_rev(state)
    state["steps"] = steps


def apply_update_plan(state: dict, inp: dict) -> str | None:
    """The desktop app's mcp__ccd_turn__update_plan: the whole list, or a delta."""
    steps = state["steps"]
    if "items" in inp:
        replace_plan(state, inp["items"], "content")
        return "plan"
    if not steps:
        return None  # a delta without a known plan (e.g. hook installed mid-session)
    if inp.get("advance"):
        cur = next((i for i, s in enumerate(steps) if s["status"] == "doing"), None)
        if cur is not None:
            steps[cur]["status"] = "done"
        nxt = next((s for s in steps if s["status"] == "todo"), None)
        if nxt:
            nxt["status"] = "doing"
    for n in inp.get("done") or []:
        if isinstance(n, int) and 1 <= n <= len(steps):
            steps[n - 1]["status"] = "done"
    start = inp.get("start")
    if isinstance(start, int) and 1 <= start <= len(steps):
        for s in steps:
            if s["status"] == "doing":
                s["status"] = "done"
        steps[start - 1]["status"] = "doing"
    return "step"


def apply_tool(state: dict, tool: str, inp: dict, resp) -> str | None:
    steps = state["steps"]
    if tool == "mcp__ccd_turn__update_plan":
        return apply_update_plan(state, inp)
    if tool == "TodoWrite":
        replace_plan(state, inp.get("todos"), "content")
        return "plan"
    if tool == "TaskCreate":
        task_id = ((resp or {}).get("task") or {}).get("id") if isinstance(resp, dict) else None
        # Several TaskCreate calls in a row (no TaskUpdate in between) belong to one plan version
        if not state.get("_rev_open"):
            bump_rev(state)
        steps.append({"id": str(task_id or len(steps) + 1), "title": short(inp.get("subject")),
                      "status": "todo"})
        return "plan"
    if tool == "TaskUpdate":
        state.pop("_rev_open", None)
        step = next((s for s in steps if s["id"] == str(inp.get("taskId"))), None)
        if step is None:
            return None
        if inp.get("status") == "deleted":
            steps.remove(step)
            bump_rev(state)
            return "plan"
        if inp.get("subject"):
            step["title"] = short(inp["subject"])
        if inp.get("status") in STATUS:
            step["status"] = STATUS[inp["status"]]
        return "step"
    return None


def progress(state: dict) -> tuple[int, int, str | None]:
    """(steps done, steps in total, title of the step in progress)."""
    steps = state["steps"]
    done = sum(s["status"] == "done" for s in steps)
    current = next((s["title"] for s in steps if s["status"] == "doing"), None)
    return done, len(steps), current


def to_event(state: dict, etype: str) -> dict:
    done, total, current = progress(state)
    return {
        "v": SCHEMA_VERSION, "ts": now_iso(), "actor": state["actor"], "agent": "claude-code",
        "session": state["session"], "repo": state["repo"], "task": state["task"],
        "feature": state["feature"], "type": etype, "plan_rev": state["plan_rev"],
        "steps": [{"n": i + 1, "title": s["title"], "status": s["status"]}
                  for i, s in enumerate(state["steps"])],
        "progress": {"done": done, "total": total}, "milestone": milestone(done, total),
        "current": current,
    }


def handle(payload: dict) -> dict | None:
    """One hook call -> one event (or None if the call does not touch the plan)."""
    hook = payload.get("hook_event_name")
    session = str(payload.get("session_id") or "unknown")
    tool = payload.get("tool_name")
    if hook == "PostToolUse" and tool not in PLAN_TOOLS:
        return None
    lock_path = home() / f"{safe_id(session)}.lock"
    with Lock(lock_path):
        state = load_state(session) or new_state(session, payload.get("cwd") or os.getcwd())
        claim = read_claim(state.get("git_dir"))  # cheap file check, so a mid-session claim is noticed
        state["claimed"] = bool(claim)
        if claim:
            state["task"] = claim
        if hook == "SessionStart":
            state.update(resolve_context(payload.get("cwd") or state["cwd"]))
            etype = "started"
        elif hook == "PostToolUse":
            inp = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            etype = apply_tool(state, tool, inp, payload.get("tool_response"))
        elif hook == "Stop":
            etype = "heartbeat"
        elif hook == "SessionEnd":
            steps = state["steps"]
            etype = "done" if steps and all(s["status"] == "done" for s in steps) else "paused"
        else:
            etype = None
        if state.get("task") and state.get("since_task") != state["task"]:
            # When this session began on the task: the board shows "working for 1 h 20 min"
            state["since"], state["since_task"] = now_iso(), state["task"]
        if etype is None:
            save_state(state)
            return None
        state["seq"] += 1
        state["last_type"] = etype
        state["last_ts"] = now_iso()
        save_state(state)
        event = to_event(state, etype)
    log = home() / "events.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def spawn_push(session: str) -> None:
    """Start push.py detached, so the hook returns at once."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen([sys.executable, str(Path(__file__).with_name("push.py")), session],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags,
                     start_new_session=sys.platform != "win32")


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    event = handle(json.loads(raw))
    if event and event["task"] and config.setting("push"):
        spawn_push(event["session"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never block the agent
        try:
            with (home() / "errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{now_iso()} emit: {exc!r}\n")
        except OSError:
            pass
    sys.exit(0)
