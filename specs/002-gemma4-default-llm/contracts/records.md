# Contract: the confirmation's records

The files the confirmation writes and reads. Result directories stay out of the repository, like
every run's. `reading.yaml` and `verdict.md` are committed in this feature's directory.

## `prompts.jsonl`

One JSON object per line, one line per inference of a summarized chapter. The judge's inferences
aren't recorded.

```json
{"variant": "gemma4_12b", "chapter": "Inheritance", "model": "gemma4:12b",
 "estimate_tokens": 4310, "prompt_tokens": 4402, "window": 8192, "max_tokens": 3000,
 "finish_reason": "stop"}
```

- `variant` and `chapter` come from the runner's last "summarizing" message. In the probe,
  `variant` is null.
- `estimate_tokens`: the sum of `count_tokens(message.content)` over the prompt.
- `prompt_tokens`: Ollama's `prompt_eval_count`.

## `probe.jsonl`

One JSON object per line.

```json
{"kind": "marker", "model": "gemma4:12b", "item": "on_liberty_unanswerable_02",
 "language": "French", "run": null, "insufficient_evidence": false,
 "text": "...", "citations": [], "invented_citations": [], "wait_seconds": 0.91}
{"kind": "analytical", "model": "gemma4:12b", "item": "Inheritance", "text": "...",
 "steps": 4, "incomplete_steps": 0, "detected_language": "en", "book_language": "en",
 "error": null}
```

- `kind` is one of `warmup`, `whole_library`, `marker` or `analytical`.
- `wait_seconds` is null for the warm-up, which isn't timed.
- `citations` lists the cited passages' numbers.

## `reading.yaml`

Written by hand during the reading: one entry per item and model.

```yaml
- item: on_liberty_multi_section_01
  kind: answer
  model: gemma4:12b
  errors: [unanswered_part]
  note: >-
    Says the passages don't cover the second part, though passage 3 states it.
- item: Inheritance@summarization_20261108T213459590645Z
  kind: summary
  model: gpt-oss:20b
  errors: []
  note: Every claim is in the chapter's chunks.
- item: think_python_unanswerable_03@French
  kind: probe_reply
  model: gemma4:12b
  label: abstains
  errors: []
  note: >-
    "[AUCUNE-PREUVE] Les passages ne contiennent pas..." shown as an answer.
```

**Fields**:
- **item**:
  - a question id, for an `answer`;
  - `chapter@run`, for a `summary`. The run is a results directory's name, or `probe`;
  - `question@language`, for a `probe_reply`.
- **kind**: `answer`, `summary`, `probe_reply` or `probe_summary`.
- **model**: gpt-oss:20b or gemma4:12b.
- **errors**: a subset of `unsupported_claim`, `misattribution`, `unanswered_part`,
  `abstention_with_evidence` and `false_citation`.
- **label**: `abstains` or `answers`. It is required for a `probe_reply`, and absent otherwise.
- **note**: required when `errors` isn't empty.

**Complete** means it has both models' entries for:
- all 15 multi-section questions;
- every gemma4 summary the confirmation scores 0.5 or lower on factual consistency, with gpt-oss's
  summary of the same chapter;
- "Inheritance" and "Fruitful functions" from each earlier summarization run where gemma4 scored
  0.5;
- both `analytical` summaries;
- every marker reply not shown as an abstention.

## `verdict.md`

Written by the `verdict` subcommand, in this order:

1. **Inputs**:
   - the commit;
   - the two results directories, with their dates and `complete`;
   - the probe directory;
   - the SHA-256 of `reading.yaml`.
2. **(a) Nothing gated is worse**: a table of the 13 gated metrics. Each row has gpt-oss's mean,
   gemma4's mean, the difference with its 95% interval, the pairs, and `worse` or `—`.
3. **(b) The wins repeat**:
   - wrong abstentions, as two counts;
   - seconds and steps, as differences with their intervals;
   - the novel's coverage, as two means.

   Each has pass or fail.
4. **(c) The reading**: per error kind, how many multi-section items and summaries have it for
   gemma4 and not for gpt-oss, against the thresholds 3 and 2.
5. **(d) The probe**: the five blocking findings, each with its numbers and pass or fail:
   - trap answers per model;
   - unrecognized abstentions per model;
   - the `analytical` summaries' outcome;
   - gemma4's largest undercount, against `safety_margin × window`;
   - the median waits.
6. **(e) The real-model checks**: `passed`, `failed` or `pending`.
7. **Verdict**: `switch to gemma4:12b`, `keep gpt-oss:20b`, with the conditions that failed, or
   `pending`.
8. **Follow-ups**: added by hand after the subcommand writes the rest.
