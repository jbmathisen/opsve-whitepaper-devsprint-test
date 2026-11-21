"""Comment commands: how people and any LLM join a sprint without the plugin.

A command is a line in an issue comment that starts with one of:

    /claim              take the task (refused if someone else has it)
    /join               work on it together with whoever has it (reviews, pairs)
    /release            let go of it; a sprintmaster may write /release @someone
    /done               finished, waiting for the sprintmaster
    /waiting <whom>     waiting on @user, #12, or a few words ("the board")
    /back               not waiting any more
    /ready              (sprintmasters) mark the task as free to take

A command only counts for the comment's author, so nobody can claim for someone else. Text
after the command is data, cut to 40 characters. Commands from bots are ignored.

`fold(issue, ...)` replays an issue's comments in order and returns who is on the task, their
state and what the Action should do (assign, unassign, reply, add a label). board.py turns the
people into rows and, in the Action, carries out the actions once per comment.
"""
import re

COMMANDS = ("claim", "join", "release", "done", "waiting", "back", "ready")
LINE_RE = re.compile(r"^[ \t]*/(" + "|".join(COMMANDS) + r")\b[ \t]*(.*)$", re.M | re.I)
MENTION_RE = re.compile(r"^@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\b")
ISSUE_RE = re.compile(r"^#(\d{1,7})\b")
TEAM_ASSOC = {"OWNER", "MEMBER", "COLLABORATOR"}
MAX_COMMANDS = 3  # per comment


def parse(body: str) -> list[tuple[str, str]]:
    """[(command, argument)] in order, at most MAX_COMMANDS. Code blocks are skipped."""
    body = re.sub(r"```.*?```", "", body or "", flags=re.S)
    out = []
    for m in LINE_RE.finditer(body):
        arg = " ".join(m.group(2).split())[:40]
        out.append((m.group(1).lower(), arg))
        if len(out) == MAX_COMMANDS:
            break
    return out


def target(arg: str) -> dict:
    """What /waiting waits on: {"user": login} | {"issue": n} | {"text": words}."""
    m = MENTION_RE.match(arg)
    if m:
        return {"user": m.group(1)}
    m = ISSUE_RE.match(arg)
    if m:
        return {"issue": int(m.group(1))}
    return {"text": arg or "someone"}


def is_bot(comment: dict) -> bool:
    author = comment.get("author") or {}
    login = author.get("login") or ""
    return author.get("__typename") == "Bot" or login.endswith("[bot]") or login == "github-actions"


def fold(issue: dict, masters: list[str], who_can_claim: str = "anyone",
         ready_label: str = "ready") -> dict:
    """Replay the comments. Returns {"people": {login_lower: person}, "actions": [...]}.

    person: {"who", "role" (claim|join), "since", "last", "done", "waiting"}.
    The issue's assignees count as holders too, so /claim on an assigned task is refused.
    action: {"comment": id, "do": assign|unassign|reply|label, "who"?, "text"?, "label"?}
    """
    masters_l = {m.lower() for m in masters}
    people: dict[str, dict] = {}
    actions: list[dict] = []
    assignees = [a["login"] for a in (issue.get("assignees") or {}).get("nodes") or [] if a.get("login")]
    labels = {lb["name"] for lb in (issue.get("labels") or {}).get("nodes") or [] if lb.get("name")}

    def holders() -> list[str]:
        return [p["who"] for p in people.values()] or assignees

    for c in (issue.get("comments") or {}).get("nodes") or []:
        if is_bot(c):
            continue
        who = (c.get("author") or {}).get("login") or ""
        if not who:
            continue
        me, cid, ts = who.lower(), c.get("id") or "", c.get("createdAt")
        is_master = me in masters_l
        # Any comment from someone on the task counts as a sign of life; one from the person
        # they wait on ends the wait.
        if me in people:
            people[me]["last"] = ts
        for p in people.values():
            w = p.get("waiting") or {}
            if w.get("user", "").lower() == me and p["who"].lower() != me:
                p["waiting"] = None

        for cmd, arg in parse(c.get("body") or ""):
            if cmd in ("claim", "join"):
                if who_can_claim == "collaborators" and c.get("authorAssociation") not in TEAM_ASSOC \
                        and not is_master:
                    actions.append({"comment": cid, "do": "reply", "who": who, "text": "collaborators"})
                    continue
                others = [h for h in holders() if h.lower() != me]
                if cmd == "claim" and others:
                    actions.append({"comment": cid, "do": "reply", "who": who, "text": "taken",
                                    "holders": others})
                    continue
                if me not in people:
                    people[me] = {"who": who, "role": cmd if others else "claim", "since": ts,
                                  "last": ts, "done": False, "waiting": None}
                    actions.append({"comment": cid, "do": "assign", "who": who})
                else:
                    people[me].update(done=False, last=ts)
            elif cmd == "release":
                m = MENTION_RE.match(arg)
                gone = m.group(1) if m and is_master else who
                if people.pop(gone.lower(), None) is not None or gone.lower() in (a.lower() for a in assignees):
                    actions.append({"comment": cid, "do": "unassign", "who": gone})
            elif cmd in ("done", "waiting", "back"):
                p = people.get(me)
                if p is None:
                    continue
                if cmd == "done":
                    p.update(done=True, waiting=None)
                elif cmd == "waiting":
                    p["waiting"] = target(arg)
                else:
                    p["waiting"] = None
            elif cmd == "ready":
                if not is_master:
                    actions.append({"comment": cid, "do": "reply", "who": who, "text": "not-master"})
                elif ready_label and ready_label not in labels:
                    labels.add(ready_label)
                    actions.append({"comment": cid, "do": "label", "label": ready_label})
    return {"people": people, "actions": actions}


def reply_text(action: dict, masters: list[str]) -> str:
    """The Action's short answer to a refused command. Only logins, never issue text."""
    who = action.get("who") or "?"
    kind = action.get("text")
    if kind == "taken":
        held = ", ".join("@" + h for h in action.get("holders") or [])
        return (f"@{who} {held} already has this task. Write `/join` to work on it together, "
                f"or ask {held} first.")
    if kind == "not-master":
        sm = ", ".join("@" + m for m in masters) or "the sprintmaster"
        return f"@{who} only {sm} can mark a task as ready."
    if kind == "collaborators":
        return f"@{who} in this repo only collaborators can take tasks. Comment here and a sprintmaster will help."
    return ""
