# Bug Fix: two processes creating an empty catalog at once fail with "table already exists"

- **Slug**: catalog-first-start-race
- **Fixed**: 2026-11-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`BookCatalog` now creates its tables and its index with `CREATE … IF NOT EXISTS`, which SQLite runs
atomically, in place of `create_all`, which checked first and created after. Two processes opening
a new catalog at once, such as the server starting and `make pull-models` beside it, now both
succeed. The schema is the one `create_all` made.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `app/storage/catalog.py` | modified | `_create_schema()`: `CreateTable(table, if_not_exists=True)`, then `CreateIndex(index, if_not_exists=True)` for each index, over `_Base.metadata.sorted_tables`, in one `engine.begin()`; `BookCatalog.__init__` calls it in place of `create_all` |
| `tests/unit/test_catalog.py` | added tests | the race's window, a second open, and the schema compared with `create_all`'s |

## Diff Highlights (optional)

```python
def _create_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        for table in _Base.metadata.sorted_tables:
            connection.execute(CreateTable(table, if_not_exists=True))
            for index in sorted(table.indexes, key=lambda index: index.name or ""):
                connection.execute(CreateIndex(index, if_not_exists=True))
```

```diff
-        _Base.metadata.create_all(self._engine)
+        _create_schema(self._engine)
```

## Tests Added or Updated

- `tests/unit/test_catalog.py::test_a_catalog_opens_even_when_its_tables_appeared_after_it_checked`
  — the race's window, deterministically: on a catalog whose tables exist, SQLite's `has_table`
  answers `False`, as it did to the slower process. It failed on `main`'s code with
  `OperationalError: table books already exists`, and passes now.
- `tests/unit/test_catalog.py::test_opening_a_catalog_again_keeps_what_it_holds` — a second open
  creates nothing: the book and the counter are still there.
- `tests/unit/test_catalog.py::test_the_schema_is_the_one_create_all_makes` — the tables and indexes
  in `sqlite_master` are those `create_all` makes: `books`, `chapters`, `counters`, `indexes`,
  `operations` and `ix_books_checksum`.

## Local Verification

- Commands run:
  - `pytest tests/unit/test_catalog.py` → before the fix, 1 failed (the race's window) and 14
    passed; after it, 15 passed.
  - `ruff check .` and `ruff format --check .` → clean.
  - `pytest -m "not integration"` → 1,191 passed: `main`'s 1,188, and the 3 new ones.
- Manual checks: a stress script (not part of the suite) started 4 processes at once through a
  barrier on a new catalog, 40 times. With `main`'s `create_all`, 40 of 40 rounds had a process fail;
  with the fixed `BookCatalog`, 0 of 40.

## Deviations from Assessment

None. The optional multi-process stress check was run by hand, as the assessment suggested, and
not added to the suite, since its timing makes it slow and its failure on `main` depends on the
machine.

## Follow-ups

- **`make up` could wait for a healthy app** (`docker compose up -d --build --wait`), so that a
  command right after it doesn't meet a server still starting. It isn't needed for this bug, and
  it would make `make up` block for up to the app's health-check retries.
- **The OpenAI branch** (`feat/openai-provider`) changes `tests/unit/test_container.py` and other
  tests, not `app/storage/catalog.py`, so the two merge independently.
