# Verdict: the default LLM

Written by `devtools/default_llm.py verdict`, applying the rule of
[spec.md](spec.md) FR-002. The baseline is first in every comparison, the candidate second.

## Inputs

- **Commit the runs started from**: `f6f53a8`
- **Generation run**: `default_llm_generation_20261109T041359173775Z`, 2026-11-09T04:13:59+00:00, Ollama 0.40.15, dataset `767e4cceb315`, gemma4:12b `6114515d63c1`, gpt-oss:20b `f38aa0c53da5`, qwen3-embedding:0.6b `ac6da0dfba84`
- **Summarization run**: `default_llm_summarization_20261109T060210125028Z`, 2026-11-09T06:02:10+00:00, Ollama 0.40.15, dataset `767e4cceb315`, gemma4:12b `6114515d63c1`, gpt-oss:20b `f38aa0c53da5`, qwen3-embedding:0.6b `ac6da0dfba84`
- **Probe**: `default_llm_probe_20261109T062308173324Z`, 2026-11-09T06:39:55+00:00
- **Earlier summarization runs**: `summarization_20261108T170744515174Z`, `summarization_20261108T213459590645Z`
- **Reading**: `specs/002-gemma4-default-llm/reading.yaml`, SHA-256 `f3a2c3a140cb54c763afe7f0175b6c8006513e7b2efa67be8bd0978b8624800b`

## (a) Nothing gated is worse

| Metric | gpt-oss:20b | gemma4:12b | Difference (95%) | Pairs | |
| --- | --- | --- | --- | --- | --- |
| faithfulness | 0.809 | 0.858 | +0.053 (-0.020 to +0.134) | 74 | — |
| answer_correctness | 0.677 | 0.699 | +0.022 (-0.020 to +0.063) | 73 | — |
| answer_relevance | 0.789 | 0.767 | -0.021 (-0.054 to +0.011) | 74 | — |
| citation_accuracy | 0.919 | 0.987 | +0.068 (+0.014 to +0.135) | 74 | — |
| language_consistency | 1.000 | 1.000 | +0.000 (+0.000 to +0.000) | 90 | — |
| abstention_quality | 0.989 | 0.989 | +0.000 (-0.033 to +0.033) | 90 | — |
| multi_section_answer_correctness | 0.549 | 0.496 | -0.058 (-0.155 to +0.047) | 13 | — |
| argument_coverage | 0.518 | 0.683 | +0.166 (-0.019 to +0.337) | 6 | — |
| concept_preservation | 0.917 | 0.875 | -0.042 (-0.208 to +0.208) | 6 | — |
| factual_consistency | 0.917 | 0.833 | -0.083 (-0.333 to +0.167) | 6 | — |
| coherence | 0.875 | 0.917 | +0.042 (+0.000 to +0.125) | 6 | — |
| completeness | 0.750 | 0.792 | +0.042 (+0.000 to +0.125) | 6 | — |
| citation_traceability | 0.899 | 0.971 | +0.072 (+0.015 to +0.134) | 6 | — |

**Passed**

## (b) The wins repeat

- **Wrong abstentions**: 1 for the baseline, 0 for the candidate
- **Seconds per summary**: 48.617 and 35.143, a difference of -13.474 (-33.392 to +2.108)
- **Steps per summary**: 4.833 and 3.500, a difference of -1.333 (-3.333 to +0.000)
- **The novel's coverage**, over 2 chapters, direction only: 0.261 and 0.633

**Failed: total_seconds, steps**

## (c) The reading finds no systematic weakness

| Error kind | Multi-section answers | Summaries |
| --- | --- | --- |
| abstention_with_evidence | 0 of 3 | 0 of 2 |
| false_citation | 0 of 3 | 0 of 2 |
| misattribution | 0 of 3 | 0 of 2 |
| unanswered_part | 1 of 3 | 0 of 2 |
| unsupported_claim | 0 of 3 | 0 of 2 |

Counted where the candidate's entry has the kind and the baseline's, for the same item, doesn't.

**Passed**

## (d) The probe finds nothing that blocks

- **The trap answered**: 0 of 3 and 0 of 3
- **Unrecognized abstentions**: 0 and 8 (Spanish 0 and 2; French 0 and 2; German 0 and 4; Italian 0 and 0)
- **The analytical summary, gpt-oss:20b**: error None, language en of en, 0 incomplete steps
- **The analytical summary, gemma4:12b**: error None, language en of en, 0 incomplete steps
- **The largest undercount**, of 24 prompts: 277 tokens, against 819 (0.1 of 8192); 0 over it
- **The median wait for the first visible word**: 0.64 s and 0.32 s, at most 1 s more

**Failed: unrecognized_abstentions**

## (e) The real-model checks pass

pending

**Pending: not run, since (a) to (d) didn't all pass**

## Verdict

**Keep gpt-oss:20b.** Failed: (b), (d).

## Follow-ups

_Added by hand after the verdict._
