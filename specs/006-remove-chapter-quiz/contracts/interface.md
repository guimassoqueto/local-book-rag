# Contract: the interface without the quiz

## Tabs

The Gradio interface has four tabs, in this order (FR-001):

| Tab | Unchanged from `main` |
| --- | --------------------- |
| Library | yes |
| Chat | yes |
| Summarization | yes |
| Research | yes |

No Quiz tab, and no label, note or message names the quiz (FR-006).

## Refreshing the book lists

On page load, and after each change in the Library tab, whether it succeeds or fails, one handler
refreshes the lists. Each keeps its selection while the book exists:

| Output | Before | After |
| ------ | ------ | ----- |
| the Library table and index status | yes | yes |
| the Library tab's book | yes | yes |
| the Chat tab's books | yes | yes |
| the Summarization tab's book | yes | yes |
| the Quiz tab's book | yes | removed |

## Files Gradio keeps

| What | Before | After |
| ---- | ------ | ----- |
| downloads | a quiz result, written into `data/quiz_downloads` | none |
| uploads | the Library tab's two pickers, add and replace | unchanged |
| the cache sweep | `delete_cache=(600, 3000)`: every 10 minutes, copies older than 50 minutes; all on shutdown | unchanged: it now serves the uploads' copies (R4) |

## Stopping

`docker compose stop` or `restart` sends SIGTERM. The app turns it into the interrupt Gradio
closes on, as on `main` (FR-007). Gradio shuts down and deletes its cache, and a restart takes
under 2 s (SC-004).

## Commands

No command is added or removed: the quiz had none. `serve` builds the four tabs. Every command
still loads and validates the whole configuration first, so a leftover `generation.quiz` stops
each of them (`contracts/configuration.md`).
