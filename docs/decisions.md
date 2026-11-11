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

**Nothing is kept in a volume.** Departs from the spec, which put ChromaDB and Ollama in named
volumes and mounted `data/` and `logs/` from the host. The owner wanted pruning the containers to
leave no data behind. So each container keeps its own data, `config/` is copied into the image, and
the repository no longer has `data/` or `logs/` folders. What it costs:

- `docker compose down` now deletes the library, the vectors and the models, as only `down -v` did
  before.
- A rebuild recreates the app container alone. Its library comes back empty while ChromaDB keeps
  the vectors, and the new catalog numbers its indexes from 1 again, so the first index would reuse
  the old `book_chunks_v1` collection with the old passages in it. Index versions are never reused
  within one catalog, but nothing carries the count across containers. `reset-everything` deletes
  every `book_chunks_v*` collection, so it is the first step after such a rebuild.
- A configuration change no longer reaches the app on a restart alone. It is copied into the
  running container with `docker compose cp`, since the rebuild that would bring it empties the
  library.

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

**Old Portuguese spellings match modern ones in lexical search.** The benchmark's *Quincas Borba*
prints Sophia, elle, anno and facto, where readers type Sofia, ele, ano and fato. 27 of the 46
question words that never matched the book were in it in an older spelling.
- **Only keys are folded.** Lexical search folds the keys it compares, never the text, so a
  question in either spelling finds the other. Nothing stored changes, so turning
  `bm25.historical_spelling` on or off needs no reindex, and it stays out of the index fingerprint,
  like the query template.
- **y → i comes before stemming.** Snowball's Portuguese stemmer doesn't take y for a vowel: it cuts
  "tipo" to `tip` and leaves "typo" whole.
- **The other ten patterns apply to the stemmed, accent-free key**, where they collide less. They are
  ph, th, doubled consonants, ct, gn, bd, a leading sc, a final z, an h between vowels and oup. z → s
  alone makes 72 groups of modern words identical when applied after stemming, and 124 before.
- **It needs stemming**, because the words kept apart (below) are stemmed keys.
- **It ships switched off.** On the benchmark, lexical search alone gained 0.030 Recall@5 on the
  novel, with an interval from −0.03 to +0.12. The default configuration didn't change at all:
  dense retrieval and the reranker already found those passages. One question gained its evidence,
  and one lost part of it: once folded, its "Sofia" matched the book's 347 Sophias, which crowded
  the evidence out. The spec had settled beforehand that a gain within noise ships the feature off
  (`specs/001-historical-spelling`).

**Modern words that a pattern would merge are left as they are.** The patterns were measured against
Debian's `wbrazilian` 3.0~beta4-25: 274,246 forms of modern Brazilian Portuguese, making 44,858 keys.
- **What the patterns would do**: they change 1,103 of those keys, and some would make different
  words identical, such as pacto and pato, facção and facão, or signo and sino.
- **Kept as they are**: the 97 keys involved keep their spelling, which is 34 for a final z, 20 for
  ct, 14 for gn, 12 for doubled consonants, 9 for y, 4 for th, 2 for bd, and one each for h and
  oup.
- **The result**: no two words of the list collide, and all 28 of the spec's pairs match. Dropping
  the colliding patterns instead would have left 5 of the 28.
- **The cost**: some of the 97 are variants of one word or name, which then stay apart, such as
  Souza and Sousa, Tereza and Teresa, or dactilógrafo and datilógrafo.
- **"Modern" means Brazilian.** In Portugal, facto ("fact") and fato ("suit") are two words, so
  European Portuguese readers get that false match.
- **Rerunning it**: `devtools/measure_historical_spelling.py` reruns the measurement after any change
  to a pattern, and fails while the kept keys in `app/retrieval/bm25.py` differ from what it finds.
  The word list, which is GPL-2, stays out of the repository.

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

**The marker rule keeps its wording.** gemma4 and qwen3.5 sometimes abstain without the
marker. This happens when the passages mention what was asked about, but not what was asked: asked
who denounced the will, they reply that the text says only "someone", as if that were part of an
answer. Two rewordings were measured, and both made gpt-oss, the default, abstain on questions its
passages answer (`.specify/bugs/unmarked-abstentions/`):
- **The first** made three changes. It limited the partial-answer rule to questions that ask for
  several things, and asked for the marker "even when they mention the people, places or events
  it asks about". It also allowed adding what the passages do say after the marker. gpt-oss's
  wrong abstentions rose from 1 to 22 of 75, and its abstention quality fell by 0.233 (−0.322 to
  −0.144). About half said "the source doesn't contain the answer; however…", then gave it. Most
  of the rest denied an answer the passages hold. gemma4's unmarked abstentions in the probe fell
  from 8 of 60 to 3.
- **The second** kept only the narrower partial-answer rule. On the same contexts and seed,
  gpt-oss made 9 wrong abstentions, and gemma4 left 3 unanswerable questions unmarked instead of 1.

Tests on a single passage in six languages had favored the first wording, and predicted neither
result. A wording is better measured on the generation benchmark's own contexts, without the
judge, which takes minutes: whether a reply abstains needs no judging.

**Some models read their replies again for an abstention.** With `check_abstentions` in its
profile, a model that leaves out the marker is asked one more question, about its finished reply:
does it give the reader any of the information the question asks for? A NO makes the reply an
abstention. It is on for gemma4:12b and qwen3.5:9b.
- **After the reply, which displays the same way.** The application shows an abstention only once
  the reply is finished, under it. During streaming the marker is only removed.
- **The model that wrote the reply reads it.** Another model would often have to be loaded in its
  place, which costs far more than the check.
- **Without the passages.** The check reads what the reply gives, not whether the passages
  support it: weighing the evidence is what the rewordings moved, for every model at once.
- **Per profile.** The answering prompt doesn't change, so neither does any model's answer.
  gpt-oss, the default, runs no check: it left one abstention unmarked in 240 replies, and its
  check would reason on every answer.
- **Never at the cost of an answer.** A verdict it can't read, a failed call, or a check too long
  for the context leaves the reply an answer, and is logged.
- **The first wording asked for ANSWER or ABSTENTION**, and both models took partial answers that
  say what is missing for abstentions: qwen3.5 10 of 25 known answers, gemma4 2. Asking whether
  the reply gives any of what was asked, with "someone" for who counting as nothing, fixed that.
- **A phrase parser was ruled out.** Some answers are negations ("Mill does not state that he
  accepts…"), and some partial answers open by saying something is missing.

The proof (`tests/integration/test_generation.py`) has each model read its own known
replies, as in use: 23 for gemma4 and 20 for qwen3.5, asked in six languages, all read as
labeled but one. It also ran over the benchmark's replies:
- **Every unanswerable question left unmarked** was recognized.
- **Answers taken for abstentions**, in gemma4's 150 and qwen3.5's 75:
  - replies whose evidence retrieval had missed;
  - one of qwen3.5's, which gives the amount asked, then concludes that the passages don't
    contain it;
  - gemma4's partial answer to `think_python_multi_section_05`, in both runs, depending on how
    the model was loaded.

Its limits:
- **gemma4's verdict on one of its partial answers depends on the load.** "The book states… While
  the text does not provide a direct step-by-step parallel, it describes…" came out an answer
  under one load of the model and an abstention under another, every time within each, at
  temperature 0. The reader then sees the whole answer, under the note that the model found
  none. The owner kept the check on for gemma4: it ended gemma4's unmarked abstentions in the
  probe, 8 of 60, and the proof marks this case as a known misread.
- **Read by the other model, a few known replies came out otherwise.** gemma4 took 4 of qwen3.5's
  terse partial answers for abstentions, and qwen3.5 missed gpt-oss's "por alguém (o nome não é
  especificado)".
- **The benchmark's abstention quality didn't move**, 0.989 for gemma4 and 0.978 for qwen3.5. The
  unanswerable questions it now recognizes are offset by abstentions on answerable questions
  whose evidence retrieval missed, which the metric counts as wrong. `evidence_in_context` tells
  the two apart.

**The default LLM is chosen by a rule fixed before its runs.** gpt-oss:20b stays the default.

Why gpt-oss was the first default:
- The first version's spec (`.TASK/task.md` § 3.1) recommended it for "Reasoning and
  summarization", with gemma4:12b as the alternative.
- That was before the comparison its § 15.3 asked for. When that comparison ran, it leaned toward
  gemma4 (see `docs/benchmark-results.md`).

So `specs/002-gemma4-default-llm` wrote down, before any confirmation run, what gemma4 would have to
show. The confirmation:
- **Generation**: `default_llm_generation_20261109T041359173775Z`.
- **Summarization**: `default_llm_summarization_20261109T060210125028Z`.
- **The probe**: what the benchmark doesn't cover.
- **The reading** of the outputs.

All of it ran on 2026-11-09, from commit `f6f53a8`, with only these two models and gpt-oss judging.
How each condition came out:
- **(a) No gated metric worse, by an interval excluding zero**: passed.
- **(b) The earlier wins repeat**:
  - **Passed**: fewer wrong abstentions (0 against 1), and higher coverage of the novel (0.633
    against 0.261).
  - **Failed**: faster summaries. The −13.5 s and −1.33 steps a chapter both have intervals that
    reach zero.
  - **Why**: gemma4 took the same steps on every chapter in all three runs. gpt-oss's steps depend
    on how often its replies overrun their limits, and that varies from run to run. The 104 s
    recorded before was its slowest run.
- **(c) No error kind that gemma4 makes and gpt-oss doesn't, in 3 answers or 2 summaries**:
  passed, with one.
- **(d) Nothing the probe finds worse for gemma4**: failed.
  - 8 of its 60 abstentions in Spanish, French and German explained what the passages do say,
    without the no-evidence marker. So the application showed them as answers. None of gpt-oss's
    did.
  - In the probe, gemma4 also wrote the first visible word sooner, 0.32 s against 0.64 s.
- **(e) The real-model checks with gemma4 configured**: not run, since the switch needs (a) to
  (d).

What would reopen the question: unmarked abstentions no more frequent than gpt-oss's, through the
`fix/unmarked-abstentions` follow-up, and a speed win that holds across more chapters than the
dataset's six. A new spec would be needed, since this one is delivered. The reading also found
gpt-oss making more errors than gemma4 in its multi-section answers, 10 of 15 against 5. The
judge's scores didn't show that, and they still decide.

**A quiz question is written from one passage, by one call.** The assessment's probe asked for 9 or
10 questions from a batch of passages: 14 of 18 came from the batch's first 3 passages, and one
unreadable reply lost 6 of 30 questions. One call per passage lets the application choose the
passages, retry or replace one question, and show each as soon as it is ready
(`specs/003-chapter-quiz`, research R2).

**The model never chooses a letter.** In the probe the key was never D or E. The writer replies with
the question, the right answer, four wrong ones and an explanation, and the application puts the
right one on a letter from a balanced set, shuffled over the quiz, so every letter is the key as
often as any other, in every quiz (R3, R7). The order is a random permutation, drawn again when it
matches the text's (R7).

**The application chooses the passages.** A chapter is cut into as many contiguous strata as
questions, and one passage is drawn from each, drawn again when a third of the chapter would have
none. A whole book is divided among its chapters by their share of its words, by largest
remainder, so each is within one of its share (R6). A refused question is written again from the
same passage up to three times, then from another passage of its stratum, then from the nearest.

**A quiz's default length follows the text's.** One question per 300 words of the chosen text,
rounded half up, at least 1 and at most 20, and never more than the text's passages, the most it
can hold (at most 50). The words are counted over the chunks, overlaps included, which runs about
15% above the plain text: that is the count behind the spec's examples, 10 questions for the 3,115
words of *História econômica global*'s Capítulo 1. The rounding is written out, since Python's
`round` rounds half to even (R8).

**The Quiz tab builds its question slots up front.** It has `max_questions` slots, each hidden
until a question fills it, and the preparing handler is a generator that fills one slot at a time
and leaves the others alone (`gr.skip()`), so answers already chosen stay while the rest of the
quiz arrives. `gr.render` would rebuild every slot on each change, and clear them. Stop cancels a
preparation through `cancels`, which closes the service's generator at once; Prepare is inactive
meanwhile, since Gradio runs one call of an event at a time and would queue a second Prepare
behind the first instead of replacing it (R9).

**Questions don't point to their passage.** In the probe, numbered passages under book, chapter,
section and page headers led 20 of 24 questions to say "segundo o trecho 7" or the like. The writer
now gets its passage with nothing to point at, and the reader refuses what still points: a word for
the passage with a number or a pointer ("segundo o trecho", "the passage", "ao fim do trecho"), a
page, a section or, in a whole-book quiz, the chapter. A title counts only quoted, after a word for
chapter or section, or with its number: *História econômica global*'s section titles are mostly
subjects, such as "Japão", that a question may well ask about. "Trecho" alone also means a stretch
of road, and "the passage of" an act is its passing, so neither counts (R4).

**An empty fifth wrong answer is no answer.** gpt-oss:20b ended the list of wrong answers with an
empty string in 3 of its first 4 replies, which were all refused for not having four. The reader
drops blank entries before counting; three or five written ones are still refused (R4).

**The model skips a passage with nothing to ask about.** The catalog keeps a chapter's number and
title only, and this book's references and lists came in as chapters, so content decides, not
titles. A chapter whose first two passages tried are both skipped is left out (R5). A publisher's
advertisements for other books still get questions, when ingestion leaves them in a chapter: see
`docs/benchmark-results.md`, Known limitations.

**Preparing a quiz logs its own operation lines.** `operation()` tags every line logged inside it
through a context variable, set at the start and reset at the end. A quiz is prepared by a
generator, whose steps Gradio runs in worker threads, each in a context of its own, so the reset at
the end would fail. `QuizService.prepare()` logs the same started, finished and failed lines itself,
plus stopped when Stop closes it, and the lines logged inside it go without its execution ID.

**The quiz's key check reasons on a provider of its own.** Reasoning is a profile setting, sent with
every call, so the check runs on a provider built for `check.model` with `check.reasoning`, even on
the writer's model: gpt-oss writes at `low` and checks at `medium` (R11, R13).

**The download is the service's file, and Gradio's copy goes on shutdown.** The tab writes nothing:
`QuizService.export()` writes the result into `data/quiz_downloads`, which it empties whenever a
quiz is prepared and at each start. Gradio serves its own copy, and deletes it only when its
server shuts down. The app is the container's first process, and ignored the SIGTERM of `docker
compose restart` until it was killed 10 s later, so Gradio never shut down and the copies outlived
the restart. `serve()` now turns SIGTERM into the interrupt Gradio closes on: the restart takes 1 s,
and a Gradio app with the same settings then deleted its copy. `delete_cache=(600, 3000)` removes
copies older than 50 minutes every 10, so none lasts an hour; hourly copies older than an hour let
one last almost two (R9).

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

**The benchmark's files left the repository.** The owner removed `benchmarks/` with the volumes, as
the folder was mounted into the app with them, and its result files went too. The dataset and the
experiments are still in commit `c7bb785`, from which the README's Benchmarks section restores
them, and `docs/benchmark-results.md` remains the record of what the runs found. The runner, the
metrics and the report stay, with the unit tests of how they work, which now write their own
datasets. The tests of the removed files went with them: that the experiments covered every
comparison of the spec, that each variant was a valid configuration, that the dataset held its 90
questions, and that the default LLM's confirmation kept the variants and the judge of the
experiments it came from.

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

**The quiz measurement pairs runs by seed.** The `quiz` experiment prepares quizzes on six chapters
through the same `QuizService` as the tab, with a seed that fixes passages, letters and order, so
models and prompt rounds compare question by question. It can index `local_books`: the owner's copy
of a book that isn't public, checked against its checksum and never fetched. Each run writes
`reading.csv`, every question with its passage, to be marked by FR-020's rubric; it stays with the
results, out of the repository. The known cases of the key check hold a quote of at most 30 words
instead of their passage.

**The quiz's length bias is measured both ways.** gpt-oss:20b wrote the right answer as the longest
option in 85% of questions, and answered 85% right without the passage. Asking for five alike
answers, the right one never the longest, brought that to 53% (−0.32, interval −0.42 to −0.22);
writing the wrong ones first brought it back to 88%. The target is 35%, and the owner accepted the
miss for now. gemma4:12b's right answer is never the longest but is the shortest in 97% of its
questions, which counting only the longest hid: `key_is_shortest` is measured too.

**The quiz's key check ships switched off, unproven.** About a quarter of gpt-oss's quiz keys aren't
stated by their passage: 65 of round 2's 88 were marked sound by the agent's reading, not yet
reviewed, against a target of 90%. Most give
the author an argument the passage only reports or rejects. The check reads each question again
against its passage, and rejects it unless the passage supports exactly its key. On development
cases, at `medium`, it caught 12 of 27 flawed keys and rejected 2 of 85 sound ones, where the writer
answering with the passage caught 2. Like any judge, it has to prove itself before it decides
anything (constitution VI): FR-027's rule, on test cases from runs no wording was tried on. The
owner left that proof to a later feature, so the check stays off, and the passage shown after
submission remains the reader's safeguard.

**A comparator answers in JSON, not in words.** The key check is proved against the writer answering
each known case with its passage. Searching a reply for a letter would read the article in "A
resposta é C" as the answer, so it replies `{"answer": "C"}`, and an answer that can't be read is
left out and counted, not scored as wrong.

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
