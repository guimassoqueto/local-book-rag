# local-book-rag

Local RAG research platform for books. `.TASK/task.md` was the specification of the first version,
v0.1.0, built one milestone at a time (it stays local: `.git/info/exclude` keeps it out of the
repository). Every change since that isn't trivial goes through Spec Kit, as "How changes are made"
describes.

`README.md` explains how the system works, and `docs/decisions.md` why. Read the second before
changing a behavior that looks odd: most of those decisions came from a failure on real books
or real model output, which unit tests didn't show.

## The constitution

The rules every change keeps, with a Spec Kit flow or without one, are in the constitution:
@.specify/memory/constitution.md

Read it before changing anything. Claude Code loads it through the line above; other agents have
to open it. Its Development Workflow section holds the conventions: Python and uv, linting, tests,
branches, commits and releases. They aren't repeated here, so the two can't disagree.

## How changes are made

| Change                                      | Flow                                                                  | Branch               | Record                         | PR title          |
| ------------------------------------------- | --------------------------------------------------------------------- | -------------------- | ------------------------------ | ----------------- |
| Trivial: wording, a typo, a dependency bump | none                                                                  | `docs/…`, `chore/…`  | none                           | `docs:`, `chore:` |
| A bug: existing behavior is wrong           | `/speckit-bug-assess`, `-fix`, `-test`                                | `fix/<slug>`         | `.specify/bugs/<slug>/`        | `fix:`            |
| An idea whose worth is uncertain            | `/speckit-assess-intake`, `-research`, `-define`, `-shape`, `-decide` | `docs/assess-<slug>` | `.specify/assessments/<slug>/` | `docs:`           |
| A feature                                   | `/speckit-specify`, `-plan`, `-tasks`, `-implement`, `-converge`      | `feat/<slug>`        | `specs/NNN-<slug>/`            | `feat:`           |

A change usually starts from a bead, and the bead's kind picks its row (Issues, below).

- The flows are skills that run inside the agent: `/speckit-specify` in Claude Code,
  `$speckit-specify` in Codex, and usually `/speckit-specify` in the other agents that read
  `.agents/skills/`. Start a core one (constitution, specify, clarify, plan, checklist, tasks,
  analyze, implement, converge) only when the user invokes it. Claude Code enforces this; other
  agents have to keep to it themselves, since Spec Kit can't set it for their copies.
- Create the branch by hand, from an up-to-date `main`, before the first command. Spec Kit creates
  no branches here: it follows the active feature through `.specify/feature.json`, which stays
  local.
- When a feature touches the library's lifecycle or journal, the index fingerprint, prompts or
  citation parsing, or a judge or a metric, it also runs `/speckit-clarify` before the plan,
  `/speckit-checklist` after it, and `/speckit-analyze` after the tasks, before implementing.
- Implement and converge repeat until converge reports "Converged".
- An assessment that ends in `go` becomes a feature: `/speckit-specify` with the handoff in its
  `decision.md`. One that ends in `kill` is kept as the record of why.
- A bug fix keeps to its assessment: work it reveals beyond the bug is recorded under the fix
  report's Follow-ups, not done. Each follow-up also becomes a bead. It is `discovered-from` the
  bug's bead, or has the fix's record as its `found_in` when the bug had none, and the report's
  entry names it.
- Spec Kit's generated files are never edited by hand: `.claude/skills/speckit-*`,
  `.agents/skills/speckit-*`, and everything in `.specify/` except the constitution and the bug and
  assessment records. Run its CLI as `uv run specify`, and after `make update` brings a new
  `specify-cli`, regenerate them with `make speckit-upgrade` and review the diff.

## Issues

The constitution's Development Workflow makes beads the backlog (**Beads**). This section says how.
The tracker is the owner's private `guimassoqueto/issues`, which `make beads` connects a clone to
(README, Setup). A session starts with the commands, from `.beads/PRIME.md`; one that didn't gets
them with `bd prime`.

- **What counts.** Anything found while working on something else: a bug, a vulnerability, a
  feature, an idea whose worth is uncertain, or a trivial change.
- **How.** A bead has exactly one label `repo:<repository>`, `repo:local-book-rag` here, which
  `bd label add` gives to one that lacks it. A bead found here about another of the owner's
  repositories gets that repository's label, and lists with its beads. Its description says what was seen and where (the file
  and line, the command and its output, the record or the run), and is never empty. Its kind is `bug`,
  `vulnerability`, `feature`, `idea` or `chore` (a trivial change), and its priority runs from 0,
  critical, to 4, backlog. It links to the work it came from: `discovered-from` that work's bead,
  or, when the work has none, its path or branch in `found_in`. Work started without a bead gets
  one, in progress, when it starts, so that what it finds can link to it. Record without asking,
  and say in the report what was recorded, with its ID and title.
- **Which flow.** A bead picked up goes in progress, then into its kind's row above: `bug` to the
  bug flow, `idea` to the assessment, `feature` to the feature flow, `chore` to none.
  `vulnerability` follows its own rule, below. The agent starts the bug and assessment skills. A
  core skill such as `/speckit-specify` is started by the owner, so the agent says which command
  to run and gives the bead's description as its input.
- **Linking and closing.** Once its flow writes the record, the bead's `spec_id` names it
  (`specs/NNN-<slug>`, `.specify/bugs/<slug>` or `.specify/assessments/<slug>`). Once its pull
  request opens, the bead's `external_ref` is `gh-<n>`, and one pull request can close several
  beads. A bead blocks another only when it has to land first. It closes when its pull request
  merges, with "Merged in #<n>". Nothing in CI reaches the tracker, so the first session that
  sees the merge closes it. A pull request closed unmerged puts the bead back to open, with its
  links. An assessment that ends in `kill`, or finds no bug, closes the bead with its reason and
  its record. A duplicate closes as "Duplicate of <id>".
- **Vulnerabilities.** A vulnerability's details go in its bead only, with a priority of 0 or 1 and
  a title that says just enough for the owner to recognize it. Nothing public describes it before
  its fix merges: no branch, commit, pull request, release note or fix report entry. A public record
  may name the bead's ID, never its title. When the fix starts, `gh repo view --json visibility`
  decides its path:
  - **Private**: the usual bug flow.
  - **Public**: the owner opens a draft security advisory on the repository
    (`gh api repos/<owner>/<repo>/security-advisories -X POST`) and its temporary private fork
    (`…/security-advisories/<ghsa_id>/forks -X POST`). The fix and its bug record are made in that
    fork, and merged from the advisory, whose status checks and branch rules don't apply there. The
    bead's `external_ref` is the advisory's `GHSA-…` ID. The advisory is published once the fix
    has merged, and the first session that sees it published closes the bead with "Fixed through
    GHSA-…" (`.beads/PRIME.md`). One closed without a fix puts the bead back to open, and leaves
    its fork, which the owner deletes (`gh repo delete` needs the `delete_repo` scope).
  - **If the visibility changes while the fix is open**, the visibility when the fix started still
    decides. A fix begun in the usual bug flow while the repository was private is merged before
    the repository is made public. If it can't be, its branch and pull request are deleted before,
    and the fix is made again through an advisory.
- **Tasks.** A feature's tasks stay in its `tasks.md`: no task becomes a bead.
- **Without beads.** When the session says beads isn't available, work as usual, and list in the
  report what would have been recorded.
- **Sync.** The tracker is pulled at the start of a session and pushed at its end
  (`.beads/PRIME.md`).
