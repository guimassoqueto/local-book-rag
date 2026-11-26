---

description: "Task list for tracking the issues found during development in beads"
---

# Tasks: Issues found during development, tracked in beads

**Input**: Design documents from `specs/010-beads-issue-tracking/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: One unit test, of the agents' hook script (FR-025): `tests/unit/test_beads_hook.py`,
written first and seen to fail (US4). Everything else this feature delivers is configuration and
text that tools and agents read, so it is checked by the trial in quickstart.md, one section per
success criterion. Each story's phase ends with its sections of the trial.

**Organization**: The tracker comes first, outside this repository (Phase 1), then this clone's
connection to it and the bead of this feature (Phase 2), which every story needs. The stories
then add, in priority order:
- **US1** (P1): recording what is found. The MVP.
- **US2** (P2): picking a bead up through its Spec Kit flow, and the seed of the existing backlog.
- **US3** (P3): vulnerabilities, by visibility.
- **US4** (P4): every session and every clone, through the hooks and the README.

US1 and US2 write the same two files, `.beads/PRIME.md` and `AGENTS.md`, each adding its own
sections, so they run in that order. US3 adds one bullet to `AGENTS.md`. US4's script and test
touch other files and can start after Phase 2.

**The owner's part**: Some steps are the owner's to approve or to run, and tasks marked
**(owner)** wait for them. These are creating the tracker repository, writing the agents' hook
files, starting new agent sessions for the trial, each outward step on GitHub in § 6, and
`/speckit-constitution`.

**Findings**: Anything found while implementing that is outside this feature becomes a bead,
`discovered-from` this feature's bead (T007), as the feature itself asks (FR-008).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US4).

## Path Conventions

This repository's root, as plan.md lays it out: `.beads/`, `.claude/`, `.codex/`, `devtools/`,
`tests/unit/`, and the `Makefile`, `.gitignore`, `AGENTS.md`, `README.md` and `docs/decisions.md`
at the root. The tracker is cloned at `../<tracker>`. `<owner>/<tracker>` and `<prefix>` are the
names T001 confirms, recorded under Notes.

---

## Phase 1: Setup (the tracker, outside this repository)

**Purpose**: The one private tracker, created once (research.md R2; quickstart.md § 1).

- [X] T001 **(owner)** Ask the owner to confirm the tracker repository's name and its issue prefix, proposed `issues` and `iss` (data-model.md Tracker.Issue prefix), and that it may be created on GitHub, private. Record both under Notes in `specs/010-beads-issue-tracking/tasks.md`
- [X] T002 Create the private repository with `gh repo create <owner>/<tracker> --private --description "Issues of <owner>'s projects (beads)"`, and clone it to `../<tracker>` over SSH (research.md R2)
- [X] T003 Initialize the tracker in `../<tracker>`. Steps: `git config beads.role maintainer` (data-model.md Tracker.beads.role); `bd init --prefix <prefix> --skip-agents --skip-hooks --non-interactive` (Tracker.Issue prefix, Tracker.Git hooks, Tracker.Remote); `bd config set types.custom "idea,vulnerability"` (Tracker.Custom types), leaving `dolt.auto-push` unset (Tracker.Auto-push). Write `../<tracker>/README.md` saying what the repository holds and how a project connects to it (`make beads`), commit it with a conventional message, `git push origin main`, and `bd dolt push`. Check that `git ls-remote origin` lists `refs/heads/main` and `refs/dolt/data`, and that `bd types` lists `idea` and `vulnerability` (quickstart.md § 1)

---

## Phase 2: Foundational (this clone reaches the tracker)

**Purpose**: `make beads` and the bead of this feature. Every story records, lists or reads beads
through them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Add `.beads/*` and `!.beads/PRIME.md` to `.gitignore`, beside "Runtime data", with a comment saying that beads' redirect and whatever else beads writes there stay local (data-model.md, Files this repository commits)
- [X] T005 [P] Add the `beads` target to `Makefile`, following contracts/make-beads.md: the variables `BEADS_TRACKER_URL` and `BEADS_TRACKER_DIR`, defaulting to T001's names; steps 1 to 6 in order, each failure stopping the target with the contract's message; the role of data-model.md Tracker.beads.role. Add `beads` to `.PHONY`, with a comment above the target like the other targets'. It never runs `bd init`, `bd setup` or `bd hooks`
- [X] T006 Run `make beads`, and check quickstart.md § 2: the tracker "via redirect", a count of 0, nothing from `.beads/` in `git status --short --untracked-files=all`, and no ref but heads, tags and pull requests in `git ls-remote origin` (SC-002). Run it again: only the redirect is written again. Check step 2 by hand: with a scratch `.beads/metadata.json`, it fails and deletes nothing. Then remove the scratch file (contracts/make-beads.md)
- [X] T007 Record this feature's bead, and keep its ID under Notes. Its fields: kind `feature` (data-model.md Bead.Kind), the label `repo:local-book-rag` (Bead.Repository), priority 2 (Bead.Priority), a description of the feature with the branch `feat/beads` (Bead.What was seen and where), and `--spec-id specs/010-beads-issue-tracking` (Bead.Record). Then `bd update <id> --status in_progress` (Bead.Status; not `--claim`, research.md R5). Findings made while implementing link to it (Bead.Found from)

**Checkpoint**: This clone reaches the tracker, which holds one bead, and holds no issue data of
its own.

---

## Phase 3: User Story 1 - What is found mid-task is recorded, not fixed on the spot (Priority: P1) 🎯 MVP

**Goal**: An agent or the owner records what they find as a bead of this repository, linked to
the work it came from, and the tracker syncs. Nothing of it reaches `local-book-rag`.

**Independent Test**: spec.md, User Story 1. A bead recorded by the agent and one by hand are both
in the tracker, labeled and linked. Neither is in the working tree, the branch's commits or
`origin`'s refs. A second copy of the tracker sees both after a sync.

- [X] T008 [P] [US1] Write `.beads/PRIME.md` with sections 1, 3, 4 and 7 of contracts/prime.md, plus the `bd dolt pull` of section 2. Section 2's pull request checks come with US2. The label follows data-model.md Bead.Repository, the kinds Bead.Kind, the link Bead.Found from (`discovered-from`, or `metadata.found_in` when the work has no bead), and the description Bead.What was seen and where. Leave out everything contracts/prime.md lists under "Never in it"
- [X] T009 [P] [US1] Add the Issues section to `AGENTS.md`, after How changes are made, with these bullets of contracts/agents-md.md: "What becomes a bead", "How", "Tasks", "Without beads", and "Setup and sync". Also add a line telling an agent whose session didn't start with beads' context to run `bd prime`. The rules on fields cite data-model.md: Bead.Repository (exactly one label, added with `bd label add` when a bead lacks it), Bead.What was seen and where (never empty), Bead.Priority, Bead.Found from (work started without a bead gets one when it starts)
- [X] T010 [US1] From this repository, check that `bd prime` prints `.beads/PRIME.md`'s text followed by the tracker's memories, and that `bd prime --hook-json` wraps the same text in the SessionStart envelope (research.md R6)
- [X] T011 [US1] **(owner)** Trial, quickstart.md § 4, second bullet (SC-001). The owner starts a new Claude Code session, which gets the rules through `CLAUDE.md`'s import of `AGENTS.md`, since the hook comes with US4. In it, a small task on a scratch branch, and an unrelated problem pointed out. Check that within a minute the agent records a bead labeled, typed, described and linked as T009 asks, names it in its reply, and goes back to the task. Then record a bead by hand, run `bd dolt push`, and repeat T006's `git status` and `git ls-remote origin` checks (SC-002). In `../<tracker>`, or a second clone of it, `bd dolt pull` shows both. Close both with `--reason "Trial"`, and delete the scratch branch

**Checkpoint**: The MVP. What is found is recorded, and this repository stays free of it.

---

## Phase 4: User Story 2 - A bead picked up goes through its Spec Kit flow (Priority: P2)

**Goal**: A bead picked up starts the flow its kind maps to, links to its record and pull request,
and closes on the merge. A fix report's Follow-ups become beads. The tracker holds the existing
backlog.

**Independent Test**: spec.md, User Story 2, and SC-009. Each kind leads to its flow. A bead links
to its record and its pull request, closes on a merge, and reopens when its pull request is closed
unmerged. The seed is in the tracker.

- [X] T012 [P] [US2] Complete `.beads/PRIME.md` with contracts/prime.md's section 2 pull request checks, section 5 (picking up) and section 6 (closing), following data-model.md Bead.Record, Bead.Pull request, Bead.Reason closed and the State transitions
- [X] T013 [P] [US2] In `AGENTS.md`, under the table of flows, add the line contracts/agents-md.md asks for: a change usually starts from a bead, and its kind picks the row. In Issues, add the bullets "Which flow" (data-model.md, Flow mapping, with core skills started by the owner from the bead's description) and "Linking and closing" (data-model.md Bead.Record, Bead.Pull request, Bead.Reason closed, Bead.Blocked by, and the State transitions). Extend the bullet "A bug fix keeps to its assessment": each Follow-up also becomes a bead, `discovered-from` the bug's bead, or with the fix's record as `found_in` when the bug had none, and the report's entry names it (FR-010)
- [X] T014 [US2] **(owner)** Show the owner data-model.md's seed table, so they can change kinds or priorities. Then record S1 to S18 with `bd create` or `bd batch`. Each bead gets its kind (data-model.md Bead.Kind), its priority (Bead.Priority), the label (Bead.Repository), and a description saying what its source says, quoting the source where it is short (Bead.What was seen and where). It also gets `--metadata '{"found_in": "<file>, <section>"}'` (Bead.Found from). Check quickstart.md § 3: all 18 exist beside this feature's bead, each `found_in` names a place in the table, and none of the four left-out items is a bead (SC-009)
- [X] T015 [US2] **(owner)** Trial, quickstart.md § 5 (SC-004). Record four made-up beads (`bug`, `feature`, `idea`, `chore`). In a new session, the owner picks each up. Check that each goes `in_progress`, and that the agent names, offers or hands over the right flow. Stop before any record is written, except for the `chore`. The `chore` gets a one-line change on a `chore/…` branch and a draft pull request, then `--external-ref gh-<n>` (data-model.md Bead.Pull request). Close the pull request unmerged, and check that the next session's start protocol sets the bead back to `open` with its link. Close the made-up beads with `--reason "Trial"`, and delete the branch

**Checkpoint**: The backlog is in the tracker, and each bead's path through Spec Kit is traced.

---

## Phase 5: User Story 3 - A vulnerability stays out of public view until its fix lands (Priority: P3)

**Goal**: A vulnerability goes through the usual bug flow while the repository is private, and
through a draft advisory's temporary private fork while it is public, as now. Nothing public
describes it before the merge.

**Independent Test**: spec.md, User Story 3, and SC-008. A made-up vulnerability is taken through
a draft advisory and its fork, up to the merge, and nothing public holds its phrase.

- [X] T016 [US3] Add the "Vulnerabilities" bullet to `AGENTS.md`'s Issues section, as contracts/agents-md.md words it. The path is decided by `gh repo view --json visibility` when the fix starts. While public, the advisory and its fork are opened with research.md R8's `gh api` calls. Cite data-model.md for the fields: Bead.Title (only enough for the owner to recognize it), Bead.Priority (0 or 1), Bead.Pull request (the advisory's `GHSA-…` ID), and the vulnerability row of Flow mapping
- [X] T017 [US3] **(owner)** Trial, quickstart.md § 6 (SC-008), with the owner confirming each outward step. Record a made-up vulnerability with a distinctive phrase, and pick it up. The agent should say the repository is public, so an advisory. Open a draft advisory marked as a trial, and its temporary private fork. Push a branch with one made-up file holding the phrase, and open a pull request in the fork. Then run § 6's searches: the phrase is in the tracker and the fork only. Close the advisory unpublished, check that the fork is gone (delete it if not), and close the bead with `--reason "Trial: not a real vulnerability"`

**Checkpoint**: The vulnerability rule works on the public repository, short of a merge.

---

## Phase 6: User Story 4 - Any session and any clone knows the tracker (Priority: P4)

**Goal**: Claude Code and Codex sessions start with beads' context, again after compaction. A clone
without beads, or without the tracker, works as on `main`. A fresh clone reaches the tracker from
the README alone.

**Independent Test**: spec.md, User Story 4. Sessions answer "what next?" from the tracker. A fresh
clone lists the same beads. Without `bd`, everything works and the session says so.
`make speckit-upgrade` leaves it all working.

### Test for User Story 4 (write first, and see it fail)

- [X] T018 [P] [US4] Write `tests/unit/test_beads_hook.py`. It runs `devtools/beads-hook.sh` with `subprocess`. The `PATH` holds a `tmp_path` directory with a stand-in `bd` script, plus the directories of `bash`, `sort`, `head` and the other tools the script needs, but not the real `bd`. Standard input is a hook payload. One test per row of contracts/agent-hooks.md's table:
  - no `bd`: Claude Code, and Codex `SessionStart`, get the "isn't installed" context, and Codex `PreCompact` prints nothing;
  - `bd` reporting 1.3.3: the "too old" context;
  - `bd where` exiting 1: the "not connected" context, naming `make beads`;
  - `bd` 1.3.4 with `where` exiting 0: Claude Code's output is the stand-in's `prime --hook-json` output, unchanged, and a Codex event runs `codex-hook <event>` with the payload on its standard input.

  Every case exits 0, and every context is valid JSON whose `hookSpecificOutput.hookEventName` is `SessionStart`. Run `make test`, and see the new tests fail because the script doesn't exist yet

### Implementation for User Story 4

- [X] T019 [US4] Write `devtools/beads-hook.sh` (`#!/usr/bin/env bash`, executable) following contracts/agent-hooks.md. It compares the version with `sort -V` against 1.3.4, checks the tracker with `bd where >/dev/null 2>&1`, and then `exec`s `bd prime --hook-json` or `bd codex-hook "<event>"`. Otherwise it prints the one-paragraph context, or nothing for Codex's other events. It always exits 0, writes nothing, and calls no network. Make T018 pass, and check that git records the executable bit
- [X] T020 [P] [US4] **(owner)** With the owner's approval, write `.claude/settings.json` with contracts/agent-hooks.md's `SessionStart` hook running `devtools/beads-hook.sh claude`, and nothing else
- [X] T021 [P] [US4] **(owner)** With the owner's approval, write `.codex/hooks.json` with the four events of contracts/agent-hooks.md, each running `devtools/beads-hook.sh codex <event>` with beads' matchers, and `.codex/config.toml` with `[features]` `hooks = true` only. Check that pre-commit's `check-toml` accepts it
- [X] T022 [P] [US4] Update `README.md` (FR-023, FR-028). **Requirements**: beads 1.3.4 or later, for development only, not to run the application, test it, or for CI. **Setup**: `make beads`, what it does, its two variables, a fresh clone, how to check with `bd where`, and `bd metrics off` (research.md R13). **How changes are made**: beads holds what is still to be handled, a bead's kind picks the flow, `AGENTS.md`'s Issues has the rules, and the terminal commands (`bd ready --label repo:local-book-rag`, `bd create`, `bd show`, `bd close`, `bd dolt pull`, `bd dolt push`). **Layout**: `.beads/PRIME.md`, `.claude/settings.json`, `.codex/` and `devtools/`
- [X] T023 [US4] **(owner)** Trial, quickstart.md § 4, first bullet (SC-006, Claude Code). The owner starts a new session and asks "what should I work on next?", without mentioning beads. Check that the answer comes from `bd ready --label repo:local-book-rag`, and that none of it is a task of a `tasks.md`. Then run `/compact`, and check that the context came back
- [X] T024 [US4] Trial, quickstart.md § 8 (SC-006, Codex). If Codex is installed, the owner asks the same question in a Codex session. If it isn't, run § 8's command by hand and check that its context is `PRIME.md`'s text. Record which was done under Notes
- [X] T025 [US4] Trial, quickstart.md § 7 (SC-003). Clone into `mktemp -d`, run `make beads` with `BEADS_TRACKER_DIR` there, and time it. Check that the count matches, and that only the README was needed. Remove the directory
- [X] T026 [US4] Trial, quickstart.md § 9 (SC-005). With `bd` off the `PATH`, run `make install`, `make test`, `make lint-check`, a whitespace-only commit on a scratch branch (same fixes, same message check), and `devtools/beads-hook.sh claude` (the "isn't installed" context, exit 0). With `bd` back, move `.beads/redirect` aside, check the "not connected" context, and put it back. Delete the scratch branch
- [X] T027 [US4] Trial, quickstart.md § 10 (SC-007). Run `make speckit-upgrade` and `git status --short`. No Spec Kit file may differ because of beads; discard any regenerated file this feature didn't cause, or keep it for a separate `chore:` change. Then run T023's question again in the current session with `bd prime`

**Checkpoint**: Every session and clone sees the tracker, and nothing needs beads that didn't
before.

---

## Phase 7: Polish & Cross-Cutting Concerns (the records)

**Purpose**: Why, in `docs/decisions.md`; the constitution's bullet; the last checks; the results.

- [X] T028 [P] Add the feature's decisions to `docs/decisions.md`, Process (FR-029). Each says what was decided and the finding that decided it:
  - the separate private tracker (R2), and its wiring by redirect (R1);
  - the `repo:` label (R3), and the custom kinds (R4);
  - closing in a session, not in CI (R5);
  - `PRIME.md` over beads' default text, and the hand-written hooks, with no `bd setup` and no beads skill (R6);
  - no beads git hooks (R7);
  - the vulnerability rule by visibility, with the same switch deciding whether `protect-main` is enforced (R8, R12);
  - no auto-push (R9), and the seed (R10);
  - tasks not mirrored into beads, and beads not mirrored to GitHub Issues (spec.md, Clarifications).
- [X] T029 **(owner)** The owner runs `/speckit-constitution` with contracts/agents-md.md's **Beads** bullet for Development Workflow, as a MINOR amendment, 3.0.0 to 3.1.0 (research.md R11). Then remove the Sync Impact Report from `.specify/memory/constitution.md` before committing (Governance), and check that `AGENTS.md` and the README don't restate the rule
- [X] T030 Run `make lint-check` and `make test`, the new test included. Check that `git status` shows only the files of plan.md's Source Code tree, and this directory's
- [X] T031 Trial, quickstart.md § 11 (SC-002): no bead title in any branch of this repository outside `specs/010-beads-issue-tracking/`
- [X] T032 Append "Results of the implementation, <date>" to `specs/010-beads-issue-tracking/spec.md`, as earlier specs do. It holds each success criterion's outcome, what wasn't run and why (Codex live, if so; the advisory merge), and corrections made during implementing. Then run `bd dolt push`
- [ ] T033 After the pull request merges, quickstart.md § 12: in the first session after the merge, this feature's bead closes with `Merged in #<n>` (data-model.md Bead.Reason closed), and `bd dolt push` sends it

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 first, since the names are the owner's. T002 and T003 follow, in order.
- **Foundational (Phase 2)**: depends on Phase 1. T004 and T005 in parallel, then T006, then T007.
  It blocks every story.
- **US1 (Phase 3)**: after Phase 2.
- **US2 (Phase 4)**: after US1, since T012 and T013 add to the files T008 and T009 write.
- **US3 (Phase 5)**: after T009, which writes the Issues section that T016 adds to. Its trial
  doesn't need US2.
- **US4 (Phase 6)**: T018 to T022 can start after Phase 2. Its trials T023 to T027 need
  `PRIME.md` complete (T008, T012).
- **Polish (Phase 7)**: after the stories. T029 before the pull request is merged. T033 after.

### Within Each User Story

- The text first (`PRIME.md`, `AGENTS.md`), then the check, then the trial.
- US4: T018 written and failing before T019.
- A trial that starts a new session waits for the owner.

### Parallel Opportunities

- T004 and T005 (`.gitignore`, `Makefile`).
- T008 and T009 (`PRIME.md`, `AGENTS.md`), and T012 and T013.
- T018, then T020, T021 and T022, beside US1 to US3: their files are their own.
- T028 beside the trials of Phase 6.

---

## Parallel Example: User Story 1

```bash
Task: "Write .beads/PRIME.md sections 1, 3, 4 and 7 of contracts/prime.md"   # T008
Task: "Add the Issues section to AGENTS.md, per contracts/agents-md.md"       # T009
```

## Parallel Example: User Story 4

```bash
Task: "Write tests/unit/test_beads_hook.py, per contracts/agent-hooks.md"     # T018, then T019
Task: "Write .codex/hooks.json and .codex/config.toml (owner approval)"       # T021
Task: "Update README.md: Requirements, Setup, How changes are made, Layout"   # T022
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1: the tracker, once the owner confirms its name.
2. Phase 2: `make beads`, and this feature's bead.
3. Phase 3: `PRIME.md` and `AGENTS.md`'s recording rules, and the trial of § 4.
4. **Stop and check**: a bead found mid-task is recorded, and this repository holds nothing of it.

### Incremental Delivery

1. Setup and Foundational: the tracker reachable.
2. US1: recording, the MVP.
3. US2: the flows, the links, the seed.
4. US3: vulnerabilities.
5. US4: the hooks, the README, every clone.
6. Polish: the decisions, the constitution, the results.

---

## Notes

- **Tracker**: `<owner>/<tracker>` = `guimassoqueto/issues`; `<prefix>` = `iss` (the owner, T001,
  2026-11-26). Its clone: `../issues`.
- **This feature's bead**: `iss-bzz` (T007).
- **Codex**: not installed on the owner's machine, so T024 ran the hook command by hand: `bd codex-hook SessionStart`, through `devtools/beads-hook.sh`, returned `.beads/PRIME.md`'s text, from the root and from `app/`. No live Codex session was tried.
- Commit in conventional commits of at most 72 characters, when the owner asks. The pull request's
  title is the owner's to choose: `feat:` releases a minor version (plan.md, Constitution Check).
- A trial bead is always closed with a reason that says it was a trial.

## Phase 8: Convergence

- [ ] T034 Close a vulnerability bead fixed through an advisory once the advisory's fix has merged, with the advisory named: add it to `AGENTS.md`'s Vulnerabilities bullet, and to `.beads/PRIME.md`'s start-of-session check, which reads only `gh-<n>` refs today. A `GHSA-…` ref is read with `gh api repos/<owner>/<repo>/security-advisories/<id> --jq .state` per FR-019, US3/AC5 (partial)
- [ ] T035 Verify recording without a network and from two places before a sync, on a scratch tracker with a local bare remote: a bead recorded with the remote unreachable is kept and reaches the remote at the next push, and beads recorded in two clones before syncing are both in each after a pull and a push. Record the outcome in `specs/010-beads-issue-tracking/spec.md`'s Results per FR-006, US1/AC4, Edge Cases (partial)
- [ ] T036 Once `feat/beads` is pushed, rerun quickstart.md § 7 from a clone of GitHub, not a copy of the working tree, and update SC-003's entry in `specs/010-beads-issue-tracking/spec.md`'s Results per SC-003 (partial)
- [ ] T037 Say in `AGENTS.md`'s Issues, How, that a bead found here about another repository gets that repository's label, `repo:<name>`, per Edge Cases, "A bead about another repository" (partial)
- [ ] T038 Correct `../issues/README.md`, What is here: `main` also holds `.beads/README.md`, `.beads/.gitignore` and `.gitignore`. Commit and push it to the tracker per T003 (partial)
