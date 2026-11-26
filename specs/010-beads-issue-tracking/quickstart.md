# Quickstart: validating the beads tracker

The trial that proves the feature, step by step, on the owner's machine. `<owner>/<tracker>` and
`<prefix>` are the names the owner confirms in § 1. Each section names the success criteria it
checks. Nothing here touches the application, its containers or its library.

## 0. Prerequisites

- `bd version` says 1.3.4 or later; `gh auth status` is logged in; `ssh -T git@github.com`
  authenticates.
- `gh repo view <owner>/local-book-rag --json visibility` says `PUBLIC` (§ 6 depends on it).
- The branch is `feat/beads`, and `git status` is clean.

## 1. The tracker (once)

The owner confirms the repository's name and prefix first: creating it is outward-facing.

```bash
gh repo create <owner>/<tracker> --private --description "Issues of <owner>'s projects (beads)"
git clone git@github.com:<owner>/<tracker>.git ../<tracker>
cd ../<tracker>
git config beads.role maintainer
bd init --prefix <prefix> --skip-agents --skip-hooks --non-interactive
bd config set types.custom "idea,vulnerability"
# a README saying what this repository is, then:
git add README.md && git commit -m "docs: say what this tracker is" && git push origin main
bd dolt push
```

Expected: `git ls-remote origin` lists `refs/heads/main` and `refs/dolt/data`; `bd types` lists
`idea` and `vulnerability`.

## 2. This clone (SC-003, SC-002)

```bash
cd ../local-book-rag
make beads
git status --short --untracked-files=all
git ls-remote origin | grep -v -E 'refs/(heads|tags|pull)/|HEAD'
```

Expected: `make beads` prints the tracker's `.beads` "via redirect" and a count of 0, the status
shows nothing from `.beads/`, and the last command prints nothing (contracts/make-beads.md).

## 3. The seed (SC-009)

Record this feature's bead (`feature`, in progress, `--spec-id specs/010-beads-issue-tracking`),
then S1 to S18 of data-model.md, each with `repo:local-book-rag` and its `found_in`.

Expected: `bd count --label repo:local-book-rag` is 19, and each seed bead's `metadata.found_in`
names a place in the table. None of the four left-out items is a bead.

## 4. A Claude Code session (SC-006, SC-001)

Start a new Claude Code session in this repository.

- Ask "what should I work on next?", without mentioning beads. Expected: the answer comes from
  `bd ready --label repo:local-book-rag`, highest priority first, and none of it is a task of a
  `tasks.md`.
- Give it a small task on a scratch branch, and point out an unrelated problem along the way.
  Expected: within a minute it records a bead (label, kind, description, `discovered-from` or
  `found_in`), names it in its reply, and goes back to the task.

## 5. Picking beads up (SC-004)

Record four made-up beads, one per kind: `bug`, `feature`, `idea`, `chore`.

- Pick each up. Expected: the bead goes to `in_progress`. For `bug` and `idea`, the agent names
  `/speckit-bug-assess` and `/speckit-assess-intake` and offers to start them. For `feature`, it
  tells the owner to run `/speckit-specify` with the bead's description. For `chore`, it proposes
  a `chore/…` branch with no flow. Stop there, before any record is written, except for the
  `chore`.
- The `chore`: make a one-line change on a `chore/…` branch, open a draft pull request,
  `bd update <id> --external-ref gh-<n>`, close the pull request unmerged, and start a new
  session. Expected: the session's start protocol sets the bead back to `open`, with its
  `external_ref`.
- Close the made-up `bug`, `feature` and `idea` beads with `--reason "Trial"`.
- This feature's bead closes in the first session after its pull request merges (§ 12).

## 6. A vulnerability, while the repository is public (SC-008)

Record a made-up `vulnerability` bead whose description holds a distinctive phrase, and pick it
up. Expected: the agent says the repository is public, and that the owner opens a draft advisory,
not a `fix/…` branch. The owner confirms each outward step:

1. A draft advisory whose summary says it is a trial, opened with
   `gh api repos/<owner>/local-book-rag/security-advisories -X POST` (summary, description,
   severity), and its temporary private fork, with `…/security-advisories/<ghsa_id>/forks -X POST`.
2. In a clone of the fork, a branch with one made-up file holding the phrase, pushed there, and a
   pull request opened in the fork. `bd update <id> --external-ref <ghsa_id>`.
3. The search:

   ```bash
   git fetch origin && git grep -F "<phrase>" $(git for-each-ref --format='%(refname)' refs/remotes/origin)
   gh search code "<phrase>" --repo <owner>/local-book-rag
   gh pr list --repo <owner>/local-book-rag --state all --search "<phrase>"
   gh release list --repo <owner>/local-book-rag | head
   ```

   Expected: the phrase is nowhere in `local-book-rag`, and only in the tracker
   (`bd count --desc-contains "<phrase>"`: `bd search` reads titles only) and the advisory's fork.
4. Stop before the merge: close the advisory with `-X PATCH -f state=closed`. Closing leaves the fork,
   which the owner deletes (`gh repo delete` needs the `delete_repo` scope). Close the bead with
   `--reason "Trial: not a real vulnerability"`.

The private path is the usual bug flow, which needs nothing new to try.

## 7. A fresh clone (SC-003)

```bash
CHECK=$(mktemp -d)
time (git clone git@github.com:<owner>/local-book-rag.git "$CHECK/lbr" \
      && cd "$CHECK/lbr" && make beads BEADS_TRACKER_DIR="$CHECK/tracker" \
      && bd list --label repo:local-book-rag --json | jq length)
```

Expected: the tracker is cloned and bootstrapped into `$CHECK/tracker`, and the count matches
§ 3's plus what § 4 to § 6 recorded, in under ten minutes, following only the README. Remove
`$CHECK` afterwards.

## 8. Codex (SC-006)

If Codex is installed: start a session here and ask "what should I work on next?". Expected: the
same answer as § 4. If it isn't (it isn't on the owner's machine as of the plan), run what Codex
would run, and record that the live session wasn't tried:

```bash
echo '{"hook_event_name":"SessionStart","source":"startup"}' | devtools/beads-hook.sh codex SessionStart
```

Expected: the hook JSON, with `.beads/PRIME.md`'s text as its context.

## 9. Without beads (SC-005)

With `bd` off the `PATH` (a `PATH` without `~/.local/bin`, or wherever `which bd` points):

```bash
make install && make test && make lint-check
devtools/beads-hook.sh claude; echo "exit=$?"
```

Then commit a whitespace-only change on a scratch branch. Expected: `make` targets pass as on
`main`, the hook prints a context saying beads isn't installed and exits 0, and the commit gets
the same fixes and the same message check. Then, with `bd` back, rename `.beads/redirect` for a
moment and run the hook again: the context says this clone isn't connected to the tracker
(contracts/agent-hooks.md). Put the redirect back.

## 10. Spec Kit's upgrade (SC-007)

```bash
make speckit-upgrade
git status --short
```

Expected: nothing changes, or only Spec Kit's generated files, none of them because of beads, and
§ 4's "what next" still works.

## 11. No issue text in this repository (SC-002)

```bash
TITLES=$(mktemp)
bd list --all --label repo:local-book-rag --json | jq -r '.[].title' > "$TITLES"
git grep -F -f "$TITLES" $(git for-each-ref --format='%(refname)' refs/heads refs/remotes) -- . ':!specs/010-beads-issue-tracking'
rm "$TITLES"
```

Expected: nothing. The seed's titles are in this feature's `data-model.md` by design (they come
from public records), and the pathspec leaves that directory out.

## 12. After the merge

In the first session after the pull request merges: this feature's bead closes with
`Merged in #<n>` (§ 2 of contracts/prime.md), and `bd dolt push` sends it.
