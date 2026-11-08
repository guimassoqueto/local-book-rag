# Benchmark results

What the five experiments in `benchmarks/experiments` found, on 2026-11-07 and 08. Result files
stay out of the repository, so this page is their record. Every number in it comes from those
files, and `book-rag benchmark-report` shows each run with the paired comparisons quoted below.

The setup was an RTX 5060 Ti with 16 GB, a Ryzen 9 9950X3D, 60 GB of RAM and Ollama 0.40.15.
Models ran at the quantizations Ollama serves: MXFP4 for gpt-oss:20b, Q4_K_M for the others. The
dataset has 90 questions over three books, of which 75 can be answered from them, and the key points
of six chapters, two per book.

Extraction, retrieval and performance ran on commit `4fcd1cb`, generation on `f90a1b0` and
summarization on `826c977`. The commits in between changed the summarizer, the summary prompts
and the key points, none of which the other experiments use. The one after them, `c7dd6ac`,
recognizes a translated no-evidence marker: see Generation.

## How far to trust these numbers

- **The dataset is small.** Each comparison below went through a paired bootstrap (4,000
  resamples, 95% interval). A difference is called real only when its interval excludes zero, and
  most aren't.
- **The judge disagrees with itself.** gemma4:12b gave the same 75 answers, byte for byte, on
  both days, so every change in their scores is the judge's own. A single answer's faithfulness
  moved by 0.13 on average, and went from 0 to 1 for two of them. Correctness moved by 0.06 and
  relevance by 0.05. The average over the run moved by 0.03. So only averages over a whole run
  mean much, and faithfulness by book, over 25 answers, means little.
- **The judge is also a candidate.** gpt-oss:20b scores every model's answers, its own included.
  It passed checks on cases with known answers before these runs, but a judge can still prefer
  its own way of writing.
- **The questions were written with the books open**, so they often share the book's words. That
  favors lexical search. Readers who paraphrase would see less of BM25's strength.
- **Automated scores are a first signal.** The conclusions below also rest on reading the answers
  and summaries.

## Extraction

| Extractor | Book | TOC entries | TOC coverage | Chapters | Chunks | Pages covered |
| --- | --- | --- | --- | --- | --- | --- |
| pymupdf | quincas_borba | 6 | 1.000 | 205 | 454 | – |
| pymupdf | think_python | 240 | 1.000 | 23 | 425 | 0.967 |
| pymupdf | on_liberty | 14 | 1.000 | 11 | 176 | – |
| docling | quincas_borba | 6 | 1.000 | 205 | 454 | – |
| docling | think_python | 240 | 0.967 | 25 | 386 | 0.967 |
| docling | on_liberty | 14 | 1.000 | 11 | 176 | – |

Only *Think Python* is a PDF, so it is the only book where the extractors can differ: EPUBs don't
go through the PDF extractor. PyMuPDF keeps all 240 entries of the book's outline as headings.
Docling keeps 232, and detects 25 chapters where PyMuPDF detects 23. PyMuPDF stays the default for
born-digital PDFs like this one. Docling is there for layouts PyMuPDF reads badly, and this dataset
has none.

Before this run, PyMuPDF's pipeline lost 20 of those headings, and the metric hid it: see
"Changes these benchmarks led to", below.

## Retrieval

The 75 answerable questions, under nine configurations. Rerankers ran on the GPU here. By default
the reranker runs on the CPU, where it takes about 4 s per question.

| Variant | Recall@5 | Recall@10 | MRR | nDCG@10 | Context precision | Rerank p50 |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3_dense | 0.802 | 0.841 | 0.793 | 0.746 | 0.776 | – |
| bge_m3_dense | 0.804 | 0.842 | 0.807 | 0.746 | 0.768 | – |
| bm25 | 0.851 | 0.929 | 0.877 | 0.822 | 0.840 | – |
| hybrid_weighted | 0.863 | 0.917 | 0.870 | 0.825 | 0.851 | – |
| hybrid_rrf | 0.851 | 0.924 | 0.842 | 0.811 | 0.821 | – |
| hybrid_rrf_qwen3_reranker (default) | 0.897 | 0.943 | 0.961 | 0.876 | 0.903 | 0.79 s |
| hybrid_rrf_bge_reranker | 0.912 | 0.954 | 0.931 | 0.885 | 0.909 | 0.38 s |
| chunks_300 | 0.837 | 0.913 | 0.902 | 0.830 | 0.884 | 0.53 s |
| chunks_800 | 0.938 | 0.959 | 0.956 | 0.908 | 0.920 | 1.15 s |

- **Reranking is the one change that clearly helps.** Over plain hybrid RRF it adds 0.119 to MRR
  (95% interval +0.068 to +0.176) and 0.047 to Recall@5 (+0.006 to +0.096). The passage holding
  the answer comes first for most questions.
- **The two rerankers are equivalent.** BGE's differences from Qwen3's (+0.014 Recall@5, −0.030
  MRR) are within noise, and it takes half the time.
- **Larger chunks find more of the evidence, which they would by construction.** 800 tokens adds
  0.041 to Recall@5 over 500 (+0.008 to +0.080), and 300 takes 0.060 away (−0.102 to −0.025). But
  a larger chunk holds more of the evidence just by holding more text, and costs 60% more prompt
  per question. Whether answers improve is untested, so 500 stays.
- **Hybrid search beats dense search alone** by 0.049 Recall@5 (+0.007 to +0.100), but not BM25
  alone (0.000).
- **Within noise:** the two embedding models (+0.001 Recall@5), BM25 against dense (+0.048), and
  weighted against RRF fusion (+0.012). The embedding comparison also compares chunk sizes, since
  chunks are counted with each model's tokenizer: bge-m3 makes 416 chunks of *Quincas Borba* where
  qwen3-embedding makes 454, and 457 of *Think Python* against 425.
- **Dense retrieval is weakest on the Portuguese novel.** On *Quincas Borba*, Recall@5 is 0.715
  for qwen3-embedding and 0.695 for bge-m3, against 0.803 for BM25. The default configuration
  reaches 0.886 there, 0.946 on *Think Python* and 0.861 on *On Liberty*.
- **Evidence spread across sections is what retrieval misses.** By category, the default
  configuration's Recall@5 is 1.000 for factual questions, 0.960 for questions about one chapter,
  0.887 for conceptual ones and 0.640 across sections: five passages can't hold evidence from up
  to six places. One question has no evidence at all in its top five, and 14 have part of it,
  10 of them multi-section.

Context recall is left out of the table because it equals Recall@5 here, by construction.

## Generation

The four models answered the 90 questions from the same retrieved passages, those of the default
configuration, and gpt-oss:20b judged them all. Faithfulness, correctness and relevance are
RAGAS's, over the answers that didn't abstain. Generation speed is the median over the run.

| Model | Faithfulness | Correctness | Relevance | Citation accuracy | Abstention quality | Wrong abstentions | Generation t/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss:20b (default) | 0.813 | 0.706 | 0.783 | 0.944 | 0.956 | 3 | 95 |
| gemma4:12b | 0.894 | 0.702 | 0.771 | 0.987 | 0.978 | 0 | 99 |
| qwen3.5:9b | 0.837 | 0.647 | 0.764 | 0.947 | 0.978 | 0 | 71 |
| qwen3:14b | 0.790 | 0.721 | 0.786 | 0.973 | 0.978 | 1 | 44 |

- **The four are close.** Paired with gpt-oss, two differences exclude zero: gemma4's faithfulness
  (+0.090, from +0.012 to +0.174) and qwen3.5's correctness (−0.054, from −0.098 to −0.012).
  Neither is safe from the judge's noise. An interrupted run the day before, with the same
  question-answering code, had gemma4 ahead on faithfulness by only 0.011. Take it as a direction,
  and qwen3.5's lower correctness as a hint.
- **Every answer was in the question's language**, for every model. With the old prompt, a probe
  on the same passages had 14 of 180 gpt-oss answers in the wrong one.
- **gpt-oss abstains when it holds part of the answer.** Its three wrong abstentions, all on
  *Quincas Borba*, had half or more of the evidence in front of them, as had four of its five in
  the interrupted run. It says what the passages contain, under the no-evidence marker, instead of
  answering that part, as the prompt asks. The other models didn't do this once. qwen3:14b's one
  abstention was right: retrieval brought none of the evidence.
- **Abstention quality counts the marker, not honesty.** Each model "answered" one or two of the
  15 questions the books can't answer. Five of those six replies said plainly that the text
  doesn't tell, only without the marker, or, once, with gemma4's translation of it, which the
  application didn't recognize until `c7dd6ac`. The sixth was a real error: qwen3:14b had Rubião
  travel to Barbacena by tilbury, a carriage the passages mention for a ride along the beach.
- **Questions across sections are the hardest for every model**, with correctness from 0.48 to
  0.59 against 0.71 to 0.80 for factual ones. Retrieval brings only 64% of their evidence.
- **gemma4 and gpt-oss write fastest**, and gemma4 needs 9.2 GB of VRAM against 12.5 GB. gpt-oss
  reads prompts more than twice as fast: see Performance.

The run took 3 h 43 min, slowed by checks run alongside its scoring: without them, the
interrupted run took about 36 s per question, almost all of it scoring.

## Summarization

Each model wrote a `standard` summary (about 500 words) of the six chapters, and gpt-oss:20b
judged them against the chapters' key points and passages. Argument coverage is the share of key
points the judge found. The four rubric criteria run from 1 to 5, scaled to 0 to 1.

| Model | Argument coverage | Concepts | Consistency | Coherence | Completeness | Traceability | Words | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss:20b (default) | 0.543 | 0.792 | 0.833 | 0.833 | 0.792 | 0.922 | 758 | 104 |
| gemma4:12b | 0.665 | 0.917 | 0.792 | 0.750 | 0.708 | 0.967 | 633 | 35 |
| qwen3.5:9b | 0.709 | 0.833 | 0.792 | 0.792 | 0.792 | 0.961 | 1050 | 51 |
| qwen3:14b | 0.313 | 0.792 | 0.708 | 0.792 | 0.625 | 0.933 | 536 | 51 |

Every model summarized every chapter from all of its chunks, and in the book's language.

- **qwen3:14b covers least**, in this run and the one before: it names the chapter's topics
  without saying what the chapter claims about them. Its difference from gpt-oss excludes zero
  (−0.230, from −0.444 to −0.004), as does qwen3.5's in the other direction (+0.167, from +0.014
  to +0.333), which comes mostly from the novel.
- **The other three are close on the English chapters**, whose key points were the same in both
  runs: 0.708 to 0.750 here, 0.604 to 0.771 in the run before, with the order changing. A
  chapter's coverage moved by 0.08 to 0.19 between runs, as much as the gaps between models.
- **gpt-oss is weak on the novel**: 0.211 against 0.578 for gemma4 and 0.628 for qwen3.5. Read
  closely, its summary of CAPITULO L has Palha say what Sophia says, and leaves out the debt, the
  wine and the ending. The judge's low score is right.
- **qwen3.5's lead is partly length.** It wrote about 1,050 words for a 500-word target, and more
  words hold more key points. Its summaries are also the most detailed to read, with a few
  garbled sentences.
- **The rubric separates little.** Six chapters on a five-point scale give steps of 0.04, and
  most of its differences are within noise. gemma4's concepts (+0.125, from +0.042 to +0.208)
  are the one that isn't. It also gave gpt-oss's wrong summary of CAPITULO L 0.75 for consistency.
- **gpt-oss is the slowest**, at 104 s a chapter against 35 s for gemma4. Its replies overrun
  their limits, so its batches are redone in halves and its merges take several rounds: 9.8 steps
  a chapter, against 3.5.

## Performance

The median of three runs after a cold start and a warm-up, generating up to 256 tokens from four
passages of *On Liberty*. All four models ran entirely on the GPU at both context sizes.

| Model | Context | Quantization | Load (s) | First token (s) | Prompt t/s | Generation t/s | Total (s) | Peak VRAM (MB) | VRAM over idle (MB) | RAM over idle (MB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss:20b | 8K | MXFP4 | 2.3 | 0.31 | 5156 | 96.1 | 2.03 | 12987 | 12546 | 793 |
| gpt-oss:20b | 16K | MXFP4 | 2.3 | 0.31 | 5161 | 95.8 | 2.04 | 13187 | 12746 | 903 |
| gemma4:12b | 8K | Q4_K_M | 2.5 | 0.67 | 2153 | 102.0 | 1.89 | 9599 | 9158 | 4364 |
| gemma4:12b | 16K | Q4_K_M | 2.5 | 0.67 | 2152 | 101.9 | 1.88 | 9759 | 9318 | 4142 |
| qwen3.5:9b | 8K | Q4_K_M | 1.6 | 0.42 | 3338 | 71.2 | 4.01 | 7091 | 6650 | 1446 |
| qwen3.5:9b | 16K | Q4_K_M | 1.6 | 0.42 | 3335 | 71.1 | 4.02 | 7363 | 6922 | 1408 |
| qwen3:14b | 8K | Q4_K_M | 1.9 | 0.70 | 1996 | 44.0 | 3.15 | 10665 | 10224 | 1250 |
| qwen3:14b | 16K | Q4_K_M | 1.9 | 0.70 | 1995 | 43.9 | 3.16 | 11961 | 11520 | 1429 |

- gemma4:12b and gpt-oss:20b write fastest, at about 100 tokens per second. qwen3.5:9b writes
  at 71, and qwen3:14b at 44.
- gpt-oss reads a prompt fastest, at about 5,200 tokens per second against 2,000 to 3,300 for
  the others: it is a mixture of experts, and only part of it runs for each token.
- Doubling the context to 16K costs gpt-oss 200 MB of VRAM and qwen3:14b 1.3 GB. gpt-oss takes
  the most memory, 12.5 GB of the 16. The defaults leave the GPU to the LLM, with the reranker and
  query embeddings on the CPU.
- Total time isn't comparable across models, since each writes a different amount: compare the
  rates. Loads take 1.6 to 2.5 s, from the system's file cache. From disk they take longer.

## Recommendations

The defaults stay as they are. These are what the results suggest changing, and what each change
would cost.

- **gemma4:12b as the default LLM.** It matched gpt-oss's correctness and relevance, never
  abstained with evidence in front of it, was ahead on faithfulness in both runs, summarized the
  novel far better (0.578 against 0.211), and summarized three times as fast. It writes slightly
  faster, and needs 3.4 GB less VRAM. Against it: gpt-oss reads prompts 2.4 times as fast, so its
  first token comes in 0.31 s against 0.67 s. gpt-oss should stay the judge either way: a new
  judge would have to pass the known-answer checks again.
- **bge-reranker-v2-m3 as the reranker.** It matched Qwen3-Reranker-0.6B in half the time. Both
  were timed on the GPU, though, and the default runs the reranker on the CPU: time it there first.
- **500-token chunks until generation says otherwise.** 800 finds more of the evidence, but by
  holding more text. A generation run at 800 would tell whether answers improve.
- **Two generation runs before trusting a faithfulness difference**, or a stronger judge. A
  single run can't tell a gap of 0.05 from the judge's own noise.

## Known limitations

- **The judge's noise**, described at the top: per-answer faithfulness means little.
- **The judge resolves names badly in the novel.** An answer that calls Palha by his first name,
  Christiano, or says what a letter's "eu" says of its writer, can lose its faithfulness even when
  the passage says exactly that.
- **The novel's old spelling.** *Quincas Borba* writes Sophia, Theophilo and Christiano, and the
  questions use the modern Sofia and Teófilo, as a reader would. BM25 can't match those names, and
  nothing normalizes historical spelling.
- **Abstention quality counts the marker**, so an honest "the text doesn't say" without it counts
  as an answer.
- **Each question searches only its own book.** Asked of the whole library after these runs,
  gpt-oss answered a trap it had refused in the benchmark, naming the daughter of Maria Benedicta
  "D. Fernanda", with a citation of a chapter that doesn't say so.
- **Six chapters** are too few for the summary rubric to separate models, and coverage favors
  longer summaries.
- **A summary's "References" heading is always in English.**
- **The embedding comparison also compares chunk sizes**, since each model's tokenizer counts the
  500 tokens: see Retrieval.

## Changes these benchmarks led to

Running the experiments in full, and reading what they produced, found problems in the
application as well as in the benchmarks. `docs/decisions.md` has the detail of each.

- **Answers in the wrong language.** Told to answer "in the language of the question",
  gpt-oss:20b answered 4 of the 50 English questions in Spanish, and abstained in English on
  Portuguese ones. The prompt now names the question's language: on the same passages, answers
  in the wrong language fell from 14 to 1 in 180, and wrong abstentions from 9 to 3.
- **Abstentions shown as answers.** gpt-oss sometimes writes the no-evidence marker with a
  non-breaking hyphen, and gemma4 translated it once, as `[NO-EVIDÊNCIA]`. The application
  recognized neither. The command line also streamed gpt-oss's citations as `【1】`, unlike the
  finished answer.
- **Lost headings.** The PDF loader took 20 of *Think Python*'s section headings, such as
  "Glossary", for running heads, so each glossary went to the section before it. The extraction
  metric had reported full coverage.
- **A judge that failed quietly.** It lost 16 scores to gpt-oss leaving a JSON list unclosed,
  retried at temperature 0 with the same result, read the references after a summary as the
  model's own words, and asked the same relevance question three times.
- **Load times that timed the disk** on each model's first context size.
- **Summaries that couldn't be finished.** gpt-oss:20b merged partial summaries into texts nearly
  as long as their parts, whatever length it was asked for, and 2 of the 6 chapters ended in "too
  long to combine". Merges that don't condense now ask for half the length, and the two chapters
  completed 7 times in 7.
- **Portuguese summaries in English.** The summary prompts gave the book's language as its code,
  and told "Write in pt", gpt-oss and qwen3.5 summarized both Portuguese chapters in English.
  qwen3.5 also kept the English headings it was asked to translate.
- **Key points the judge couldn't use.** Those first written for *Quincas Borba* packed several
  details into each event, and the coverage judge gave a close summary the same 0.2 as a wrong
  one. Rewritten one event per point, they separate the two, 0.6 against 0.3.

## Reproducing

```bash
docker compose exec app book-rag pull-models --all          # every candidate model
docker compose exec app book-rag fetch-benchmark-books      # checked against their checksums
docker compose exec app book-rag validate-benchmark

make benchmark EXPERIMENT=extraction       # about a minute
make benchmark EXPERIMENT=retrieval        # about 7 minutes, indexing four workspaces
make benchmark EXPERIMENT=performance      # about 3 minutes
make benchmark EXPERIMENT=summarization    # about 45 minutes
make benchmark EXPERIMENT=generation       # about 3.5 hours
```

Retrieval is deterministic: two earlier runs agreed to four decimals. Generated text and the
judge's verdicts vary a little from run to run, even at a fixed seed, so judged scores won't repeat
exactly.
