# Bug Fix: Abstentions without the no-evidence marker

- **Slug**: unmarked-abstentions
- **Fixed**: 2026-11-09 (attempted, not applied)
- **Assessment**: ./assessment.md
- **Status**: not-applied

## Summary

The preferred remediation, a rewording of the answering prompt's two rules, was tried in two
forms. Each was measured on the real models. Both made gpt-oss:20b, the default, abstain on
questions its passages answer, which the assessment's risks ruled out ("for the default above
all"). So the prompt is back to `main`'s, and the bug stays open. The attempt is kept in
`attempt-rev1.patch`, and the next step is a new assessment, with the evidence below.

## Changes

| File | Change | Notes |
| --- | --- | --- |
| `app/generation/prompts.py` | modified, then reverted | the first rewording; in `attempt-rev1.patch` |
| `tests/unit/test_question_answering.py` | modified, then reverted | a test of the rule's wording, and one made independent of the prompt's length |
| `tests/integration/test_generation.py` | modified, then reverted | 72 real-model cases; in `attempt-rev1.patch` |
| `.specify/bugs/unmarked-abstentions/attempt-rev1.patch` | added | the three files as tried: `git apply` it on `7b7e64c` |
| `docs/decisions.md` | modified | "The marker rule keeps its wording, for now", after the marker entry |
| `docs/benchmark-results.md` | modified | "The marker rule, reworded": the runs, the replays and their numbers |

## Diff Highlights

The original rules:

```text
- If the passages answer only part of the question, answer that part and say what is missing.
- If the passages don't answer the question at all, begin your reply with [NO-EVIDENCE], then say that the source doesn't contain enough information. Don't guess, and don't answer from general knowledge.
```

**The first rewording**, measured by a full run and the probe:

```text
- If the question asks for several things and the passages give only some of them, answer those and say which are missing.
- If the passages don't give what the question asks for, begin your reply with [NO-EVIDENCE], even when they mention the people, places or events it asks about. Write the marker exactly so, in any language. Then say that the source doesn't contain the answer; you may add what the passages do say. Don't guess, and don't answer from general knowledge.
```

**The second rewording** kept only the narrower first rule and "Write the marker exactly so, in any
language", with the original second rule. It was measured by a replay.

## Tests Added or Updated

None remain. Those written for the attempt are in `attempt-rev1.patch`:
- **`test_passages_that_only_mention_what_was_asked_about_draw_the_marker`**: two passages from
  *Quincas Borba*, verbatim from the workspace (chunks 0049 and 0216).
  - Each mentions what is asked about but not what is asked: who denounced the will, and which
    city had the epidemic.
  - Each case runs on every pulled LLM profile, in the six interface languages, at seed 7.
- **`test_a_question_answered_in_part_is_answered_not_abstained_from`**: a two-part question
  whose passage answers one part must not abstain.
- **Unit**: the system prompt keeps the marker at the start of the rule, for `_MarkerFilter`.
  `test_passages_that_dont_fit_are_left_out_rather_than_cut_by_ollama` checked its intent instead
  of an exact count, which depended on the prompt's length.

## Local Verification

- **The integration tests, while choosing the first rewording**: five wordings, 72 cases each,
  on gpt-oss:20b, gemma4:12b, qwen3.5:9b and qwen3:14b. Seed 7 means one sample per case.

  | Wording | Failures | Which |
  | --- | --- | --- |
  | original | 7 | qwen3.5 unmarked in 6 languages, gpt-oss abstaining wrongly in German |
  | first rewording | 2 | gpt-oss abstaining wrongly in French and German |
  | + "Don't use the marker below in that case" in the partial rule | 11 | fewer markers; gemma4 invented a name |
  | "give none of what" in the marker rule | 8 | all unmarked |
  | first rewording + a pointer back to the partial rule | 4 | gemma4 and qwen3.5 unmarked once each, gpt-oss abstaining wrongly in German and Italian |

  `make test-integration` with the first rewording: 94 passed, 2 xfailed. `make test`: 839
  passed.
- **The generation benchmark, first rewording**: `default_llm_generation_20261109T125707928285Z`,
  1 h 37 min. Preflight first matched the confirmation run: Ollama 0.40.15, the same digests,
  dataset `767e4cceb315`. Compared with `default_llm_generation_20261109T041359173775Z`:
  - **gpt-oss:20b**:
    - Wrong abstentions rose from 1 to 22 of 75, 14 of them with all their evidence retrieved.
    - Abstention quality fell by 0.233 (−0.322 to −0.144).
    - About half of these replies say "the source doesn't contain the answer; however…", then
      give it. Most of the rest deny an answer the passages hold.
  - **gemma4:12b**:
    - `quincas_borba_unanswerable_01` is now marked, so 15 of 15 unanswerable questions are.
    - It made two wrong abstentions. In `quincas_borba_conceptual_05`, retrieval missed the
      evidence (0.0). In `quincas_borba_factual_09`, it says the text lacks the value, then gives
      it.
    - `on_liberty_multi_section_01` is still unmarked.
  - **No other interval excludes zero**, except gpt-oss's multi-section correctness, +0.091. That
    counts only the 11 of 15 answers it still gave.
- **The probe, first rewording**: `default_llm_probe_20261109T143458804914Z`, against
  `default_llm_probe_20261109T062308173324Z`.
  - **gemma4's unmarked abstentions** fell from 8 of 60 to 3: Spanish 1, German 2. All three say
    what the passages mention: `quincas_borba_unanswerable_01` in both languages, and `_02` in
    German. The Spanish one came back in Portuguese.
  - **gpt-oss** marked 59 of 60. The other one, `think_python_unanswerable_04` in Spanish, wasn't
    an abstention: it answered from general knowledge (`super().__init__()`), which it hadn't
    done before.
- **Replays, without the judge**: the benchmark's 90 questions, on the confirmation run's
  retrieved contexts, with its seed 0 and the configured temperature 0.2.
  - **Whether a reply abstains needs no judge.** Answering takes about 4 minutes a model, while
    the judge takes the rest of the 2 hours.
  - **The original prompt, replayed**, matched the confirmation run on all 180 answers of both
    models. This replay also gave qwen3.5's baseline.
  - **The second rewording, replayed**:

    | Model | Wrong abstentions | Unanswerable abstained | Abstention quality |
    | --- | --- | --- | --- |
    | gpt-oss:20b | 9 (1 before) | 14 of 15 (15) | 0.889 (0.989) |
    | gemma4:12b | 2 (0) | 12 of 15 (14) | 0.944 (0.989) |
    | qwen3.5:9b | 2 (0) | 15 of 15 (13) | 0.978 (0.978) |

- **On the original prompt, the bug's size on the benchmark**:
  - gpt-oss: no unmarked abstentions.
  - gemma4: one, `quincas_borba_unanswerable_01`.
  - qwen3.5: two, `quincas_borba_unanswerable_01` and `_05`.

  Each says what the passages mention about the subject, as if that were part of an answer. The
  other replies that say "the passages don't contain…" are partial answers to multi-section
  questions, as the rule asks.
- **After reverting**: the app image was rebuilt with `main`'s prompt, and the container serves
  it. Ollama and ChromaDB weren't restarted.

## Deviations from Assessment

- **The preferred remediation doesn't work.** The assessment expected a rewording to mark these
  replies without making the default abstain more. Both wordings tried did make it abstain more,
  and the second didn't mark gemma4's replies either.
  - The models pull in opposite directions. gemma4 and qwen3.5 treat "the text only says someone"
    as part of an answer. Any wording that pushes them toward the marker pushes gpt-oss further,
    onto answers it does have.
  - Nothing more was changed, as `/speckit-bug-fix` requires: the prompt is `main`'s again, and a
    new assessment should choose the remediation.
- **The unit test of passages that don't fit was rewritten**, since the longer prompt changed its
  exact count. It went back with the rest.
- **These tests didn't predict the benchmark.** One passage and one seed favored the first
  rewording, while the benchmark's five passages and other seed rejected it. A wording is better
  measured by a replay of the benchmark's contexts, at more than one seed.

## Follow-ups

- **A new assessment** (`/speckit-bug-assess`), with this report as its evidence. The options left:
  - **A classifier of the finished reply.** The assessment found it too heavy, before any
    measurement. Constitution VI requires proving it on known cases first. The replays give 540
    real answers, and the two probes 240 replies in four more languages. Once labeled, they could
    serve as those cases. The first probe's 8 unmarked replies are labeled already, in the
    spec's `reading.yaml`.
  - **A rule only for the models that need it.** Per constitution I, what differs between models
    belongs in their profiles in `config/models.yaml`. That is a new setting, so a feature, not a
    bug fix.
  - **Recording it as a limitation of gemma4 and qwen3.5.** The default doesn't show it: none in
    the confirmation run, none in either probe.
- **Measure wordings at several seeds.** At temperature 0.2, each benchmark answer is one sample.
  The first rewording's 22 wrong abstentions are far beyond that noise; the second's 9 may not
  all be.
- **A replay mode for the generation benchmark.** It would answer without judging, to compare
  prompts in minutes. Here it was a script in the session's scratch directory, which isn't kept.
- **gemma4 answered a Spanish probe question in Portuguese.** That belongs to the answer-language
  follow-up already recorded (`fix/answer-language-setting`).
- **Condition (d) of `specs/002-gemma4-default-llm/verdict.md` stays failed.**
