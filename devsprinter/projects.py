"""GitHub Projects: mirrors the sprint board into a Projects board (table or kanban).

`python projects.py state.json --project owner/number` reads the file that
`board.py --state-out` wrote and makes sure every open issue in the repo is in the project
with the fields:

  Devsprinter    single select: active, quiet, assigned, stale, done, free
  Who            accounts that have the task
  Plan           v2 · 3/5 (50 %)
  Now            the current step
  Last active    time of the latest signal (UTC), only changes when something happens

Missing fields are created. Only fields that changed are written. The project is given as
`owner/number` (the number in the project's URL), or in the environment as DEVSPRINTER_PROJECT.
With neither, the script does nothing and exits with 0.

Needs a token with project scope: locally `gh auth refresh -s project`,
in Actions a secret DEVSPRINTER_PROJECT_TOKEN (classic PAT with `project` and `repo`).
`--dry-run` shows what would change.
"""
import argparse
import json
import os
import subprocess
import sys

FIELD_STATE = "Devsprinter"
TEXT_FIELDS = ["Who", "Plan", "Now", "Last active"]
OPTIONS = [("active", "GREEN"), ("quiet", "YELLOW"), ("assigned", "GRAY"), ("stale", "RED"),
           ("done", "PURPLE"), ("free", "BLUE")]
ORDER = [o for o, _ in OPTIONS]
PROJECT_FIELDS = """id title url
fields(first:50){nodes{... on ProjectV2FieldCommon{id name dataType}
  ... on ProjectV2SingleSelectField{options{id name}}}}
items(first:100){nodes{id content{... on Issue{id number repository{nameWithOwner}}}
  fieldValues(first:30){nodes{
    ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2FieldCommon{name}}}
    ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2FieldCommon{name}}}}}}}"""


class GhError(RuntimeError):
    pass


def graphql(query: str, **variables) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise GhError(f"could not run gh: {type(e).__name__}") from e
    text = out.stdout.decode("utf-8", errors="replace")
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {}
    if out.returncode != 0 or data.get("errors"):
        msg = "; ".join(e.get("message", "") for e in data.get("errors") or []) or \
            out.stderr.decode("utf-8", errors="replace").strip()
        raise GhError(msg or "unknown error")
    return data.get("data") or {}


def load_project(owner: str, number: int) -> dict:
    errors = []
    for kind in ("user", "organization"):
        q = f"query($o:String!,$n:Int!){{{kind}(login:$o){{projectV2(number:$n){{{PROJECT_FIELDS}}}}}}}"
        try:
            p = (graphql(q, o=owner, n=number).get(kind) or {}).get("projectV2")
        except GhError as e:
            errors.append(str(e))
            continue
        if p:
            return p
    hint = " Does the token have project scope? Locally: gh auth refresh -s project." \
        if any("scope" in e.lower() or "permission" in e.lower() for e in errors) else ""
    raise SystemExit(f"Could not find project {owner}/{number}.{hint}")


def desired(state: dict) -> dict[int, dict]:
    """Wanted field values per issue number, from the board's rows."""
    out: dict[int, dict] = {}
    for r in state.get("rows") or []:
        cur = out.get(r["n"])
        if cur is None:
            out[r["n"]] = {"id": r.get("id"), "rows": [r]}
        else:
            cur["rows"].append(r)
    result = {}
    for n, v in out.items():
        rows = sorted(v["rows"], key=lambda r: ORDER.index(r["state"]))
        top = rows[0]
        ts = top.get("ts")
        plan = top.get("plan") or "–"
        if top.get("total"):
            plan += f" ({top.get('pct', 0)} %)"
        result[n] = {"id": v["id"], FIELD_STATE: top["state"],
                     "Who": ", ".join(dict.fromkeys(r["who"] for r in rows)),
                     "Plan": plan, "Now": top.get("now") or "–",
                     "Last active": ts.replace("T", " ").replace("Z", " UTC") if ts else "–"}
    for f in state.get("free") or []:
        result[f["n"]] = {"id": f.get("id"), FIELD_STATE: "free", "Who": "–", "Plan": "–",
                          "Now": "–", "Last active": "–"}
    return result


def current(project: dict, repo: str) -> dict[int, dict]:
    """Current project items for the repo's issues: {number: {item, values}}."""
    out = {}
    for it in (project.get("items") or {}).get("nodes") or []:
        c = it.get("content") or {}
        if not c.get("number") or (c.get("repository") or {}).get("nameWithOwner", "").lower() != repo.lower():
            continue
        values = {}
        for fv in (it.get("fieldValues") or {}).get("nodes") or []:
            name = ((fv or {}).get("field") or {}).get("name")
            if name:
                values[name] = fv.get("text", fv.get("name"))
        out[c["number"]] = {"item": it["id"], "values": values}
    return out


def plan(want: dict[int, dict], have: dict[int, dict]) -> tuple[list[int], list[tuple[int, str, str]]]:
    """(issues to add, [(issue, field, value)] to write)."""
    add = sorted(n for n in want if n not in have)
    updates = []
    for n in sorted(want):
        old = (have.get(n) or {}).get("values") or {}
        for field in [FIELD_STATE, *TEXT_FIELDS]:
            if old.get(field) != want[n][field]:
                updates.append((n, field, want[n][field]))
    return add, updates


def gql_str(s: str) -> str:
    return json.dumps(str(s), ensure_ascii=False)


def ensure_fields(project: dict, dry: bool) -> list[str]:
    names = {f.get("name") for f in (project.get("fields") or {}).get("nodes") or [] if f}
    missing = [f for f in [FIELD_STATE, *TEXT_FIELDS] if f not in names]
    if missing and not dry:
        parts = []
        for i, f in enumerate(missing):
            if f == FIELD_STATE:
                opts = ",".join(f"{{name:{gql_str(o)},color:{c},description:\"\"}}" for o, c in OPTIONS)
                extra = f"dataType:SINGLE_SELECT,singleSelectOptions:[{opts}]"
            else:
                extra = "dataType:TEXT"
            parts.append(f"f{i}:createProjectV2Field(input:{{projectId:{gql_str(project['id'])},"
                         f"name:{gql_str(f)},{extra}}}){{clientMutationId}}")
        graphql("mutation{" + " ".join(parts) + "}")
    return missing


def apply(project: dict, want: dict, have: dict, add: list[int], updates: list) -> None:
    pid = gql_str(project["id"])
    if add:
        parts = [f"a{n}:addProjectV2ItemById(input:{{projectId:{pid},contentId:{gql_str(want[n]['id'])}}})"
                 "{item{id}}" for n in add if want[n].get("id")]
        res = graphql("mutation{" + " ".join(parts) + "}") if parts else {}
        for n in add:
            item = ((res.get(f"a{n}") or {}).get("item") or {}).get("id")
            if item:
                have[n] = {"item": item, "values": {}}
    fields = {f["name"]: f for f in (project.get("fields") or {}).get("nodes") or [] if f and f.get("name")}
    options = {o["name"]: o["id"] for o in (fields.get(FIELD_STATE) or {}).get("options") or []}
    parts = []
    for i, (n, field, value) in enumerate(updates):
        item, f = (have.get(n) or {}).get("item"), fields.get(field)
        if not item or not f:
            continue
        if field == FIELD_STATE:
            if value not in options:
                print(f"Projects: option '{value}' is missing from the field {FIELD_STATE}, skipping.",
                      file=sys.stderr)
                continue
            val = f"{{singleSelectOptionId:{gql_str(options[value])}}}"
        else:
            val = f"{{text:{gql_str(value)}}}"
        parts.append(f"u{i}:updateProjectV2ItemFieldValue(input:{{projectId:{pid},itemId:{gql_str(item)},"
                     f"fieldId:{gql_str(f['id'])},value:{val}}}){{clientMutationId}}")
    for start in range(0, len(parts), 50):  # keep each call a reasonable size
        graphql("mutation{" + " ".join(parts[start:start + 50]) + "}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", help="the file from board.py --state-out")
    ap.add_argument("--project", default=os.environ.get("DEVSPRINTER_PROJECT", ""),
                    help="owner/number, e.g. octocat/1")
    ap.add_argument("--dry-run", action="store_true", help="show the changes, write nothing")
    args = ap.parse_args()
    if not args.project.strip():
        print("Projects: no project given (DEVSPRINTER_PROJECT), skipping.")
        return 0
    try:
        owner, number = args.project.strip().rsplit("/", 1)
        number = int(number)
    except ValueError:
        raise SystemExit("Give the project as owner/number, e.g. octocat/1.")
    state = json.loads(open(args.state, encoding="utf-8").read())
    project = load_project(owner, number)
    missing = ensure_fields(project, args.dry_run)
    if missing and not args.dry_run:
        project = load_project(owner, number)
    want, have = desired(state), current(project, state.get("repo") or "")
    add, updates = plan(want, have)
    head = f"Projects: {project.get('title')} – {len(add)} new, {len(updates)} field changes"
    if missing:
        head += f", {'would create' if args.dry_run else 'created'} the fields {', '.join(missing)}"
    print(head + ".")
    if args.dry_run:
        for n, field, value in updates:
            print(f"  #{n} {field} = {value}")
        return 0
    apply(project, want, have, add, updates)
    print(f"Projects: done. {project.get('url', '')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GhError as e:
        print(f"Projects: GitHub answered: {e}", file=sys.stderr)
        sys.exit(1)
