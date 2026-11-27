# Bug Assessment: ragas sends usage analytics to a third party whenever the judge is built or embeds

- **Slug**: ragas-analytics
- **Created**: 2026-11-26
- **Source**: pasted text (bead iss-6fu, recorded in `.specify/assessments/ci-unit-tests/research.md`,
  Found Along the Way)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> ragas 0.4.4 posts usage events to https://t.explodinggradients.com unless RAGAS_DO_NOT_TRACK=true
> (.venv/lib/python3.13/site-packages/ragas/_analytics.py:37,41,223-233), and nothing in app/,
> tests/, the Dockerfile, docker-compose or the Makefile sets it. The RAGAS judge's
> embedding_factory('openai', model=...) (app/evaluation/generation_metrics.py:84-91) calls
> track(EmbeddingUsageEvent(provider='openai', model=<the judge's local embedding model>, ...))
> (ragas/embeddings/base.py:745), and ragas/llms/base.py tracks LLM use too; each event carries a
> persistent random user id kept in ~/.local/share/ragas/uuid.json and the ragas version. So each
> generation benchmark, and the unit test tests/unit/test_generation_metrics.py:90, contacts a third
> party nobody chose, against Principle I and README's 'the app contacts a provider at no other
> time'. No book text or key is in the payload. Seen 2026-11-26 while researching
> .specify/assessments/ci-unit-tests: a unit run with an empty HOME created
> .local/share/ragas/uuid.json.

Context: `.specify/assessments/ci-unit-tests/decision.md` (go) has this land before iss-az3, a
required CI check running `make test`, so that a CI run sends nothing to a third party and needs no
switch of its own. So the fix turns the analytics off wherever ragas is imported: the image, the
benchmarks and the unit tests.

**URL in the report**: `https://t.explodinggradients.com` (host: `t.explodinggradients.com`). Not
fetched (policy: unrecognized host, and not a description of the bug): it is the analytics
endpoint the report is about. Everything here comes from ragas's installed source and local runs.

## Symptom

Building the generation benchmark's RAGAS judge makes ragas send an HTTP POST to
`t.explodinggradients.com`, and so does each embedding request the judge makes while scoring. Each
carries a persistent random ID, the ragas version and the local judge's embedding model name. The
same happens in the unit test that builds the judge. Expected: nothing leaves the machine except to
the local models and to a cloud provider the user picked for the request (Principle I; `README.md:488`,
"the app contacts a provider at no other time, except when you ask for a check").

## Reproduction

Ran 2026-11-26 on `fix/ragas-analytics` (`a2d05ed`), with ragas's own debug switch,
`__RAGAS_DEBUG_TRACKING=true`, which logs each event's payload instead of posting it
(`ragas/_analytics.py:228-231`), so nothing was sent:

1. `HOME=<empty dir> __RAGAS_DEBUG_TRACKING=true uv run pytest "tests/unit/test_generation_metrics.py::test_the_judges_client_reaches_ollama_with_its_own_key_whatever_the_environment_says" -o log_cli=true --log-cli-level=INFO`
2. ragas logs the event it would have posted:

   ```text
   INFO ragas._analytics:_analytics.py:230 Tracking Payload: {'event_type': 'embedding_usage',
     'user_id': 'a-<32 hex>', 'ragas_version': '0.4.4', 'provider': 'openai', 'model': 'e',
     'embedding_type': 'factory_modern', 'num_requests': 1, 'is_async': False}
   ```

   (`'e'` is the test's fake embedding model name. A benchmark sends the judge's real one,
   `qwen3-embedding:0.6b` in `benchmarks/experiments/generation.yaml:8`.)
3. The same command with `RAGAS_DO_NOT_TRACK=true` added logs no payload, and the test passes.

Without the debug switch, step 1 posts the event. `track` is wrapped in `@silent`, which swallows
any error, so a run with or without network looks the same (`ragas/_analytics.py:58,222-233`).

## Suspected Code Paths

- `app/evaluation/generation_metrics.py:79-98` (`RagasJudge._metrics`): imports ragas and calls
  `embedding_factory("openai", model=self._config.embedding_model, client=client)` (line 91), which
  tracks one `EmbeddingUsageEvent` at once (`ragas/embeddings/base.py:745`). The embeddings it
  returns, used by `AnswerRelevancy` and `AnswerCorrectness`, track one more event for each
  embedding request (`ragas/embeddings/openai_provider.py:46,70,97,127`), so a benchmark sends
  several events per answer judged.
- `app/evaluation/ragas_llm.py:11,20-43` (`ProviderLLM`): subclasses `InstructorBaseRagasLLM` and
  overrides `generate` and `agenerate`, so the tracking in ragas's own `InstructorLLM.generate` and
  `llm_factory` (`ragas/llms/base.py:758,1176,1222`) isn't reached. No LLM event was seen.
- `ragas/_analytics.py:37-49`: the endpoint, and `do_not_track()`, which reads
  `RAGAS_DO_NOT_TRACK` once and caches it (`@lru_cache(maxsize=1)`). The switch has to be set
  before the first event, not merely before the import.
- `ragas/_analytics.py:80-90` (`get_userid`): creates `~/.local/share/ragas/uuid.json`, the
  persistent ID, the first time an event is built.
- `app/evaluation/__init__.py`: empty. Both modules that import ragas are in this package, so it
  runs before either.
- `Dockerfile:31-40`: already turns off the other libraries' telemetry in the image
  (`HF_HUB_DISABLE_TELEMETRY=1`, `GRADIO_ANALYTICS_ENABLED=False`, `ANONYMIZED_TELEMETRY=False`,
  since `3b93cce`, milestone 1), and `app/storage/chroma.py:53` does it in code for ChromaDB
  (`anonymized_telemetry=False`). ragas was missed.
- `tests/unit/test_generation_metrics.py:90` and `tests/unit/test_ragas_llm.py`: the unit tests
  that import ragas. The first builds the judge, and so sends the event.

## Root Cause Hypothesis

High confidence. ragas is opt-out: it posts usage analytics unless `RAGAS_DO_NOT_TRACK=true`. The
project turned off every other library's telemetry when the image was first built, but ragas came
later with the benchmarks, and its switch was never added. Nothing in `README.md` or
`docs/decisions.md` records the telemetry switches or the rule behind them. The one in the
Dockerfile also wouldn't reach the unit tests on the host or in CI, which don't run in the image.

## Proposed Remediation

**Preferred**: turn ragas's analytics off in the code, in `app/evaluation/__init__.py`, by setting
`os.environ["RAGAS_DO_NOT_TRACK"] = "true"` with a comment saying why. Every module that imports
ragas is in this package, so the switch is set before ragas is imported, and before
`do_not_track()` first reads and caches it. One place covers the image, the benchmarks, the unit
tests and CI. It is set outright, not with `setdefault`: no one using this application has a
reason to send ragas analytics, and an environment value left over from elsewhere shouldn't turn
them back on (Principle I).

Then record it. `docs/decisions.md` (Evaluation, or beside Cloud models) says that the libraries'
own analytics are off and how each is turned off: ragas in code, ChromaDB in code, Hugging Face and
Gradio in the image. It also says why ragas's is in code rather than the Dockerfile: the unit tests
and CI import ragas outside the image. `README.md:488` stays true once the fix lands, and needs no
change.

**Alternatives**:

- **Add `RAGAS_DO_NOT_TRACK=true` to the Dockerfile's `ENV`**, beside the other switches. The
  image and its benchmarks stop sending, but the unit tests on the host and in CI don't, which the
  `ci-unit-tests` decision needs. As a second copy beside the code, it is redundant.
- **Set it in `tests/conftest.py` and the Dockerfile.** That covers both, in two places, and misses
  any process that imports `app.evaluation` outside the two, such as a script run with
  `uv run python` on the host.
- **Patch `ragas._analytics.track` away.** That reaches into a private module that can change with
  any ragas release, where the environment variable is ragas's documented switch
  (`ragas/_analytics.py:272`, "Disable tracking by setting the environment variable
  RAGAS_DO_NOT_TRACK to True").

**Files likely to change**:

- `app/evaluation/__init__.py`
- `tests/unit/test_generation_metrics.py`, or a new `tests/unit/test_analytics.py`
- `docs/decisions.md`

**Tests to add or update**:

- A unit test that builds the RAGAS judge (as `test_generation_metrics.py:90` does) with
  `requests.post` in `ragas._analytics` replaced by a recorder, and asserts that nothing was posted.
  It skips without ragas, like `test_ragas_llm.py`. Before the fix it fails: the factory's event
  reaches the recorder.
- A second case, which makes ragas track an embedding request directly (`track(EmbeddingUsageEvent(...))`,
  as `openai_provider.py` does on each request) and asserts that nothing is posted. It locks the
  per-request events, which need an embedding server to happen for real.

## Risks & Considerations

- **The switch is read once.** `do_not_track()` caches its first answer. Setting the variable
  in the package's `__init__` runs first for every import path in the app. A process that imported
  ragas and sent an event before importing `app.evaluation` would keep tracking. Nothing in the
  repository does, and the tests above would show it.
- **A side effect at import.** Setting the process's environment from a package `__init__` is
  unusual. The comment says why, and `docs/decisions.md` records it, so it isn't removed as noise
  (Principle VIII).
- **Since when.** Every generation benchmark run since the RAGAS judge was added has sent these
  events, from the app container, with the ID kept in the container's
  `/home/app/.local/share/ragas/uuid.json` (`ASSUMPTION`: the container user's home, not checked).
  Recreating the container drops the ID. Nothing already sent can be recalled. What was sent holds
  model names and counts, no book text, question, answer or key.
- **Not a vulnerability.** No secret or library content is exposed, and ragas documents the
  behavior. It is a breach of Principle I, so it is handled as a bug, in public.
- **No real-model check needed.** The change touches no prompt, parser or judge logic, only whether
  ragas posts analytics, so the judge's scores can't move (Principle V, VI). The unit tests show
  it: the judge is built the same way, with the switch set.
- **The image needs `make up`** to take the fix in, which recreates the app container and empties
  the library (README, Running).

## Open Questions

- None blocking. One for the owner, not this fix: the other telemetry switches (Hugging Face,
  Gradio) live only in the Dockerfile. The unit suite doesn't launch Gradio or download from the
  Hub, so it doesn't reach them today (`tests/unit` has no `.launch(`). The Hub's agent-registry
  fetch seen in `research.md` isn't telemetry and isn't stopped by `HF_HUB_DISABLE_TELEMETRY`
  (`huggingface_hub/utils/_detect_agent.py:189-196`, only `HF_HUB_OFFLINE` stops it).
