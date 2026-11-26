# Contract: `AGENTS.md`, Issues, and the constitution's bullet

The rules agents follow (FR-008 to FR-019, FR-027), in the file every agent reads, with
`CLAUDE.md` still only importing it (FR-021).

## `AGENTS.md`

**How changes are made**: the table keeps its rows and columns. One line under it says that a
change usually starts from a bead, and that its kind picks the row.

**A new section, Issues**, after How changes are made, says:

- **What becomes a bead**: whatever an agent or the owner finds while working on something else (a
  bug, a vulnerability, a feature, an idea whose worth is uncertain, a trivial change) is recorded,
  not done on the spot. This extends the bug-fix rule: each of a fix report's Follow-ups becomes a
  bead too, and its entry in the report names it.
- **How**: the fields of data-model.md, Bead: the `repo:local-book-rag` label, a description of
  what was seen and where, the kind, a priority, and the link to the work it came from. Work
  started without a bead gets one when it starts. The agent records without asking, and says what
  it recorded in its report.
- **Which flow**: data-model.md, Flow mapping. A core skill is started by the owner: the agent says
  which command to run, with the bead's description.
- **Linking and closing**: data-model.md, Bead (record, pull request, reason), and the state
  transitions.
- **Vulnerabilities**: details in the bead only. While the repository is private, the usual bug
  flow. While it is public, the owner opens a draft security advisory, and the fix and its bug
  record are made in the advisory's temporary private fork. Nothing public describes it before the
  fix merges: no branch, commit, pull request, release note or fix report entry. A public record
  may name a bead's ID, never a vulnerability's title.
- **Tasks**: a feature's tasks stay in its `tasks.md`, and no task becomes a bead.
- **Without beads**: when the session context says beads isn't available, the agent works as
  usual, and its report lists what it would have recorded.
- **Setup and sync**: `make beads` once per clone (README, Setup); `PRIME.md`'s protocol pulls at
  the start of a session and pushes at its end.

## The constitution (via `/speckit-constitution`, R11)

One bullet in Development Workflow, after **Spec Kit**:

- **Beads** holds what is still to be handled: what is found while working on something else
  becomes a bead in the owner's private tracker, not a change on the spot, and a bead picked up
  goes through the flow `AGENTS.md` maps its kind to. The repository holds no issue data, and a
  vulnerability is never described in public before its fix lands. `AGENTS.md` says how.

Version 3.1.0, MINOR. No principle changes, and the Governance section's "AGENTS.md is the runtime
guidance file" already covers the how.
