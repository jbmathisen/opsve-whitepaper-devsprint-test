# Devsprinter field test: content sprint on the OpenSverige whitepaper

**What:** Devsprinter v0.5.0 (`jbmathisen/devsprinter` at `13e49df`) used as the process manager for a *content* sprint (review, feedback, decisions, text edits), not a coding sprint. Several contributors from the OpenSverige community, one project lead who approves.
**Where:** this repo (`jbmathisen/opsve-whitepaper-devsprint-test`), seeded from `jbmathisen/opensverige-whitepaper` at `dc0aed6` plus three uncommitted files (`infomote.html`, `infomote-punkter.md`, `PR-varfor.md`).
**At the end:** the finished content goes back to `opensverige-whitepaper`. The findings marked **export** go to the Devsprinter repo as issues or notes.

Legend: ✅ works · ⚠️ works with friction · ❌ does not work / missing · 💡 idea

## Setup (2026-11-21)

| # | | Finding | Export |
|---|---|---|---|
| S1 | ❌ | **The plugin repo is private**, so community contributors cannot run `claude plugin marketplace add jbmathisen/devsprinter`. For a multi-person test the repo must be public, or contributors skip the plugin. | export |
| S2 | ⚠️ | **Turning on the board means copying `devsprinter/` (10 Python files) into the project.** In a content repo that is noise in the file list and needs a README note. The copy also drifts from the installed plugin version. A reusable action (`uses: jbmathisen/devsprinter/board@v0.5`) would need only the workflow file. | export |
| S3 | ⚠️ | README step 2 doesn't mention `.github/devsprinter.json`. Content tasks run for days, so the default 30 min / 4 h makes everything stale. Picked *long tasks* (60 min / 8 h) by hand. Even 8 h is short for "wait for the board's answer". | export |
| S4 | ✅ | The `ready` label is a good gate. Board questions (`styrelsen`) stay without `ready`, so nobody's agent gets Start on a question only people can answer. | |
| S5 | ❌ | **No way to claim without Claude Code.** A contributor who comments "Jag tar den" isn't shown on the board. Self-assigning needs triage or write access, and a non-collaborator in a public repo can't be assigned at all. Today everyone who wants to show up on the board has to be a collaborator. | export |
| S6 | ❌ | **One assignee per task doesn't fit review work.** "At least two people give feedback" is the normal shape of a review issue. The board can't show "2 of 2 reviews in" or who has commented. | export |
| S7 | ❌ | **Progress comes only from an agent's plan steps.** Human content work has no plan, so these issues only ever show ⚪ assigned. Confirms LARDOMAR #1: the missing state is *waiting on whom* (board, reviewer, project lead). | export |
| S8 | ⚠️ | First push was refused: "push declined due to email privacy restrictions" (commit had the private email). Fixed with the noreply address in the repo's git config. Not a Devsprinter bug, but worth a line in a "new repo" checklist. | |
| S9 | ✅ | **The board created and pinned itself** while the issues were being created, with no manual step. The first run after the push found the right settings (footer: quiet 1 h, stale 8 h). | |
| S10 | ⚠️ | The board issue took number **#12** in the middle of the sprint issues. Tip for the README: run the workflow once (`workflow_dispatch`) *before* creating issues, so the board is #1. | export |
| S11 | ⚠️ | Creating 20 issues started 20 board runs. 17 were cancelled by the concurrency queue, as designed, but the Actions tab looks alarming to a non-developer. | export |
| S12 | ❌ | **"Free (20)" lumps everything together.** The 11 board questions (`styrelsen`, no `ready`) sit next to the 7 open tasks. A content team needs the board grouped: *free to take* (ready), *waiting on a decision*, *blocked* (#21 waits on #1). The board knows `ready_label` but doesn't use it here. | export |
| S13 | ⚠️ | The board footer only says "take a task with `/devsprinter:claim N`", so people without Claude Code get no instructions. Linked to S5. | export |

## Requirements from the project lead (2026-11-21)

Responses to S5–S7. These change what Devsprinter is: from "a Claude Code plugin" to "a sprint protocol on GitHub that any LLM or person can join".

| # | Requirement | From | Export |
|---|---|---|---|
| R1 | **Anyone can connect the repo to their own LLM**, get the information they need and contribute. No Claude Code, no plugin, no collaborator access required. | S1, S5, S13 | export |
| R2 | **Roles: 1–2 sprintmasters and the workers.** Sprintmasters approve, set what is ready and answer "waiting on" items. | S6, S7 | export |
| R3 | **First-time setup asks how the team wants to work** (who are the sprintmasters, who may take tasks, code or content, task length) and writes the setup, instead of the owner copying files and editing JSON. | S2, S3 | export |
| R4 | Tasks can have several people (reviews need 2+), and the board shows *waiting on whom*. | S6, S7, S12 | export |
| R5 | **The usual contribution is a PR from a fork**: the repo is shared openly in the Discord, contributors have no write access, and the sprintmaster approves PRs. The board must show linked PRs as *in review, waiting on the sprintmaster*. Today it ignores PRs completely. | S5 | export |

| R6 | **Safe AI review of PRs from strangers.** The sprintmaster wants to review PRs with their own AI. Text in a fork's PR (diff, description, HTML comments, hidden text, file names) can carry instructions to that AI. A checked-out branch can also change `CLAUDE.md`, `AGENTS.md`, `.claude/settings.json` (hooks run code) and `.github/workflows/`. Devsprinter's setup should add `CODEOWNERS` for those paths, offer a read-only check that flags hidden text and changes outside content files, and its review instructions should read PRs with `gh pr diff`, never by checking them out. | export |

| R7 | **Trust profiles in setup.** Public or private, and trusted, known or open contributors, with a plain explanation of each and the settings that follow. The owner decides how much to trust people, and can raise named people. The safety notice for PR review is always included, not something to remember. The goal is a smooth start and a smooth sprint. | export |

| R8 | **No commands to learn.** Contributors ask their own model what is available, what they can review and what's going on. They pick a task, the model does the work, and it delivers through a comment or a PR. The commands become something the model does for them. This is how it felt in the hackathon project that Devsprinter comes from. Goals: a better overview (a dashboard view), and use beyond code, for content too. | export |

Proposal for R1–R8: `docs/proposal-open-sprint.md` in the Devsprinter repo.

## Sprint

*(Filled in as the sprint runs: claims, collisions, board updates, what contributors said.)*

| # | | Date | Finding | Export |
|---|---|---|---|---|
| F1 | ✅ | 11-21 | **Devsprinter 0.6 deployed** (branch `feature/open-sprint`): comment commands, PRs linked with `Fixes #N`, grouped board, PR check, `AGENTS.md`. Settings: @jbmathisen as sprintmaster, `styrelsen` as a waiting label, content types .html .md .css. 115 unit tests pass. | |
| F2 | ✅ | 11-21 | **The grouped board works live:** *Free to take (7)*, *Not ready yet (2)*, *Waiting on a decision (11)* with "waiting on styrelsen". Fixes S12. | |
| F3 | ❌→✅ | 11-21 | **Git Bash on Windows turned `/claim` into `C:/Program Files/Git/claim`** when sent with `gh issue comment --body "/claim"` (MSYS path conversion), so the command was lost without an error. `AGENTS.md` now sends commands through stdin: `echo "/claim" \| gh issue comment 12 --body-file -`. Any agent on Windows would have hit this. | export |
| F4 | ✅ | 11-21 | **`/claim` → assigned, 🙋 claimed on the board and a "took #19" event; `/waiting styrelsen` → ⏳ waiting on styrelsen; `/release` → unassigned, free, and a "released" event.** Each took one run of about 20–40 s. | |
| F5 | ✅ | 11-21 | **A PR with `Fixes #19` moved #19 to 👀 in review, waiting on @jbmathisen**, and back to free when the PR was closed. | |
| F6 | ❌→✅ | 11-21 | **The PR check failed on its first live run:** `gh pr view` has no `authorAssociation` field. The unit tests never call `gh` for real, so they didn't catch it. Fixed by reading it from the REST API. 💡 Devsprinter needs a small live smoke test against a test repo before a release. | export |
| F7 | ✅ | 11-21 | **The PR check found all four planted problems** (an HTML comment, text aimed at an AI, `display:none`, a new `.claude/settings.json`), quoted none of them, started with the notice, and passed because the author is trusted. One comment, updated in place. | |
| F8 | ⚠️ | 11-21 | `pull_request_target` runs started about 20 s after the PR was opened. Fine, but someone watching may think nothing happened. | |
| F9 | ⚠️ | 11-21 | Changes made with the Action's own token (assign, label) start no new run. That avoids loops, but `/ready` showed the task as "Not ready yet" until the next event. Fixed: the board applies the label in the same run. | export |
| F10 | ⚠️ | 11-21 | PR reviews (approve, changes requested) don't start the board: `pull_request_review` from a fork gets a read-only token. The hourly run catches them, so *changes asked* can lag up to an hour. | export |
| F11 | 💡 | 11-21 | The sprintmaster's own PR says "waiting on @jbmathisen", i.e. on themself. It should say "ready to merge". | export |
| F13 | ✅ | 11-21 | **R8 built: `devsprinter/sprint.py`** (start, tasks, review, status, show, take, join, wait, back, release, deliver as a comment or a PR), **`AGENTS.md` as a conversation playbook**, and a `sprint` skill in the plugin for Claude Code. The README tells contributors to "talk to your AI", with typed commands as the fallback. | |
| F14 | ✅ | 11-21 | **Live:** `start`, `tasks` and `review` give short, groupable answers a model can retell (your tasks, waiting on you, free, review tasks, decisions). `take 19` → assigned and 🙋 on the board. A second `take 19` → "You already have #19" right away, because the tool reads the comments itself and doesn't wait for the Action. `release 19` → free again. | |
| F15 | ⚠️ | 11-21 | **The real test of fluency is still open:** a fresh model asked only "Vad finns att göra?" in the repo. Headless `claude -p` couldn't log in here ("OAuth session expired"). Next: the sprintmaster tries it in their own session, then the first contributor tries it with another tool (Codex or Cursor). | |
| F16 | ⚠️ | 11-21 | One full test run had 1 error that didn't repeat in three reruns. Probably the local dashboard server tests (ports). Watch for it. | |
| F17 | 💡 | 11-21 | Not built yet: `deliver --pr` from a fork hasn't run live (it needs a contributor with a fork). The plugin's progress hooks post to `origin`, which is the fork in a fork clone, not the sprint repo. They should follow the same parent rule as `sprint.py`. | export |
| F18 | ✅ | 11-21 | **Dashboard without GitHub Pages.** Pages is always public on GitHub Free (private Pages needs Enterprise Cloud), so the project lead chose a local HTML page instead. `sprint.py dashboard` ("show me the dashboard") builds a snapshot with the person's own `gh` login and opens it in the browser. It has free tasks grouped (free to take, not ready yet, waiting on a decision, and on whom), open PRs, and the latest events. Works for private repos, and nothing is published. Checked in the browser at phone and desktop width. | export |
| F19 | 💡 | 11-21 | Trust profiles in setup should follow this: a public project can offer the Pages dashboard; a private one gets the local page and the board issue only. | export |
| F20 | ✅ | 11-21 | **Dashboard redesign** after the project lead found the long scroll unconvincing. Guidance came from the original Impeccable (`pbakaus/impeccable`, Apache 2.0) and Taste Skill (`Leonxlnx/taste-skill`, MIT). They were read as references, not installed, because Impeccable's installer adds a hook. Look-alike copies of both exist under other names. The new layout follows Impeccable's "Operate" mode: a sprint board people already know, with five lanes (free to take → in progress → waiting → in review → done) that scroll on their own, so the page fits one screen; a rail with decisions, PRs and activity; and a flow strip in a navy header as the signature move, showing the count per step and the mix. On a phone the flow strip becomes CSS-only tabs (works as a local file without scripts). Drawn dots instead of emoji, monogram avatars, aligned numbers, themed focus rings and scrollbars, light and dark. Checked at 1440×900 in light and dark and at 390×844 (tab switching works, nothing overlaps). Fixed along the way: the lanes needed 1148 px but had 1084 px at 1440. | export |
| F21 | 💡 | 11-21 | The README screenshot in Devsprinter (`docs/dashboard.png`) still shows the old design and needs a new capture. The server test `test_actions_are_guarded` failed once more in a full run and never alone (F16): probably a reset local connection on Windows. | export |
| F12 | ⏳ | 11-21 | **Not tested yet, needs a second account or the first contributor:** a refused `/claim`, assigning someone who isn't a collaborator, `/join`, `/ready`, a PR from a fork, and the check failing for someone who isn't trusted. | |

## Wrap-up

*(What to export to Devsprinter, in priority order.)*
