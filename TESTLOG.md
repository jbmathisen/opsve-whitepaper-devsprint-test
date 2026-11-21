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

Proposal for R1–R7: `docs/proposal-open-sprint.md` in the Devsprinter repo.

## Sprint

*(Filled in as the sprint runs: claims, collisions, board updates, what contributors said.)*

| # | | Date | Finding | Export |
|---|---|---|---|---|

## Wrap-up

*(What to export to Devsprinter, in priority order.)*
