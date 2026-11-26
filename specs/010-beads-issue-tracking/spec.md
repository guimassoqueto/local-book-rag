# Feature Specification: Issues found during development, tracked in beads

**Feature Branch**: `feat/beads`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Track the issues found while developing this project (bugs,
vulnerabilities, ideas, and the follow-ups a bug fix leaves) with beads (`bd`, 1.3.4 or later,
https://beads.gascity.com), working together with Spec Kit.

Where the issues live: one beads database in a new private GitHub repository, shared by all of the
owner's projects. local-book-rag is only the first one, so each issue says which repository it
belongs to. This repository is public, so it commits and pushes no issue data, only what a fresh
clone needs to reach the tracker. Beads' default, pushing issues to this repository's origin under
refs/dolt/data, is not used. A vulnerability's details stay in the private tracker until its fix
lands: the public records a fix writes (bug records, specs, commits, PR text) must not disclose it
first.

How beads and Spec Kit fit together: beads is the backlog, and Spec Kit is the record of how each
item was handled. Whatever an agent or the owner finds while working on something else becomes a
bead instead of being fixed on the spot. Picking a bead up starts the flow AGENTS.md maps it to: a
bug to /speckit-bug-assess, an idea to /speckit-assess-intake, a feature to /speckit-specify, a
trivial change to none. The bead links to its record (specs/NNN-…, .specify/bugs/…,
.specify/assessments/…) and closes when its pull request merges. The Follow-ups listed in a bug fix
report become beads linked to the bug they came from. A feature's tasks.md stays the only list of
its tasks, and tasks are not mirrored into beads.

Agents: Claude Code and Codex, the two committed integrations, both get beads' workflow context and
know to record issues. CLAUDE.md keeps only importing AGENTS.md, Spec Kit's generated files stay
untouched, and the existing pre-commit and commit-msg git hooks keep working.

Scope: beads is a development tool. The app, its Docker image, `make test` and CI don't need it,
and nothing in app/ changes. README.md says beads must be installed for development and how to set
it up on a fresh clone. AGENTS.md says when and how to record an issue. docs/decisions.md records
why the tracker is a separate private repository. If the rule belongs in the constitution's
Development Workflow, the plan says so, so it can go through /speckit-constitution."

**The owner's request, before the input above**: "Ok Claude, i installed beads
(https://beads.gascity.com) in my system, and i need it to run in this project to track coding
issues during the development. The github spec kit and beads must to work together. Maybe you need
to update the README.md informing it must be installed and the AGENTS.md to track
issues/bugs/vulnerabilities while working in this project (or maybe create a new github project
just to track this project found bugs, since this monorepo could grow to multiple repos, and the
bugs in all of them could be tracked in a single project, but right now, is only this project)."
Asked where the issues should live, the owner chose a new private repository over this public one
and over a database kept on one machine only. Asked how tightly beads and Spec Kit should be tied,
the owner chose beads as the backlog, with each feature's tasks staying in its `tasks.md` alone.

## Context

Every change that isn't trivial goes through Spec Kit, and `AGENTS.md` maps each kind of change to
its flow: a feature to `/speckit-specify` and its record in `specs/NNN-<slug>/`, a bug to
`/speckit-bug-assess` and `.specify/bugs/<slug>/`, an idea whose worth is uncertain to
`/speckit-assess-intake` and `.specify/assessments/<slug>/`, a wording fix or a dependency bump to
none. Spec Kit records how each change was handled. Nothing records what is still to be handled:

- **A fix report's Follow-ups.** "A bug fix keeps to its assessment: work it reveals beyond the bug
  is recorded under the fix report's Follow-ups, not done" (`AGENTS.md`). Three fix reports list
  them now, in `.specify/bugs/*/fix.md`. They stay there, read only by whoever opens that report.
- **What the benchmarks left to do.** `docs/decisions.md` (Process) calls the Recommendations and
  Known limitations in `docs/benchmark-results.md` "a list of separate changes".
- **What an agent notices in passing.** A bug outside the task, a weakness, an idea: it is fixed on
  the spot, which breaks the rule above, or mentioned in a reply and lost.

Beads (`bd`, 1.3.4 is installed on the owner's machine) is an issue tracker built for coding
agents: each item, a bead, has a type, a priority, a status and links to other beads, and the
agent asks it for the open, unblocked work. It keeps its database in a `.beads/` directory, and
syncs it through a git remote. By default that remote is the repository's own `origin`, under
`refs/dolt/data`, a ref apart from the branches.

`local-book-rag` was public when this feature was asked for. The owner made it private the same day,
2026-11-26, then public again a few hours later, and its visibility may change again. Anyone can
fetch every ref of a public
repository, `refs/dolt/data` included, so issues kept there would be public, vulnerabilities among
them, and issues kept in a private repository would become public the day it is opened. The owner
also expects more repositories, whose issues should be tracked together with these.

In Claude Code, only the owner can start Spec Kit's core skills (`specify`, `plan`, `tasks`,
`implement`, `converge` and the others): they are installed with `--no-model-invocation`
(`docs/decisions.md`, Process). The bug and assessment skills can be started by the agent. Codex's
copies have no such restriction, so `AGENTS.md` asks Codex to keep to it.

Constitution 3.0.0 is about the application: its principles govern its models, its library, its
index, its services, its evaluation and its records, and its Development Workflow lists the tools
and conventions of working on it (Python and uv, ruff, tests, branches, commits, releases, Spec
Kit). It names no issue tracker. Beads changes no principle: nothing in the application uses it.
Whether recording issues in beads is a rule of the Development Workflow is the plan's to say.

What stays as it is: the application, its configuration, its image and its containers; the
application's tests; CI and the release workflow; Spec Kit's flows and their generated files; the
git hooks' checks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - What is found mid-task is recorded, not fixed on the spot (Priority: P1)

An agent implementing a feature in `local-book-rag` notices a bug in code the feature doesn't
touch. Instead of fixing it, it records a bead in the tracker: a bug, with a title, what it saw and
where, a priority, the repository it belongs to (`local-book-rag`) and a link to the work it was
found from. It says in its report that it recorded the bead, and goes back to its task. The owner,
noticing something while reading a result, records one the same way. At the end of the session the
tracker is synced to the private repository, and nothing about the bead appears in
`local-book-rag`: not in a tracked file, a commit, a branch or any other ref of its `origin`.

**Why this priority**: It is the feature: what is found is no longer lost, and the task at hand
keeps to its scope. Every other story works on beads recorded this way.

**Independent Test**: In a session on a feature branch, have the agent find and record one bead,
and record another by hand. Check that both are in the tracker, attributed to `local-book-rag` and
linked to the work they came from; that the working tree and the commits of the branch hold
neither; that `origin` has no ref beyond branches and tags; and that, from a second copy of the
tracker, both beads are visible after a sync.

**Acceptance Scenarios**:

1. **Given** an agent working on a task, **When** it finds a bug, a vulnerability, an idea or a
   change outside that task, **Then** it records a bead of the matching kind instead of doing the
   work, with the repository it belongs to and a link to the task it came from, and says so in its
   report.
2. **Given** a bead recorded, **When** the owner lists the open beads of `local-book-rag`, **Then**
   it is there, and the beads of other repositories are not.
3. **Given** beads recorded in a session, **When** the session ends, **Then** the tracker is synced
   to the private repository, and `local-book-rag`'s working tree, commits and `origin` hold none
   of their content.
4. **Given** no network, **When** a bead is recorded, **Then** it is kept, and reaches the private
   repository at the next sync.

---

### User Story 2 - A bead picked up goes through its Spec Kit flow (Priority: P2)

The owner asks the agent what to work on next. The agent lists the open, unblocked beads of
`local-book-rag`, highest priority first. The owner picks one, a bug: the agent marks it in
progress and starts `/speckit-bug-assess` with the bead's description. Once the assessment exists,
the bead links to `.specify/bugs/<slug>/`, and when the pull request opens, to it. The fix report
lists two Follow-ups, and each becomes a bead linked to the bug's. When the pull request merges, the
bead is closed, with the pull request named. Picked up, a feature bead makes the agent tell the
owner to run `/speckit-specify` with the bead's description, since only the owner can start it in
Claude Code; an idea leads to `/speckit-assess-intake`, and a trivial bead to a branch and a pull
request with no flow. Each feature's tasks stay in its `tasks.md`, and none of them becomes a bead.

**Why this priority**: It ties the backlog to the record: each bead says where its change was
handled, and each record can be traced back to what started it. It needs User Story 1's beads.

**Independent Test**: Record one bead of each kind (bug, feature, idea, trivial). Pick each up and
check that the agent starts, or tells the owner to start, the flow `AGENTS.md` maps it to; that the
bead is in progress and links to its record and its pull request; and that it closes when the pull
request merges. Have one assessment end in `kill`, and close one pull request unmerged: check what
happens to their beads. Check that a fix report's Follow-ups became beads linked to the bug's, and
that no task of a `tasks.md` is a bead.

**Acceptance Scenarios**:

1. **Given** open beads in several repositories, **When** the owner asks what to work on next in
   `local-book-rag`, **Then** the agent lists that repository's open beads that nothing blocks,
   highest priority first.
2. **Given** a bead picked up, **When** its flow starts, **Then** the bead is marked in progress,
   and the flow is the one `AGENTS.md` maps its kind to; when only the owner can start that flow,
   the agent says which command to run, with the bead's description.
3. **Given** a bead in progress, **When** its flow writes its record, and later when its pull
   request opens, **Then** the bead links to each.
4. **Given** a bead's pull request, **When** it merges, **Then** the bead is closed, with the pull
   request named; **When** it is closed unmerged, **Then** the bead is open again, and keeps its
   links.
5. **Given** an assessment that ends in `kill`, or a bug assessment that finds no bug, **When** it
   is written, **Then** the bead closes with the reason and a link to the record.
6. **Given** a fix report with Follow-ups, **When** it is written, **Then** each follow-up is a
   bead linked to the bug it came from, and the report's entry names it.
7. **Given** a feature's `tasks.md`, **When** it is generated, implemented or converged, **Then** no
   bead is created for its tasks.

---

### User Story 3 - A vulnerability stays out of public view until its fix lands (Priority: P3)

An agent finds that a command writes something it shouldn't to the logs. It records a bead of kind
vulnerability in the tracker, with the details. Until the fix merges, nothing public describes it.
How the fix is made depends on the repository's visibility when the bead is picked up. While
`local-book-rag` is private, nothing in it is public, and the bead goes through the usual bug
flow. While it is public, as it is now, the bead leads to a draft security advisory on
`local-book-rag`, and the fix is made in the advisory's temporary private fork: its branch, its bug
record, its commits and its pull request stay private there until the fix merges into `main`. Once
it has, the bug record is in `main`, saying what was fixed, and the advisory is published.

**Why this priority**: A repository that is public, or may be made public again, is what a separate
private tracker is for. It is rarer than the other stories, and builds on both.

**Independent Test**: With the repository public, record a made-up vulnerability with a
distinctive phrase in its details, and pick it up. A draft advisory is opened, and a branch holding
the phrase is pushed to its temporary private fork, with a pull request there. Search this
repository's files, branches, commits, pull requests and releases for the phrase: nothing is found.
Then close the advisory without merging or publishing it. The private path is the usual bug flow,
which every bug already exercises.

**Acceptance Scenarios**:

1. **Given** a vulnerability found, **When** it is recorded, **Then** its bead is marked as a
   vulnerability, and its details are in the tracker only.
2. **Given** a vulnerability bead picked up while the repository is private, **When** its fix
   starts, **Then** it goes through the usual bug flow, as any bug does.
3. **Given** a vulnerability bead picked up while the repository is public, **When** its fix
   starts, **Then** a draft security advisory is opened on `local-book-rag`, and the fix, its bug
   record included, is made in the advisory's temporary private fork.
4. **Given** a vulnerability bead not yet fixed in a public repository, **When** anything public is
   written about it (a record, a commit, a pull request, a fix report's Follow-ups), **Then** it
   doesn't disclose the vulnerability.
5. **Given** the fix merged into `main`, **When** the owner looks, **Then** the bug record in
   `main` says what was fixed, and the bead closes with the pull request, or the advisory and its
   merge, named. A fix made through an advisory has its advisory published.

---

### User Story 4 - Any session and any clone knows the tracker (Priority: P4)

A Claude Code session, or a Codex one, starts in `local-book-rag` with beads' workflow context:
what is open, how to record, how to sync, and `AGENTS.md`'s rules on when to record and which flow
a bead leads to. On another machine, the owner clones `local-book-rag`, follows the README's Setup,
and reaches the same tracker, with the same beads. Someone else who clones the repository without
access to the tracker, or without beads, can still install, test and run the application,
commit with the same checks, and start an agent session, which says beads isn't available.

**Why this priority**: It makes the other stories hold in every session and on every machine, and
keeps the tracker from becoming a requirement of the application.

**Independent Test**: Start a Claude Code session and a Codex session, and ask each what to work
on next, without mentioning beads: each answers from the tracker. Clone the repository into a new
directory, follow the README only, and list the beads. On a machine, or in a container, without
beads: run `make install`, `make test` and `make lint-check`, commit, and start an agent session.

**Acceptance Scenarios**:

1. **Given** a Claude Code or a Codex session in this repository, **When** it starts, or resumes
   after its context is compacted, **Then** it has beads' workflow context and `AGENTS.md`'s rules.
2. **Given** a fresh clone on the owner's other machine, **When** the owner follows the README's
   Setup, **Then** the clone reaches the tracker, and lists the same beads.
3. **Given** a clone without beads, or without access to the tracker, **When** someone installs,
   tests, lints, commits or starts an agent session, **Then** each works as on `main`, and the
   session says beads isn't available instead of failing.
4. **Given** `make speckit-upgrade`, **When** it regenerates Spec Kit's files, **Then** the beads
   integration still works, and no regenerated file carries anything of it.

---

### Edge Cases

- **Beads missing, or older than 1.3.4.** The setup says so, and what to install. Nothing else
  fails: the application, the tests, the hooks and CI don't use it.
- **The tracker unreachable** (offline, or its remote down). Recording and listing work on the local
  copy, and the next sync sends what was recorded. Nothing is lost.
- **Two machines record before syncing.** Both beads are kept, and the next syncs bring both to
  each machine.
- **A bead about another repository**, found while working here. It is recorded as that
  repository's, and lists with it.
- **A duplicate.** A bead that repeats an open one is linked to it and closed as its duplicate.
- **A bead that turns out not to be a bug, or not worth doing.** It closes with the assessment's
  reason, and the record stays, as a `kill` decision does now.
- **One pull request for several beads.** Each closes when it merges.
- **A follow-up that is itself a vulnerability.** The fix report's public entry doesn't describe
  it, and its bead holds the details.
- **The existing backlog.** The tracker doesn't start empty: what is still open of the three fix
  reports' Follow-ups and of the Recommendations and Known limitations of
  `docs/benchmark-results.md` becomes beads when it is set up (FR-031). What was done since is left
  out.
- **A made-up vulnerability**, such as the trial's. It closes as not a real one. Had it gone
  through an advisory, the advisory would be closed without being published.
- **The repository's visibility changes** while a vulnerability is open. What decides is the
  visibility when its fix starts. A fix begun in the usual bug flow while the repository was
  private is merged before it is made public, or its branch and pull request are deleted and the
  fix is made again through an advisory.
- **An advisory's private fork and `main`'s rules.** Status checks don't run in an advisory's
  temporary private fork, and GitHub doesn't enforce the target branch's protection rules when an
  advisory's changes merge (research.md, R8), so the `pr-title` check neither runs nor blocks.
- **A tool that wants to write elsewhere.** Beads' own setup for Claude Code adds a section to
  `CLAUDE.md`, which only imports `AGENTS.md`. Neither that nor anything else of the integration
  writes into `CLAUDE.md`'s import, Spec Kit's generated files, or the git hooks' checks.
- **Beads' git hooks.** If any are installed, the pre-commit fixers and the commit-msg check run
  first and as before, and a commit fails or passes as it does on `main`.
- **Work without an agent.** The owner records, lists and closes beads from the terminal, as the
  README says.
- **A session that finds a bead's pull request merged.** A bead in progress whose pull request has
  merged is closed in the next session that sees it, since nothing in this repository's CI can
  reach the private tracker.

## Clarifications

### Session 2026-11-26 (specify)

- Q: Where does the beads database live, given that this repository is public and beads syncs to
  its `origin` by default? → A: In a new private GitHub repository, one tracker for all of the
  owner's projects. This repository commits no issue data, only the setup that points at it.
- Q: How tightly are beads and Spec Kit tied? → A: Beads is the backlog: what is found becomes a
  bead, picking one up starts its flow, and the bead links to its record and closes when its pull
  request merges. A feature's `tasks.md` stays the only list of its tasks.
- Q: How is a vulnerability fixed, when the bug flow writes its record, branch and pull request in
  this public repository? → A: In the temporary private fork of a GitHub security advisory on
  `local-book-rag`. Nothing of it is public until the fix merges into `main`, and the advisory is
  published after.
- Q: Does the existing backlog become beads when the tracker is set up? → A: Yes, what is still open
  of the three fix reports' Follow-ups and of the Recommendations and Known limitations of
  `docs/benchmark-results.md`.
- Q: Are beads mirrored to the private repository's GitHub Issues, to be read on github.com? → A:
  No. Beads are read and written with `bd` and the agents only.

### Session 2026-11-26 (plan)

- The plan's research found `local-book-rag` private: the owner had changed its visibility that
  day, after the spec was written. GitHub's security advisories exist only for public repositories.
- Q: How does the spec adapt? → A: By visibility. The separate private tracker stays, shared by the
  owner's future repositories, so that this one can be made public again with no issue data in it.
  While the repository is private, a vulnerability goes through the usual bug flow, since nothing
  in it is public. While it is public, it goes through an advisory's temporary private fork. The
  advisory path can't be tried until the repository is public.
- Corrected by the plan: FR-025 said nothing in `tests/` changes, but the project unit-tests its
  development scripts (`tests/unit/test_default_llm_devtool.py`, `test_dump_chunks.py`,
  `test_compare_runs.py`). The agents' hook script gets one too, with a stand-in for `bd`.
- Later that day, the owner made the repository public again. The rule by visibility already
  covers that, and no requirement changed. The trial now runs the advisory path up to the merge
  (SC-008), and `main`'s ruleset, which GitHub Free enforces on public repositories only, is
  enforced again (research.md, R12).

## Requirements *(mandatory)*

### Functional Requirements

#### The tracker

- **FR-001**: The issues are kept in one beads database, synced to a new private GitHub repository
  of the owner's, the tracker, shared by all of the owner's projects. `local-book-rag` is the first.
- **FR-002**: Each bead names the repository it belongs to. Listing one repository's beads shows
  only them; listing all shows every repository's.
- **FR-003**: This repository holds no issue data: no tracked file holds a bead's content, and no
  ref of its `origin` holds the database. Beads' default, syncing to the repository's own `origin`
  under `refs/dolt/data`, is not used.
- **FR-004**: What this repository commits for beads is only what a clone needs to reach the
  tracker. It holds no issue content and no credential.
- **FR-005**: The tracker is reached with the owner's existing access to GitHub. No token or key
  is written to this repository, to the tracker's configuration or to a log.
- **FR-006**: Recording, listing and updating beads work without a network. A sync sends and
  receives what changed, and two places that recorded beads before syncing both keep theirs.
- **FR-007**: The tracker needs beads 1.3.4 or later. A missing or older `bd` is reported by the
  setup, with what to install.

#### Recording what is found

- **FR-008**: Whatever an agent or the owner finds while working on something else is recorded as
  a bead instead of being done on the spot: a bug, a vulnerability, a feature, an idea whose worth
  is uncertain, or a trivial change. The bead has a title, what was seen and where, a priority, its
  kind, its repository, and a link to the work it was found from.
- **FR-009**: An agent that records a bead says so in its report, with the bead's ID and title,
  and goes back to its task.
- **FR-010**: Each Follow-up of a bug fix report becomes a bead, linked to the bead of the bug it
  came from, or to the fix's record when the bug had no bead. The report's entry names the bead.
- **FR-011**: A feature's `tasks.md` stays the only list of its tasks. No task is mirrored into
  beads, and implement and converge keep reading and checking `tasks.md` as they do now.

#### Picking a bead up

- **FR-012**: Asked what to work on next, an agent lists the open beads of the current repository
  that no other bead blocks, highest priority first.
- **FR-013**: A bead picked up is marked in progress, and goes through the flow `AGENTS.md` maps
  its kind to: a bug to `/speckit-bug-assess`, an idea to `/speckit-assess-intake`, a feature to
  `/speckit-specify`, a trivial change to none. When only the owner can start that flow, the agent
  says which command to run, with the bead's description as its input.
- **FR-014**: A bead in progress links to its record (`specs/NNN-<slug>/`, `.specify/bugs/<slug>/`
  or `.specify/assessments/<slug>/`) once the flow writes it, and to its pull request once it opens.
- **FR-015**: A bead closes when its pull request merges, with the pull request named. A pull
  request closed unmerged leaves the bead open again, with its links. An assessment ending in
  `kill`, or a bug assessment that finds no bug, closes the bead with its reason and its record.
- **FR-016**: Recording, picking up, linking and closing beads need no change to Spec Kit's
  generated files, and keep working after `make speckit-upgrade`.

#### Vulnerabilities

- **FR-017**: A vulnerability's bead is marked as one, and its details are kept in the tracker
  only, until its fix starts.
- **FR-018**: Until its fix merges, nothing written about it is public and discloses it: no tracked
  file, branch, commit, pull request title or description, release note, or fix report entry of a
  public repository.
- **FR-019**: How a vulnerability is fixed depends on the repository's visibility when its fix
  starts. While `local-book-rag` is private, it goes through the usual bug flow. While it is public,
  it is fixed in the temporary private fork of a draft GitHub security advisory opened on
  `local-book-rag`: its branch, its bug record, its commits and its pull request stay in that fork
  until the fix merges into `main`, and the advisory is published after. Either way, the bug record
  in `main` says what was fixed, and the bead closes with the pull request, or the advisory, named.

#### Agents

- **FR-020**: A Claude Code or a Codex session in this repository starts with beads' workflow
  context, again after its context is compacted, and with `AGENTS.md`'s rules on when to record a
  bead, which flow each kind leads to, and the vulnerability rule.
- **FR-021**: `CLAUDE.md` keeps only importing `AGENTS.md`. Spec Kit's generated files
  (`.claude/skills/speckit-*`, `.agents/skills/speckit-*`, and `.specify/` but for the constitution
  and the bug and assessment records) are not edited.
- **FR-022**: A session in a clone without beads, or without access to the tracker, starts as it
  does on `main`, and the agent says beads isn't available instead of failing.

#### Development setup

- **FR-023**: The README's Requirements say that beads 1.3.4 or later is needed for development,
  not to run the application, and its Setup says how a fresh clone reaches the tracker and how to
  check that it does.
- **FR-024**: The pre-commit fixers and the commit-msg check run as they do on `main`, and
  `make install` still installs them. Beads' git hooks, if any are installed, don't replace them.
- **FR-025**: The application, its image, `make install`, `make test`, `make lint-check`, CI and
  the release workflow don't need beads. Nothing in `app/`, `config/` or the Dockerfile changes.
  `tests/` gains only a unit test of the agents' hook script, as the other development scripts
  have, and it runs with a stand-in for `bd`, so `make test` still needs no beads.
- **FR-026**: Beads are read and written with `bd` and the agents only. They aren't mirrored to the
  tracker's GitHub Issues or to any other tracker, and no GitHub token is needed for them.

#### Records

- **FR-027**: `AGENTS.md` says when to record a bead, how to record, pick up, link and close one,
  which flow each kind leads to, and the vulnerability rule. Its table of flows says where beads
  come in.
- **FR-028**: `README.md` says how beads fits the way changes are made (How changes are made), and
  how to use it from the terminal.
- **FR-029**: `docs/decisions.md` records why the tracker is a separate private repository (this one
  was public and may be again, every ref of a public repository can be fetched, vulnerabilities,
  and the owner's other repositories), why a vulnerability's path depends on the repository's
  visibility, why tasks aren't mirrored into beads and
  beads aren't mirrored to GitHub Issues, and how the integration keeps to `CLAUDE.md`'s import and
  Spec Kit's generated files.
- **FR-030**: The plan says whether recording found work in beads belongs in the constitution's
  Development Workflow. If it does, the amendment goes through `/speckit-constitution` before this
  feature lands.

#### The existing backlog

- **FR-031**: When the tracker is set up, what is still open of the Follow-ups of the three fix
  reports in `.specify/bugs/*/fix.md`, and of the Recommendations and Known limitations of
  `docs/benchmark-results.md`, becomes beads of `local-book-rag`, each with its kind and a link to
  where it was listed. What was done since is left out, and the plan lists what it seeds and what
  it leaves out, with the reason. The reports and `docs/benchmark-results.md` aren't edited.

### Key Entities

- **Tracker**: the one beads database of the owner's projects, synced to a private GitHub
  repository. Its copies on each machine sync with it.
- **Bead**: one item to handle. It has a title, a description of what was seen and where, a kind
  (bug, vulnerability, feature, idea, trivial), a priority, a status (open, in progress, closed),
  the repository it belongs to, and links: to the work it was found from, to the beads that block
  it, to its record, and to its pull request, or, for a vulnerability fixed while the repository is
  public, to its security advisory.
- **Record**: what a Spec Kit flow writes for a change: `specs/NNN-<slug>/` for a feature,
  `.specify/bugs/<slug>/` for a bug, `.specify/assessments/<slug>/` for an idea. A bead links to at
  most one, and a record can be traced back to the bead that started it.
- **Flow**: the Spec Kit commands `AGENTS.md` maps a kind of change to, or none for a trivial one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a trial session, an item found mid-task is recorded without leaving the session,
  in under a minute, and the agent's next step is back on its task.
- **SC-002**: After the trial, which records at least five beads, one a vulnerability, a search of
  this repository's files, commits, branches, tags and other refs finds none of their text.
- **SC-003**: Following the README alone, a fresh clone in a new directory lists the same beads as
  the first, in under ten minutes.
- **SC-004**: Of the beads picked up in the trial (one of each kind), every one went through the
  flow `AGENTS.md` maps it to, links to its record and its pull request, and closed when its pull
  request merged, or reopened when it was closed unmerged.
- **SC-005**: Without beads installed, `make install`, `make test`, `make lint-check` and CI pass as
  on `main`, and a commit gets the same fixes and the same message check.
- **SC-006**: Asked what to work on next, without being told about beads, a Claude Code session and
  a Codex session each answer from the tracker.
- **SC-007**: After `make speckit-upgrade`, no regenerated file differs because of beads, and the
  trial's recording, picking up and closing still work.
- **SC-008**: The trial's made-up vulnerability, picked up while the repository is public, leads
  to a draft advisory and its temporary private fork. With a branch and a pull request holding a
  phrase of its details in that fork, a search of this repository and its pull requests and
  releases finds the phrase nowhere. The trial stops before the merge, and closes the advisory
  unpublished.
- **SC-009**: Once the tracker is set up, each open item of the plan's list of the existing backlog
  is a bead linked to where it was listed, and no item the plan found done is.

## Assumptions

- The owner is the only developer. The agents are Claude Code and Codex, the two integrations
  committed; the other agents that read `AGENTS.md` get its rules, but aren't verified.
- Beads 1.3.4 is installed on the owner's machine, and is what the tracker is set up and verified
  with.
- The tracker repository is created once, while implementing, after the owner confirms its name.
  It is private, and owned by the owner's GitHub account.
- The tracker is reached through the owner's existing SSH access to GitHub, as `origin` is.
- Security advisories are available on `local-book-rag` only while it is public. The owner opens
  them, by hand or with `gh`, when a vulnerability is picked up then.
- An agent records a bead without asking first, and says so in its report. The tracker is synced at
  the end of each session, and whenever the owner asks.
- Closing a bead when its pull request merges is done by the agent or the owner, in the next
  session that sees the merge. This repository's CI isn't given access to the private tracker,
  which would put a credential to it in workflows that may run in a public repository again.
- A bead's ID reveals nothing about it, so public records can name it: a fix report's Follow-up,
  a spec's Input, a pull request's description. A vulnerability's ID appears without its title.
- Beads' own kinds and priorities are used as they are. "Idea" and "vulnerability" are told apart
  from the others in whatever way beads allows, and the plan says which.

## Results of the implementation, 2026-11-26

The implementation is on `feat/beads`, uncommitted at the time of these checks, on `main` at
`27780d3`. The tracker is `guimassoqueto/issues`, private, prefix `iss`, cloned at `../issues`,
initialized with `bd` 1.3.4 and holding the custom types `idea` and `vulnerability`.
`local-book-rag` was public. The session trials (T011, T015, T023) ran in fresh Claude Code
sessions started headless by the implementing agent, with the owner's leave (`claude -p`, with
tools restricted to `bd`, `gh pr view` and reading files). They loaded the project's hooks as any
session does, and weren't told about beads.

- **SC-001: pass.** Asked what `make down` does, and told in passing that the README's Layout
  doesn't list `scripts/`, the session answered, and recorded `iss-9ln`: `chore`, P4,
  `repo:local-book-rag`, a description with the file, lines and what `scripts/` holds, and its
  `found_in`, since that work had no bead. It named the bead, pushed the tracker and changed
  nothing in the repository, all in a turn of 53 seconds.
- **SC-002: pass.** After every trial, `git status` showed nothing of `.beads/` but `PRIME.md`, and
  `origin` had no ref beyond branches and tags. Searched for in every branch, the 28 bead titles
  turned up in two files only, `docs/benchmark-results.md` and the unmarked-abstentions fix report,
  where two seed beads (S5, S18) took their titles from what those public records say.
- **SC-003: pass.** At first the branch wasn't pushed, so the check ran on a copy of the working
  tree, in a new git repository: `make beads BEADS_TRACKER_DIR=<new directory>` cloned the
  tracker, bootstrapped it, and listed the 19 beads then, in 7 seconds. Once `feat/beads` was
  pushed (convergence, T036), a clone of it from GitHub ran the same command, with a new
  directory for the tracker. It listed all 28 beads in 10 seconds, from the clone to the count,
  and the clone's `git status` stayed clean.
- **SC-004: pass.** Picked up, the four trial beads went in progress. The session named the bug
  flow for the bug, the assessment for the idea, and no flow for the chore. For the feature, it
  told the owner to run `/speckit-specify` with the bead's description. Pull request #29, a draft
  trial linked to the chore as `gh-29`, was closed unmerged, and the next fresh session set the
  bead back to `open`, with its link. Closing on a merge is checked when this feature's pull
  request merges (T033).
- **SC-005: pass, against `main`'s own failures.** Without `bd` on the `PATH`, `make install` and
  `make lint-check` passed, and the hook printed "bd isn't installed" and exited 0. The
  commit-msg check accepted a conventional header, and `.git/hooks` stayed pre-commit's.
  `make test` fails on `main` already, so it can't be "as on `main`" and passing: #27 moved ragas
  to 0.3.1, which stops collection (`iss-30k`) and fails a generation-metrics test, and two config
  tests expect a reasoning #27 changed (`iss-e5z`). Leaving out the module that can't be
  collected, 1,331 tests passed and those 3 failed, with `bd` and without.
- **SC-006: pass for Claude Code, by hand for Codex.** Asked "What should I work on next?", a fresh
  session ran the start protocol, found no merged pull request to close, and answered from
  `bd ready --label repo:local-book-rag`, with `iss-30k` first and the bug flow it would start.
  After `/compact`, the transcript showed SessionStart again with `PRIME.md`. With every tool
  disabled, the session still named this repository's pick-up command and why it isn't `--claim`.
  Codex isn't installed on the owner's machine, so its hook was run by hand. Its `SessionStart` and
  `UserPromptSubmit` returned `PRIME.md`, and its `PreCompact` and `PostCompact` returned nothing,
  from the root and from `app/`.
- **SC-007: pass.** `make speckit-upgrade` changed nothing because of beads, and the hook still
  served `PRIME.md`. It did rewrite the Claude copies of the eight bug and assessment skills, and
  the manifests' dates, with nothing to upgrade. Those were restored, and recorded as `iss-4yg`.
- **SC-008: pass.** A made-up vulnerability (`iss-1un`), picked up while the repository was public,
  led to draft advisory GHSA-725w-r8gv-xvjv and its temporary private fork. A branch and pull
  request #1 there held a random phrase. That phrase was in the tracker's description and the fork
  only: nothing in `local-book-rag`'s refs, pull requests, code search or releases, and the fork
  and the draft answered 404 to an anonymous visitor. The advisory was closed unpublished. Closing
  left the fork, which was deleted once the owner granted `gh` the `delete_repo` scope.
- **SC-009: pass.** The 18 seed beads, with this feature's (`iss-bzz`), made 19, each with its
  `found_in`, and none of the four items left out.
- **FR-006, US1/AC4: pass (convergence, T035).** On the research's scratch tracker, with a local
  bare repository standing in for GitHub:
  - With the remote moved away, a bead was recorded and kept. Its push failed, and once the
    remote was back the next push sent it, and a second clone pulled it.
  - Beads recorded in both clones before a sync were in both after it. The second clone's push
    was refused until it pulled, which merged the two, and then it pushed.

  `.beads/PRIME.md` now says to pull and push again when a push is refused.

### Corrections during implementation

- **`--status in_progress`, not `--claim`.** A claim takes a lease of a few minutes, kept alive by
  `bd heartbeat` and reaped by `bd reclaim` (research.md R5).
- **`bd prime` reads `PRIME.md` only from the directory it runs in.** From `app/`, it gave beads'
  default text. The hook script runs `bd` from the repository's root, the hooks name it by an
  absolute path (`$CLAUDE_PROJECT_DIR`, `git rev-parse --show-toplevel`), and a unit test holds it
  (research.md R6).
- **The tracker's `.beads` is made 0700 after a clone.** git checks it out 0775, and beads warned on
  every command.
- **`make` exits 2, not 1,** when a recipe fails, so the contract says "fails". The redirect keeps
  `BEADS_TRACKER_DIR` as given, relative to the root or absolute.
- **`.dockerignore` leaves out `.beads` and `.codex`,** as it does `.claude` and `.agents`, which
  the tasks didn't list.
- **`bd search` reads titles only.** The quickstart's search of the tracker uses
  `bd count --desc-contains`.
- **Closing an advisory leaves its temporary fork.** `AGENTS.md` says that the owner deletes it.
- **`AGENTS.md` points to the rule instead of restating it.** Once the constitution held the
  **Beads** bullet (3.1.0, T029), the Issues section's opening sent readers to it, and its first
  bullet, "What becomes a bead", became "What counts". The Governance section keeps the rules out
  of `AGENTS.md`.

Found outside this feature, and recorded as beads `discovered-from` `iss-bzz`: `iss-30k` (ragas
0.3.1 breaks `make test`), `iss-e5z` (the config tests' reasoning), `iss-4yg` (`make
speckit-upgrade` isn't idempotent). The trial recorded `iss-9ln` (`scripts/` missing from the
README's Layout).
