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

**The app stops on SIGTERM, and Gradio's cache is swept.** The app is the container's first
process, and ignored the SIGTERM of `docker compose restart` until it was killed 10 s later, so
Gradio never shut down, and the files in its cache outlived the restart. `serve()` turns SIGTERM
into the interrupt Gradio closes on: a restart takes 1 s, and Gradio deletes its cache as it
closes. That cache holds a copy of every upload, such as a book added in the Library tab, up to
the upload limit. `delete_cache=(600, 3000)` also removes the copies older than 50 minutes every
10, so none waits for a restart. Gradio 6.32 sweeps uploads with the rest: `upload_file_set` is
one of the `temp_file_sets` that its sweep goes through.

**CUDA 13.4 torch.** The RTX 5060 Ti is a Blackwell GPU, which older CUDA builds can't drive.

## Dependencies

**Left out of the spec's list:** `FlagEmbedding`, because `CrossEncoder` loads both reranker
candidates and it would load the same model a second way; `aiosqlite` and `pytest-asyncio`,
because the service layer is synchronous (`pytest-asyncio` still arrives through LlamaIndex).

**Added:** `bm25s` and `PyStemmer` for lexical search, `py3langid` for language detection, which
is deterministic, and `tokenizers` for each model's own token counts.

**`langchain-community<0.4.2`.** ragas 0.4.3 imports a module that 0.4.2 removed.

**`ragas>=0.4.4`.** Listed unbounded, ragas went from 0.4.4 back to 0.3.1 in a `make update`:
`jiter` moved up to 0.19, `instructor` caps it below that, and 0.3.1 is the last ragas without
`instructor`, so the resolver gave up ragas rather than `jiter`. 0.3.1 has no
`InstructorBaseRagasLLM`, which `ProviderLLM` subclasses: `make test` stopped at collection, and
the generation benchmark couldn't judge. The bound is a constraint, like the one above, so the
dependency lists stay unpinned, and 0.4.4 is the version the judges were verified on. It holds
`jiter` below 0.19 for the whole project, `anthropic` and `openai` included, until `instructor`
lifts its cap: one lock resolves every extra together.

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

**Books are Markdown, converted outside the application** (specs/005-markdown-only, v0.5.0).
Departs from the first version's spec, which read PDF, EPUB and Markdown. The owner converts every
book with Microsoft MarkItDown, with their own plugins and open-source ones, so converting inside
the application did the same work again, with readers they no longer used. PDF and EPUB also
carried most of the ingestion code: PyMuPDF and Docling's layout models and OCR, EbookLib, and the
cleaning of running heads and page breaks. A PDF or an EPUB is now refused with a message to convert
it first. Removing them took 45 packages out of the lock, Docling's dependencies and `torchvision`
among them, and the app image went from 10,997,762,162 to 10,372,670,123 bytes, 5.7% smaller.

**A book's title is its file's name, and it has no author.** The owner's conversions have no front
matter, and their top-level headings name no title, so they were already titled after their file
names. The name is what the owner controls when converting. The catalog keeps the author field, empty,
for a later feature that may read one. A single top-level heading is still the book's own title line
for the structure rules, so its text shows nowhere.

**Pages were dropped, not read from markers in the Markdown.** Only PDFs ever gave pages, and the
conversions have none. Citations, the passages shown and the prompt's passage header locate a
passage by book, chapter and section; the excerpt a summary's references quote is how to find it in
the text. Constitution VII was amended for it (2.0.1). The chunk metadata lost its two
page fields, so its schema version, which the index fingerprint holds, went to 2.

**The benchmark's books are pinned to their conversion.** They are the owner's Markdown conversions,
named by their sha256, with their originals and the conversion recorded: MarkItDown's version and
commit, each plugin's version and commit, Python's version, and the command. The questions hold only
for those files, so a newer conversion makes a new dataset version, validated again. The first
conversion showed the owner's PDF plugin writing code without fences, so that 22 of *Think Python*'s
46 top-level headings were Python comments and one split a chapter, and keeping running heads and
syllable hyphens. It was fixed in the plugin, since the application adds no rule for a conversion's
quirks. Then two of the 280 evidence quotes needed correcting, to `lexi-con` and `n − 1`.

**What isn't the book's text is left out, by Gutenberg's markers and whole headings**
(`.specify/bugs/publisher-back-matter`). E-books carry matter that isn't the book, and the
conversions keep it, so it was indexed as the book's:
- **The ads.** Asked about the advertisements at the end of *História econômica global*, `search`
  returned them first: its top four passages were the ads and the table of contents. They sat in a
  "Table of Contents" section at the end of its last chapter.
- **The rest.** Each Gutenberg book had a chapter of license (9 chunks), and *Think Python* had a
  chapter of table of contents (24) and one of printed index (28).

The pipeline now keeps only what lies between Project Gutenberg's own START and END markers, when a
book has both. It also drops a section whose whole heading names a table of contents or a printed
index ("Table of Contents", "Contents", "Sumário", "Index", "Índice remissivo"), down to the next
heading at its level or above. "Índice" alone isn't on the list, since Portuguese books use it for
either. Both rules run before the language is detected, so an English license no longer counts
toward a Portuguese novel's language. On the benchmark's dataset, retrieval gained nDCG@10
+0.005, an interval that barely leaves zero out, and no question got worse
(`docs/benchmark-results.md`).

The rules see only markers and whole headings. A publisher's pages without a heading, such as a
catalog record or a copyright notice, are the conversion's to remove, as the owner chose, so the
application guesses at no wording. This isn't a rule for a conversion's quirk: the matter is in the
e-books themselves. Dropping a chapter, as Gutenberg's header and *Think Python*'s contents were,
moves the chapters after it down by one.

**Normalization keeps the cleaning that applies to any text**: Unicode composition, ligatures,
invisible characters and whitespace. Its configuration section went with its only key.

**Chapter numbers are positions, not printed numbers.** A preface has no printed number and two
parts can both have a "Chapter 1", while a filter needs a unique key. The title keeps what is
printed.

**A heading that says "Chapter N" outranks its depth, when depth clearly got it wrong.** A table
of contents with a single entry left the 200 chapters of a novel as subsections. The rule only
fires when numbered headings far outnumber what depth found, because many books print "Chapter 3"
above a title that the table of contents already has.

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

## Cloud models

**Answers and summaries may come from a cloud model, picked per request.** Departs from the first
version's spec, which put local-first at the top of its design principles, and from the
constitution before 3.0.0, which kept all inference local. The owner wanted Claude beside the local
model for answers and chapter summaries (`specs/008-cloud-llm-providers`). Constitution 3.0.0 made
it an opt-in: the local model stays the default, and a cloud model answers only a request that
picks it, since a cloud call sends a book's text to a third party. That is the user's choice each
time, not a setting left on, and the request carries no more than it needs: the question and its
passages, or the chapter. Embeddings, reranking, benchmarks and judges stay local: a cloud model
has no digest and no seed, so nothing that the index or a comparison rests on can depend on one.

**Cloud models are allowed in the environment, with one profile per provider.** Two settings per
provider, `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS`, the fewest the owner could set, and read apart
from `Settings` and `EnvironmentSettings`, so that the key reaches nothing that records or copies
them, such as a benchmark's result. Allowing a model takes one name in `.env`, where an entry in
`config/` would take a rebuild. What a provider's models share is one profile,
`cloud_profiles.anthropic`, validated at startup with the rest of `config/`. Changing either
setting still recreates the app container, which empties the library: the README says so where it
explains them.

**The local model ends every sequence.** Whatever fails before it, a request gets an answer from
the model that runs here, unless that one fails too. A fallback list can't name it: it is always
last.

**A summary is written by one model.** When a step fails, the summary starts again from its first
step with the next model, instead of finishing with another: a summary whose parts came from one
model and whose final step from another would make its record false. The failed attempt's tokens
are recorded too, since they were billed.

**Only the sequence's models answer.** Anthropic's API can fall back to another model on its own,
which its reference advises turning on for Claude Opus 5.5 and Sonnet 5.5. It stays off: it would
answer a declined request with a model that the user didn't put in the sequence.

**`reindex-all` leaves a cloud summary as it was.** Writing the saved summaries again calls no
cloud model. A summary that names a cloud provider stays, whether or not that provider is
configured now, and is listed, with a caveat: its references were made from the chunks before the
rebuild, and summarizing the chapter again refreshes them. Writing it again with the local model
would replace a summary the owner paid for with another model's, behind their back.

**No temperature, and no seed.** The current Claude models refuse any sampling setting with a 400,
so `config/generation.yaml`'s temperature doesn't apply to them; its token limits do, with the
profile's room for reasoning added. The API has no seed, which is one more reason benchmarks don't
run cloud models.

**A silent model gets 120 seconds, once.** The SDK's own retries are off: they would try a timeout
again too, turning 120 seconds of silence into six minutes. The provider tries a request again
itself, at most twice, after a rate limit, an overload or a lost connection, waiting 2 then 6
seconds, or the API's `retry-after` when it is shorter than 10, and only before anything has
streamed. A timeout is never tried again, so the profile's `request_timeout_seconds` is the
longest a sequence waits on one model. The owner chose 120 seconds.

**Tokens are counted with an approximation, which runs low.** Claude's tokenizer isn't public, so
`o200k_base` stands in. On the real models it ran about a third low: Claude counted 3,801 tokens in
a question's prompt that the app estimated at 2,543, and 4,803 in a chapter summary's estimated at
3,143, 1.49 and 1.53 times as many, more than `generation.context.safety_margin` absorbs. Nothing
is lost to it: Principle V's rule exists because Ollama cuts a prompt silently, while the API
refuses one that doesn't fit, and the models' own window, a million tokens, is far above the
profile's. What changes is the cap: `context_size: 65536` limits a request to about 100K of
Claude's own tokens, not 64K. Counting exactly would cost a request for each passage fitted.

**The profile's values.** `reasoning: low`, since the tasks read passages and write a short answer
or a summary; `reasoning_tokens: 4000`, room for the reasoning beside task limits set for
`gpt-oss`; `context_size: 65536`, a cap on what one request sends, and so on its cost;
`request_timeout_seconds: 120`; and `check_abstentions`, planned off, since a check costs a call
per answer, and turned on by the first run on the real models (below). Each stays while the checks
on the real models pass: a case that a higher effort passes raises the effort, a reply that stops
at its limit without text raises the room for reasoning, and a reply that abstains in words turns
the abstention check on.

**Checked on Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 (2026-11-20).** `doctor` found the three,
each with a window of a million tokens, taking the profile's effort and adaptive reasoning. The
integration tests ran each on an excerpt written for them, five questions it answers, three it
doesn't, and a short summary, and the quickstart's checks ran on *On Liberty*. What they write
differently from the local models:
- **They cite as the app asks**, `[1]`, where `gpt-oss` writes `【3】`. Every citation resolved,
  none was invented, and each answer cited the passage that holds its answer.
- **Haiku abstains in words.** Sonnet and Opus opened all three unanswerable replies with the
  no-evidence marker. Haiku did once, and twice wrote the abstention without it: "The passages
  don't say how much the electric lamp and the diesel generator cost the harbor board", and "The
  passages do not give the name of the convoy's commander". So `check_abstentions` is on for the
  provider. Given those two replies, Haiku's own check read both as abstentions, and with the
  check on, the 9 unanswerable cases and the 15 answerable ones came out right on all three
  models. It costs one more short call per answer without the marker.
- **They write more.** Answers ran 750 to 1,000 tokens, reasoning included, against `gpt-oss`'s
  200 to 280 for the same question, with bold labels in Markdown ("**Society as a tyrant.**").
  Asked in Portuguese, Sonnet answered in Portuguese.
- **They are fast to start.** Haiku's first token came in 1.5 s, and its answers in 12 to 17 s in
  all, Sonnet's in 19 s; `gpt-oss` took 15 s once loaded. No request came near the 120-second
  timeout, and no reply stopped at its limit, so `reasoning: low` and `reasoning_tokens: 4000`
  held.
- **A summary fits in one step.** Haiku summarized a 7-chunk chapter in one step, reading 4,803
  tokens and generating 1,737, with 5 of 33 statements close to no passage. The longest chapter of
  *On Liberty*, 22,274 tokens by the app's count, fits the 52,177 that `context_size: 65536` leaves
  a one-step summary, so that value held too.

**A command marks the text it can't take back.** The Chat tab removes what a failed model wrote
before the next one starts. A terminal can't, so `ask` says on standard error that the text above
is discarded, and which model answers from the start. Holding a cloud answer back until it is
whole would leave nothing to withdraw, but would stream nothing either.

**The provider reads three things the plan's mapping left out.** The SDK reports an error that
arrives inside a stream, such as an overload after the request was accepted, with the stream's HTTP
status, 200, so the API's error type decides its reason: an overload or an API error is an outage, a
rate limit a rate limit, an authentication, permission or billing error a refused key, and any
other a rejected request. A reply that stops because it filled the model's window
(`model_context_window_exceeded`) is read like one that stopped at its token limit: an answer when
it has text. And a check that can't reach Anthropic, or gets nothing in time, ends with one row, as
a refused key does, instead of waiting the profile's 120 seconds once for each allowed model.

**Benchmark results from now on have another configuration hash.** `Settings` gained
`cloud_profiles`, which every result records with the rest of the configuration, so a run of the
same local setup has another `configuration_sha256` than one made before. Nothing in the code
compares the two.

**Anthropic's SDK is its 2.x line.** The plan expected 1.x; `uv add` resolved 2.12.0, which runs on
`httpx2` as planned, apart from the `httpx` that Ollama's client and LlamaIndex use, so neither
constrains the other. Its model descriptions come back as typed objects, which the provider check
reads for the effort and the adaptive reasoning that the profile sends.

**OpenAI came through the same structure.** `specs/009-openai-provider` added OpenAI's models as
`specs/008` meant a second provider to come: a provider kind of its own, registered in
`CLOUD_PROVIDERS` after Anthropic, its profile, `cloud_profiles.openai`, and its two settings,
`OPENAI_API_KEY` and `OPENAI_MODELS`. No service, tab or command changed: `git diff` lists none
of `app/services/`, `app/interface/` or `app/main.py`, and a unit test keeps any of them from naming
OpenAI. The structure needed four changes, each for every provider:
- **Each kind names the efforts its profile may hold.** `CloudProfile.reasoning` listed
  Anthropic's names only, and OpenAI has two more, `none` and `minimal`. The profile now takes
  every provider's names, and the kind says which are its own: a profile with another one stops
  the app at startup. Anthropic's may still be empty, sending no effort; OpenAI's must name one,
  or each model would reason at its own default.
- **A name that two providers offer stops the app.** The choices kept the first provider's model
  for a name, so a name in both lists would have gone to Anthropic without a word. The same rule
  refuses a cloud name that is also the local model's, in either list.
- **"Out of credit" is a reason of its own** (below).
- **The retry waits moved to one place.** Both providers try a rate limit, an overload or a lost
  connection again after 2 and 6 seconds, or a shorter `retry-after`, from `app/generation/cloud.py`;
  Claude's provider tests pass unchanged on it, and so did Claude's integration tests.

**OpenAI's Responses API, streamed, and read raw.** Only the Responses API returns a summary of a
model's reasoning, which the Research tab shows, and OpenAI steers its reasoning models to it. The
provider reads the raw event stream rather than the SDK's `responses.stream()` helper, whose
final response exists only after `response.completed`, while a reply cut off by its limit ends
with `response.incomplete`, an answer when it has text. A request carries the prompt's messages
with their own roles and text, `system` included, so that the prompt is the local model's byte for
byte; the token limit, with the reasoning room added; the effort, and a request for the
reasoning's summary; `store: false`, so that OpenAI keeps no response for later retrieval; and
`truncation: "disabled"`, so that a prompt too long fails instead of losing its first messages,
the instructions among them, as Ollama would cut it. It carries no tool, so a reply can come from
the passages only, no sampling setting, which the GPT-6 models refuse, and nothing that names the
user or the library. The client is given the key and OpenAI's address, so `OPENAI_BASE_URL` can't
send either elsewhere; the benchmarks' judges, which reach Ollama through OpenAI's library too,
are given Ollama's address and a key of their own, and a unit test checks that every client of the
library in the app is.

**An account that can't pay is said as such, and not tried again.** OpenAI answers an exhausted
account with the status of a rate limit, 429, so the error's code decides: `insufficient_quota`,
`credit_balance_exhausted`, and the spending and usage limits of the organization or the project
are "out of credit or over a spending or usage limit", never tried again, since waiting doesn't
fix them. Only a 401 is a refused key: a 403, for a model the project may not use or a country
OpenAI doesn't serve, is a rejection with OpenAI's code. OpenAI's error messages are never shown,
since a refused key's message quotes the end of the key. Anthropic's billing error still reads as a
refused key, since Claude's provider was left as it was; moving it to "out of credit" is a
follow-up.

**What OpenAI doesn't document is handled, and was never needed.** OpenAI streams some models only
to a verified organization, without saying which error it gives: the provider recognizes it by
the parameter it names, `stream`, or by its words, says "OpenAI streams this model only to a
verified organization", and never asks again without streaming, which would leave the request
without the bound on a silent model (the owner's choice). The owner's organization streamed all
three models. Likewise, a request refused for asking a reasoning summary is sent once more without
it; OpenAI accepted the request on all three.

**Checked on GPT-6 Luna, GPT-6.1 Terra and GPT-6.2 Sol (2026-11-20).** The integration tests ran
each on the excerpt that Claude's models pass, five questions it answers, three it doesn't, and a
short summary: all 30 cases passed, beside Claude's three models' 30, in 145 s. A probe asked each
one answerable and one unanswerable question more. What they write differently:
- **They cite as the app asks**, `[2]`, and every citation resolved to the passage that answers.
- **They abstain with the marker, every time,** and then cite the passage that shows what is
  missing: "[NO-EVIDENCE] The passages say Marta inherited the lighthouse-keeper post from her
  father, but they do not give his name. [1]". So `check_abstentions` stays off for OpenAI.
- **They write little, and don't reason.** At effort `low`, OpenAI reported no reasoning tokens
  for these questions, so no summary of the reasoning came back, and the Research tab says that
  none did. Answers ran 31 to 57 tokens, where Claude Haiku's ran 99 to 280 and Sonnet's 82 to 186
  on the same questions; a one-step summary generated 294 to 398.
- **They start fast**: the first token in 0.7 to 1.0 s, a whole answer in 1.0 to 1.6 s.
- **They report the name they were asked for**, with no dated snapshot.

**The token estimate is close for OpenAI.** `o200k_base`, the encoding tiktoken gives the GPT-5
and GPT-4o models, has no entry for GPT-6 yet. On the real models, OpenAI counted 1.015 to 1.018
times the app's estimate, about 10 tokens a prompt, which is the messages' formatting: well within
`generation.context.safety_margin`, so `context_size: 65536` caps about 64K of OpenAI's own
tokens, where Claude's caps about 100K of Claude's.

**OpenAI's profile's values.** `reasoning: low`, which all three take, which OpenAI advises over
`none` or `minimal`, and which passed every case; `reasoning_tokens: 4000`, which no reply came
near; `context_size: 65536`, as for Claude, a cap on one request's size and cost, at most about
$0.13 on `gpt-6.2-sol`; `check_abstentions: false`, since every unanswerable case got the marker;
and `request_timeout_seconds: 120`, the owner's bound for Claude, with silence meaning that nothing
at all arrives, not even an event of the stream. No model was dropped from the owner's list.

**OpenAI's SDK came as RAGAS's dependency.** `openai` 3.3.0 was already in `uv.lock` for RAGAS, and
became a direct dependency without moving. The unit tests' fakes are built from its own types, so
a release that changes what the provider reads fails `make test` when `make update` brings it.
`Settings` changed again, with `cloud_profiles.openai` and the efforts' names, so a benchmark run
records another `configuration_sha256` than one made before.

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

**What an operation counts follows how long its stages take** (specs/004-library-progress). Timed on
the four benchmark books: chunks are embedded at 0.2 to 0.3 s a batch of 16, so they are counted.
A Markdown book's text is extracted in a tenth of a second or less, so extraction shows no count: a
count would be gone before it could be read. Until v0.5.0 a PDF's pages were counted, at 0.07 to
0.09 s a page. A removal and the resets took 0.05 to 0.10 s, so they show their steps by name,
without a count. Books took 3.1 to 39 s each, and a saved summary about 104 s with gpt-oss, varying
with its chapter's length, so a reindex counts them without a time left: the pace of those done
says little about those left.

**The time left is the weighted median of a stage's pace,** shown once the stage has run 3 s and
done a tenth of its items, and counting down between advances. In one run, one of *Think Python*'s
27 batches took 8.4 s against 0.2 to 0.3 s for the others. A mean carries such a stall to the end
of the stage, three times off halfway through when it comes early; a median doesn't move. A
time left for the whole operation, from paces kept across operations, was left out: the stage
lines in the log are where it would start from.

**The operation runs in a thread of its own, and the tab polls its progress.** Gradio's progress
bar draws over an event's outputs, and the Library tab's events had none, so its
`progress(0, desc=…)` calls most likely showed nowhere; it also estimates the whole operation from
the event's earlier runs, and disappears when the event ends. The service can't be a generator
instead: the library lock belongs to the thread that took it, and `operation()`'s log context,
a context variable set at the start and reset at the end, can't be reset across the worker threads
that run a Gradio generator's steps, each in a context of its own. So the handler starts the call
in a daemon thread, as Gradio's own worker threads
are, and renders `Progress.snapshot()` every half second. A page closed midway only stops the
polling: the operation runs to its end.

**Nothing in the progress raises into an operation.** `add_book` turns any exception from
ingestion into a failed book, so a display that broke would fail the book. A sink that raises is
logged and dropped, and a stage that wasn't declared, or a count past its total, is a warning. A
unit test runs every operation with a `Progress` and fails on such a warning, and compares each
operation, and each stage failing in turn, with the same one run without progress: the same
files, rows, vectors, collections and journal calls.

**The seven buttons are disabled by an event of their own, and enabled on success and on
failure.** Gradio's `then` doesn't run after an error, the same reason the list of books
refreshes on both. The operation's event keeps its `api_name`, so `gradio_client` calls it as
before; its outputs gain the progress area.

**Removing the earlier failed attempt of a file is not a stage of its addition.** It runs in a
journal entry of its own, before the addition's operation begins, where its stage line couldn't
carry the operation's execution ID. It takes moments.

**The commands print their progress to the error stream.** `reindex-all` printed its "Indexing …"
lines to standard output; they moved, so standard output holds each command's result only.

**Measured against `main` on the four benchmark books** (three runs each,
`library_progress_20261112T174811290268Z` and `…T181157104518Z`): the extracted, normalized and chunk
files came out byte for byte the same; no operation got slower beyond its spread, adding *Think
Python* taking 27.47 s against 28.27 and a reindex 53.37 against 54.69; 417 of 421 times left were
within half and double the time actually left; and every operation's stages added up to it within
0.036 s.

## Evaluation

**Relevance is stored as evidence quotes, not chunk IDs.** The spec asks for "relevant source
chunks", but IDs change with every chunk size, and comparing chunk sizes is one of the experiments.
A quote finds its chunks under any configuration, and the validator proves it is in the book.

**Citation accuracy means reaching the evidence.** A passage without the gold quote can still
support a claim, so a share of "correct" citations would punish correct answers.

**Experiments run in their own workspace**, on separate files and `bench_*` collections, so that
nothing they do can reach the real library.

**RAGAS sends no analytics, and its switch is in the code.** RAGAS posts usage events to its
authors, at `t.explodinggradients.com`, unless `RAGAS_DO_NOT_TRACK` is `true`. It sends one when
the judge's embeddings are built and one for each embedding request while the judge scores. Each
carries a persistent random ID, the RAGAS version and the embedding model's name, but no book text,
question, answer or key. Nothing set the switch, so every generation run sent them until
`.specify/bugs/ragas-analytics`, against Principle I: nothing contacts a third party nobody chose.
The other libraries' telemetry was off from the first image: ChromaDB's in the client's settings
(`app/storage/chroma.py`), Hugging Face's and Gradio's in the Dockerfile. RAGAS's is set in
`app/evaluation/__init__.py`, which runs before any module that imports RAGAS. It is in code, not
the Dockerfile, for two reasons: the unit tests and CI import RAGAS outside the image, and RAGAS
reads the switch only once, so it has to be set before then. It is set outright, not as a
default, so a value left in the environment can't turn the analytics back on.

**The benchmark's files left the repository.** The owner removed `benchmarks/` with the volumes, as
the folder was mounted into the app with them, and its result files went too. The experiments are
still in commit `c7bb785`. The dataset's last version, whose books became Markdown in v0.5.0, is in
`specs/005-markdown-only/benchmarks/`, with the experiment that compared it with the originals:
recorded where it was made, so that its corrected quotes and the checksum its results carry point
at files. The README's Benchmarks section restores
both, and `docs/benchmark-results.md` remains the record of what the runs found. The runner, the
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

**A judge has to prove itself before its scores mean anything.** Four bugs in this project gave
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
- The extraction benchmark reported full coverage of *Think Python*'s headings while 20 of its
  "Glossary", "Exercises" and "Debugging" headings had been dropped as running heads: it checked each
  title against the set of headings left, and every one of them survived somewhere else.

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

**Retrieval rows record what was retrieved.** Each lists, by chunk ID, its ranking, every passage
the search considered in the order its scores read, and its context, the passages kept. Without
them, the publisher-back-matter fix couldn't read what had outranked the evidence on `main`, only
infer it, and its report left that as a follow-up: Principle VI reads rows before concluding, and
a retrieval row held nothing to read but its scores. IDs and not texts, as the owner asked: an ID
tells the book, the chapter's position and the chunk's place, and the run's commit and books give
the text again. An ID holds within its run only, since another chunk size or ingestion renumbers
the chunks, so `devtools/compare_runs.py` shows each run's IDs under its own label and never
matches them across runs. Relevance stays stored as quotes. For a question that moved, the
comparison reads each run down to the lowest-ranked evidence among the first ten, or to the first
piece of evidence when none is there. The scores that decide whether a question moved read no
deeper, and `on_liberty_conceptual_01` moved below its first piece of evidence: its MRR was 1.0 in
both runs of the fix's check, while on `main` three of its seven quotes ranked sixth to tenth.

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

### Beads, the backlog (`specs/010-beads-issue-tracking`)

Spec Kit records how each change was handled, but nothing recorded what was still to be handled.
A fix report's Follow-ups were read only by whoever opened that report, and what an agent noticed
in passing was fixed on the spot or lost. [Beads](https://beads.gascity.com) (`bd` 1.3.4) is now
the backlog, and Spec Kit stays the record.

**One private tracker for all of the owner's projects, not this repository's `origin`.** By
default, beads syncs its Dolt database to the repository's own `origin`, under `refs/dolt/data`.
Anyone can fetch every ref of a public repository, so every issue would be public, vulnerabilities
among them. `local-book-rag` was public, private for a few hours on 2026-11-26, and public again.
The issues live in `guimassoqueto/issues`, private, which the owner's other repositories share,
and this one keeps no issue data whatever its visibility.

**Reached through `.beads/redirect`, written by `make beads`.** A redirect in `.beads/` sends every
`bd` started in the clone, and in its linked worktrees, to the tracker's clone beside it. A
relative path counts from the repository's root. Beads keeps the file local, and so does the
`.gitignore`. `BEADS_DIR`, which beads documents for a shared tracker, lives in a shell profile,
which an agent started elsewhere doesn't see. `bd init` here was never an option: it commits its
files to the current branch, and wires this repository's `origin` as the remote. So `make beads`
refuses to run when `.beads/` holds a database.

**Which repository a bead belongs to is a label, `repo:<name>`.** A beads store has a single issue
prefix, so a prefix per repository would need explicit IDs or routes to other stores. Every
listing an agent makes filters on the label.

**`idea` and `vulnerability` are custom types.** Beads' `bug`, `feature` and `chore` cover three of
the flows. A `security` label would be easy to leave out, and `bd ready -t` couldn't select it.
Beads' `spike` is time-boxed research, not an idea for an assessment to weigh. The types are stored
in the database, so every clone has them.

**A bead closes in the first session that sees its pull request merged, not in CI.** This
repository's workflows would need a credential to the private tracker, in a repository that is
public. Beads are picked up with `--status in_progress`, not `--claim`. A claim takes a lease of a
few minutes, kept alive by `bd heartbeat` and reaped by `bd reclaim`, which suits short-lived
workers under a supervisor. A change here lasts days.

**`.beads/PRIME.md` replaces beads' session text.** The default says "Use beads for ALL task
tracking", against `tasks.md` staying the one list of a feature's tasks. It also says not to use
the agents' own memory files. A `PRIME.md` in the clone's `.beads` wins over the default and over
the tracker's. It holds the commands, and `AGENTS.md`, Issues, the rules, so the two can't
disagree. `bd prime` reads `PRIME.md` only from the directory it runs in. From `app/`, it gave the
default text, so the hook runs it from the repository's root.

**The hooks are written by hand, through `devtools/beads-hook.sh`.** `bd setup claude` writes a
section into `CLAUDE.md`, which only imports `AGENTS.md`. `bd setup codex` writes a managed
section into `AGENTS.md` and a beads skill into `.agents/skills/`, both carrying the default text.
So `.claude/settings.json` and `.codex/` take the shapes beads documents for manual setup, and call
one script. Without `bd` 1.3.4, or without a tracker, the script tells the session why, and always
exits 0, so a session starts whatever beads' state. It is tested with a stand-in `bd`, so
`make test` needs no beads. Codex wasn't installed on the owner's machine, so its hook was checked
by running it by hand. Nothing of the integration is in a file Spec Kit generates: the skills in
`.claude/skills/speckit-*` and `.agents/skills/speckit-*`, and `.specify/` but for the constitution
and the records. After `make speckit-upgrade` regenerated them, the hook still served `PRIME.md`.

**No beads git hooks.** With the Dolt backend, issue data never travels in commits, and beads' git
hooks only chain the others and add agent trailers. pre-commit keeps `.git/hooks` as it was.

**No auto-push.** Beads keeps it opt-in, because concurrent pushes to a git remote can corrupt or
strand its history. A session pulls at its start and pushes at its end.

**A vulnerability's path depends on the repository's visibility, as `main`'s protection does.**
Repository security advisories exist only on public repositories. While this one is public, a
vulnerability is fixed in an advisory's temporary private fork. Status checks don't run there, and
GitHub doesn't enforce the target branch's rules when the advisory merges. A trial on 2026-11-26
kept a phrase in the fork's branch and pull request, and found it nowhere in the public repository.
Closing the advisory unpublished left the fork, which has to be deleted by hand. While it is private,
nothing in it is public, and the usual bug flow does. The same switch decides whether `main` is
protected. GitHub Free enforces `protect-main` on public repositories only, and while the
repository was private, the API refused to read it and `main` took direct pushes.

**Neither tasks nor beads are mirrored.** A feature's tasks stay in `tasks.md`, which implement and
converge check off: copied into beads, the two lists would drift apart. Beads aren't mirrored to
GitHub Issues either (`bd github sync`), which would need a token on each machine and conflict when
both sides are edited.

**The tracker started with the open backlog.** The three fix reports' Follow-ups and
`docs/benchmark-results.md`'s Recommendations and Known limitations held 25 items. Four were done
or moot, and three pairs were duplicates, so 18 became beads, each with the place it was listed in
`found_in`. The reports themselves weren't edited.

## Removed with PDF and EPUB (v0.5.0)

The library reads Markdown only since v0.5.0 (Ingestion). These decisions explained the readers
that went, each with the failure that taught it.

- **Running heads were recognized by their page numbers**: "10.13. Debugging 99" is unique to its
  section and never repeats, but its number follows the page at a fixed distance.
- **Each table-of-contents entry claimed one heading, exact matches first**: otherwise "Tuples are
  immutable" overwrote the heading "Tuples", and the chapter's text went to the one before.
- **A heading the outline named on its page was never a running head**: 20 of *Think Python*'s
  "Glossary", "Exercises" and "Debugging" headings had been dropped as running heads.
- **Docling, with OCR for scanned PDFs, was the alternative PDF reader**: its layout models were
  slower than PyMuPDF and suited complex layouts.

## Removed: the chapter quiz (v0.6.0)

**The chapter quiz was removed in v0.6.0** (`specs/006-remove-chapter-quiz`). Its tab, added in
v0.3.0 (`specs/003-chapter-quiz`), wrote a multiple-choice quiz on a chapter or a whole book, one
question per passage. The owner tried it for a while, didn't use it, and wasn't satisfied with it,
and its measurements agreed:
- **Keys the passage doesn't state.** About a quarter of gpt-oss's keys weren't stated by their
  passage: the agent's reading, never reviewed, found 65 of 88 sound, against a target of 90%. The
  key check meant to catch the others never proved itself, so it shipped switched off.
- **The right answer stood out.** It was the longest option in about half the questions, 53%
  against a target of 35%.

Improving it would have taken the key check's proof and a rule against a key that stands out by its
length. The owner chose to remove it instead, so both follow-ups were dropped. The tab, the service,
the writer and its prompts, the key check, the `generation.quiz` settings, the `quiz` and
`quiz_check` experiment kinds with their metrics, and the provider factory's per-task model and
reasoning, which only the key check used, all went. Its decisions were deleted rather than
shortened. Their reasoning stays in `specs/003-chapter-quiz`, in the assessment that led to it
(`.specify/assessments/chapter-quiz/`), and in the code at the tag `v0.5.0`, the last release with
the quiz. What it taught that still applies stayed where it applies: the stop on SIGTERM and
Gradio's cache sweep (Infrastructure), and the Library tab's operation thread (Library
lifecycle).
