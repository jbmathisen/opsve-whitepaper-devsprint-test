"""Settings: one team file in the repo and one personal file on this computer.

Team settings live in the repo as `.github/devsprinter.json`, so everyone, the board workflow,
the hooks and the dashboard use the same values:

    {"quiet_minutes": 30, "stale_minutes": 240, "ready_label": "ready"}

- quiet_minutes: no signal for this long and a task shows as quiet.
- stale_minutes: no signal for this long and it is stale (someone should check on it).
- ready_label: the label an issue needs before it can be started from the dashboard.

Open sprints (anyone may join with a comment, a fork PR or any LLM) add, all optional:

    {"sprintmasters": ["anna"], "who_can_claim": "anyone", "claim_stale_hours": 72,
     "waiting_labels": {"board": "the board"}, "input_labels": ["input"], "trusted": ["anna", "bo"],
     "content_types": [".html", ".md", ".css"]}

- sprintmasters: 1-2 accounts that approve work and may use /ready and /release @someone.
  Empty: the repo owner.
- who_can_claim: "anyone" (open communities) or "collaborators".
- claim_stale_hours: a claim made with a comment (people, not agents) turns stale after this
  long without a comment from that person.
- waiting_labels: label -> who it waits on. The board lists those issues as waiting, not free.
- input_labels: issues open for input from everyone (questions, proposals). Nobody takes them;
  people give their view in a comment. Default: ["input"].
- trusted: accounts whose PRs the PR check does not hold back.
- content_types: file endings a PR may change without being flagged. Empty: any type.

Personal settings live in `~/.devsprinter/config.json` and never leave this computer:

    {"signal": "milestones", "push": true, "context": true, "launch": "auto", "worktrees": ""}

The dashboard's Setup page writes both. Environment variables win over the files
(DEVSPRINTER_SIGNAL, DEVSPRINTER_NO_PUSH, DEVSPRINTER_NO_CONTEXT, DEVSPRINTER_READY_LABEL).
Every value is checked; a broken or missing file gives the defaults.
"""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

TEAM_FILE = ".github/devsprinter.json"
TEAM_DEFAULTS = {"quiet_minutes": 30, "stale_minutes": 240, "ready_label": "ready",
                 "sprintmasters": [], "who_can_claim": "anyone", "claim_stale_hours": 72,
                 "waiting_labels": {}, "input_labels": ["input"], "trusted": [], "content_types": []}
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
# Ready-made choices for teams whose tasks are short, mixed or long: (quiet, stale) in minutes
PRESETS = {"short": (10, 60), "mixed": (30, 240), "long": (60, 480)}
LOCAL_DEFAULTS = {"signal": "milestones", "push": True, "context": True, "launch": "auto", "worktrees": ""}
ENV = {"signal": "DEVSPRINTER_SIGNAL", "push": "DEVSPRINTER_NO_PUSH",
       "context": "DEVSPRINTER_NO_CONTEXT", "ready_label": "DEVSPRINTER_READY_LABEL"}
MAX_MINUTES = 7 * 24 * 60


def _home() -> Path:
    return Path(os.environ.get("DEVSPRINTER_HOME", Path.home() / ".devsprinter"))


def _int(value, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(low, min(high, int(value)))


# ---------- team ----------

def clean_team(raw) -> dict:
    """Checked team settings. Stale is always later than quiet."""
    raw = raw if isinstance(raw, dict) else {}
    quiet = _int(raw.get("quiet_minutes"), TEAM_DEFAULTS["quiet_minutes"], 1, MAX_MINUTES - 1)
    stale = _int(raw.get("stale_minutes"), TEAM_DEFAULTS["stale_minutes"], 2, MAX_MINUTES)
    if stale <= quiet:
        stale = quiet + 1
    label = raw.get("ready_label", TEAM_DEFAULTS["ready_label"])
    label = " ".join(str(label).split())[:50] if isinstance(label, str) else TEAM_DEFAULTS["ready_label"]
    return {"quiet_minutes": quiet, "stale_minutes": stale, "ready_label": label,
            "sprintmasters": _logins(raw.get("sprintmasters"))[:2],
            "who_can_claim": "collaborators" if raw.get("who_can_claim") == "collaborators" else "anyone",
            "claim_stale_hours": _int(raw.get("claim_stale_hours"), TEAM_DEFAULTS["claim_stale_hours"], 1, 24 * 60),
            "waiting_labels": _waiting(raw.get("waiting_labels")),
            "input_labels": _labels(raw.get("input_labels"), TEAM_DEFAULTS["input_labels"]),
            "trusted": _logins(raw.get("trusted")),
            "content_types": _types(raw.get("content_types"))}


def _logins(value) -> list[str]:
    """GitHub account names only (no @, no spaces), at most 50."""
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        v = str(v).strip().lstrip("@") if isinstance(v, str) else ""
        if LOGIN_RE.match(v) and v.lower() not in (o.lower() for o in out):
            out.append(v)
    return out[:50]


def _waiting(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    for k, v in list(value.items())[:20]:
        k = " ".join(str(k).split())[:50]
        v = " ".join(str(v).split())[:40] if isinstance(v, str) else ""
        if k:
            out[k] = v or k
    return out


def _labels(value, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    out = []
    for v in value[:20]:
        v = " ".join(str(v).split())[:50] if isinstance(v, str) else ""
        if v and v.lower() not in (o.lower() for o in out):
            out.append(v)
    return out


def _types(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for v in value[:30]:
        v = str(v).strip().lower() if isinstance(v, str) else ""
        v = v if v.startswith(".") else "." + v if v else ""
        if re.fullmatch(r"\.[a-z0-9]{1,10}", v) and v not in out:
            out.append(v)
    return out


def sprintmasters(team: dict, repo: str | None = None) -> list[str]:
    """The sprintmasters, or the repo owner when none are set."""
    masters = clean_team(team)["sprintmasters"]
    if not masters and repo and "/" in repo:
        masters = [repo.split("/", 1)[0]]
    return masters


def team_from_text(text: str | None) -> dict:
    try:
        return clean_team(json.loads(text or ""))
    except ValueError:
        return clean_team(None)


def team_at(root: str | Path | None) -> dict:
    """Team settings from a checkout (the board workflow and the hooks read it from disk)."""
    if not root:
        return clean_team(None)
    try:
        return team_from_text((Path(root) / TEAM_FILE).read_text(encoding="utf-8"))
    except OSError:
        return clean_team(None)


def team_text(team: dict) -> str:
    return json.dumps(clean_team(team), indent=2) + "\n"


def _gh(*args: str, data: bytes | None = None) -> tuple[bool, str]:
    try:
        out = subprocess.run(["gh", *args], capture_output=True, timeout=30, input=data)
    except (OSError, subprocess.SubprocessError) as e:
        return False, type(e).__name__
    text = (out.stdout if out.returncode == 0 else out.stderr).decode("utf-8", errors="replace")
    return out.returncode == 0, text.strip()


def team_remote(repo: str) -> tuple[dict, str | None]:
    """(team settings, sha of the file on the default branch, or None if there is no file)."""
    ok, out = _gh("api", f"repos/{repo}/contents/{TEAM_FILE}")
    if not ok:
        return clean_team(None), None
    try:
        meta = json.loads(out)
        text = base64.b64decode(meta.get("content") or "").decode("utf-8")
    except (ValueError, TypeError):
        return clean_team(None), None
    return team_from_text(text), meta.get("sha")


def save_team_remote(repo: str, team: dict, sha: str | None) -> tuple[bool, str]:
    """Commit the team file to the default branch with the user's own gh login."""
    team = clean_team(team)
    body = {"message": f"Devsprinter settings: quiet after {team['quiet_minutes']} min, "
                       f"stale after {team['stale_minutes']} min",
            "content": base64.b64encode(team_text(team).encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    ok, out = _gh("api", "-X", "PUT", f"repos/{repo}/contents/{TEAM_FILE}", "--input", "-",
                  data=json.dumps(body).encode("utf-8"))
    if ok:
        return True, f"Saved {TEAM_FILE} in {repo}."
    return False, out[:300] or "GitHub refused the change."


# ---------- personal ----------

def clean_local(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = dict(LOCAL_DEFAULTS)
    if raw.get("signal") in ("milestones", "steps"):
        out["signal"] = raw["signal"]
    for k in ("push", "context"):
        if isinstance(raw.get(k), bool):
            out[k] = raw[k]
    if raw.get("launch") in ("auto", "none"):
        out["launch"] = raw["launch"]
    if isinstance(raw.get("worktrees"), str):
        out["worktrees"] = raw["worktrees"].strip()[:500]
    return out


def load_local() -> dict:
    try:
        return clean_local(json.loads((_home() / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return clean_local(None)


def save_local(values: dict) -> dict:
    clean = clean_local({**load_local(), **(values if isinstance(values, dict) else {})})
    path = _home() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    return clean


def overridden(name: str) -> str | None:
    """The environment variable that currently decides `name`, if any."""
    var = ENV.get(name)
    return var if var and os.environ.get(var) is not None and os.environ.get(var) != "" else None


def setting(name: str):
    """A personal setting with the environment applied on top of the file."""
    if name == "signal" and overridden("signal"):
        return "steps" if os.environ["DEVSPRINTER_SIGNAL"].strip().lower() == "steps" else "milestones"
    if name in ("push", "context") and overridden(name):
        return False
    return load_local()[name]
