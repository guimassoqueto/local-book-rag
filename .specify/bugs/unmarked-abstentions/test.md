# Bug Verification: Abstentions without the no-evidence marker

- **Slug**: unmarked-abstentions
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Asked through the question service, gemma4:12b and qwen3.5:9b showed all 46 of their replies to
unanswerable questions as abstentions. The bug occurred in 9 of them, and the check caught every
one. Nothing else broke. The fix's one known limit showed up as recorded: gemma4 took one of its
own partial answers for an abstention, the case `fix.md` documents and the owner accepted.

## Checks Performed

| Check | Command / Action | Result | Notes |
| --- | --- | --- | --- |
| Reproduction (post-fix) | the assessment's question and the rest, through `container.questions.stream()` on the benchmark workspace, each model chosen in memory, with the result rendered by Gradio's `sources_markdown()` | pass | 46 of 46 unanswerable shown as abstentions; 9 of them by the check |
| Reproduction, end to end | the probe `default_llm_probe_20261109T161109798344Z`, run by `/speckit-bug-fix` | pass | gemma4's unshown abstentions 0 of 60, down from 8 |
| New / updated tests | `uv run pytest tests/unit/... -k "abstention or check or marker"` | pass | 23 passed |
| The proof | `uv run pytest -m integration tests/integration/test_generation.py -k known_replies` | pass | 42 passed; the known misread passed too |
| Regression suite, unit | `make test` | pass | 856 passed |
| Regression suite, real models | `make test-integration` | pass | 66 passed, 1 xfailed: the known misread |
| Lint | `make lint-check` | pass | clean, 140 files formatted |

**How the reproduction was run.**
- **What it covered:**
  - **The question service**, the same `QuestionAnsweringService.stream()` the Chat tab calls, in
    the rebuilt app container. It ran without a seed, as the application does, so every reply was
    a fresh sample.
  - **The books**: the benchmark workspace, which holds *Quincas Borba* and the dataset's other
    books.
  - **The questions**, for each model:
    - the 15 unanswerable questions, in their own language;
    - the four of *Quincas Borba* again, in Spanish and in German, which gemma4 had left unmarked;
    - the 15 multi-section questions, where an answer is likeliest to be misread.
  - **What it recorded**:
    - whether each reply was shown as an abstention, and the note Gradio's `sources_markdown()`
      would put under it;
    - whether the check, rather than the marker, made it one, through a wrapper that records each
      call.
- **What it left out:**
  - **Your configuration**: the assessment's step of setting `llm.model` in `config/models.yaml`
    and running `make up` wasn't followed. That would have switched your real library's model.
  - **Your library and the Gradio page**: the books were the benchmark workspace's, and the page
    wasn't opened. The note was rendered with Gradio's own function instead.

## Output Excerpts

```text
## gemma4:12b: 38 asks
- unanswerable shown as abstentions: 23 of 23; by the check: 6; notes: {'The model found no answer in the selected books.'}
- multi-section shown as abstentions: [('think_python_multi_section_05', 'check'), ('on_liberty_multi_section_01', 'check')]
## qwen3.5:9b: 38 asks
- unanswerable shown as abstentions: 23 of 23; by the check: 3; notes: {'The model found no answer in the selected books.'}
- multi-section shown as abstentions: []
```

**The 9 replies the check caught**, each read: all are abstentions in words that the application
would have shown as answers.
- **gemma4**:
  - `quincas_borba_unanswerable_01`, in Portuguese: "foi dada por 'alguém' [1]. O texto não
    identifica…";
  - `_01`, `_02`, `_03` and `_05` in German, and `_02` in Spanish: "Die Passagen enthalten keine
    Informationen darüber…".
- **qwen3.5**: `_05` in Portuguese, and `_01` and `_05` in German.

**The two multi-section replies the check turned into abstentions**, both gemma4's:
- `on_liberty_multi_section_01` is right. "The provided passages do not contain information
  regarding how Mill finally deals with the objection…": retrieval had missed the evidence (0.2).
- `think_python_multi_section_05` is the known misread. "The book states that class interfaces can
  be discovered by 'data encapsulation'… While the text does not provide a direct step-by-step
  parallel, it describes the components of each…" is a partial answer.

```text
make test           ===================== 856 passed, 67 deselected in 17.84s ======================
make test-integration ==== 66 passed, 856 deselected, 1 xfailed, 2 warnings in 108.79s (0:01:48) =====
proof, alone        42 passed, 2 deselected, 1 xpassed in 22.97s
```

## Residual Risks

- **gemma4 can mislabel a partial answer, depending on how the model was loaded.**
  - Here, it did so on 1 of 15 multi-section answers. In the full integration run its verdict on
    the known case was an abstention, and in the proof run alone an answer.
  - The reader then sees the whole answer, under "The model found no answer in the selected
    books."
  - The owner accepted this during the fix. A misread found in use is a new case for
    `tests/integration/abstention_cases.yaml`.
- **The Gradio page and your library weren't exercised**: the service and Gradio's formatter were
  (see above). The page only shows what `sources_markdown()` returns.
- **qwen3.5 has no probe**, since the probe compares only gpt-oss and gemma4. Its end-to-end
  evidence is this reproduction's 38 asks, with the proof and the check over the run of
  2026-11-08.
- **The benchmark's abstention quality doesn't show the gain.** It counts an abstention after a
  retrieval miss as wrong, so a future run's figure stays about where it was (`fix.md`,
  Follow-ups).
- **gpt-oss:20b, the default, has no check.** It left one abstention unmarked in 240 replies, and
  none in this session's two probes.

## Recommendation

Close the bug. Both models' abstentions without the marker are now shown as abstentions: 9 of 9
in this reproduction, and gemma4's 8 of 60 in the probe. Nothing else broke, and the answering
prompt and the default model are untouched. Keep watching for the one known side effect, gemma4
mislabeling a partial answer under some loads. If it turns up in use more often than the 1 in
15 to 75 measured here, reconsider gemma4's `check_abstentions`.
