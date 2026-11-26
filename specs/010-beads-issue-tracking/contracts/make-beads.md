# Contract: `make beads`

Connects this clone to the tracker. It is the only setup step beads needs, and nothing else in
the Makefile depends on it: `make install`, `make test`, `make lint`, `make lint-check` and the rest
work without beads, as on `main` (FR-025).

## Variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `BEADS_TRACKER_URL` | `git@github.com:<owner>/<tracker>.git` | The private tracker repository, over SSH (FR-005: the owner's existing access, no token) |
| `BEADS_TRACKER_DIR` | `../<tracker>` | Where the tracker is cloned, relative to this repository's root |

Both can be overridden on the command line (`make beads BEADS_TRACKER_DIR=~/src/<tracker>`).

## Steps, in order

1. **`bd` present, 1.3.4 or later.** Otherwise: fails (`make` exits non-zero), and says which version
   was found (or none) and where beads is installed from (FR-007).
2. **No database in this repository's `.beads`.** If `.beads/` holds `embeddeddolt/`, `dolt/`,
   `metadata.json` or `config.yaml`, fails (`make` exits non-zero): a `bd init` has run here, and its
   remote may be this repository's `origin` (FR-003). It deletes nothing.
3. **The tracker cloned.** If `BEADS_TRACKER_DIR` doesn't exist, clones `BEADS_TRACKER_URL` there,
   makes its `.beads` 0700 (git checks it out 0775, and beads warns on every command until it
   is 0700), sets `beads.role` to `maintainer` in its git config, and runs `bd bootstrap` in it.
   If it exists, leaves it as it is.
4. **The redirect.** Writes `.beads/redirect` with `BEADS_TRACKER_DIR/.beads`, as given: a
   relative directory is relative to this repository's root, which is where beads resolves it
   from (research.md R1), and an absolute one stays absolute. Overwrites an existing redirect.
5. **The role.** Sets `beads.role` to `maintainer` in this clone's git config, which silences
   beads' warning (GH#2950) and keeps contributor routing off.
6. **The check.** Runs `bd where`, and `bd count --label repo:local-book-rag`, and prints both.
   A failure of either fails (`make` exits non-zero).

Running it again changes nothing but the redirect, which it writes again.

## Never

- Runs `bd init` in this repository, installs git hooks, or runs `bd setup`.
- Writes a tracked file: `.beads/redirect` is ignored (`.gitignore`: `.beads/*`, `!.beads/PRIME.md`).
- Pushes anything to this repository's `origin`.
