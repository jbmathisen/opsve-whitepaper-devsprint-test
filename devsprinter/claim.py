"""Claiming is a deliberate choice: `python claim.py 33` takes issue #33 in this worktree.

1. Checks on GitHub whether someone else already has #33 (assignee or Devsprinter comment).
   If it is taken it stops with exit code 3, unless `--force` is given. Closed issue: also 3.
2. Makes you the assignee (`gh issue edit --add-assignee @me`).
3. Writes the local marker `<.git folder>/devsprinter-claim`. It is never committed and only
   applies to this worktree. From now on the hooks send progress to the issue.

`python claim.py --release` releases the claim: removes the marker, the assignee and your
Devsprinter comment on the issue, so others can see the task is free.

Without a GitHub remote or network it is only the local marker (with a warning).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from context import describe, fetch_issue
from emit import CLAIM_FILE, git, read_claim, resolve_context

TAKEN = 3


def gh(cwd: str, *args: str) -> str | None:
    """stdout on success ("" if empty, e.g. DELETE), None on failure."""
    try:
        out = subprocess.run(["gh", *args], cwd=cwd or None, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", errors="replace").strip() if out.returncode == 0 else None


def do_claim(cwd: str, number: str, force: bool = False) -> tuple[int, str]:
    git_dir = git(cwd, "rev-parse", "--absolute-git-dir")
    if not git_dir:
        return 1, "Not in a git repository."
    task = f"#{number}"
    marker = Path(git_dir) / CLAIM_FILE
    if read_claim(git_dir) == task:
        return 0, f"{task} is already claimed in this worktree."
    ctx = resolve_context(cwd)
    repo, me = ctx.get("repo"), ctx.get("actor") or ""
    notes = []
    if not repo:
        notes.append("Warning: no GitHub remote (origin). Local claim only, nothing is sent.")
    else:
        issue = fetch_issue(repo, task, cwd, fresh=True)
        if issue is None:
            notes.append(f"Warning: could not read {task} in {repo} (does it exist? is gh logged in?). "
                         "Local claim only.")
        else:
            if issue.get("state") != "OPEN" and not force:
                return TAKEN, f"{task} is closed. Run with --force if you want it anyway."
            other = describe(task, issue, me, session="")
            if other and not force:
                return TAKEN, (f"{task} is already taken, so it was not claimed:\n{other}\n"
                               "Talk to whoever has it, or run with --force to take it anyway.")
            if other:
                notes.append(f"Note: taken with --force despite:\n{other}")
            assignees = [a["login"].lower() for a in (issue.get("assignees") or {}).get("nodes") or []]
            if me.lower() not in assignees:
                if gh(cwd, "issue", "edit", number, "--repo", repo, "--add-assignee", "@me") is None:
                    notes.append(f"Warning: could not make you the assignee of {task}.")
                else:
                    notes.append(f"You are now the assignee of {task}.")
    marker.write_text(number + "\n", encoding="utf-8")
    where = f"{repo}{task}" if repo else task
    notes.insert(0, f"Claimed {where} in this worktree. Progress from the agent's plan is now "
                    "sent to the issue automatically, at each milestone (25/50/75/100 %).")
    return 0, "\n".join(notes)


def do_release(cwd: str) -> tuple[int, str]:
    git_dir = git(cwd, "rev-parse", "--absolute-git-dir")
    if not git_dir:
        return 1, "Not in a git repository."
    task = read_claim(git_dir)
    (Path(git_dir) / CLAIM_FILE).unlink(missing_ok=True)
    if not task:
        return 0, "No claim in this worktree."
    notes = [f"Released {task}. Local log only from now on."]
    ctx = resolve_context(cwd)
    repo, me = ctx.get("repo"), ctx.get("actor") or ""
    if repo:
        number = task.lstrip("#")
        if gh(cwd, "issue", "edit", number, "--repo", repo, "--remove-assignee", "@me") is not None:
            notes.append(f"You are no longer the assignee of {task}.")
        ids = gh(cwd, "api", f"repos/{repo}/issues/{number}/comments", "--paginate", "--jq",
                 f'.[] | select(.user.login == "{me}") '
                 f'| select(.body | startswith("<!-- devsprinter actor={me} -->")) | .id')
        for cid in (ids or "").split():
            if gh(cwd, "api", "-X", "DELETE", f"repos/{repo}/issues/comments/{cid}") is not None:
                notes.append("Removed your Devsprinter comment from the issue.")
    return 0, "\n".join(notes)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles are cp1252 otherwise
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("issue", nargs="?", help="issue number, e.g. 33")
    ap.add_argument("--release", action="store_true", help="release the claim")
    ap.add_argument("--force", action="store_true", help="take it even if someone else has it")
    args = ap.parse_args()
    if args.release:
        code, msg = do_release(os.getcwd())
    else:
        number = (args.issue or "").lstrip("#")
        if not number.isdigit():
            ap.error("give an issue number, e.g. 33")
        code, msg = do_claim(os.getcwd(), number, args.force)
    (sys.stdout if code == 0 else sys.stderr).write(msg + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
