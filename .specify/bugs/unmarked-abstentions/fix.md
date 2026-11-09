# Bug Fix: Abstentions without the no-evidence marker

- **Slug**: unmarked-abstentions
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

gemma4:12b and qwen3.5:9b now read each of their replies without the no-evidence marker again,
in one short call. A reply that gives none of what was asked is shown as an abstention. The
answering prompt is unchanged, and gpt-oss:20b, the default, runs no check. The first attempt, a
rewording of the prompt, is in `assessment-1.md` and `fix-1.md`.

## Changes

| File | Change | Notes |
| --- | --- | --- |
| `app/config/settings.py` | modified | `LLMProfile.check_abstentions`, a boolean, off by default |
| `config/models.yaml` | modified | on for gemma4:12b and qwen3.5:9b |
| `app/generation/prompts.py` | modified | `abstention_check_messages()`: the question and the reply, without the passages |
| `app/generation/question_answering.py` | modified | `check_abstention()`, called by `QuestionAnsweringService.stream()` before the `Answer` |
| `app/evaluation/benchmark.py` | modified | the same check in `_run_generation()` |
| `tests/unit/test_question_answering.py` | added tests | 15 |
| `tests/unit/test_benchmark.py` | added test | the benchmark recognizes what the application does |
| `tests/unit/test_config.py` | added tests | a boolean, off unless a profile asks |
| `tests/integration/test_generation.py` | added test | the proof: each model reads its own known replies |
| `tests/integration/abstention_cases.yaml` | added | 51 real replies, labeled by reading them |
| `README.md` | modified | how an abstention is recognized, and the setting |
| `docs/decisions.md` | modified | "Some models read their replies again for an abstention" |
| `docs/benchmark-results.md` | modified | "The abstention check": its measurements |
| `assessment-1.md`, `fix-1.md` | renamed | the first attempt's records, kept beside this one |

## Diff Highlights

The check's question, after one revision (see Deviations):

```text
Does the reply give the reader any of the information the question asks for?
- YES if it gives what was asked, or some of it, even when it also says that something else is missing. An answer can be a negation, such as "No, he rejects it".
- NO if it only says that the passages don't contain what was asked, perhaps with what they say around it. A vague stand-in, such as "someone" for who, gives nothing.

Reply with one word: YES or NO.
```

`check_abstention()` runs only for a reply without the marker, and only when the model's profile
asks. It uses the reply's token limit at temperature 0, and it returns the reply unchanged when:
- the check wouldn't fit the context (constitution V);
- the call fails;
- the verdict's first word is neither YES nor NO.

Each of those is logged as `abstention check skipped`, with its reason and never any text.

## Tests Added or Updated

- **`tests/unit/test_question_answering.py`**:
  - **When the check runs**: an unmarked reply that the check calls an abstention is shown as
    one, with its text and citations kept. A YES leaves the reply an answer.
  - **What it sends**: the check reads the question and the reply, without the passages, at
    temperature 0 and with the reply's token limit.
  - **How the verdict is read**: it is the first word (`**No**`, `no.` with an explanation,
    `"NO"`). An unreadable verdict ("Maybe.", "The answer is no.", "Nope", or nothing) leaves the
    answer.
  - **When it doesn't change anything**:
    - a failed check, or one too long for the context, leaves the answer;
    - there is no check without the profile setting, or on a marked reply.
  - **What is logged**: a skipped check is logged, without the question, reply or verdict.
- **`tests/unit/test_benchmark.py`**,
  `test_an_abstention_without_the_marker_is_recognized_as_the_application_does`: the generation
  benchmark applies the same check.
- **`tests/unit/test_config.py`**: the setting takes only a boolean, and is off unless a profile
  asks.
- **`tests/integration/test_generation.py::test_the_check_reads_known_replies_as_they_were_labeled`**:
  the proof.
  - **What it runs**: each model whose profile sets `check_abstentions` reads its own known
    replies in `abstention_cases.yaml`, and each must come out as labeled.
  - **The cases**: 23 for gemma4 (13 abstentions, 10 answers), and 20 for qwen3.5 (9 and 11).
  - **One expected failure**: gemma4's partial answer to `think_python_multi_section_05` is marked
    as a known misread, a non-strict `xfail` (see Local Verification).
  - **Where it lives**: in the file the assessment named. As a file of its own, it sorted before
    `test_docling.py`. It then left gemma4 and qwen3.5 loaded in Ollama, and Docling ran out of
    GPU memory.

## Local Verification

- **`make lint`** is clean. **`make test`**: 856 passed.
- **The known cases**, `tests/integration/abstention_cases.yaml`: 51 real replies, each read and
  labeled.
  - **23 abstentions without the marker**:
    - the 8 of the probe `default_llm_probe_20261109T062308173324Z`;
    - 3 of the first rewording's probe;
    - `quincas_borba_unanswerable_01` by gpt-oss, gemma4 and qwen3.5, and qwen3.5's `_05`;
    - two answerable questions whose evidence retrieval missed;
    - qwen3.5's replies to "who presented the denunciation?" on chapter XXV alone, asked in six
      languages at seed 7.
  - **25 answers that look like abstentions**:
    - 11 replies to "what happened to it, and who presented it?" on the same passage. There were
      12, but gemma4's English and French ones were identical.
    - 5 partial answers, mostly to multi-section questions;
    - 4 answers that are negations;
    - 2 wrong answers, one from general knowledge and one invented, which are still answers;
    - 3 plain answers.
  - **3 ambiguous replies**, recorded and not scored.
- **The proof**, `uv run pytest -m integration tests/integration/test_generation.py -k known_replies`:
  - **The first wording**, ANSWER or ABSTENTION, with each model reading all 48 scored cases:
    - qwen3.5 took 10 answers for abstentions;
    - gemma4 took 2 answers for abstentions, and missed 1 abstention.
  - **The revised wording, all 48 cases**:
    - **gemma4** took 4 of qwen3.5's partial answers for abstentions. Each reads "a denúncia foi
      apresentada por 'alguem'… foi destruída".
    - **qwen3.5** missed gpt-oss's "foi apresentada por **alguém** (o nome não é especificado no
      texto)".
    - **On their own replies, every case came out as labeled in this run.** One of gemma4's didn't
      in later runs: see below.
  - **The bar, by the owner's decision**: each model reads its own replies, as it does in use
    (see Deviations).
  - **gemma4's verdict on one of its own answers depends on how the model was loaded.** Its
    partial answer to `think_python_multi_section_05` reads "The book states… While the text does
    not provide a direct step-by-step parallel, it describes…".
    - **Across loads**: in ten runs of the whole proof, it came out an answer six times and an
      abstention four times, the last four in a row.
    - **Within a load**: the verdict didn't vary. Under the last load, 18 checks in a row read it
      as an abstention, whether each followed another check or an answering call. The prompt
      cache isn't the cause.
    - **The owner kept the check on for gemma4** after hearing this, so the case is marked as a
      known misread.
- **The check over the benchmark's replies**, as a new run would get them. The answering prompt
  is unchanged and the seed is fixed, so these are the same replies. Read under the load where
  gemma4 calls `think_python_multi_section_05` an answer:

  | Run, variant | Unmarked replies read | Unanswerable recognized | Answerable taken for abstentions | Median time per check |
  | --- | --- | --- | --- | --- |
  | `default_llm_generation_20261109T041359173775Z`, gemma4 | 76 | 15 of 15 (14 before) | `on_liberty_multi_section_01`, evidence 0.2 | 0.26 s |
  | `generation_20261108T175100527075Z`, gemma4 | 77 | 15 of 15 (13 before) | `on_liberty_multi_section_01`, evidence 0.2 | 0.26 s |
  | `generation_20261108T175100527075Z`, qwen3.5 | 77 | 15 of 15 (13 before) | `quincas_borba_conceptual_05`, evidence 0.0; `quincas_borba_factual_09`, evidence 1.0 (ambiguous) | 0.18 s |

  - **gemma4's 13 before in the 2026-11-08 run includes `_04`**, written `[NO-EVIDÊNCIA]`, which
    the marker parser has recognized since.
  - **Under the other load**, gemma4 also took its `think_python_multi_section_05` answer for an
    abstention, in both runs: 1 of 75 answers.
  - **Abstention quality is unchanged**: gemma4 stays at 0.989, or 0.978 under the other load,
    and qwen3.5 stays at 0.978. The unanswerable questions it gains are offset by abstentions
    where retrieval missed, which the metric counts as wrong.
- **The probe**: `default_llm_probe_20261109T161109798344Z`, through the application's services,
  against `default_llm_probe_20261109T062308173324Z`.
  - **gemma4's abstentions shown as answers**: 0 of 60, down from 8. By language, Spanish, French,
    German and Italian: 0, 0, 0, 0, down from 2, 2, 4, 0.
  - **gpt-oss** runs no check, and stayed at 0 of 60.
  - **The whole-library question with an answer** was answered in all 3 runs by both models, and
    the trap was refused in all 3.
  - **The wait for the first visible word didn't change**: gemma4's median on the unanswerable
    questions was 1.12 s, against 1.14 s.
- **`make test-integration`**: 66 passed, 1 xfailed.
- **The app image was rebuilt** with the check. The container reads it on for gemma4:12b and
  qwen3.5:9b, and off for gpt-oss:20b and qwen3:14b.

## Deviations from Assessment

- **The check's wording was revised once.** The first, a choice between ANSWER and ABSTENTION,
  failed the proof both ways. The models took partial answers that say what is missing for
  abstentions. The revision asks whether the reply gives any of the information asked for, and
  says that "someone" for who gives nothing. It was the only revision: more tuning on the same
  cases would have fitted them. The benchmark's replies and the probe served as held-out checks.
- **The proof's bar was scoped to each model's own replies.** The assessment asked, for each
  checked model, that every known abstention be caught and no answer turned into an abstention,
  without saying whose replies. With the revised wording, neither model met that bar on all of
  the others' replies (see Local Verification). The owner chose to count each model's own
  replies, since the check only ever reads those, and to record the rest here.
- **gemma4 doesn't fully meet that bar either, and its check stays on.** Under some loads, it takes
  one of its own partial answers for an abstention: 1 of 75 answers per benchmark run. The owner
  kept the check on, since it ends gemma4's unmarked abstentions, 8 of 60 in the probe. The
  reader still sees the answer, under the note that the model found none.
- **The proof and the integration test are one test.** The assessment listed a proof and "a few
  known cases" as an integration test. One test, with every known case, is re-runnable, as
  constitution VI asks of a judge after a change to its prompt or model.
- **The 11 two-part replies and qwen3.5's 6 one-question replies are new.** They were generated
  for the proof on `main`'s prompt, on one passage at seed 7, since the replies on disk had no
  partial answers outside Portuguese and English.

## Follow-ups

- **Abstention quality counts an abstention after a retrieval miss as wrong.** A variant of the
  metric that uses `evidence_in_context` would show what the check gained.
- **A row doesn't record whether the marker or the check made it an abstention.** That would help
  reading a run, and the check could log its verdict in the "question answered" event.
- **The check can misread a partial answer.** gemma4 does so with one of its own under some
  loads, and did with four of qwen3.5's terse ones. A misread found in use is a new case for
  `abstention_cases.yaml`. If they turn out common, gemma4's setting should be reconsidered.
- **Why gemma4's verdict changes between loads isn't known.** Ollama may place the model on the
  GPU differently, depending on what else is loaded. Reading it once per load would show whether
  that matters elsewhere.
- **gpt-oss left one abstention unmarked in 240 replies.** If that recurs, its check can be proved
  the same way, at the cost of a reasoning call per answer.
- **Replies in Portuguese when another language was asked**, in the generated cases, belong to
  `fix/answer-language-setting`.
- **An unjudged replay mode for the generation benchmark**, carried over from `fix-1.md`.
- **Condition (d) of `specs/002-gemma4-default-llm/verdict.md`** can now be reopened with the
  probe's numbers below, through a new spec.
