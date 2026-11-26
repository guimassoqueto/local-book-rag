# Contract: `.beads/PRIME.md`

The text an agent session starts with when beads is available, in place of beads' default
(research.md, R6). It holds commands and the session protocol, and the rules stay in `AGENTS.md`,
so the two can't disagree. It holds no issue data: it is committed and may be public.

## Sections, in order

1. **What this is**: one paragraph. This repository's issues are beads in the owner's private
   tracker, labeled `repo:local-book-rag`. The rules on when to record one, which flow each kind
   leads to, and vulnerabilities are in `AGENTS.md`, Issues. A feature's tasks stay in its
   `tasks.md`, never in beads.
2. **At the start of a session**: `bd dolt pull`. Then, for each of this repository's beads in
   progress with a pull request (`bd list --status in_progress --label repo:local-book-rag --json`),
   `gh pr view <n> --json state`: `MERGED` → `bd close <id> --reason "Merged in #<n>"`; `CLOSED` →
   `bd update <id> --status open`.
3. **What to work on next**: `bd ready --label repo:local-book-rag`.
4. **Recording what is found**: `bd create "<title>" -t <kind> -p <0-4> -l repo:local-book-rag
   -d "<what was seen, and where>" --deps discovered-from:<id>`, or `--metadata
   '{"found_in":"<path or branch>"}'` when the work has no bead. Then say it in the report, with
   the ID and the title, and go back to the task.
5. **Picking one up**: `bd update <id> --status in_progress`; once the flow writes its record,
   `bd update <id> --spec-id <path>`; once its pull request opens,
   `bd update <id> --external-ref gh-<n>`.
6. **Closing**: as in 2, or `bd close <id> --reason "<why>; see <record>"` for an assessment that
   ends in `kill` or finds no bug, and `--reason "Duplicate of <id>"`.
7. **At the end of a session**: `bd dolt push`. The tracker is private, and pushing it needs no
   other permission. Committing and pushing this repository still follow `AGENTS.md`.

## Never in it

Issue titles or IDs, the tracker's name or URL beyond what the Makefile already holds, "use beads
for all task tracking", or anything about the agents' own memory files.
