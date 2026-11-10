# Quickstart: validating the chapter quiz

Runnable checks that the feature works end to end. They point to the contracts rather than repeat
them. Run them from the repository root.

## Prerequisites

- The stack is up and the configured models are pulled: `make up`, then `make pull-models`.
- *História econômica global* is in the library as `book_001`, added through the Library tab
  from the owner's copy.
- `make up` empties the library after any change to the code or to `config/` (README, Running), so
  add the book again after a rebuild.

## 1. Unit tests and lint

```bash
make lint-check
make test
```

**Expected**: all pass, including the new tests of the rules:
- passages, thirds and shares (R6);
- letters and order (R7);
- the default count (R8);
- the reply reader and the form checks (R4);
- grading and the ranking;
- the result document;
- the configuration's validation (FR-029).

## 2. Real-model checks

```bash
make test-integration
```

**Expected**: `tests/integration/test_quiz.py` passes with the configured model (research R14):
- a question comes back readable and in form;
- the bibliography passage is skipped;
- the named language is the one written;
- the check's verdict is readable.

## 3. One chapter (User Story 1)

In the Quiz tab, choose `book_001`, then *Capítulo 1: A grande divergência*.

1. **Questions shows 10**, and its info line shows the limit, which is the chapter's 13 passages.
2. **Prepare.** Questions appear one by one, in place, with "n of 10 ready". Answer question 1
   while the rest arrive: your choice stays. Submit stays inactive until the end.
3. **The finished quiz:**
   - every letter A to E is the right answer exactly twice, as you'll see after submitting;
   - the order isn't the chapter's: the pages of the passages, shown after submitting, jump
     around;
   - the questions come from the chapter's start, middle and end: their pages span 6 to 19. The
     unit tests pin the exact thirds rule (SC-005).
4. **Submit** with two questions unanswered and two wrong:
   - the score is right ÷ 10;
   - the unanswered ones say "not answered";
   - each missed one shows the right answer, the explanation, and its passage with pages.
5. **Download.** The `.md` file holds everything `contracts/quiz-tab.md` § Download lists.

## 4. Stop, and errors (User Story 1, edge cases)

1. Prepare a 20-question quiz on *Capítulo 6*, and press Stop after a few questions. The shown
   questions stay, Submit stays inactive, and the progress line says it was stopped. Prepare
   works again.
2. Stop Ollama (`docker compose stop ollama`) and prepare. A notification says the model can't be
   reached, and stays until dismissed. Start it again (`docker compose start ollama`): stopping
   keeps its models.

## 5. The whole book (User Story 2)

Choose `book_001` and "The whole book", with 20 questions.

**Expected**:
- **Each chapter's count** is within one of its share of the book's words.
- **No question comes from** *Agradecimentos*, *Referências bibliográficas*, *Leituras
  complementares*, *Lista de ilustrações* or *Lista de tabelas*. If those chapters had a share,
  the quiz still has 20, or says how many it has (SC-006).
- **After submitting**, the ranking lists the chapters by questions missed, most first.

A one-chapter quiz shows no ranking.

## 6. Nothing kept (User Story 3, SC-012)

1. After a submission and a download, prepare another quiz. The earlier questions and result are
   gone from the tab, and the tab's temporary directory holds no earlier file.
2. Restart the app with `docker compose restart app`, which keeps the library. Then:

   ```bash
   docker compose exec app sh -c 'find / -xdev -name "quiz-*.md" 2>/dev/null'
   ```

   **Expected**: nothing. This also checks that `delete_cache` emptied Gradio's cache on restart.

## 7. The measurement (User Story 4)

Restore the benchmarks and bring in the quiz experiments and the owner's book (README,
Benchmarks):

```bash
git archive c7bb785 benchmarks | tar -x
cp specs/003-chapter-quiz/benchmarks/*.yaml benchmarks/experiments/
docker compose cp -a benchmarks app:/app/
docker compose cp ~/Documents/livros/01_historia_economica_global.pdf \
    app:/app/benchmarks/books/historia-economica-global.pdf   # the name quiz.yaml lists
docker compose exec app book-rag fetch-benchmark-books
docker compose exec app book-rag benchmark benchmarks/experiments/quiz.yaml --commit "$(git rev-parse --short HEAD)"
docker compose cp app:/app/benchmarks/results benchmarks/
```

**Expected**:
- **The result directory** holds `results.json`, `rows.csv`, `summary.csv` and `reading.csv`.
- **The environment block** holds the model digests, versions, hardware, configuration, commit,
  and every book's checksum.
- **`benchmark-report <dir>`** shows:
  - the letter spread, balanced;
  - `key_is_longest`, targeted at ≤ 35% (SC-002);
  - `closed_book_correct`;
  - where questions come from;
  - `delivered_share`, targeted at ≥ 95% (SC-004);
  - the times.

Then:
1. **Mark** `reading.csv` (sound or flawed, with a reason), and run `benchmark-report` again. The
   share of sound keys appears: at least 90% is the target (SC-003).
2. **Run it again** with another configured model as a variant (SC-010). It reports the same
   measures, and the two pair question by question with `--baseline`.

## 8. The key check's proof (User Story 5)

Once `key_cases.yaml` holds at least 10 flawed and 30 sound cases:

```bash
docker compose exec app book-rag benchmark benchmarks/experiments/quiz_check.yaml --commit "$(git rev-parse --short HEAD)"
```

**Expected**: per variant, the shares the check catches and wrongly rejects, the comparator's
catch share, and `rule_passes` (FR-027). The verdict, and the remaining rate of flawed keys, go to
`docs/decisions.md` and `docs/benchmark-results.md`. `generation.quiz.check.enabled` ships as the
rule says.
