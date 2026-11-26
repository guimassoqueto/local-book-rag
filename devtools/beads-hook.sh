#!/usr/bin/env bash
# Gives a Claude Code or Codex session in this repository beads' context
# (specs/010-beads-issue-tracking/contracts/agent-hooks.md):
#
#   devtools/beads-hook.sh claude              from .claude/settings.json, at SessionStart
#   devtools/beads-hook.sh codex <event>       from .codex/hooks.json
#
# With bd 1.3.4 or later and the tracker reachable (`make beads`), it hands over beads' own hook,
# which reads .beads/PRIME.md. Otherwise it tells the session why beads isn't available. It always
# exits 0, so a session starts whatever beads' state, and it makes no network call.

set -u

agent=${1:-}
event=${2:-SessionStart}
minimum=1.3.4

case "$agent" in
    claude | codex) ;;
    *)
        echo "usage: devtools/beads-hook.sh claude | codex <event>" >&2
        exit 0
        ;;
esac

# Only SessionStart takes context. Codex's other events get nothing when beads isn't there.
unavailable() {
    if [ "$agent" = codex ] && [ "$event" != SessionStart ]; then
        exit 0
    fi
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
        "Beads isn't available in this session: $1. Work as usual, and where AGENTS.md (Issues) asks for a bead, list in your report what you would have recorded."
    exit 0
}

command -v bd > /dev/null 2>&1 || unavailable "bd isn't installed (README, Requirements)"

# bd prime reads .beads/PRIME.md only from the directory it runs in, and gives beads' default text
# from any other, so bd runs from this repository's root, wherever the session started.
here=${BASH_SOURCE[0]%/*}
[ "$here" = "${BASH_SOURCE[0]}" ] && here=.
cd -P -- "$here/.." 2> /dev/null || unavailable "the repository's root couldn't be entered"

version=$(bd version 2> /dev/null | sed -n 's/^bd version \([0-9][0-9.]*\).*/\1/p' | head -n 1)
if [ -z "$version" ] ||
    [ "$(printf '%s\n%s\n' "$minimum" "$version" | sort -V | head -n 1)" != "$minimum" ]; then
    unavailable "bd ${version:-of an unknown version} is older than $minimum (README, Requirements)"
fi

bd where > /dev/null 2>&1 || unavailable "this clone isn't connected to the tracker: run make beads (README, Setup)"

if [ "$agent" = claude ]; then
    bd prime --hook-json
else
    bd codex-hook "$event"
fi
exit 0
