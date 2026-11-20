# Contract: the configuration without the quiz

## `config/generation.yaml`

| Section | After |
| ------- | ----- |
| `question_answering` | unchanged |
| `summarization` | unchanged |
| `quiz` | removed, with its comments (FR-003) |
| `context` | unchanged |
| `response_languages` | unchanged, still offered by the Chat and Summarization tabs |

No other file in `config/` changes. `config/models.yaml` keeps every profile: no model had a
profile for the key check alone (spec, Edge Cases).

## A leftover `quiz` section

| Configuration | Outcome |
| ------------- | ------- |
| `generation.quiz`, with any content | every command, `serve` included, stops at startup: `error: Invalid configuration in <dir>: generation.quiz: Extra inputs are not permitted` |
| any other unknown key | the same, naming that key, as on `main` |

The wording after the key is Pydantic's. The unit test adds a section with a neutral name and
matches that key, so that no test names the quiz (R10). On the stack, `main`'s configuration is
refused, naming `generation.quiz` (quickstart § 6).

## Startup checks

`Settings` keeps its checks on the embedding and LLM profiles, the chunk overlap, the context's
size and the two remaining tasks' token limits. The check that `generation.quiz.check.model` has a
profile, and the one on the quiz's token limits, go with the section.

## The LLM provider

`create_llm_provider(settings, runtime)` builds one provider for `llm.model` with its profile
(R3). The application builds one, shared by questions and summaries. A benchmark variant or judge
on another model or reasoning level gets its own through `apply_overrides`, as on `main`.
