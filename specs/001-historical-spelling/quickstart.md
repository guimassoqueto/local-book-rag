# Quickstart: validating historical spelling in lexical search

How to show that the feature does what [spec.md](spec.md) asks. The setting is described in
[contracts/configuration.md](contracts/configuration.md), and the patterns and kept keys in
[data-model.md](data-model.md).

## Prerequisites

- `make install`. In the Bash tool, uv and asdf aren't on PATH, so first run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"`.
- For scenarios 4 and 5: the stack running (`make up`), the default models pulled, and the
  benchmark books fetched (`book-rag fetch-benchmark-books`).

## 1. Unit tests (FR-001 to FR-009, SC-003, SC-004)

```bash
make test
uv run pytest tests/unit/test_bm25.py tests/unit/test_config.py -q
```

Expected: everything passes, including tests that show:

- **Pairs:** every one of the 28 pairs from the spec gives the same key in both spellings.
- **Curated collisions:** each pair (facção/facão, pacto/pato, sessão/seção/cessão, signo/sino,
  coser/cozer, selo/zelo, gnomo/nome, garoupa/garupa) still gives two different keys.
- **The switch off:** text in English, in a language that isn't Portuguese, or without a language
  gives exactly today's tokens.
- **The question** "Sofia" finds a passage that says "Sophia", and the passage's text is returned
  unchanged.
- **The setting:** it is required, and refused together with `stemming: false`.

## 2. The measurement (FR-003, SC-005)

```bash
mkdir -p /tmp/wbrazilian && cd /tmp/wbrazilian && apt-get download wbrazilian \
  && dpkg-deb -x wbrazilian_*.deb extracted && cd -
uv run python devtools/measure_historical_spelling.py /tmp/wbrazilian/extracted/usr/share/dict/brazilian
```

Expected: about 274,000 words and 44,858 keys, **0 collisions**, **28 of 28 pairs**, and the kept
keys equal to those committed in `app/retrieval/bm25.py` (97 with version 3.0~beta4-25). The script
exits with an error otherwise. Its output, with the package version, goes into `docs/decisions.md`.

## 3. Speed (SC-006)

Tokenize *Quincas Borba* with the setting on and off, as in [research](research.md) R5. Expected:
on is no more than 50 ms slower than off over the whole book. The research measured 39 ms on
against 47 ms off.

## 4. The benchmark (SC-001, SC-002, SC-003)

```bash
make benchmark EXPERIMENT=historical_spelling        # four variants, a few minutes
docker compose exec app book-rag benchmark-report benchmarks/results/historical_spelling_<time> \
  --baseline bm25_exact_spelling
```

SC-001 and SC-002 are about *Quincas Borba* alone. So the same paired bootstrap is run on that
book's rows:

```bash
docker compose exec app python - benchmarks/results/historical_spelling_<time>/results.json <<'EOF'
import json, sys
from app.evaluation.report import paired_difference
rows = [r for r in json.load(open(sys.argv[1]))["rows"] if r["book"] == "quincas_borba"]
for baseline, variant in [("bm25_exact_spelling", "bm25_historical_spelling"),
                          ("default_exact_spelling", "default_historical_spelling")]:
    for metric in ("recall_at_5", "recall_at_10", "mrr", "ndcg_at_10", "context_precision"):
        print(variant, metric, paired_difference(rows, baseline, variant, metric))
EOF
```

Expected:

- **SC-001:** for `bm25_historical_spelling`, Recall@5 has an interval above zero. Recall@5 alone
  decides. MRR and the other metrics are reported, not judged.
- **SC-002:** for `default_historical_spelling`, no metric has an interval wholly below zero. Its
  differences go into `docs/benchmark-results.md` whatever they are.
- **SC-003:** for `think_python` and `on_liberty`, every row is identical between each pair of
  variants: same metrics, question by question. The rows don't record the ranked passages, so
  scenario 1 carries the stronger half of SC-003: the words compared are identical, so the passages,
  order and scores are too.

If SC-001 or SC-002 fails, `config/retrieval.yaml` ships with `historical_spelling: false`, and
the result is recorded (spec, Assumptions).

## 5. By hand (User Story 1)

Only if *Quincas Borba* is in the library (`book-rag list-books`):

```bash
docker compose exec app book-rag search "O que Sofia responde a Rubião?" --book <its id>
```

Expected: passages that say "Sophia" among the results, printed as the book has them, with a
BM25 score.
