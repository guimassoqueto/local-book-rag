# Feature Specification: Historical spelling in lexical search

**Feature Branch**: `feat/historical-spelling`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Let lexical (BM25) search match Portuguese words across their old and modern spellings. Quincas Borba (1891), in the benchmark's Project Gutenberg edition, keeps the spelling of its time: Sophia, Theophilo, Benedicta, elle, anno, facto, philosopho, apparecer, commissão, apezar, Thereza, marquez. Readers type Sofia, Teófilo, Benedita, ele, ano, fato, filósofo, aparecer, comissão, apesar, Teresa, marquês, and BM25 only matches identical stems, so those words never match. [...] It must be possible to switch it off, so the retrieval benchmark can compare search with and without it. Success: on Quincas Borba, BM25 alone improves Recall@5 or MRR with a paired bootstrap interval that excludes zero; the default configuration doesn't get worse, and its difference is reported whatever it is; the English books' results don't change at all. A modern Portuguese word must not start matching a different modern word because of this."

## Context

Portuguese books printed before the 20th-century spelling reforms (1911 in Portugal, 1943 in
Brazil) spell many words differently from how a reader types them today. *Quincas Borba*, in the
benchmark's Project Gutenberg edition, writes Sophia, Theophilo, elle, anno, facto, philosopho,
apparecer and apezar.

Lexical search matches words by their stems, so a question in modern spelling never meets these
words. Of the 46 distinct words, longer than two letters, in the novel's 30 benchmark questions that
never occur in the book under today's lexical search, 28 are in it in an older spelling:

| Typed today | In the book | Occurrences in the book |
| --- | --- | --- |
| Sofia (in 9 questions) | Sophia | 347 |
| ele, ela, eles | elle, ella, elles | 427, 220, 37 |
| Benedita | Benedicta | 104 |
| Teófilo | Theophilo | 38 |
| comissão | commissão | 20 |
| frase | phrase | 19 |
| marquês | marquez | 18 |
| diretor | director | 16 |
| apesar | apezar | 15 |
| Teresa | Thereza | 15 |
| filósofo | philosopho | 13 |
| cupê | coupé | 13 |
| ano, fato | anno, facto | 11, 11 |
| ofício | officio | 8 |
| aparecer, cena, compreendê | apparecer, scena, comprehende | 6, 6, 6 |
| alegoria | allegoria | 4 |
| assinasse | assignasse | 3 |
| tipográfico, constelação, alegando | typographico, constellação, allegando | 2, 2, 2 |
| tipo, catástrofes, súdito | typo, catastrophes, subdito | 1, 1, 1 |

Dense retrieval can't make up for it: it is weakest on this book, with a Recall@5 of 0.715 against
0.803 for lexical search alone, and `docs/benchmark-results.md` lists the old spelling as a known
limitation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask in today's spelling about a book in the old one (Priority: P1)

A reader asks about a Portuguese book printed in the old spelling, writing the way people write
today: "O que Sofia responde a Rubião?". Lexical search finds the passages that say "Sophia", as it
already finds those that share the reader's spelling.

**Why this priority**: it is the whole point of the feature. Without it, a reader's modern spelling
silently loses the passages that hold the answer, and nothing tells them why.

**Independent Test**: search *Quincas Borba* with the lexical strategy alone for a question that
uses a modern spelling from the table above, and check that the passages holding the old spelling
are among the results, shown exactly as the book prints them.

**Acceptance Scenarios**:

1. **Given** *Quincas Borba* in the library, **When** a reader searches for "Sofia", **Then**
   passages containing "Sophia" are returned, with their text as printed.
2. **Given** the same book, **When** a reader searches for a word in the book's own spelling, such
   as "Sophia", **Then** every passage that matched before still matches, though its score and
   position may change.
3. **Given** the same book, **When** a reader searches for "filósofo" or "Teresa", **Then**
   passages containing "philosopho" or "Thereza" are returned.

---

### User Story 2 - Measure it against search without it (Priority: P2)

A researcher compares lexical search with and without the feature in the retrieval benchmark, on the
same dataset, and reads the paired difference in the benchmark report, as with any other variant.

**Why this priority**: in this project, a change made for quality counts only once a benchmark
shows it. The switch is also what lets anyone go back to the previous behavior.

**Independent Test**: run the retrieval experiment with two variants that differ only in this
setting, and read the paired comparison in `benchmark-report`.

**Acceptance Scenarios**:

1. **Given** an experiment with a variant that turns the feature off and one that turns it on,
   **When** the experiment runs, **Then** both variants share the same stored index, and the report
   compares them question by question.
2. **Given** the feature switched off, **When** any search runs, **Then** its results are the same
   as before this feature existed.

---

### User Story 3 - Search a modern edition with words copied from an old one (Priority: P3)

A reader copies a word from an old edition, such as "philosopho", and searches a Portuguese book
written in modern spelling. Lexical search finds "filósofo".

**Why this priority**: less common than the first story, but it is the same equivalence read the
other way, so it comes with it.

**Independent Test**: search a Portuguese text in modern spelling for an old spelling from the
table above, and check that the passages with the modern spelling are returned.

**Acceptance Scenarios**:

1. **Given** a Portuguese book in modern spelling, **When** a reader searches for "Theophilo",
   **Then** passages containing "Teófilo" are returned.

### Edge Cases

- **Two different modern words that would look alike.** Some old-to-modern changes, applied
  blindly, would make two different modern words identical: dropping a doubled consonant turns
  "facção" (faction) into "facão" (machete), and dropping the c of "ct" turns "pacto" into "pato"
  (duck). Such pairs must stay apart.
- **Words that differ only in European Portuguese.** In Portugal, "facto" (fact) and "fato" (suit)
  are two words in use today, while in Brazil "facto" is only the old spelling of "fato". Since
  "modern" means Brazilian spelling, the two match. That is a known false match for European
  Portuguese readers, recorded in `docs/decisions.md`.
- **Modern words and names that keep an old-looking spelling**, such as "Thaís" or "Matheus" in
  Brazilian names. They must still match themselves. Also matching their simplified spelling is
  acceptable, because it is the same name.
- **Words from other languages inside a Portuguese book**, such as the French "coupé" or Latin
  quotations, go through the same matching as the Portuguese text around them.
- **A book whose language is unknown, or isn't Portuguese**, is searched exactly as today.
- **A question in another language asked of a Portuguese book** uses the book's matching, as
  lexical search already does, since matching follows the book's language.
- **A search across several books** applies the feature to each Portuguese book and leaves the
  others as they are.
- **One book mixing both spellings**, as reprints sometimes do: both spellings match either one.

## Clarifications

### Session 2026-11-08

- Q: How is FR-003 checked, so that no modern word starts matching a different one? → A: Both
  ways. A one-off measurement against a modern Portuguese word list, made while the equivalences
  are being designed, with its result recorded in `docs/decisions.md`. The pairs at risk are kept
  as permanent tests.
- Q: In FR-003, does "modern" mean Brazilian spelling, European Portuguese spelling, or both?
  → A: Brazilian spelling. The measurement uses a Brazilian Portuguese word list. facto ↔ fato is
  accepted, and recorded as a known false match for European Portuguese readers.
- Q: Should the equivalences cover only the 28 pairs, the general spelling patterns behind them, or
  every documented difference between the old and modern spelling? → A: The patterns behind the
  28 pairs, applied to every word, minus whatever the FR-003 measurement shows would make two
  modern words identical.
- Q: When a passage is found only because of a spelling equivalence, should the search diagnostics
  say so? → A: No. The diagnostics stay as they are.
- Q: Must all 28 pairs in the Context table match, or may some be left out if a future pattern can
  only match them by making two modern words identical? → A: All 28 must match for this feature.
  Leaving out any pair fails SC-004, and needs the spec changed first.
- Q: When an old spelling appears in another form of the same word, must it match the modern word
  too, or only the forms the spec lists? → A: Every form lexical search already treats as one
  word matches across spellings.
- Q: When a reader searches with the book's own spelling, may the passages they already found move
  up or down, as long as they're still found? → A: Yes. Every passage found today must still be
  found, but its score and position may change. The benchmark judges whether the ranking improved.
- Q: Should lexical search's gain on *Quincas Borba* be judged by one metric chosen now, or may it
  pass on either Recall@5 or MRR? → A: Recall@5 alone decides SC-001. MRR and the other metrics
  are reported, not judged.
- Q: Should "no two modern words collide" be judged against the exact word list measured, or
  against whatever version is newest when the check runs? → A: Against `wbrazilian`
  3.0~beta4-25, named in the spec. A newer list means a new measurement, and any new collisions are
  a later change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Lexical search on a Portuguese book MUST treat a word's old spelling and its modern
  spelling as the same word, in both directions: a modern spelling in the question finds the old
  one in the text, and an old spelling finds the modern one. This holds for every form that lexical
  search already treats as one word: "aparecer" finds "apparecia", and "Sofia" finds "Sophias". The
  equivalences are the spelling patterns behind the pairs in the Context table, applied to every
  word, not only to those pairs.
  The measurement in FR-003 narrowed each one to the smallest form that still matches its pairs:
  - ph for f, th for t and y for i
  - a doubled consonant for a single one, except rr and ss, which modern spelling keeps
  - the silent c of ct, g of gn and b of bd, as in facto, assignasse and subdito
  - sc for c at the start of a word, before e or i, as in scena
  - z for s at the end of a word's root, the part left once its ending is removed, as in apezar,
    marquez and Thereza
  - an h between two vowels, as in comprehende
  - oup for up, as in coupé

  Accents need no pattern, since lexical search already ignores them.
- **FR-002**: Every word pair in the Context table MUST match in both directions, unless it can
  only match by making two modern words identical. FR-003 takes precedence: such a pair is left
  out, and recorded in `docs/decisions.md` with the collision that rules it out. For this feature,
  leaving one out fails SC-004 until the spec is changed.
- **FR-003**: The feature MUST NOT make a modern Portuguese word match a different modern word.
  "Modern" means today's Brazilian spelling. This is checked in two ways:
  - **Once, by a measurement.** While the equivalences are being designed, they are measured
    against a modern Brazilian Portuguese word list. That shows every pair of distinct words that
    the equivalences would make identical. The word list, the count it found and how each collision
    was resolved are recorded in `docs/decisions.md`. The word list isn't kept in the repository or
    in the tests.
  - **Permanently, by curated pairs.** The pairs at risk are kept as tests, and must stay apart.
    They are the known ones (facção/facão, pacto/pato, sessão/seção/cessão, and the others listed
    in the tasks), plus one pair the measurement found for each pattern that needed words left as
    they are. The measurement checks all the others whenever it runs.

  Where a pattern would make two modern words identical, the modern words involved are left as
  they are. They keep matching themselves, and don't gain the old-spelling matching. A pair is left
  out under FR-002 only when that can't keep it.
  - **Spellings of one name stay apart too**: Souza and Sousa, and Tereza and Teresa, are such
    words.
  - **The pairs aren't affected**: Thereza still matches Teresa, since its old spelling isn't one
    of the words left as they are.
- **FR-004**: A word spelled as the book spells it MUST keep matching every passage it matches
  today. Those passages' scores and positions may change, since merging spellings changes how rare
  a word counts as. Whether the ranking improved is for SC-001 and SC-002 to judge.
- **FR-005**: The text the reader sees MUST stay exactly as the book prints it: passages,
  citations, the quotes in a summary's references, and the passages shown in diagnostics. The
  diagnostics show what they show today, and don't say which words matched through an
  equivalence.
- **FR-006**: Nothing stored MUST change: not the chunks, the embeddings, nor the index. Turning
  the feature on or off MUST NOT require a reindex.
- **FR-007**: The feature MUST be switched on or off in the retrieval configuration, validated at
  startup like every other setting, and a benchmark experiment MUST be able to set it per variant.
- **FR-008**: Books in any language other than Portuguese, and books whose language is unknown,
  MUST get exactly the same results with the feature on or off.
- **FR-009**: Dense retrieval and reranking MUST be unaffected: they keep seeing the question and
  the text as they are.

### Key Entities

- **Spelling equivalence**: the relation that says two Portuguese spellings are the same word for
  lexical matching, such as Sophia and Sofia, or anno and ano. It applies only to Portuguese books.
- **The switch**: one retrieval setting that turns the equivalence on or off. It is set in the
  configuration, and an experiment variant can override it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the 25 answerable *Quincas Borba* questions, lexical search alone improves Recall@5
  over the same configuration without the feature, with a paired bootstrap interval (4,000
  resamples, 95%) that excludes zero.
  - **Recall@5 alone decides**, chosen before the run: two chances at a significant result would
    raise the odds of a lucky pass. MRR, Recall@10, nDCG@10 and context precision are reported,
    not judged.
  - **Why all 25, not only those with an old-spelled word**: 21 of the 25 contain one, so
    restricting to them would change little, and a subset chosen after seeing results would bias
    them.
  - **The other 4 can still change**: merging spellings changes how rare a word counts as.
- **SC-002**: The default configuration, hybrid search with reranking, doesn't get worse on *Quincas
  Borba*: none of Recall@5, Recall@10, MRR, nDCG@10 or context precision drops with an interval that
  excludes zero. Its differences are reported in `docs/benchmark-results.md` whatever they are.
- **SC-003**: For books in any language other than Portuguese, the words lexical search compares
  are the same with the feature on and off. So every search on them returns the same passages, in
  the same order and with the same scores. In the benchmark, *Think Python* and *On Liberty* get
  the same metrics, question by question, under both settings.
- **SC-004**: All 28 word pairs in the Context table match in both directions. Leaving any pair out
  fails this criterion, and needs the spec changed first.
- **SC-005**: The measurement against the modern Brazilian Portuguese word list in Debian's
  `wbrazilian` package, version 3.0~beta4-25, finds no pair of distinct words that the final
  equivalences make identical, and every curated pair still stays apart. A newer list is a new
  measurement: any new collisions it finds are a later change, which reruns the measurement and is
  recorded in `docs/decisions.md`.
- **SC-006**: Searching stays as responsive as today: a search on a book of about 1,300 passages
  takes at most 50 ms longer the first time the book is searched, and no longer after that.

## Assumptions

- **Portuguese is recognized by the language the book was indexed with** (`pt`), as lexical search
  already does to pick its stemming. No other language is in scope.
- **The modern spelling is Brazilian**, as in the benchmark's questions and for the people who
  will type them. A book's `pt` code doesn't say which variety it uses, so the same equivalences
  apply to every Portuguese book.
- **The old spelling is the one in use before the 20th-century reforms**, as printed in the
  benchmark's edition of *Quincas Borba*. The equivalences are the patterns listed in FR-001.
  Patterns that none of the 28 pairs shows, such as the mn of "indemnização", can follow later.
- **On by default.** The description asks for a way to switch it off, and nothing changes for
  books in other languages. If SC-001 or SC-002 fails, the feature ships switched off, and the
  result is recorded in `docs/benchmark-results.md`.
- **The measurement rests on one book.** *Quincas Borba* is the only Portuguese book in the
  benchmark, with 25 answerable questions, so only a clear difference will show. The benchmark
  questions keep the modern spelling, as a reader would type it (`docs/decisions.md`).
- **Nothing the reader sees is modernized**, and dense retrieval isn't changed: that would need a
  reindex, and a different feature.
- **Showing which words matched through an equivalence is out of scope.** The lexical score, the
  switch and the benchmark rows are enough to see the feature's effect. It can be a later feature,
  if reading results shows a need.
