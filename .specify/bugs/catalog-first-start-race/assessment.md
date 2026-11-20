# Bug Assessment: two processes creating an empty catalog at once fail with "table already exists"

- **Slug**: catalog-first-start-race
- **Created**: 2026-11-20
- **Source**: pasted text (the owner's terminal, `make up && make pull-models && make doctor`)
- **Verdict**: valid
- **Severity**: low

## Report (verbatim or summarized)

On a stack created from scratch after a Docker prune, the owner ran
`make up && make pull-models && make doctor`. `make up` rebuilt the image and started the three
containers. `make pull-models`, which runs `docker compose exec app book-rag pull-models`
(`scripts/pull_models.sh`), then failed:

```text
File "/app/app/main.py", line 26, in main
    arguments.handler(build_container(console_logs=arguments.handler is _serve), arguments)
File "/app/app/container.py", line 76, in build_container
    return assemble(settings, environment, environ=os.environ)
File "/app/app/container.py", line 104, in assemble
    catalog = BookCatalog(root / "metadata" / "catalog.db")
File "/app/app/storage/catalog.py", line 195, in __init__
    _Base.metadata.create_all(self._engine)
...
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table chapters already exists
[SQL: CREATE TABLE chapters (...)]
make: *** [Makefile:82: pull-models] Error 1
```

Afterwards the catalog held all five tables (`books`, `chapters`, `counters`, `indexes`,
`operations`), the app container was healthy and had never restarted (`RestartCount` 0), and the
owner ran the commands again and added a book without error. The app was built from
`feat/openai-provider` (`a41a34f`); the catalog's code is the same on `main` (`664df70`).

## Symptom

When two processes open the catalog of an empty library at the same moment, one of them fails with
`table … already exists` and stops. Expected: both open the catalog, whichever created it.

## Reproduction

On the stack, timing-dependent:
1. Start from an app container with no `data/metadata/catalog.db`: a new container, after
   `make down`, a prune, or any change that makes `make up` recreate it.
2. Run `make up && make pull-models`. `make up` (`docker compose up -d --build`) returns as soon as
   the container has started, before it is healthy, so `book-rag serve` (the image's `CMD`) is still
   building its container when `pull-models` builds its own.
3. One of the two fails on its first `CREATE TABLE` whose table the other has just created.

Deterministically, as research for the fix (ran 2026-11-20 on `main`'s code): create a catalog,
then open it again with SQLite's `has_table` patched to answer `False`, as a process that checked
before the other created the tables sees it. `BookCatalog(path)` raises
`OperationalError: table books already exists`.

## Suspected Code Paths

- `app/storage/catalog.py:191-195`, `BookCatalog.__init__` — `_Base.metadata.create_all(self._engine)`
  checks which tables exist, then creates the missing ones, one statement at a time. Nothing makes
  the check and the creation atomic across processes, so two processes on an empty database both
  find every table missing, and the second `CREATE TABLE` (or `CREATE INDEX ix_books_checksum`) of
  the slower one fails.
- `app/container.py:102`, `assemble()` — every `book-rag` process builds the catalog first: the
  server at startup, and each command run with `docker compose exec`.
- `Makefile:68-69`, `up` — `docker compose up -d --build` returns before the app is ready, which
  opens the window that the owner's `make up && make pull-models` fell into. It is how the bug was
  met, not its cause: two commands run at once on a new container meet it too.

## Root Cause Hypothesis

`create_all` is check-then-create: it asks SQLite which tables exist, then issues a plain
`CREATE TABLE` (and `CREATE INDEX`) for each one it found missing. Between one process's check and
its creation, another process can create a table, and SQLite then refuses the plain `CREATE` with
"already exists". On a new container the server and the first command run `BookCatalog()` within
the same second, so the window is real. Confidence: high: the traceback, the deterministic
reproduction, and the complete catalog afterwards all agree.

What the loser leaves: the process stops before doing anything. If it is a command, its user sees a
traceback and runs it again. If it is the server, `book-rag serve` exits, and Compose restarts the
container (`restart: unless-stopped`), which then finds the tables. The schema is never left
partial, since the winner creates every table, and no data exists yet to lose.

## Proposed Remediation

**Preferred**: make schema creation idempotent in SQL, so that no check can go stale. Replace
`_Base.metadata.create_all(self._engine)` with one transaction that runs, for each table of
`_Base.metadata.sorted_tables`, `CreateTable(table, if_not_exists=True)`, then
`CreateIndex(index, if_not_exists=True)` for each of its indexes. SQLAlchemy 2.1.9, the locked
version, supports both, and SQLite compiles them to `CREATE TABLE IF NOT EXISTS …` and
`CREATE INDEX IF NOT EXISTS ix_books_checksum …`, which SQLite runs atomically: a second process
creates nothing and fails at nothing. The tables, their columns, keys and the index stay exactly
as `create_all` makes them, so an existing catalog is untouched.

**Alternatives**:
- *A file lock around `create_all`* (`fcntl.flock` on a file beside `catalog.db`): also correct,
  and would cover any future first-start step, but adds a lock to every process's start for a
  problem that SQL already solves.
- *Catch "already exists" and run `create_all` again*: it works, but recognizes the error by its
  message, and needs a loop while the other process is still creating tables.
- *`make up` with `--wait`*, so that it returns only once the app is healthy: it would have spared
  the owner this time, but leaves two commands at once, or a command run right after
  `docker compose up`, exposed. A possible follow-up, not the fix.

**Files likely to change**:
- `app/storage/catalog.py`
- `tests/unit/test_catalog.py`

**Tests to add or update**:
- The race's window, deterministically: with SQLite's `has_table` patched to answer `False` on a
  catalog whose tables exist, `BookCatalog(path)` opens without error (it raises on `main`).
- Opening a catalog twice keeps its books and counters: the second open creates nothing.
- The schema `BookCatalog` creates matches what `create_all` creates: the five tables and
  `ix_books_checksum`, read back from `sqlite_master`.
- Optional, as a stress check rather than a unit test: several processes opening one new
  catalog at once, through a barrier, none failing.

## Risks & Considerations

- **The catalog is the library's journal** (constitution II). The change touches only how its
  empty schema is created, not a row, a transaction of an operation, or recovery, and an existing
  catalog runs `IF NOT EXISTS` statements that do nothing.
- **No migration.** `IF NOT EXISTS`, like `create_all`, never changes an existing table's columns:
  a future schema change still needs its own handling, as today.
- **Foreign keys** stay on through the existing `connect` listener; the DDL is the same.
- **Scope.** Per `AGENTS.md`, the fix keeps to the catalog's creation. `make up --wait`, and any
  other first-start step that might race, go to the fix report's Follow-ups.
- **Measurement.** A unit test reproduces the window exactly, so no stack run, which would empty
  the owner's library again, is needed to prove the fix.

## Open Questions

- None blocking. The owner may later want `make up` to wait for a healthy app (Alternatives), as a
  separate change.
