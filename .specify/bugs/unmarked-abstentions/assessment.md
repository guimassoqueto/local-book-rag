# Bug Assessment: Abstentions without the no-evidence marker

- **Slug**: unmarked-abstentions
- **Created**: 2026-11-09
- **Source**: this directory's first assessment and fix report, `assessment-1.md` and `fix-1.md`.
  There is no new report: this assessment follows the failed fix.
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

The bug, as `assessment-1.md` recorded it from `specs/002-gemma4-default-llm/verdict.md`:
- **The symptom**: gemma4:12b abstains without the no-evidence marker when it explains what the
  passages do say, so the application shows the abstention as an answer. Constitution VII requires
  an abstention to be shown as one.
- **The probe `default_llm_probe_20261109T062308173324Z`**: 8 of gemma4's 60 abstentions were
  unmarked, against none of gpt-oss:20b's.
- **The generation run `default_llm_generation_20261109T041359173775Z`**: gemma4 did the same on
  two questions.

That assessment chose a rewording of the answering prompt. `fix-1.md` measured two rewordings, and
both made gpt-oss, the default, abstain on questions its passages answer: 22 wrong abstentions of
75 instead of 1, in a full generation run. The prompt stayed as on `main`, and this assessment
chooses again, with the evidence those runs gave.

## Symptom

- **What happens**: a model sometimes abstains in words, without writing the marker. For example:
  "the text says only that 'someone' made the denunciation, and doesn't name them". The
  application then shows the reply as an answer: its sources and a cited passage, or a warning
  that it cites none.
- **What is expected**: the note "The model found no answer in the selected books", as for a
  marked abstention. The generation benchmark should also count it as an abstention.

## Reproduction

1. Set `llm.model` to `gemma4:12b` or `qwen3.5:9b` in `config/models.yaml`, and run `make up`.
2. In the Chat tab, ask *Quincas Borba* the dataset's `quincas_borba_unanswerable_01`: "Quem
   apresentou a denúncia contra o testamento de Quincas Borba, alegando que ele não podia
   testar?"
3. The reply says that the text names only "alguém". Below it, the sources list `[1]`, instead
   of the note that the model found no answer.

The application answers without a fixed seed, so a single question may not reproduce it. How often
it happened, on `main`'s prompt:

| Where | gpt-oss:20b | gemma4:12b | qwen3.5:9b |
| --- | --- | --- | --- |
| Unanswerable questions, run of 2026-11-08 | 1 of 15 | 1 of 15 | 2 of 15 |
| Unanswerable questions, confirmation run | 0 of 15 | 1 of 15 | not run |
| The same questions, replayed unjudged (`fix-1.md`) | 0 of 15 | 1 of 15 | 2 of 15 |
| The probe, unanswerable questions in 4 other languages | 0 of 60 | 8 of 60 | not run |

- **The run of 2026-11-08**: `generation_20261108T175100527075Z`.
- **gemma4 also did it on an answerable question** whose evidence retrieval missed:
  `on_liberty_multi_section_01`, with evidence 0.2. Abstaining was right there, but unmarked.
- **gemma4's unmarked `quincas_borba_unanswerable_04` in that run doesn't count.** It translated
  the marker as `[NO-EVIDÊNCIA]`, which the application has recognized since.
- **qwen3:14b's unmarked `quincas_borba_unanswerable_05`** is an invented answer, not an
  abstention: it is out of scope, as before.

## Suspected Code Paths

- `app/generation/question_answering.py:288` `_read_marker()`, called by `read_reply()`
  (line 83): the marker alone sets `insufficient_evidence`. Nothing else in a reply can make it an
  abstention.
- `app/generation/question_answering.py:113` `QuestionAnsweringService.stream()`: streams the text
  through `_MarkerFilter`, then reads the finished reply (line 168) and yields the `Answer`. A check
  of the finished reply would go between the two.
- `app/interface/formatting.py:92` and `app/main.py:219`: Gradio and the command line show the
  abstention only after the reply has finished, under its sources. During streaming, the marker is
  only removed, so nothing streamed marks a reply as answer or abstention. A decision made on the
  finished reply is displayed exactly as one made on its first characters.
- `app/evaluation/benchmark.py:377` `_run_generation()`: calls `read_reply()` directly, not the
  service. A check placed only in the service wouldn't reach the generation benchmark. The probe
  asks through the service (`devtools/default_llm.py` `_ask()`).
- `app/config/settings.py:52` `LLMProfile`, and `config/models.yaml:43` `llm_profiles`: where
  what differs between models lives (constitution I).
- `app/generation/prompts.py:18-19`: the two rules. `fix-1.md` shows why they stay as they are.

## Root Cause Hypothesis

The marker is a choice the model must make before it writes anything. Some replies begin by saying
what the passages do contain ("the denunciation was made by 'someone'"). By then the reply has
already started without the marker, and what follows reads as the partial answer the other rule
asks for.

Rewording the prompt moves every model's line between answering and abstaining at once, and the
default's line moved first. gpt-oss made 22 wrong abstentions with one wording and 9 with the
other, while gemma4 still left some of its abstentions unmarked. Whether a reply abstains can only
be read reliably from the finished reply.

Confidence: high for the mechanism, measured on two wordings and five sets of integration tests.
Medium that a model can read that decision from the reply, which no one has measured yet.

## Proposed Remediation

**Preferred: check the finished reply, for the models whose profile asks for it.**
- **When it runs**: when a reply has no marker and the model's profile in `config/models.yaml`
  enables a new setting (e.g. `check_abstentions: true`).
- **What it does**: asks the same model one short question about its own reply. Does the reply
  give what the question asks for, even in part, or does it say that the passages don't contain
  it? The answer is read as `answer` or `abstention`. An abstention sets `insufficient_evidence`,
  and the application shows its note as for a marked one.
- **What it needs**: the question and the reply, without the passages. It reads what the reply
  says, not whether the passages support it, so it judges no evidence. Judging evidence was the
  line the rewordings moved.
- **Why it costs little**:
  - **The answering prompt doesn't change**, so every model answers as it does now.
  - **The default runs no check**: gpt-oss's profile leaves the setting off.
  - **No model is swapped in**: the model already loaded answers the check.
  - **The reader sees the same thing, a moment later**: the abstention was already shown only
    after the reply.
- **The same function serves the service and the generation benchmark**, so the benchmark
  measures what the application shows.

**Robustness** (constitution V):
- **The check's reply is parsed leniently**: case, punctuation and extra words are allowed around
  the verdict.
- **Anything unreadable leaves the reply as an answer and is logged**: an unrecognized verdict, or
  a failed or timed-out call. A failed check must never cost the user their answer.
- **It never runs when it can't apply**: on a marked reply, or when nothing was retrieved.

**Alternatives**:
- **A rewording of the answering prompt**: measured and rejected in `fix-1.md`.
- **A parser of abstention phrasing**: rejected again, now with data.
  - **Some answers are negations**: gemma4's "Mill does not state that he accepts…"
    (`on_liberty_multi_section_05`), and qwen3:14b's "functions that … don't return a value"
    (`think_python_factual_02`).
  - **Some partial answers open by saying something is missing**: qwen3.5's
    `think_python_multi_section_05`.
  - **The unmarked abstentions** come in five languages.
- **A rule only for the models that need it, in their profiles.** gemma4 with the first rewording
  went from 8 unmarked abstentions in the probe to 3, and made 2 wrong ones. It reduces the
  problem without ending it, and each model's wording would need its own measurement.
- **Recording it as a limitation of gemma4 and qwen3.5.** It costs nothing, and the default rarely
  shows it. But their abstentions stay unshown in the application, and the generation benchmark
  keeps counting them as answers, which skews any comparison with them. The probe found what
  decided condition (d) of the default-LLM verdict, by hand. This is the fallback if no model's
  check passes its proof.

**Files likely to change**:
- `app/generation/question_answering.py`: the check, and its call in `stream()`
- `app/generation/prompts.py`: the check's messages
- `app/config/settings.py`: the profile setting
- `config/models.yaml`: the setting, on for the models whose check passed its proof
- `app/evaluation/benchmark.py`: the same check in `_run_generation()`
- `tests/unit/test_question_answering.py`, `tests/unit/test_benchmark*.py`, the settings tests
- `tests/integration/test_generation.py`
- `README.md` (how an abstention is recognized), `docs/decisions.md`, `docs/benchmark-results.md`

**Tests to add or update**:
- **Unit, with fake models**:
  - With the setting on, an unmarked reply the check calls an abstention yields
    `insufficient_evidence`.
  - A reply the check calls an answer, and an unreadable verdict, stay answers.
  - A failed check call leaves the answer and logs it.
  - With the setting off, or on a marked reply, the check isn't called.
  - The benchmark's generation applies the same check.
  - An unknown value for the setting stops the configuration from loading.
- **The proof, first** (constitution VI: a judge-like component proves itself on known cases):
  - **Known cases**: the replies already on disk, labeled by reading them.
    - **Abstentions**: the 8 unmarked ones of the probe `default_llm_probe_20261109T062308173324Z`,
      all labeled already in `specs/002-gemma4-default-llm/reading.yaml`. Also, from the runs
      above: the unmarked `quincas_borba_unanswerable_01` replies of gpt-oss, gemma4 and qwen3.5,
      qwen3.5's `_05`, and gemma4's `on_liberty_multi_section_01`.
    - **Answers the check must leave alone**: the partial answers and negations above, and a sample
      of plain answers.
  - **The bar**: for each model whose setting would be on, every known abstention caught, and no
    answer turned into an abstention.
  - **Its cost**: the check's latency.
- **Integration (real models)**: for each profile with the setting on, a few known cases through
  `read_reply` and the check: an unmarked abstention and a partial answer, in two languages.
- **Measurement**:
  - **The effect on the benchmark, computed from existing replies.** The answering prompt doesn't
    change and the benchmark's seed is fixed, so the confirmation run's replies are the ones a new
    run would get. Running the check over them gives the new abstentions exactly.
  - **The probe** (`dl probe`), end to end through the service. gemma4's unshown abstentions should
    fall from 8 of 60 to none, with no answer shown as an abstention.

## Risks & Considerations

- **A check that misreads a reply hides a real answer.** That is the failure that sank the
  rewording, so the bar for the proof is no answer turned into an abstention. Only models that
  pass get the setting.
- **The model checks its own reply.** A model that wrote an unmarked abstention may also misread
  it. The proof shows whether it does, per model. Checking with a different model would mean
  loading a second one, often swapping the first out of memory, which costs far more.
- **Latency.** One short call per answered question, only for models with the setting on: likely
  under a second for gemma4 or qwen3.5, which don't reason. The proof measures it. gpt-oss would
  pay more, since it reasons whatever it is told, and its setting stays off unless the user
  decides otherwise.
- **The benchmark's abstention metric changes for those models**, and the judge then skips their
  newly recognized abstentions. `docs/benchmark-results.md` has to say which runs checked.
- **A new setting.** It is validated at startup like every other one (constitution I), and the
  README documents it.
- **This is larger than the first remediation**: a setting, a model call, a prompt and a proof.
  AGENTS.md sends a feature that touches prompts or a judge through `/speckit-clarify`,
  `/speckit-checklist` and `/speckit-analyze`. A bug fix has no such steps, so the proof above
  takes their place: the check ships only if it passes. See the open questions.
- **Out of scope**, as before:
  - the wrong answer language (`fix/answer-language-setting`);
  - qwen3:14b's invented answer;
  - choosing the default LLM again, which needs a new spec;
  - an unjudged replay mode for the generation benchmark (`fix-1.md`, Follow-ups).

## Open Questions

All three resolved by the owner, 2026-11-09:

- **Bug flow or feature flow?** The bug flow: it repairs existing behavior, and the proof takes the
  place of a feature's clarify, checklist and analyze steps.
- **Which models get the check?** gemma4:12b and qwen3.5:9b only, each if it passes the proof.
  gpt-oss:20b and qwen3:14b keep the setting off.
- **Which measurement closes it?**
  - the proof on known cases;
  - the integration tests;
  - the check over the confirmation run's replies,
    `default_llm_generation_20261109T041359173775Z`, for gemma4;
  - the probe, against `default_llm_probe_20261109T062308173324Z`.

  The confirmation run and the probe don't include qwen3.5, so the check runs over its replies in
  `generation_20261108T175100527075Z`. No full generation run.
