# Implementation Plan: Issues found during development, tracked in beads

**Branch**: `feat/beads` | **Date**: 2026-11-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-beads-issue-tracking/spec.md`

## Summary

The issues found while developing this project are kept as beads in one private tracker, a new
GitHub repository shared by all of the owner's projects. This repository stays free of issue data.
A clone reaches the tracker through `.beads/redirect`, an untracked file that `make beads` writes,
pointing at a clone of the tracker beside this one (research.md, R1, R2). Each bead says which
repository it belongs to with a `repo:<name>` label (R3). Its kind is one of beads' types, two of
them custom (`idea`, `vulnerability`) (R4). It links to the work it was found from, to its Spec
Kit record and to its pull request, and closes in the session that sees the pull request merged
(R5).

Agents get the context at session start. A committed `.beads/PRIME.md` replaces beads' default
text, which would contradict FR-011 and the agents' own memory. Hand-written hooks, for Claude Code
in `.claude/settings.json` and for Codex in `.codex/`, call one script that says when beads isn't
available (R6). `bd setup` isn't used, since it would write into `CLAUDE.md` and `AGENTS.md`, and
beads' git hooks aren't installed (R7). A vulnerability goes through the usual bug flow while the
repository is private, and through a security advisory's temporary private fork while it is
public, as it is now (R8).

The tracker starts with what is still open of the existing backlog: 18 beads (R10).
`AGENTS.md` gets the rules, the README the setup, and
`docs/decisions.md` the reasons. The constitution's Development Workflow gets one bullet, through
`/speckit-constitution` (R11).

## Technical Context

**Language/Version**: Bash for the hook script and the `make beads` recipe; JSON and TOML for the
agents' hook configuration; Markdown for `PRIME.md` and the documents. Python 3.13 (asdf) only for
the script's unit test.

**Primary Dependencies**: `bd` 1.3.4 or later, a development tool only: not in `uv.lock`, the image
or CI. Git with the owner's SSH access to GitHub. `gh`, for the session protocol's pull request
checks. Claude Code's `SessionStart` hook, and Codex's hooks (Codex 0.129.0 or later).

**Storage**: The tracker's embedded Dolt database, in a clone of `<owner>/<tracker>`, synced to
that repository's `refs/dolt/data`. Nothing in this repository.

**Testing**: `tests/unit/test_beads_hook.py` runs `devtools/beads-hook.sh` with a stand-in `bd` on
the `PATH`, in each case of contracts/agent-hooks.md, so `make test` needs no beads. The rest is the
trial in quickstart.md, on the owner's machine: the tracker, this clone, a fresh clone, a Claude
Code session, Codex's hook, a `PATH` without `bd`, and a made-up vulnerability through a draft
advisory's private fork, stopped before the merge.

**Target Platform**: The owner's Linux machine. Codex isn't installed there (quickstart.md § 8).

**Project Type**: Development tooling and process for a Python application. No code of the
application changes.

**Performance Goals**: A session's hook makes no network call: `bd where` and `bd prime` read the
local database. A fresh clone reaches the tracker in under ten minutes (SC-003).

**Constraints**: No issue data in this repository, in a tracked file or in a ref of its `origin`
(FR-003). `CLAUDE.md` and Spec Kit's generated files untouched (FR-021). The pre-commit fixers and
the commit-msg check untouched (FR-024). Neither the application, `make test` nor CI needs `bd`
(FR-025). Writing the agents' hook files needs the owner's approval: Claude Code's auto mode
refused hook installs during research (R6).

**Scale/Scope**: One owner, two agents, one repository now. 19 beads at setup: the 18 of the seed,
and this feature's.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No model, provider, profile or configuration key changes. Nothing is sent to a model provider. The tracker is the owner's GitHub repository, not an inference service, and it holds issue text, not book text sent for a request. No key or token is written: the tracker is reached over the owner's SSH access, and beads needs no GitHub token (FR-005, FR-026). `config/` is untouched, so startup validation is unchanged. | Pass | Pass: R2, contracts/make-beads.md. |
| II. The library is never at risk | No operation on the books, the catalog or the index. No container is created, recreated or removed, and no volume or host folder is mounted: the tracker's clone is a development tool's directory beside the repository, not the application's data. Benchmarks are untouched. | Pass | Pass: data-model.md, Files this repository commits. |
| III. Index integrity | No embedding, chunking, template, tokenizer or metadata setting changes. No reindex. | Pass | Pass. |
| IV. One service layer | No service, Gradio tab or command changes. | Pass | Pass. |
| V. Verified on real models and real books | No prompt, parser of model output, judge or ingestion code changes, so no model or book run is due. What the agents read is checked in practice: `PRIME.md` through `bd prime` and `bd codex-hook` in research, and a real Claude Code session in the trial (quickstart.md § 4). Codex is tried through its hook command only, unless the owner installs it (§ 8). | Pass | Pass: R6, quickstart.md § 4, § 8. |
| VI. Measured, not assumed | No claim of quality or speed, and no default of the application changes. No benchmark or judge changes. | Pass | Pass. |
| VII. Every answer traceable to its passages | Answers, summaries, citations and the no-evidence path don't change. | Pass | Pass. |
| VIII. Decisions are recorded | `docs/decisions.md`, Process, was read first. It says why `CLAUDE.md` only imports `AGENTS.md`, why there is no agent-context extension (a generated block in a hand-written `AGENTS.md`), and why only the owner starts a core skill. R6 keeps to all three. Tasks update the README (Requirements, Setup, How changes are made), `AGENTS.md` (Issues) and `docs/decisions.md` (Process: the tracker, its wiring, the hooks, the vulnerability rule, why tasks and GitHub Issues aren't mirrored). No delivered spec is edited. | Pass | Pass: contracts/agents-md.md; R6, R11. |

**Development Workflow.** The constitution names the tools of working on this project and doesn't
name an issue tracker. Recording found work is a convention every change keeps, so R11 adds a
**Beads** bullet (3.1.0, MINOR) through `/speckit-constitution`, which the owner starts before the
pull request is merged. The bullet "The PR title decides the release" says `main` takes no direct
pushes. That holds only while the repository is public: GitHub Free doesn't enforce the ruleset on
a private one (R12). It holds now, and `docs/decisions.md` notes it beside the vulnerability rule,
which the same switch decides. With a `feat:` title, this pull request releases a minor version,
though the application doesn't change. The title is the owner's to choose.

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-beads-issue-tracking/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R13
├── data-model.md        # the tracker, a bead, the flows, the committed files, the seed
├── quickstart.md        # the trial, §§ 0–12
├── contracts/
│   ├── make-beads.md    # `make beads`
│   ├── agent-hooks.md   # devtools/beads-hook.sh, .claude/settings.json, .codex/
│   ├── prime.md         # .beads/PRIME.md
│   └── agents-md.md     # AGENTS.md's Issues section, the constitution's bullet
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
.beads/
└── PRIME.md                     # new, committed: the session context (contracts/prime.md)
.claude/
└── settings.json                # new: SessionStart hook (contracts/agent-hooks.md)
.codex/
├── config.toml                  # new: [features] hooks = true
└── hooks.json                   # new: the four Codex events
devtools/
└── beads-hook.sh                # new: the hooks' entry point
tests/unit/
└── test_beads_hook.py           # new: the script's cases, with a stand-in bd
Makefile                         # `make beads`, BEADS_TRACKER_URL, BEADS_TRACKER_DIR
.gitignore                       # .beads/* but PRIME.md
AGENTS.md                        # Issues; a line under the table of flows
README.md                        # Requirements, Setup, How changes are made
docs/decisions.md                # Process
.specify/memory/constitution.md  # via /speckit-constitution only (R11)
```

Outside this repository, created once with the owner's confirmation: `<owner>/<tracker>`, private,
and its clone at `../<tracker>` (quickstart.md § 1).

**Structure Decision**: No application directory changes. The new files sit where their tools
look for them (`.beads/`, `.claude/`, `.codex/`), and the one script sits in `devtools/` with the
project's other development scripts, tested in `tests/unit/` as they are.

## Complexity Tracking

No violation.
