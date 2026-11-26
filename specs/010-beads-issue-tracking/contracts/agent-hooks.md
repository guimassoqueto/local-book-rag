# Contract: the agents' hooks

How a Claude Code or Codex session in this repository gets beads' context (FR-020, FR-022), and
what it gets when beads isn't there.

## `devtools/beads-hook.sh <agent> [<event>]`

`<agent>` is `claude` or `codex`. For `codex`, `<event>` is one of Codex's hook events. Standard
input is the agent's hook payload, passed on unread.

| Case | Claude Code | Codex `SessionStart` | Codex, other events |
| --- | --- | --- | --- |
| `bd` 1.3.4+ and the tracker reachable (`bd where` exits 0) | runs `bd prime --hook-json` | runs `bd codex-hook SessionStart` | runs `bd codex-hook <event>` |
| No `bd` on the `PATH`, or older than 1.3.4 | context: beads isn't installed (or too old) | the same context | nothing |
| `bd` present, no tracker reachable | context: this clone isn't connected to the tracker; `make beads` | the same context | nothing |

- It always exits 0, so a session starts whatever beads' state (FR-022).
- It runs `bd` from the repository's root, the parent of its own directory, because `bd prime`
  reads `.beads/PRIME.md` only from the directory it runs in (research.md R6).
- "Context" is the hook JSON envelope both agents read:
  `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"<one paragraph>"}}`.
  The paragraph says beads isn't available and why, that the agent works as usual, and that where
  `AGENTS.md` asks for a bead it says in its report what it would have recorded.
- It writes nothing, and makes no network call: `bd where` and `bd prime` read the local database.
- With beads available, what the agent reads is `.beads/PRIME.md` (contracts/prime.md), followed
  by the tracker's memories.

## `.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "", "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/devtools/beads-hook.sh claude" }] }
    ]
  }
}
```

SessionStart fires on startup, resume, clear and after compaction, so it covers FR-020's "again
after its context is compacted". Nothing else goes in this file in this feature.

## `.codex/hooks.json` and `.codex/config.toml`

The shape of beads' "Manual Fallback", with each `bd codex-hook <event>` replaced by
`"$(git rev-parse --show-toplevel)"/devtools/beads-hook.sh codex <event>`: `SessionStart` (`startup|resume|clear`), `PreCompact` and
`PostCompact` (`manual|auto`), `UserPromptSubmit`. `.codex/config.toml` holds only:

```toml
[features]
hooks = true
```

## Not used

`bd setup claude` (writes a section into `CLAUDE.md`, against FR-021), `bd setup codex` (writes a
managed section into `AGENTS.md` and a beads skill into `.agents/skills/beads/`, both with beads'
default workflow text), and beads' Claude Code plugin (research.md, R6).
