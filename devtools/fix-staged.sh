#!/usr/bin/env bash
# pre-commit hook wrapper: run a fixer on the staged files, then re-stage its fixes.
# Fails only when the fixer leaves issues it cannot fix on its own.
#
#   usage (as a pre-commit entry): fix-staged.sh <fixer command...> -- <files...>
#
# The fixer runs twice: the first pass fixes, the second only reports what is left.
# Its exit code alone can't tell "fixed something" from "could not fix" (the
# pre-commit-hooks fixers exit 1 whenever they change a file).
#
# Partially staged files (staged + further unstaged edits) are fixed but NOT re-staged:
# pre-commit stashes their unstaged edits as a patch and re-applies it afterwards, and
# re-staging would make that patch conflict. Those fall back to pre-commit's normal
# "files were modified" failure, which rolls the fixes back and keeps the edits safe.

fixer=()
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
    fixer+=("$1")
    shift
done
shift

# pre-commit (our parent process) names its stash patch "patch<time>-<its pid>"
patch_dir="${PRE_COMMIT_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/pre-commit}"
stash=$(ls "$patch_dir"/patch*-"$PPID" 2>/dev/null | tail -n 1)

"${fixer[@]}" "$@"
"${fixer[@]}" "$@" >/dev/null 2>&1
status=$?

for file in "$@"; do
    git diff --quiet -- "$file" && continue  # the fixer left it unchanged
    if [ -n "$stash" ] && grep -qF "diff --git a/$file b/$file" "$stash"; then
        echo "$file has unstaged changes, not re-staging the fixes: stage the whole file and commit again"
    else
        git add -- "$file"
    fi
done
exit $status
