"""Live feed: sends the board's new events to Discord and/or Slack.

`python feed.py state.json` reads the file that `board.py --state-out` wrote and sends
`new_events` to the webhooks found in the environment:

  DEVSPRINTER_DISCORD_WEBHOOK   https://discord.com/api/webhooks/…
  DEVSPRINTER_SLACK_WEBHOOK     https://hooks.slack.com/services/…
  DEVSPRINTER_FEED_EVENTS       which types to send, comma-separated
                                (default: claimed,milestone,done,stale,released,closed;
                                also available: started,replanned,back)

With no webhook the script does nothing and exits with 0, so the Action can always run it.
Only the issue number, issue title, account, milestone and plan are sent, never the agent's
free text (step titles). Webhook addresses are never printed. `--dry-run` shows the messages.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from board import event_text

DEFAULT_TYPES = "claimed,milestone,done,stale,released,closed"
LIMIT = 1900  # Discord allows 2000 characters per message


def chosen(events: list[dict], types: str | None = None) -> list[dict]:
    wanted = {t.strip() for t in (types or DEFAULT_TYPES).split(",") if t.strip()}
    return [e for e in events if e.get("type") in wanted]


def slack_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lines(events: list[dict], repo: str, flavor: str = "Discord") -> list[str]:
    out = []
    for e in events:
        url = f"https://github.com/{repo}/issues/{e['n']}" if repo else ""
        if flavor == "Slack":
            text = event_text({**e, "title": slack_escape(e.get("title", "")),
                               "who": slack_escape(e.get("who", ""))}, at=False)
            out.append(f"{text} <{url}|open>" if url else text)
        else:
            # <url> in Discord = a link without a preview
            text = event_text(e, at=False)
            out.append(f"{text} — <{url}>" if url else text)
    return out


def chunks(text_lines: list[str], limit: int = LIMIT) -> list[str]:
    out, cur = [], ""
    for line in text_lines:
        if cur and len(cur) + 1 + len(line) > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line[:limit]
    return out + ([cur] if cur else [])


def discord_payload(text: str) -> dict:
    # No pings, not even if a title contains @everyone
    return {"content": text, "username": "Devsprinter", "allowed_mentions": {"parse": []}}


def slack_payload(text: str) -> dict:
    return {"text": text}


def post(url: str, payload: dict) -> str | None:
    """None on success, otherwise a short description of the error (without the address)."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "devsprinter-feed"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return None if 200 <= r.status < 300 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return type(e).__name__


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", help="the file from board.py --state-out")
    ap.add_argument("--dry-run", action="store_true", help="show the messages, send nothing")
    ap.add_argument("--all", action="store_true", help="take all saved events, not just new ones (testing)")
    args = ap.parse_args()
    data = json.loads(open(args.state, encoding="utf-8").read())
    events = chosen(data.get("events" if args.all else "new_events") or [],
                    os.environ.get("DEVSPRINTER_FEED_EVENTS"))
    targets = {name: os.environ.get(var, "").strip() for name, var in
               (("Discord", "DEVSPRINTER_DISCORD_WEBHOOK"), ("Slack", "DEVSPRINTER_SLACK_WEBHOOK"))}
    targets = {k: v for k, v in targets.items() if v}
    if not events:
        print("Feed: no new events.")
        return 0
    repo = data.get("repo") or ""
    if args.dry_run or not targets:
        print(f"Feed: {len(events)} events" + ("" if targets else " (no webhook set, not sent)"))
        print("\n".join(lines(events, repo)))
        return 0
    failed = False
    for name, url in targets.items():
        make = discord_payload if name == "Discord" else slack_payload
        for m in chunks(lines(events, repo, name)):
            err = post(url, make(m))
            if err:
                print(f"Feed: {name} answered {err}.", file=sys.stderr)
                failed = True
                break
        else:
            print(f"Feed: {len(events)} events to {name}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
