# Bug Verification: Matter that isn't the book is indexed as the book's

- **Slug**: publisher-back-matter
- **Tested**: 2026-11-19
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The bug no longer reproduces. The assessment's three reproduction steps were run again on the fixed
code:
- **On the running stack**, the search that returned the advertisements first now returns unrelated
  passages.
- **On the four real books**, no chunk holds a Gutenberg header or license, a table of contents, a
  printed index or an advertisement.
- **The chapters to summarize** list none of them.

The unit suite and lint pass, and so does the dataset. Retrieval improved slightly, with no question
worse. No regression was found.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction, step 1 (the stack) | `docker compose exec -T app book-rag search "Compre agora e leia um livro de Agatha Christie" --book book_001` | pass | The top five are "Agradecimentos" (reranked 0.001), "Leituras complementares" (0.000) and three passages of chapters 1, 2 and 7. None is an ad or the table of contents. Before the fix: chunks 0264, 0263, 0266 and 0267 at 1.000, 0.987, 0.983 and 0.798 |
| What the stack stored for `book_001` | `grep -c` in `/app/data/processed/book_001/r1/chunks.jsonl` | pass | 263 chunks: none holds "Compre agora e leia" or "Table of Contents". `normalized.json` keeps the ads (10 occurrences), for debugging, as the fix intends |
| Reproduction, step 2 (the real pipeline on the four books) | a throwaway script running `build_pipeline(settings).process(...)` on `benchmarks/books/*.md`, then scanning the chunks and the chapter and section titles | pass | As in `fix.md`: *História econômica global* 15 chapters and 263 chunks, *On Liberty* 9 and 165, *Quincas Borba* 202 and 443, *Think Python* 23 and 317. Languages are `pt`, `en`, `pt`, `en`. No chapter or section has a dropped title. The chunks hold no "Compre agora e leia", "Table of Contents", or Gutenberg notice after the END marker. The one "Project Gutenberg" left is *Think Python*'s own Exercise 13.2 ("Go to Project Gutenberg … and download your favorite out-of-copyright book"), which is the book's text |
| Reproduction, step 3 (the chapters the Summarization tab lists) | a throwaway script adding each book with `BookService.add_book`, then listing `BookService.chapters`. That is the call the tab makes (`app/interface/summarization.py:43`), run on a throwaway library built by `tests/library.py` | pass | No chapter names Gutenberg, a table of contents, an index or FIM. *On Liberty* runs from "Front matter" to "CHAPTER V. APPLICATIONS.", *Quincas Borba* from "1891" to "CAPITULO CCI", *Think Python* from "Front matter" to "Analysis of Algorithms". The library used the real pipeline and services, with fake models, which no chapter list depends on. Not checked in the browser, as in the assessment |
| New tests | `.venv/bin/pytest -q tests/unit/test_structure_extractor.py tests/unit/test_pipeline.py` | pass | 49 passed, the 17 new ones included |
| Regression suite | `make test` | pass | 985 passed, 66 deselected (the integration tests) |
| Lint | `make lint-check` | pass | The project configures no type checker |
| The dataset | `book-rag validate-benchmark` in the app container, with `specs/005-markdown-only`'s dataset copied in, then removed | pass | 0 problems: no evidence quote was in the dropped matter |
| The stack's health | `book-rag doctor` | pass | Index v1 in `book_chunks_v1`, built with `qwen3-embedding:0.6b` |
| Retrieval (Principle VI) | the retrieval experiment's default configuration on `main` (`84f8bf1`) and on the fix, each on a fresh workspace, then `devtools/compare_runs.py` | pass | Run during the fix, not again here. The comparison was read again from the result files |
| Integration suite | `make test-integration` | skipped | `tests/integration/test_interface.py:26` calls `/reset_everything`, which would delete the live library. None of its tests reaches ingestion |
| The residue left to the conversion | `book-rag search "Cip-Brasil. Catalogação na publicação ISBN CDD" --book book_001` | as expected | Chunk 0262 ("Lista de tabelas") comes first, at rerank 1.000. The unheaded catalog record stays, as the owner chose (Residual Risks) |

## Output Excerpts

```text
27 candidates in 0.65s, reranked in 10.91s
book_001_chapter_01_chunk_0000 (Agradecimentos) dense=0.465 rerank=0.001
book_001_chapter_13_chunk_0245 (Leituras complementares) dense=0.501 rerank=0.000
book_001_chapter_08_chunk_0147 (Capítulo 7: A África, Comércio legítimo) bm25=2.749 rerank=0.000
```

```text
== on-liberty.md: language en, 9 chapters, 165 chunks
   titled as dropped: none
   Project Gutenberg: 0 chunks; normalized document (kept for debugging): 39 blocks
   Updated editions will replace: 0 chunks; normalized document (kept for debugging): 1 blocks
== think-python.md: language en, 23 chapters, 317 chunks
   Project Gutenberg: 1 chunks; normalized document (kept for debugging): 2 blocks
      chapter 14: ...'ght consider using the string methods strip, replace and translate.\n\nExercise 13.2. Go to Project Gutenberg (http://gutenberg.org ) and download your favorite out-of-copyright book'...
```

```text
== on-liberty.md: book_002, INDEXED, language en, 9 chapters
   last:  [(7, 'CHAPTER IV. OF THE LIMITS TO THE AUTHORITY OF SOCIETY OVER THE INDIVIDUAL.'), (8, 'CHAPTER V. APPLICATIONS.')]
   titles naming Gutenberg, contents, an index or FIM: none
```

```text
make test: 985 passed, 66 deselected in 20.99s
make lint-check: All checks passed! 139 files already formatted
validate-benchmark: 0 problems
| fix | +0.006 (+0.000 to +0.017) | +0.000 (+0.000 to +0.000) | +0.007 (+0.000 to +0.020) | **+0.005 (+0.000 to +0.015)** | -0.001 (-0.014 to +0.012) | +0.006 (+0.000 to +0.017) |
```

The last line is Recall@5, Recall@10, MRR, nDCG@10, context precision and context recall: the
fix's difference from `main`, with its 95% interval.

## Residual Risks

- **The publisher's pages without a heading are still indexed.** These are *História econômica
  global*'s author bio, edition notes, catalog record and copyright: chunk 262 and the end of 261.
  A search for the catalog record returns chunk 262 first. The owner chose to remove them in the
  conversion, and `docs/benchmark-results.md` records them as a known limitation.
- **Gutenberg's markers are matched in two forms**, "START OF THE PROJECT GUTENBERG EBOOK" and
  "START OF THIS PROJECT GUTENBERG EBOOK", with their END lines. A book whose markers take another
  form, or that has only one of them, keeps all its text, header and license included: nothing of
  the book is cut, but nothing is left out either. Only two Gutenberg books were seen.
- **A real chapter titled exactly** "Index", "Contents", "Table of Contents", "Sumário" or "Índice
  remissivo" would be dropped with everything under it, as `README.md` states the rule.
- **An index built before the fix keeps the dropped matter** until its books are processed again.
  The index fingerprint doesn't change, but in practice `make up` empties the library, and
  `reindex-all` processes every book again.
- **Step 3 wasn't checked in the browser.** The Summarization tab only shows what
  `BookService.chapters` returns (Principle IV), and that call was exercised.
- **The integration suite wasn't run**, since it resets the live library.

## Recommendation

Close the bug: it is verified end-to-end, on the running stack, on the four real books, and by the
unit suite. Retrieval measured slightly better on the benchmark, with no question worse. The fix is
ready to commit on `fix/publisher-back-matter`, for a pull request titled `fix:`. The unheaded
colophon in *História econômica global* stays a known limitation, for the owner's conversion.
