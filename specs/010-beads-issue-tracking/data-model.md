# Data Model: Issues found during development, tracked in beads

Nothing in the application's data changes: no table, collection, configuration key or file under
`app/`, `config/` or `data/`. What this feature models lives in the private tracker, in beads' own
schema, and in the few files this repository commits to reach it.

## Tracker

One beads workspace, `<owner>/<tracker>` on GitHub (private), cloned at `../<tracker>` on each of
the owner's machines (R1, R2).

| Field | Value |
| --- | --- |
| Issue prefix | confirmed with the owner before it is created (proposed `iss`) |
| Storage | beads' embedded Dolt database, `<tracker>/.beads/embeddeddolt/` |
| Remote | the tracker repository's `origin`, `refs/dolt/data` (wired by `bd init`, or `bd bootstrap` on a new machine) |
| Custom types | `types.custom = idea,vulnerability`, stored in the database (R4) |
| Auto-push | off (R9) |
| Git hooks | none (R7) |
| `beads.role` | `maintainer`, in each clone's git config, here and in the tracker |

## Bead

A beads issue, with the fields beads already has. This feature only fixes how each is used.

| Spec attribute | beads field | Rule |
| --- | --- | --- |
| Title | `title` | What is wrong or wanted, in a line. A vulnerability's title says only enough for the owner to recognize it. |
| What was seen and where | `description` | Required: file and line, command, output, the record or the run it came from. |
| Kind | `issue_type` | `bug`, `vulnerability`, `feature`, `idea`, `chore` (trivial) (R4) |
| Priority | `priority` | 0 (critical) to 4 (backlog). A vulnerability is 0 or 1. |
| Status | `status` | `open`, `in_progress`, `closed` |
| Repository | label `repo:<name>` | Exactly one, `repo:local-book-rag` here (R3). |
| Found from | dependency `discovered-from:<id>`, or `metadata.found_in` | The bead of the work it came from. With no bead, the path or branch where it was found (R5). |
| Blocked by | dependency `blocks` | Only when one has to land before the other. |
| Record | `spec_id` | `specs/NNN-<slug>`, `.specify/bugs/<slug>` or `.specify/assessments/<slug>`, once the flow writes it. |
| Pull request | `external_ref` | `gh-<n>`; for a vulnerability fixed through an advisory, the advisory's `GHSA-…` ID. Shared when one pull request closes several beads. |
| Reason closed | `close_reason` | `Merged in #<n>`, `Duplicate of <id>`, or why an assessment ended in `kill` or found no bug, with the record. |

### Validation

- A bead without the `repo:` label, or with two, isn't this repository's. `AGENTS.md` asks for it at
  creation, and the agent adds it with `bd label add` when it finds one without.
- `description` is never empty (`bd create` refuses an empty one only with
  `create.require-description`, so `AGENTS.md` asks for it).
- A vulnerability's details go in `description` and the bead's notes, never in a title that a
  public record might quote.

### State transitions

```text
            claim (picked up)                 its pull request merges
  open ─────────────────────────▶ in_progress ─────────────────────────▶ closed
   ▲                                   │
   │   its pull request closes         │  an assessment ends in kill, or finds no bug,
   └───────── unmerged ────────────────┤  or it duplicates another
                                       └────────────────────────────────▶ closed
```

An `open` bead can also be closed directly: a duplicate, or one that turns out to be moot.

## Flow mapping

What `AGENTS.md`'s table says, by kind:

| Kind | Flow | Started by | Record | Branch |
| --- | --- | --- | --- | --- |
| `bug` | `/speckit-bug-assess`, `-fix`, `-test` | the agent | `.specify/bugs/<slug>/` | `fix/<slug>` |
| `vulnerability` | private repository: as `bug`. Public: a draft advisory, then the bug flow in its temporary private fork (R8) | the owner opens the advisory | `.specify/bugs/<slug>/` | the advisory's fork |
| `feature` | `/speckit-specify`, … | the owner (core skills), with the bead's description | `specs/NNN-<slug>/` | `feat/<slug>` |
| `idea` | `/speckit-assess-intake`, … | the agent | `.specify/assessments/<slug>/` | `docs/assess-<slug>` |
| `chore` | none | the agent | none | `docs/…`, `chore/…` |

## Files this repository commits

| Path | Holds | Issue data |
| --- | --- | --- |
| `.beads/PRIME.md` | The session context for this repository (contracts/prime.md) | none |
| `.claude/settings.json` | Claude Code's `SessionStart` hook (contracts/agent-hooks.md) | none |
| `.codex/hooks.json`, `.codex/config.toml` | Codex's hooks, and hooks turned on | none |
| `devtools/beads-hook.sh` | The hooks' entry point | none |
| `Makefile` | `make beads`, and the tracker's URL and directory (contracts/make-beads.md) | none |
| `.gitignore` | `.beads/*` but `PRIME.md` | none |

Never committed: `.beads/redirect`, and anything else beads writes under `.beads/`.

## The seed

The open part of the existing backlog (R10), each a bead with the label `repo:local-book-rag` and
`metadata.found_in` naming where it was listed. Kinds and priorities are proposals the owner can
change. Paths are short: "unmarked-abstentions" is `.specify/bugs/unmarked-abstentions/fix.md`, and
"Recommendations" and "Known limitations" are the sections of `docs/benchmark-results.md`.

| # | Title | Kind | P | Found in |
| --- | --- | --- | --- | --- |
| S1 | `make up` waits for a healthy app | chore | 4 | catalog-first-start-race, Follow-ups |
| S2 | An abstention-quality variant that counts retrieval misses as right | feature | 3 | unmarked-abstentions, Follow-ups |
| S3 | Rows and logs say whether the marker or the check abstained | feature | 3 | unmarked-abstentions, Follow-ups |
| S4 | Misreads of partial answers by the reply check become test cases | idea | 4 | unmarked-abstentions, Follow-ups |
| S5 | Why gemma4's verdict changes between loads | idea | 4 | unmarked-abstentions, Follow-ups |
| S6 | Unmarked abstentions from models without the reply check (gpt-oss, OpenAI) | idea | 4 | unmarked-abstentions, Follow-ups; Known limitations |
| S7 | gemma4 ignores the answer-language setting | bug | 3 | unmarked-abstentions, Follow-ups (`specs/002-gemma4-default-llm/verdict.md`) |
| S8 | A replay mode for the generation benchmark, without judging | feature | 3 | unmarked-abstentions, Follow-ups (`fix-1.md`) |
| S9 | Reopen gemma4:12b as the default LLM, condition (d) | idea | 3 | unmarked-abstentions, Follow-ups; Recommendations |
| S10 | bge-reranker-v2-m3 as the reranker, timed on the CPU first | idea | 3 | Recommendations |
| S11 | A generation run at 800-token chunks before leaving 500 | idea | 3 | Recommendations |
| S12 | A stronger judge, or two runs per faithfulness claim | idea | 4 | Recommendations; Known limitations |
| S13 | The judge resolves the novel's names badly | idea | 4 | Known limitations |
| S14 | Old-spelling matching misses ch→c and Souza/Sousa | idea | 4 | Known limitations |
| S15 | Benchmark questions that search the whole library | idea | 3 | Known limitations |
| S16 | More chapters for the summary benchmark | idea | 3 | Known limitations |
| S17 | A summary's References heading is always in English | bug | 3 | Known limitations |
| S18 | The embedding comparison also compares chunk sizes | idea | 4 | Known limitations |

Left out: the OpenAI branch's merge note (not a task), *História*'s back matter (done, `aa54d1b`),
the retrieval rows' chunk IDs (done, `16eeda4`), the publisher's pages without a heading (the same
item as the back matter, done).
