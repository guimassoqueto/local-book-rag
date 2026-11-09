# Bug Assessment: abstentions written as partial answers, without the no-evidence marker

- **Slug**: unmarked-abstentions
- **Created**: 2026-11-09
- **Source**: pasted text, the first follow-up in `specs/002-gemma4-default-llm/verdict.md`
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> gemma4:12b abstains without the no-evidence marker when it explains what the passages do say, so
> the application shows the abstention as an answer (constitution VII: an abstention must be shown
> as one). In the probe `default_llm_probe_20261109T062308173324Z`, 8 of gemma4's 60 marker replies
> (Spanish 2, French 2, German 4, Italian 0) abstain in substance without the marker, against 0 of
> gpt-oss:20b's 60; `reading.yaml` labels each `probe_reply` entry `abstains`. In the generation run
> `default_llm_generation_20261109T041359173775Z`, gemma4 did the same on
> `quincas_borba_unanswerable_01` (Portuguese) and `on_liberty_multi_section_01` (English), both
> recorded `abstained: false`. Expected: such a reply is shown as an abstention. The fix is either
> a prompt that keeps the marker in that form of reply, or a parser that recognizes it, checked on
> the real models in every interface language; the generation benchmark's abstention quality would
> show it. It is what reopens condition (d) of that verdict.

## Symptom

A model whose passages don't hold what was asked sometimes replies with what they do hold, cites
it, and says the rest is missing, without opening with `[NO-EVIDENCE]`. The application then shows
the reply as an answer with sources, instead of "The model found no answer in the selected books."
The benchmark records it as `abstained: false`, which scores abstention quality 0 on an
unanswerable question.

Expected: a reply that says the passages don't hold the answer is shown, and scored, as an
abstention.

## Reproduction

The recorded runs reproduce it. All ten cases are on the benchmark workspace `71026d902d`:

| Item | Language asked | Model | Reply opens with |
| --- | --- | --- | --- |
| `quincas_borba_unanswerable_01` | French | gemma4:12b | A denúncia … foi feita por "alguém" [1]. O texto não identifica… |
| `quincas_borba_unanswerable_01` | German | gemma4:12b | Die Passagen enthalten keine Informationen darüber, wer… |
| `quincas_borba_unanswerable_02` | Spanish | gemma4:12b | As passagens fornecidas não mencionam o nome da mãe de Rubião… |
| `quincas_borba_unanswerable_02` | French | gemma4:12b | Os passagens fornecidas não mencionam o nome… |
| `quincas_borba_unanswerable_02` | German | gemma4:12b | Die Passagen enthalten keine Informationen darüber, wie die Mutter… |
| `quincas_borba_unanswerable_03` | Spanish | gemma4:12b | As passagens fornecidas não mencionam o nome da cidade… |
| `quincas_borba_unanswerable_03` | German | gemma4:12b | Die Texte enthalten keine Informationen darüber, in welcher… |
| `quincas_borba_unanswerable_05` | German | gemma4:12b | Die Passagen enthalten keine Informationen darüber, mit welchem… |
| `quincas_borba_unanswerable_01` | the question's (pt) | gemma4:12b | A denúncia … foi dada por "alguém" [1]. O texto não identifica… |
| `on_liberty_multi_section_01` | the question's (en) | gemma4:12b | The provided passages do not contain information regarding how Mill finally deals… |

The first eight are from the probe, the last two from the generation run. To see it live:

1. Set `llm.model: gemma4:12b`, or run `dl probe --workspace 71026d902d` (`devtools/default_llm.py`),
   which picks the model in memory.
2. Ask "Como se chamava a mãe de Rubião?" (`quincas_borba_unanswerable_02`) of *Quincas Borba*,
   with the answer language set to German.
3. The reply says the passages don't name her, cites [1], and `Answer.insufficient_evidence` is
   false. The Ask tab lists [1] as a source, with no abstention note.

The temperature is 0.2, so a single run can differ from the recorded one.

**It isn't gemma4's alone.** In the earlier full run, `generation_20261108T175100527075Z`:
- gpt-oss:20b, the default, answered `quincas_borba_unanswerable_01` the same way: "foi
  apresentada por **alguém** (o nome não é especificado no texto)";
- qwen3.5:9b did on `_01` and `_05`;
- qwen3:14b answered `_05` outright from a passage about a different journey.

The confirmation's gpt-oss replies were all marked, so the default shows it rarely, not never.

## Suspected Code Paths

- `app/generation/prompts.py:18-19`: the two rules a model must choose between.
  - "If the passages answer only part of the question, answer that part and say what is missing."
  - "If the passages don't answer the question at all, begin your reply with [NO-EVIDENCE]…"

  When the passages hold a related fact but not the one asked ("someone" made the denunciation,
  but who?), the reply fits the first rule's shape. Every one of the ten replies has that shape: a
  related fact, cited, then what's missing.
- `app/generation/question_answering.py:31-35` (`_MARKER`) and `:288-300` (`_read_marker`,
  `_marker_length`): the marker is recognized only where it opens the reply, in any dash, or
  translated as `[NO-EVID…]`. None of the ten replies carries any bracketed marker, translated or
  not, anywhere in its text. The parser is working as designed: there is nothing for it to find.
- `app/generation/question_answering.py:228-248` (`_MarkerFilter`): it holds a streamed reply's
  first characters back until they can't be the marker. That is why the marker has to come first:
  a later one would arrive after the text was already shown as an answer.
- `app/interface/formatting.py:92` and `app/main.py:219`: Gradio and the command show the
  abstention note only when `insufficient_evidence` is true.
- `app/evaluation/benchmark.py:412-413`: the benchmark's `abstained` and `abstention_quality` come
  from the same flag.

## Root Cause Hypothesis

The prompt draws the line between "answers part of the question" and "doesn't answer it at all" by
the answer, not by what was asked. A question with a single ask, whose passages hold only facts
around it, reads as partially answered. So the model follows the partial-answer rule, which asks
for no marker, and writes an abstention in substance that the application can't recognize. gemma4
does it most, and most in languages other than the question's, but gpt-oss and the qwen models do
it too. Confidence: **high** for the mechanism, since all ten replies have the partial-answer
shape and none has a marker. It is **medium** for why the answer language makes it more frequent:
4 of the 8 probe cases were also written in Portuguese instead of the language asked for, which is
the separate `fix/answer-language-setting`.

## Proposed Remediation

**Preferred: draw the line in the prompt by what was asked.** Rewrite the two rules in
`_QUESTION_ANSWERING_SYSTEM`:
- The marker covers any reply where the passages don't hold the specific thing asked for, even
  when they mention related facts. It still opens the reply, and the model may then say what the
  passages do contain.
- The partial-answer rule is kept for questions with several parts, where the passages answer some
  of them.

Keep the marker's text, `[NO-EVIDENCE]`, and its place at the start. The parser and the
streaming filter then need no change.

**Alternatives**:
- **A parser that recognizes abstention phrasing** ("the passages don't contain…", "As passagens
  não mencionam…", "Die Passagen enthalten keine…"), in the six interface languages.
  - It needs no prompt change, so the benchmark's earlier runs stay comparable.
  - But it can't tell an abstention from a legitimate partial answer, which says the same about
    the part that's missing. Matching it would turn partial answers into abstentions.
  - It would also have to read the whole reply, while streaming decides on its first characters.
  - Not recommended.
- **A second, short model call that classifies the finished reply** as answer or abstention.
  - It is robust to phrasing and language.
  - It adds a model call, and its latency, to every question, and its streaming display would be
    corrected after the fact.
  - It is a new judge-like component, which constitution VI would require to prove itself on
    known cases first.
  - Too heavy for this bug.

**Files likely to change**:
- `app/generation/prompts.py`
- `tests/unit/test_prompts.py`, or wherever the prompt's rules are asserted
- `tests/integration/test_generation.py`
- `docs/decisions.md`, `docs/benchmark-results.md`

**Tests to add or update**:
- **Integration (real models, constitution V)**: for each pulled LLM profile, passages that mention
  a related fact but not the one asked (built like `quincas_borba_unanswerable_02`'s, or taken from
  the workspace). The reply must have `insufficient_evidence` true, with the question's language
  and with each of the six answer languages.
- **Integration, the other side**: a two-part question whose passages answer only one part must
  not abstain, so the fix can't trade unmarked abstentions for wrong ones.
- **Unit**: the system prompt states the marker rule for "related but not what was asked", and
  keeps the marker at the start, so `_MarkerFilter` stays correct.
- **Measurement**:
  - A generation benchmark run of `default_llm_generation` after the fix, against the
    confirmation run as its before. Abstention quality and wrong abstentions are computed, not
    judged, so they compare cleanly across runs.
  - The probe's marker test (`dl probe`), whose unrecognized abstentions should be 0 for both
    models.

## Risks & Considerations

- **The generation benchmark measures something else after a prompt change.**
  - `docs/decisions.md` records that the dash fix deliberately left the prompt alone for that
    reason ("changing the prompt would have changed what the generation benchmark measured").
  - The earlier generation runs stop being a like-for-like baseline. The before-and-after
    comparison has to be read as such, and `docs/benchmark-results.md` has to say which prompt
    each run used.
- **Over-abstaining.**
  - A stronger marker rule can make models abstain where they should answer part of a question.
  - gpt-oss already abstains wrongly at times: 1 to 3 of 75 per run, mostly on *Quincas Borba*.
  - Wrong abstentions and multi-section correctness must not get worse, for the default above all.
- **Wrong abstentions after a retrieval miss.**
  - On `on_liberty_multi_section_01`, the question is answerable but retrieval missed the
    evidence, so marking the reply is right.
  - The benchmark still scores it as a wrong abstention. `evidence_in_context` tells the two cases
    apart, and the measurement should report it.
- **The prompt is shared by every model.** The default, gpt-oss:20b, has to be checked as much as
  gemma4. Constitution V asks for the real models, in every interface language.
- **The marker stays first.** A fix that let the marker come later, after an explanation, would
  break streaming: `_MarkerFilter` decides on the reply's first characters, and the reader would
  already have seen an "answer".
- **Out of scope**, each its own follow-up from the same verdict:
  - replies in the wrong language (`fix/answer-language-setting`);
  - qwen3:14b's outright invented answer to `_05`;
  - choosing the default LLM again, which needs a new spec. This fix only makes condition (d)
    worth reopening.

## Open Questions

Both resolved by the owner, 2026-11-09:

- **Is a prompt change acceptable?** Yes. The preferred fix goes ahead, and the records say which
  prompt each generation run used.
- **Which measurement closes the bug?** All three:
  - the real-model integration tests;
  - a full `default_llm_generation` run, compared with the confirmation run
    `default_llm_generation_20261109T041359173775Z`;
  - the probe, compared with `default_llm_probe_20261109T062308173324Z`.
