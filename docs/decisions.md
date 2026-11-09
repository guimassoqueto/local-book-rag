# Architectural decisions

What was decided while building this, and why. Most of these came from measuring something,
or from a failure that only appeared on real books or real model output. The spec of the first
version is `.TASK/task.md`; where one of these departs from it, it says so. Later changes have
their own specs, under `specs/` (see Process).

## Infrastructure

**Chroma's healthcheck uses bash, and its `IS_PERSISTENT` settings are gone.** Departs from the
spec's Compose file. The `chromadb/chroma` image runs the Rust server, with no Python, so the
original healthcheck could never pass and the app would never have started. The server also
ignores those settings: its `/config.yaml` already persists to `/data`.

**Ollama and ChromaDB are published on loopback only.** The spec's Compose file publishes them on
all interfaces, and its section 18 says not to expose them. Neither has authentication, and
Docker's published ports bypass host firewalls.

**The app container gets the GPU.** Not in the spec's Compose file, but the spec wants the
reranker able to run on it, and the image tested with GPU access.

**CUDA 13.4 torch.** The RTX 5060 Ti is a Blackwell GPU, which older CUDA builds can't drive.

## Dependencies

**Left out of the spec's list:** `FlagEmbedding`, because `CrossEncoder` loads both reranker
candidates and it would load the same model a second way; `aiosqlite` and `pytest-asyncio`,
because the service layer is synchronous (`pytest-asyncio` still arrives through LlamaIndex).

**Added:** `bm25s` and `PyStemmer` for lexical search, `py3langid` for language detection, which
is deterministic, and `tokenizers` for each model's own token counts.

**`langchain-community<0.4.2`.** ragas 0.4.3 imports a module that 0.4.2 removed.

**LangChain is only here through ragas**, in the `evaluation` extra.

## Configuration

**`.env.sample` is in `devtools/`,** matching the layout of this author's other projects, rather
than `.env.example` at the root.

**One place for each setting.** The spec has the reranker's `enabled`, `model` and `top_k` in two
files, and the context size in two more. Model identity stays in `models.yaml`, use in
`retrieval.yaml`, and `llm.context_size` is the active window, capped by
`generation.context.max_size`. Two copies of a setting would disagree sooner or later. The spec's
`Qwen3/Qwen3-Reranker-0.6B` is also a typo for `Qwen/`.

**Model-specific behavior lives in profiles**, keyed by model name. Switching models is one line,
and a model without a profile fails at startup instead of embedding without its instructions.

## Ingestion

**Chapter numbers are positions, not printed numbers.** A preface has no printed number and two
parts can both have a "Chapter 1", while a filter needs a unique key. The title keeps what is
printed.

**A heading that says "Chapter N" outranks its depth, when depth clearly got it wrong.** A table
of contents with a single entry left the 200 chapters of a novel as subsections. The rule only
fires when numbered headings far outnumber what depth found, because many books print "Chapter 3"
above a title that the table of contents already has.

**Running heads are recognized by their page numbers.** "10.13. Debugging 99" is unique to its
section, so it never repeats, but its number follows the page at a fixed distance.

**Each table of contents entry claims one heading, exact matches first.** Otherwise "Tuples are
immutable" overwrites the heading "Tuples", the chapter disappears, and all its text is attributed
to the chapter before it.

**A heading the outline names on its page is never a running head.** At the top of a page, a
heading sits where running heads do, and *Think Python*'s "Glossary", "Exercises" and "Debugging"
repeat like them. 20 of them were dropped, and each glossary went to the section before it. The
extraction benchmark had reported full coverage, because it checked each title against the set of
headings left, and every one of those titles survived somewhere else. It counts them now.

**Tokens are counted with the embedding model's tokenizer**, since that is the model whose limit
matters. `cl100k_base` was 15% off on Portuguese.

## Indexing

**Queries embed on the CPU, indexing on the GPU.** Measured: 16 ms against 6 ms per query, and
5 against 59 chunks per second. This keeps the LLM alone in VRAM, as the spec asks.

**Each request names its device.** Left unset, Ollama keeps whatever runner is loaded, so indexing
after a chat silently ran on the CPU, 12 times slower.

**Input longer than the context is refused.** Ollama truncates it silently by default, which would
index part of a chunk as if it were whole.

**BM25 is built in memory for each search scope.** It takes 60 ms for a 1,300-chunk book, so there
is no second index on disk to keep in step with ChromaDB.

## Generation

**Prompts are fitted before sending.** Ollama doesn't refuse a prompt that is too long. It cuts it
silently and answers from what is left: a 12,000-word prompt came back as 4,098 tokens read.

**Citations are normalized, and code is skipped.** `gpt-oss` cites as `【3】`, and `t = [1, 2, 3]` in
an answer parsed as citations of three sources, which looks right and is false.

**Summary citations are computed, not claimed.** Asked to carry source tags through map-reduce,
`gpt-oss` numbered them upward whatever they pointed at, and often dropped them. The model writes
no citations now: each statement is looked up in the chapter's chunks.

**A map step cut off by its limit is redone in halves.** Batches sized to the context left replies
cut off after 6 of 14 passages, and the end of each batch silently vanished, while the report said
51 of 51 chunks. Batches are now sized to what a reply can hold.

**Merges that don't condense ask for less.** Asked for 540 words, `gpt-oss` merged two partial
summaries into 1,200, hardly shorter than the two. A merge of three hit its limit, was split, and
the rounds stopped making progress: 2 of the benchmark's 6 chapters ended in "too long to combine".
Merge prompts now put the limit first, and leave room for the reply in the context. A merge that
comes back no shorter than its parts keeps the parts, and a round that doesn't take a tenth off
halves the length the next one asks for. Only rounds at the shortest length that still don't
condense end the summary. Without that halving, one of the two chapters still failed 2 times in
7. With it, both completed 7 times in 7, and a round asked for 270 words brought 2,500 tokens
down to 500.

**Reranking on CPU stays in `bfloat16`.** A library warning says it may be slow. Here it is three
times faster than `float32`, thanks to AVX-512.

**The answer's language is named, not described.** Told to write "in the language of the
question", `gpt-oss` answered 4 of the benchmark's 50 English questions in Spanish, and abstained
in English on 4 Portuguese ones. With the question's language identified and named, the same
questions on the same passages, at two seeds, gave 1 answer in the wrong language instead of 14,
and 3 wrong abstentions instead of 9. Repeating the general rule after the question made it far
worse: 32 of 90 answers came back in Spanish, French or German. Short questions are often too
ambiguous to identify ("Explain recursion." reads as French), so below a confidence of 0.5 the
general rule stays.

**Summaries name their language, and show their headings in it.** A book stores its language as a
code, and the summary prompts passed it on as one: told "Write in pt", `gpt-oss` and `qwen3.5`
summarized both Portuguese chapters of the benchmark in English. Named, the language came out right.
`qwen3.5` still copied the English headings it was asked to translate, even with the language
named, so the headings are listed already translated, for the six languages the interface offers.

**The no-evidence marker is matched with any dash.** `gpt-oss` writes some hyphens as the
non-breaking hyphen, U+2011, and did so in the marker in 2 of 360 answers. Unrecognized, the
abstention was shown as an answer, with the marker in its first line. `gemma4` translated the
marker instead, as `[NO-EVIDÊNCIA]`, on the same question in both of its runs, with the same
result. A bracket that opens with `[NO-EVID` and closes within a word counts as the marker now.
The prompt still asks for it in English: changing the prompt would have changed what the
generation benchmark measured.

## Library lifecycle

**Chunks carry a book revision.** A replacement is indexed next to the live revision and one SQLite
transaction swaps them, so no search ever sees a mix, and a failure changes nothing. Record IDs
carry the revision, and `chunk_id` stays the stable ID from the spec.

**`source.json` sits next to each original.** The spec's section 8.5 clears the catalog on an index
reset and still promises a rebuild without uploading, while 8.6 reads books from the catalog. This
resolves it: a rebuild adopts originals back, with their IDs.

**Index versions are never reused,** even after `reset-everything`. A running server identifies an
index by its version, and must not mistake a new one for the one it has cached.

**Confirmations are checked in the service layer**, so Gradio and the commands can't differ.

**A journal entry closes only when the work, or its undoing, has really finished.** Cleanup that
fails is treated like a crash, so the entry stays open and recovery takes over at the next start.
A catch-all `finally` here once closed entries for work that had failed, which left half-deleted
books with nothing to finish the job.

**ChromaDB is checked before a change starts, inside the library lock.** With it down, a reset used
to fail halfway, stay journaled and run again by itself on the next start, long after anyone
remembered asking for it. Refusing up front means a change either starts on a working stack or
doesn't start at all.

**Recovery decides from the catalog whether a swap happened.** A crash between the swap and its
cleanup has to finish the job, while one before the swap has to undo it, and the revision in the
catalog is what tells them apart.

## Evaluation

**Relevance is stored as evidence quotes, not chunk IDs.** The spec asks for "relevant source
chunks", but IDs change with every chunk size, and comparing chunk sizes is one of the experiments.
A quote finds its chunks under any configuration, and the validator proves it is in the book.

**Citation accuracy means reaching the evidence.** A passage without the gold quote can still
support a claim, so a share of "correct" citations would punish correct answers.

**Experiments run in their own workspace**, on separate files and `bench_*` collections, so that
nothing they do can reach the real library.

**nDCG gives credit per quote, against a real ideal order.** Counting chunks made two quotes in one
chunk unable to reach 1, which penalized large chunks for holding more of the evidence, in the very
experiment that compares chunk sizes.

**The validator is stricter than the resolver.** A quote has to be in the book exactly as written
for `validate-benchmark` to pass, while resolving evidence under another chunking tolerates a
boundary cutting through it. Accepting half a quote at validation hid quotes that were simply wrong.

**A judge has to prove itself before its scores mean anything.** Three bugs in this project gave
believable numbers, and none of them raised an error:

- RAGAS went through Ollama's OpenAI-compatible endpoint, which can't set `num_ctx`. It ran at 4096
  tokens and silently cut prompts to about 2000, so most long answers failed and some of the ones
  that didn't were scored against part of their sources. `ProviderLLM` sends RAGAS through this
  project's own provider instead, and refuses a prompt that doesn't fit.
- At `low` reasoning, the summary judge copied the sample values from its prompt without reading
  the summary: its entire reasoning was "Likely poor". Every rating of every model came out 0.0.
  Prompts no longer show sample values.
- Exact comparison made Docling look as if it had lost 82% of a book's structure, because it keeps
  the `1.1` that the book's outline leaves out.

So before trusting a judge, check that it can separate cases whose answer is known: the correct
answer from an invented one, and a real summary from a distorted one and from another chapter's.

**Reasoning is set per judge, because the two kinds of judge need different things.** The rubric
is one prompt asking for four opinions, and needs `medium`: at `low` it doesn't read, and at `high`
reasoning eats the whole token limit and no verdict comes out. RAGAS asks small structured questions
with worked examples, so it needs only `low`: on answers built to have a known faithfulness it gave
1.00 for verbatim text, 0.64 for half-invented and 0.00 for invented, while `medium` took up to seven
times as long and sometimes reasoned until it hit the limit, even at 9000 tokens.

**A judge's JSON gets one repair, and a retry samples.** 14 of the 16 scores missing from the first
full generation run were `gpt-oss` ending a list of statements with `"...last."}`, without its `]`.
The judge runs at temperature 0, where decoding is greedy, so retries that only changed the seed got
the same broken reply three times. `read_verdict` now closes a list left open when its object
closes, and repairs nothing else: a reply cut off at its limit stays unreadable, instead of becoming
a shorter verdict. Retries sample, at temperature 0.5.

**The summary judge reads only what the model wrote.** The references after a summary quote the
opening of each passage it cites, up to 1,900 characters of the book's own words, and both the
rubric and coverage could credit them to the model. Coverage is also left out unless every key
point got a verdict: a share of the rest would be a share of a different list.

**Answer relevance asks for one question.** RAGAS sends its prompt three times by default, and a
judge decoding greedily answers it three times the same: two calls per answer, for nothing.

**Every cold start loads from the file cache.** Each model loads once before it is measured.
Before, its first context size also timed the disk, so 16K looked faster to load than 8K.

**A workspace is rebuilt when its index no longer matches.** The fingerprint that guards the real
library, including the embedding model's digest, guards workspaces too. A new workspace first
clears its prefix on the server, since one deleted by hand leaves collections that its first index
would otherwise fill again. Code changes can't be detected: after changing ingestion, delete
`benchmarks/workspace`.

**Generation rows record how much of the evidence reached the model.** Abstention quality counts
an abstention on an answerable question as wrong even when retrieval never brought the evidence,
and then abstaining is exactly what the prompt asks for. `evidence_in_context` tells the two apart.

**`peak_vram_mb` waits for the GPU, not for Ollama's model list.** A model leaves the list some
200 ms before its memory is free, and the list's own figures are unreliable (1.4 GB reported for a
model holding 9.1 GB). Without waiting, one model's memory was reported as the next one's peak. It
reads the whole machine, since Ollama is in another container, so `idle_*` records what was already
in use: a model's cost is its peak minus that.

**A novel's key points state one event each.** The first key points for *Quincas Borba* packed
three or four details into each event, and the coverage judge rejected a point for any one of them
missing, although its prompt says secondary details may be: "Sofia covers his mouth" sank a point
whose debt confession was there. A summary that, read closely, covered about 7 of 10 points scored
0.2, the same as one written in the wrong language that got the chapter's main event wrong. With
one event per point, condensed from the same points without adding to them, the two scored 0.6 and
0.3, and each chapter's summary still scored 0.0 against the other chapter's points. The points
use the book's spelling now (Sophia, Maria Benedicta), although spelling alone changed nothing.
Questions keep the modern one, as a reader would type it.

**Context recall equals Recall@5 here, by construction.** Both ask how much of the evidence is in
the same five passages. They would differ only with a final context of another size, so the
duplicate column is expected, not a bug.

## Process

**Spec Kit drives every change after v0.1.0.** `.TASK/task.md` specified the whole first version,
built one milestone at a time. Its milestones are done, and what the benchmarks left to do
(Recommendations and Known limitations in `docs/benchmark-results.md`) is a list of separate
changes. Each one gets its own record now: a spec, a plan and tasks for a feature, a diagnosis and a
test report for a bug, and evidence with a verdict for an idea.

**Two integrations are committed, Claude Code's and Codex's.** The project has to stay usable from
any agent. Codex's skills go to `.agents/skills/`, which Cursor, Gemini CLI, Copilot, OpenCode and
others read too, so a fresh clone works in all of them with nothing to install. Spec Kit's mode for
mixed teams, committing with `--integration none` and switching agents locally, would cost a switch
before every commit.

**Extension skills reach Codex by making it the default for a moment.** `specify extension add`
renders an extension's skills for the default integration only (Spec Kit issue #2948): installed
with Claude as the default, the bug and assessment skills were in `.claude/skills/` and missing from
`.agents/skills/`. `specify integration use codex` renders them, and switching back to Claude
changed nothing else, every other file byte for byte. `make speckit-upgrade` does the same after
each upgrade. The switch has one side effect: `integration use` rewrites the shared scripts in
`.specify/scripts/bash/` without their executable bit, so they were committed that way, and the
first `/speckit-specify` failed with "Permission denied". The target puts the bit back, and git
records it.

**In Claude Code, only the user can start a core skill.** Installed with `--no-model-invocation`,
Claude doesn't start a specification on its own when asked for a small change, and nine skill
descriptions stay out of its context. Extension skills can't be restricted this way, because Spec
Kit's mandatory hooks rely on the model invoking them. Neither can Codex's copies: Spec Kit's Codex
integration has no such option, so `AGENTS.md` asks the other agents to keep to the rule.

**No git extension.** It names branches `{number}-{slug}` under one fixed prefix, while branches
here are named by type (`feat/…`, `fix/…`). Its automatic commits, such as `[Spec Kit] Add
specification`, would fail the commit-msg hook. Spec Kit doesn't need it: the active feature is
recorded in `.specify/feature.json`, not read from the branch.

**No agent-context extension.** It keeps a generated block in the agent's instruction file, and
`AGENTS.md` is written by hand, with `CLAUDE.md` only importing it.

**The rules live in the constitution, which `AGENTS.md` imports.** Plan, tasks, analyze and converge
check their work against `.specify/memory/constitution.md`, but the bug commands never read it and
the assessment ones hardly do. So `AGENTS.md` imports it, which Claude follows, and tells other
agents to read it. The rules that used to be in `AGENTS.md` moved there: two copies would disagree
sooner or later.

**No template overrides yet.** An override in `.specify/templates/overrides/` replaces the whole
template, so each one would stop following upstream changes. The constitution carries this
project's checks instead, and an override waits for a change that shows a template missing
something the constitution can't supply.

**A delivered spec is history.** Its `specs/NNN-*` directory isn't edited again: a later change gets
a new one. What stays true goes to the README, and why to this file, as before.

**Spec Kit's CLI is a dev dependency.** `uv.lock` pins it as it pins commitizen, `make install`
installs it, and `make update` upgrades it with everything else. It added twelve packages and
changed the version of none, and the image installs no dev dependencies.

**The whitespace fixers skip Spec Kit's files.** It writes some of them without a final newline.
Fixed, they would no longer match the hashes Spec Kit recorded, and `specify integration upgrade`
refuses to replace files it takes for local edits.
