# Bug Verification: two processes creating an empty catalog at once fail with "table already exists"

- **Slug**: catalog-first-start-race
- **Tested**: 2026-11-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The bug no longer reproduces. Through the application's own entry point, four `book-rag` processes
started at the same instant on a new data folder failed in every round on `main`'s code, with the
errors the owner saw, and in no round with the fix. The new tests, the whole unit suite and lint
pass.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction, `main`'s code | 4 processes run `app.main.main(["list-books"])` through a barrier on a fresh `DATA_DIR`, 20 rounds, from a worktree of `main` (`664df70`) | fail, as expected | 20 of 20 rounds had a failing process: 50 × "table books already exists", 2 × "table chapters already exists" |
| Reproduction, post-fix | the same, from the fix branch | pass | 0 of 20 rounds had a failing process |
| New tests | `pytest tests/unit/test_catalog.py` | pass | 15 passed, the race's window among them, which failed before the fix (fix.md) |
| Regression suite | `pytest -m "not integration"` | pass | 1,191 passed |
| Lint | `ruff check .`, `ruff format --check .` | pass | clean; 147 files formatted |
| The stack's own reproduction | `make up && make pull-models` on a new app container | skipped | it recreates the container, which deletes the owner's library, *História* re-added, and the running image is built from `feat/openai-provider`, not this branch |

## Output Excerpts

```text
== main's code
     50 OperationalError (sqlite3.OperationalError) table books already exists
      2 OperationalError (sqlite3.OperationalError) table chapters already exists
      1 main-tree: rounds with a failing process: 20 of 20
== the fix
      1 local-book-rag: rounds with a failing process: 0 of 20
```

```text
15 passed in 0.14s                       (tests/unit/test_catalog.py)
1191 passed, 76 deselected in 26.73s     (make test's selection)
```

## Residual Risks

- **The stack itself wasn't recreated.** The reproduction ran the real entry point,
  `app.main.main`, through `build_container` and `assemble`, on the host, with four processes in
  place of the server and one command. It reproduced the owner's errors exactly on `main`. On the
  stack, the next `make up` that recreates the app container, after this fix is merged, is the
  confirmation.
- **Commands other than `list-books`** build the same container, so they open the catalog the same
  way; only their later steps differ.
- **Other first-start steps** weren't in scope. The assessment found no other racing one: the
  library's lock and recovery run under the lock, and directories are created with `exist_ok`.

## Recommendation

Close the bug — verified through the application's entry point, with `main`'s failure reproduced
first. Commit on `fix/catalog-first-start-race` and open a pull request titled
`fix: create the catalog's tables safely when two processes start at once`, which makes a patch
release. The follow-up in fix.md (`make up --wait`) stays the owner's call.
