# Contract: the `historical_spelling` setting

The only interface this feature changes is configuration. The commands (`book-rag search`, `ask`,
`summarize`), the Gradio tabs and the services keep their inputs and outputs (FR-005).

## `config/retrieval.yaml`

```yaml
retrieval:
  bm25:
    top_k: 15
    k1: 1.5
    b: 0.75
    stemming: true
    # Portuguese books: old spellings (Sophia, elle, facto) match modern ones (Sofia, ele, fato).
    # Needs stemming. Changes no stored data, so turning it on or off needs no reindex.
    historical_spelling: false   # true until the benchmark failed SC-001 (spec, Assumptions)
```

| Situation | Result |
| --- | --- |
| Key present, `true` or `false` | Loads. `true` applies to books whose language is `pt` |
| Key missing | Startup fails, naming the missing field, as for any required BM25 setting |
| Key misspelled, as in `historical_speling` | Startup fails on the unknown key |
| Not readable as a boolean, such as `"maybe"` or `3` | Startup fails on the type. As for every boolean in `config/`, `true`, `"yes"` and `"1"` all read as true |
| `historical_spelling: true` with `stemming: false` | Startup fails, with a message that names both keys |

A change takes effect after `docker compose restart app`, since `config/` is mounted read-only and
validated at startup. Nothing is reindexed.

## Experiment overrides

Any experiment variant can set it, like any other key:

```yaml
- name: bm25_historical_spelling
  overrides:
    retrieval: {strategy: bm25, reranker: {enabled: false}, bm25: {historical_spelling: true}}
```

An override goes through the same validation, so the combination with `stemming: false` is
refused there too. The run's `results.json` records the value in its full configuration.

## What doesn't change

- **Search results with the setting off**: the same passages, order and scores as before the
  feature, for every language.
- **Search results on books that aren't Portuguese**: the same with the setting on or off.
- **The text of every passage, citation and reference**: as the book prints it.
- **The index fingerprint, the catalog and ChromaDB**: untouched.
