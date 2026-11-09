# Data model: Historical spelling in lexical search

Nothing here is stored. The feature adds one setting and two constants. Lexical search computes
everything else in memory, as it already does.

## The setting: `BM25Config.historical_spelling`

| Field | Type | Required | In `config/retrieval.yaml` |
| --- | --- | --- | --- |
| `historical_spelling` | bool | yes, like every BM25 setting | `true` |

Validation, at startup and on every experiment override:

- **The key is required.** A file without it fails to load, as a missing `stemming` does today.
  Unknown keys stay errors (`ConfigModel` forbids them).
- **It needs stemming.** `historical_spelling: true` together with `stemming: false` is refused,
  with a message that names both keys. The kept keys below were computed on stemmed keys, and
  wouldn't protect unstemmed ones.

The setting doesn't join the index fingerprint (`IndexService.current_configuration`). It
changes only how a search matches words, like the query template, and the index never holds BM25
data (constitution III).

## The spelling patterns

An ordered list of patterns, kept in `app/retrieval/bm25.py`. They come in two kinds, because of
where each applies ([research](research.md) R2).

**Before stemming**, on the casefolded word:

| Pattern | Example |
| --- | --- |
| y → i | typo → tipo |

**After stemming and accent stripping**, on the key, in this order:

| Pattern | Example (old key → folded) |
| --- | --- |
| ph → f | soph → sof |
| th → t | theofil → teofil |
| doubled b, c, d, f, g, k, l, m, n, p, t → single (not r or s) | elle → ele, anno → ano |
| ct → t | fact → fat |
| gn → n | assign → assin |
| bd → d | subdit → sudit |
| sc → c at the start of the key, before e or i | scen → cen |
| z → s at the end of the key | apez → apes |
| h between two vowels → removed | comprehend → compreend |
| oup → up | coup → cup |

The order is the one the measurement used. Changing a pattern or the order means running the
measurement again (R7).

## The kept keys

A frozen set of the **97** modern keys that the patterns would make identical to another modern
key, kept in `app/retrieval/bm25.py`. Among them: `pact`, `cact`, `facca`, `ficca`, `sign`, `dign`,
`vez`, `luz`. A key in this set passes through unchanged.

- **Where they come from**: `devtools/measure_historical_spelling.py` derives them from the
  Brazilian word list ([research](research.md) R1, R3). It fails if the set in the code differs
  from what it computes.
- **What they are**: keys, as the tokenizer produces them (stemmed, accent-free), not words.

## How a word becomes a key

For a book whose language is `pt`, with `stemming` and `historical_spelling` both on:

1. **Plain key**: the casefolded word, stemmed and stripped of accents, which is today's key.
2. **Kept unchanged?** If the plain key is one of the kept keys, it is the result.
3. **Re-stem for y.** Otherwise, if the word contains `y`, it is stemmed again with y → i, and
   stripped of accents.
4. **Fold.** The patterns that apply after stemming run over that key, and give the result.

Every other case gives the plain key, byte for byte as today. That covers a language other than
`pt`, no language, `stemming` off (even if the config check was bypassed, as `model_copy` does) and
`historical_spelling` off. The key of each distinct word in a text is computed once per text
(R5).

The question and the book's text go through the same steps, which is what makes the equivalence
work in both directions (FR-001). The text the reader sees is never changed: only the keys are.

## Benchmark variants

`benchmarks/experiments/historical_spelling.yaml`, kind `retrieval`. The four variants differ
only in strategy, reranking and the new setting:

| Variant | Strategy | Reranker | `historical_spelling` |
| --- | --- | --- | --- |
| `bm25_exact_spelling` | bm25 | off | false |
| `bm25_historical_spelling` | bm25 | off | true |
| `default_exact_spelling` | hybrid, RRF | Qwen3, on the GPU | false |
| `default_historical_spelling` | hybrid, RRF | Qwen3, on the GPU | true |
