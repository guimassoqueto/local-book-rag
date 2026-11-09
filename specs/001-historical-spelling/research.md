# Research: Historical spelling in lexical search

Phase 0 of the plan. Every number here was measured on 2026-11-08 with the scripts described in
R1, against the BM25 tokenizer as it is today (`app/retrieval/bm25.py`: casefold, Snowball
Portuguese stemming, accents stripped).

## R1. The modern Brazilian word list for the measurement (FR-003, SC-005)

- **Decision**: Debian's `wbrazilian` package, version 3.0~beta4-25. It holds 274,246 distinct
  word forms, which make 44,858 distinct keys once stemmed and stripped of accents.
  - **How it was obtained**: `apt-get download wbrazilian`, unpacked with `dpkg-deb -x`, with
    nothing installed.
  - **Its source**: the br.ispell project of Ricardo Ueda Karpischek (IME-USP), GPL-2.
  - **Where it lives**: it is used only by the measurement, and isn't copied into the repository.
- **Rationale**: it is a plain list of every inflected form, which the measurement needs: a
  collision can hide in a plural or a verb form. It predates the 2009 orthographic agreement
  (it has "idéia"), but that agreement changed accents, the diaeresis and hyphens. Lexical search
  ignores all three, and none of them is among the patterns.
- **Alternatives considered**:
  - `hunspell-pt-br`, which is current (2025), but stores stems with affix rules. Expanding them
    needs `unmunch`, from a package that isn't installed.
  - A corpus of modern text: it would only find collisions between the words it happens to contain.

## R2. Where the patterns apply in the tokenizer

- **Decision**: in two places.
  - y → i is applied to the casefolded word, **before** stemming.
  - Every other pattern is applied to the final key, **after** stemming and accent stripping.
- **Rationale**:
  - **y → i goes before.** Snowball's Portuguese stemmer doesn't count `y` as a vowel, so it
    strips "tipo" to `tip` but leaves "typo" whole. Applied after stemming, y → i left tipo/typo
    unmatched (27 of 28 pairs). Before stemming, all 28 match.
  - **The rest go after.** On the final key, the patterns never change how the stemmer reads a
    suffix, and they work on accent-free text. They also collide less: on its own, z → s causes 72
    collisions applied after stemming and 124 applied before. y → i is the exception: 4 after,
    9 before.
- **Alternatives considered**:
  - Every pattern before stemming: more collisions, and the stemmer's rules depend on the
    letters a pattern changes.
  - Every pattern after: loses tipo/typo.

## R3. The patterns, and how collisions are avoided

Each pattern, measured on its own over the 44,858 modern keys. "Collisions" counts groups of
distinct modern keys that the pattern would make identical, and "pairs" counts the spec's 28
pairs it matches on its own: some pairs need two patterns.

| Pattern (where it applies) | Collisions | Pairs alone | Examples of collisions |
| --- | --- | --- | --- |
| ph → f | 0 | 4 | |
| th → t | 4 | 0 | Mathias/mate, Thomé/tom |
| y → i (before stemming) | 9 | 1 | Levy/leva, Paty/pato |
| doubled b c d f g k l m n p t → single | 5 | 10 | Bello/bel, Emma/ema |
| ct → t | 20 | 3 | espectador/espetar, compacta/compatível, cacto/catar |
| gn → n | 14 | 1 | gnomo/nome, resigno/resina, magna/man |
| bd → d | 2 | 1 | abdicar/adição |
| sc → c at the start, before e or i | 0 | 1 | |
| z → s at the end of the key | 34 | 2 | coze/cosa, reze/rês, presa/preza |
| h between vowels → removed | 1 | 1 | Bahamas/Baamas |
| oup → up | 1 | 1 | garoupa/garupa |

Which patterns each of the 28 pairs relies on, worked out by the measurement's own code, so that a
pattern dropped later shows which pairs go with it:

| Pattern | Pairs that rely on it (old spelling) |
| --- | --- |
| ph → f | Sophia, Theophilo, phrase, philosopho, typographico, catastrophes |
| th → t | Theophilo, Thereza |
| y → i | typographico, typo |
| doubled consonant | elle, ella, elles, commissão, anno, officio, apparecer, allegoria, constellação, allegando |
| ct → t | Benedicta, director, facto |
| gn → n | assignasse |
| bd → d | subdito |
| sc at the start | scena |
| z at the end | marquez, apezar, Thereza |
| h between vowels | comprehende |
| oup → up | coupé |

z → s everywhere (72 collisions) and ou → u (43) were tried and dropped in favor of the
narrower forms above. Those cover the same pairs: z → s at the end of the key matches apezar,
marquez and Thereza, whose z ends up last once stemmed, and oup → up matches coupé.

- **Decision**: apply every pattern in the table, and leave unchanged the modern keys that would
  collide with another. These keys are found by iterating until no collision is left, and the
  result is **97 keys**: 34 for z, 20 for ct, 14 for gn, 12 for doubled consonants, 9 for y, 4 for
  th, 2 for bd, 1 for medial h and 1 for oup.
  - **Examples kept unchanged**: pacto, cacto, facção, ficção, secção, signo, digno, gnomo, vez,
    voz, luz, paz, treze, Souza, Queiroz, Tereza, Mathias.
  - **Result**: with them, the measurement finds **0 collisions**, and **all 28 pairs match**
    (SC-004, SC-005).
- **What it costs**:
  - Some kept keys are variant spellings of the same word or name, which merging would have
    served: dactilógrafo/datilógrafo, contactada/contatada, Souza/Sousa, Tereza/Teresa. Telling
    those from real collisions would take a person reading all 97, and leaving them apart breaks
    nothing that works today.
  - Old texts that spell those words that way don't get the merge either.
  - The pair Thereza/Teresa still matches: Thereza's key, `therez`, isn't kept, and folds to
    Teresa's `teres`.
- **What is committed**: the list of 97 keys is this project's output, derived by the measurement,
  and goes into `app/retrieval/bm25.py`. The word list doesn't.
- **Alternatives considered**:
  - **Dropping each colliding pattern**: every pattern but ph → f and the leading sc → c collides
    somewhere, so only those two would be left. They match 5 of the 28 pairs: Sofia, frase,
    filósofo, catástrofes and cena.
  - **Narrowing each pattern by context**: no context separates "pacto" from "facto". Only the
    word does.
  - **Keeping the whole word list at runtime**: it would add a large runtime data dependency,
    which the plan's input rules out.

## R4. The switch

- **Decision**: a new required field, `historical_spelling: bool`, in `BM25Config`
  (`app/config/settings.py`). It is set to `true` in `config/retrieval.yaml`, and a validator
  refuses it without `stemming`.
- **Rationale**:
  - **Required, like the other BM25 settings.** The file then says what search does, and an
    experiment overrides it like any other key.
  - **Validated at startup.** `ConfigModel` forbids unknown keys, which makes a typo an error
    (constitution I).
  - **It needs stemming.** The kept keys were computed on stemmed keys, so with stemming off they
    would protect nothing.
- **Alternatives considered**:
  - **A default value in the model**: it would hide the setting from `config/retrieval.yaml`, where
    every other BM25 setting is written out.
  - **A per-book switch**: unneeded, because FR-003 keeps modern books safe.

## R5. Speed (SC-006)

- **Decision**: the key of each distinct word is computed once per text, and words are re-stemmed
  for y only when they contain a y.
- **Rationale**: tokenizing the whole of *Quincas Borba* (81,698 tokens, 10,989 distinct words, the
  best of five runs):
  - **Today**: 47 ms.
  - **Each token folded on its own**: 98 ms, because every token was stemmed twice.
  - **Once per distinct word**: 39 ms, faster than today.

  A book is tokenized once and then cached (`_tokenize_book`), and a query is a few words, so
  later searches cost the same as today.
- **Alternatives considered**: folding every token as it comes, which is 2.1 times today's time.
  For a book of 1,300 passages that is about 150 ms more, against SC-006's 50.

## R6. How the benchmark measures it (SC-001 to SC-003)

- **Decision**: a new experiment, `benchmarks/experiments/historical_spelling.yaml` (kind
  `retrieval`), with four variants:
  - lexical search alone, with and without the feature
  - the default configuration (hybrid RRF and the Qwen3 reranker, on the GPU as in
    `retrieval.yaml`), with and without the feature

  SC-001 and SC-002 are read per book, by calling `paired_difference` from
  `app/evaluation/report.py` on the run's rows filtered to `quincas_borba`.
- **Rationale**:
  - **Shared workspace.** The four variants index the same way, so they share one workspace.
  - **Recorded configuration.** `results.json` records the full configuration, the new setting
    with it.
  - **The report pools books.** `benchmark-report --baseline` pools all books in its paired
    comparison, while SC-001 is about one book. The same bootstrap on a subset of rows answers
    it, without changing the report.
- **Alternatives considered**:
  - **Adding variants to `retrieval.yaml`**: it would lengthen the canonical experiment and mix
    two questions in one run.
  - **A `--book` option for `benchmark-report`**: a code change outside the scope this plan was
    given.

## R7. Keeping the measurement repeatable

- **Decision**: commit the measurement script as `devtools/measure_historical_spelling.py`. It
  takes the word list's path as its argument, imports the patterns from `app/retrieval/bm25.py`,
  and prints the collisions, the pairs and the kept keys. It also fails if the kept keys differ
  from those committed.
- **Rationale**: the kept keys depend on the patterns. Anyone who changes a pattern has to be able
  to recompute them, from the same word list, without relying on someone's memory of this run.
  It is a development tool, with no runtime role, like the rest of `devtools/`.
- **Alternatives considered**:
  - **No script, only the record in `docs/decisions.md`**: the next change to a pattern would have
    no way to check itself.
  - **A test**: it would need the word list, which stays out of the repository.
