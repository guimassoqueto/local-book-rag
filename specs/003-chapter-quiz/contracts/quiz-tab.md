# Contract: the Quiz tab (`app/interface/quiz.py`)

The tab reads input, calls `QuizService`, and shows what it returns. It checks no rule of its own
(constitution IV). Domain errors appear as lasting notifications (`reports_errors`).

## Layout

| Component                 | Kind                   | Notes                                                              |
| ------------------------- | ---------------------- | ------------------------------------------------------------------ |
| Book                      | Dropdown               | Every book in the library, refreshed with the other tabs.          |
| Scope                     | Dropdown               | "The whole book", then the book's chapters by title.               |
| Questions                 | Number                 | Set to `default_count()` whenever book or scope changes. Shows the limit in its info line. |
| Write in                  | Dropdown               | "Same as the book", then `generation.response_languages`.          |
| Prepare                   | Button (primary)       | Inactive while preparing.                                          |
| Stop                      | Button                 | Visible and active only while preparing. Cancels the preparation.  |
| Progress                  | Markdown               | "Preparing: 7 of 20 questions ready", then the outcome.            |
| Question slots × `max_questions` | Markdown + Radio, each in a hidden group | A slot's Markdown holds "**7.** <question>". Its Radio holds "A) …" to "E) …". |
| Submit                    | Button (primary)       | Active only in state `ready`.                                      |
| Result                    | Markdown               | Score, and the ranking for a whole-book quiz.                      |
| Download                  | DownloadButton         | Active after submission.                                           |
| Current quiz              | State                  | The Quiz, then the Result. Per session, in memory.                 |

## Behavior

1. **Choosing book and scope** sets Questions to the default, with the limit shown. A book that
   isn't indexed shows its error and offers no scope.
2. **Prepare.** It clears every slot and the result. The service empties its download directory
   (`contracts/quiz-service.md` § `export`). Then it streams:
   - `QuizStarted` shows the progress line;
   - each `QuestionReady` makes its slot visible, filled. Every other slot is left untouched
     (`gr.skip()`), so answers already chosen stay. The reader can answer while the rest arrive;
   - `QuizReady` activates Submit, and says how many questions the quiz has when it has a
     shortfall.
3. **Stop** ends the preparation. The questions shown stay visible, Submit stays inactive, and the
   progress line says the quiz was stopped. Preparing another quiz then starts over.
4. **An error** ends the preparation the same way, with the notification saying why.
5. **Submit** calls `grade()`, with None for each unanswered slot. Then:
   - each slot shows ✓ or ✗;
   - each missed slot also shows the reader's answer (or "not answered"), the right answer, the
     explanation, and the passage, with its book, chapter, section and pages;
   - the Result shows the score, and for a whole-book quiz the ranking table: chapter, questions,
     missed;
   - the Radios become inactive, and the State holds the Result only;
   - Download becomes active, with the file `QuizService.export()` wrote. The tab writes nothing
     (constitution IV).
6. **Nothing is kept** (FR-018). The quiz and result live in the session's State. A new Prepare or
   a restart discards them. The app's Blocks are created with `delete_cache=(3600, 3600)`, so
   Gradio's copies of downloads are cleared hourly and on restart.

## Download (`result_document()`)

```markdown
# Quiz: <book title>[, <chapter title>]

- **Taken**: <YYYY-MM-DD HH:MM> UTC
- **Book**: <title> (<book_id>)
- **Chapter**: <chapter title>          ← only for a one-chapter quiz
- **Language**: <language>
- **Written by**: <writer>[; **checked by**: <checker>]
- **Score**: <right> of <questions> (<score>%)

## Chapters to reread                   ← only for a whole-book quiz

| Chapter | Questions | Missed |
| ------- | --------- | ------ |

## Questions

### 1. <question>                        ← in quiz order

- A) …
- B) …
- C) …
- D) …
- E) …

**Your answer**: <letter or "not answered"> · **Right answer**: <letter> ✓/✗

<explanation>

*Source*: <chapter>[, <section>], pp. <start>–<end>
```

Each question gets its passage's reference, not its text: the document records the quiz, not the
book.
