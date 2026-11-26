# Beads in local-book-rag

This repository's issues are beads in the owner's private tracker, `guimassoqueto/issues`, which
the owner's other projects share. Every bead of this repository has the label
`repo:local-book-rag`, and every command below filters on it. When to record a bead, which Spec
Kit flow each kind leads to, and what to do with a vulnerability are in `AGENTS.md`, Issues: this
text holds only the commands. A feature's tasks stay in its `tasks.md`, never in beads.

## At the start of a session

```bash
bd dolt pull
bd list --status in_progress --label repo:local-book-rag --json
```

For each of those beads whose `external_ref` is a pull request, `gh-<n>`, run
`gh pr view <n> --json state`. If it's `MERGED`, run `bd close <id> --reason "Merged in #<n>"`. If
it's `CLOSED`, run `bd update <id> --status open`, which keeps the bead's links.

## What to work on next

```bash
bd ready --label repo:local-book-rag
```

## Recording what is found

```bash
bd create "<title>" -t <bug|vulnerability|feature|idea|chore> -p <0-4> -l repo:local-book-rag \
  -d "<what was seen, and where>" --deps discovered-from:<the bead of the work it came from>
```

When that work has no bead, use `--metadata '{"found_in": "<path or branch>"}'` instead of
`--deps`. Then say in the report what was recorded, with its ID and title, and go back to the task.

## Picking one up

```bash
bd update <id> --status in_progress
bd update <id> --spec-id <specs/NNN-slug | .specify/bugs/slug | .specify/assessments/slug>   # once its flow writes it
bd update <id> --external-ref gh-<n>                                                      # once its pull request opens
```

Use `--status in_progress`, not `--claim`. A claim's lease lasts minutes, but a change here lasts
days.

## Closing

```bash
bd close <id> --reason "Merged in #<n>"                  # done at the start of a session, as above
bd close <id> --reason "<why>; see <record>"             # an assessment ended in kill, or found no bug
bd close <id> --reason "Duplicate of <id>"
```

## At the end of a session

```bash
bd dolt push
```

The tracker is private, and pushing it needs no other permission. Committing and pushing this
repository still follow `AGENTS.md`.
