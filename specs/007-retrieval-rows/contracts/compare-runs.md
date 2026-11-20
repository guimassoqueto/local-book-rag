# Contract: comparing two retrieval runs

## Command

```bash
uv run python devtools/compare_runs.py BASELINE CHANGED [--labels BASELINE_LABEL CHANGED_LABEL]
```

Unchanged. It runs on the host, from the repository's root, reads each directory's
`results.json`, prints Markdown on standard output, and writes no file. It refuses as today: exit
status 1, nothing on standard output and `error: …` on standard error, when a run isn't a
retrieval run, holds more than one variant, or shares no question with the other.

## Output, in order

1. `# Two runs, paired by question`, and one line per run: its label, commit, dataset, books and
   date.
2. The questions left out of the pairing.
3. The pairing, rendered by `app.evaluation.report.render`, with the first label as baseline.
4. `## Questions that moved`, and its table or `None.`
5. **New**: `## What ranked above the evidence`, and its table, when at least one question moved.

Parts 1 to 4 are what `main` prints for the same two runs, byte for byte, and part 5 follows them
after an empty line (FR-012, SC-004).

## The new table

```text
## What ranked above the evidence

| question | run | evidence at | ranked above it |
| --- | --- | --- | --- |
| <question> | <first label> | <cell> | <cell> |
| <question> | <second label> | <cell> | <cell> |
```

For each question in "Questions that moved", in that table's order, comes the first run's row, then
the second's.

### Cells

Each run's cells come from that run's row (`data-model.md`):
- **The evidence** is the IDs of the run's own `relevant_chunks`, split on "; ".
- **A rank** is a position in the run's `ranking`, from 1.
- **A chunk** is written `rank: ID`, and chunks are joined with "; ", in rank order.

| The run's row | `evidence at` | `ranked above it` |
| ------------- | ------------- | ----------------- |
| has no `ranking` | `not recorded` | `not recorded` |
| its ranking holds none of the evidence | `not retrieved` | its first ten chunks, or all of them when fewer. `none` when the ranking is empty |
| some evidence within the first ten | the evidence's ranks, up to the largest that is 10 or less, joined with ", " | each chunk above that rank that isn't evidence. `none` when there is none |
| evidence only below the first ten | the smallest evidence rank, the first piece's | every chunk above it |

### Examples

Made up, with short IDs, for a question whose evidence is `e1; e2; e3`. A run whose ranking is `c7,
c9, e1, c2, c4, c5, e2, c8, c3, c6, e3` shows:

| question | run | evidence at | ranked above it |
| --- | --- | --- | --- |
| q2 | a | 3, 7 | 1: c7; 2: c9; 4: c2; 5: c4; 6: c5 |

`e3` ranked eleventh, below anything that a moving score reads, so it isn't shown. Other rankings
of the same question:

| Ranking | Evidence at | Ranked above it |
| ------- | ----------- | --------------- |
| `e1, e2, c1, …` | `1, 2` | `none` |
| `e1, c1, c2, e2, …` | `1, 4` | `2: c1; 3: c2` |
| `c1, c2, …, c12, e1, …` | `13` | `1: c1; 2: c2; …; 12: c12` |
| `c1, c2, …, c30`, no evidence | `not retrieved` | `1: c1; 2: c2; …; 10: c10` |
| `c1, e1, c2`, a chapter of three chunks | `2` | `1: c1` |
| none recorded | `not recorded` | `not recorded` |

### Rules

- **Each run's chunks come from its own row**, under its own label. No ID of one run is matched
  with, or compared to, an ID of the other (FR-011).
- **The table reads `ranking` and `relevant_chunks`** only. The context is the ranking's first
  five, so it adds nothing to this reading.
- **A question left out of the pairing** appears in neither table, as today.

## Old and new results

| First run | Second run | The new table |
| --------- | ---------- | ------------- |
| written before this change | written before | every row says `not recorded` (FR-014) |
| written before | written after | the first run's rows say `not recorded`, and the second run's are read |
| written after | written before | the first run's rows are read, and the second run's say `not recorded` |
| written after | written after | both are read |

## Checked on the stack

- **The fix's two runs**: parts 1 to 4 as on `main`, and part 5 with the four questions that
  moved, each run `not recorded` (SC-004).
- **The fix's run and the run of SC-001**: 75 pairs, none left out, none moved, and no part 5
  (SC-004).
- **The run of SC-001 and the run with reranking off**: part 5 agrees with both runs' rows, by
  FR-009 and FR-010 (SC-005).
