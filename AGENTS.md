# local-book-rag

Local RAG research platform for books. `.TASK/task.md` was the specification of the first version,
v0.1.0, built one milestone at a time (it stays local: `.git/info/exclude` keeps it out of the
repository). Every change since goes through Spec Kit, as "How changes are made" describes.

`README.md` explains how the system works, and `docs/decisions.md` why. Read the second before
changing a behavior that looks odd: most of those decisions came from a failure on real books
or real model output, which unit tests didn't show.

## The constitution

The rules every change keeps, with a Spec Kit flow or without one, are in the constitution:
@.specify/memory/constitution.md

Read it before changing anything. Claude Code loads it through the line above; other agents have
to open it. Its Development Workflow section holds the conventions: Python and uv, linting, tests,
branches, commits and releases. Nothing in it is repeated here, so the two can't disagree.

## How changes are made

| Change                                      | Flow                                                                  | Branch               | Record                         | PR title          |
| ------------------------------------------- | --------------------------------------------------------------------- | -------------------- | ------------------------------ | ----------------- |
| Trivial: wording, a typo, a dependency bump | none                                                                  | `docs/…`, `chore/…`  | none                           | `docs:`, `chore:` |
| A bug: existing behavior is wrong           | `/speckit-bug-assess`, `-fix`, `-test`                                | `fix/<slug>`         | `.specify/bugs/<slug>/`        | `fix:`            |
| An idea whose worth is uncertain            | `/speckit-assess-intake`, `-research`, `-define`, `-shape`, `-decide` | `docs/assess-<slug>` | `.specify/assessments/<slug>/` | `docs:`           |
| A feature                                   | `/speckit-specify`, `-plan`, `-tasks`, `-implement`, `-converge`      | `feat/<slug>`        | `specs/NNN-<slug>/`            | `feat:`           |

- The flows are skills that run inside the agent: `/speckit-specify` in Claude Code, and
  `$speckit-specify` in Codex and the other agents that read `.agents/skills/`. The core ones
  (constitution, specify, clarify, plan, checklist, tasks, analyze, implement, converge) start only
  when the user calls them.
- Create the branch by hand, from an up-to-date `main`, before the first command. Spec Kit creates
  no branches here, since its git extension isn't installed: it follows the active feature through
  `.specify/feature.json`, which stays local.
- A feature also runs `/speckit-clarify` before the plan, `/speckit-checklist` after it, and
  `/speckit-analyze` before implementing, when it touches the library's lifecycle or journal, the
  index fingerprint, prompts or citation parsing, or a judge or a metric. Implement and converge
  repeat until converge reports "Converged".
- An assessment that ends in `go` becomes a feature: `/speckit-specify` with the handoff in its
  `decision.md`. One that ends in `kill` is kept as the record of why.
- A bug fix keeps to its assessment: work it reveals beyond that scope is recorded, not done.
- Spec Kit's generated files are never edited by hand: `.claude/skills/speckit-*`,
  `.agents/skills/speckit-*`, and everything in `.specify/` except the constitution and the bug and
  assessment records. Run its CLI as `uv run specify`, and after `make update` brings a new
  `specify-cli`, regenerate them with `make speckit-upgrade` and review the diff.
- The constitution changes only through `/speckit-constitution`.
