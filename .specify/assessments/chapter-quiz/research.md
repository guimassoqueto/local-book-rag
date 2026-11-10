# Idea Research: a multiple-choice quiz on chosen chapters

- **Slug**: chapter-quiz
- **Created**: 2026-11-10
- **Evidence confidence (overall)**: medium

The evidence comes from three places. The main one is a read-only probe, run on the live stack for
this research, in which the default LLM wrote questions from three real chapters, which were then
read one by one against their passages. The others are this repository's own records, and web
search results on prior art. Nothing was fetched from the web: the sources are hosts outside the
URL allowlist, so only the search results were read, and their figures are as the results report
them (see Sources).

**The probe** (`probe/quiz_probe.py`, results in `probe/results.json`, without the book's text):
- **Setup**: gpt-oss:20b (`f38aa0c53da5`), reasoning `low`, Ollama 0.40.15, the app container
  built at 2026-11-10T12:24Z from `57f9929`, the app's own provider and passage format, 8,192-token
  window. Temperature 0.2 and seed 0 for writing the questions, temperature 0 for the checks.
- **Book**: `book_001`, *História econômica global: Uma breve introdução*, in Portuguese.
- **Chapters**: Capítulo 1 (3,115 words, 13 chunks), Capítulo 3 (5,010 words, 21 chunks) and
  Capítulo 6 (9,757 words, 40 chunks).
- **Method**: each chapter's chunks were split into consecutive batches that fit the prompt budget
  (4,372 tokens, after reserving 3,000 for the reply and the 10% safety margin). The model was
  asked for 3 questions per batch, A to E, one correct, in Portuguese, as JSON, each naming the
  passage that answers it. Then the same model answered each question twice: with the batch's
  passages ("open book"), and without them ("closed book"). It was also asked three times per
  chapter how many questions would test the chapter well. Last, one batch went through Ollama's
  JSON-schema output mode (`format`) twice, outside the app's provider.
- **The reading**: every question was read against its passage, for whether the key is right and
  whether only one option can be defended.
- **Limits**: one book, one model, one seed and one first prompt, never tuned. 24 questions were
  read, by one reader (Claude).

## Users & Demand

- **One user, a stated want.** The only user is the repository's owner, who proposed the idea as
  their next implementation. There is no observed behavior to weigh: nothing in the application
  generates questions or records a reader's answers — [source: `intake.md`] (confidence: high)
- **What the quiz is for hasn't been stated.** It could be studying a book, or checking one's
  reading, and the two would value different things, such as coverage, difficulty or history —
  [ASSUMPTION; NEEDS CLARIFICATION below] (confidence: low)
- **Practice tests help memory, multiple choice included.** Meta-analyses find practice tests
  better for learning than restudying (Adesope et al., 2017). A review finds multiple-choice
  recognition tests at least as effective as free and cued recall in producing the testing
  effect, with or without feedback. One summary of a 222-study classroom meta-analysis (Yang et
  al., 2021) reports the formats working about equally well, and another classroom meta-analysis
  found short answers somewhat better than multiple choice — [source: Frontiers in Education review
  10.3389/feduc.2019.00005; learningandthebrain.com summary; search results only] (confidence:
  medium: secondary summaries, not the papers)

## Prior Art

- **Internal: summaries are the closest feature.** They read a whole chapter by map-reduce,
  fitted to the context, because Ollama cuts silently what doesn't fit. Their citations are
  computed by lookup, since gpt-oss, asked to carry source tags through map-reduce, numbered them
  upward whatever they pointed at — [source: `docs/decisions.md` § Generation] (confidence: high)
- **Internal: gpt-oss's JSON has broken before.** 14 of the 16 scores missing from the first full
  generation run were gpt-oss ending a list without its `]`. The judge's reader now repairs that
  one case and nothing else — [source: `docs/decisions.md` § Evaluation] (confidence: high). The
  probe saw two other ways of breaking (Data & Constraints).
- **Internal: judges have to prove themselves.** Three bugs gave believable numbers with no error,
  so a judge first has to separate cases whose answer is known — [source: `docs/decisions.md` §
  Evaluation; constitution VI] (confidence: high)
- **Internal: naming the language works.** Told "Write in pt", gpt-oss summarized Portuguese
  chapters in English, and named, the language came out right — [source: `docs/decisions.md` §
  Generation]. In the probe, with "Portuguese" named, all 24 questions came in Portuguese
  (confidence: high)
- **External: NotebookLM has quizzes from one's sources.** Google added Flashcards and Quizzes to
  NotebookLM in September 2025. Reported features:
  - quizzes grounded in the sources, which the user picks;
  - adjustable focus and difficulty;
  - an "explain" option that says why an answer was wrong, with citations;
  - after a quiz, a study guide or new flashcards from the questions missed.

  It is a cloud service — [source: workspaceupdates.googleblog.com, 9to5google.com; search results
  only] (confidence: medium)
- **External: wrong keys and item-writing flaws are common in LLM-written questions.**
  - A preliminary 2026 literature review (a conference poster) reports 22–30% error rates in
    medical education, including incorrect answer keys, poor distractors and item-writing flaws,
    and concludes that expert review is needed — [source: tomanet.memberclicks.net poster, Patel;
    search result only] (confidence: low: preliminary)
  - A 2026 letter on AI-written medical questions names recurring cues: the correct option
    identifiable without content knowledge, an over-explained correct option, and stem words
    repeated in the answer — [source: medicine.nus.edu.sg, LE3898; search result only]
    (confidence: medium)
- **External: models skew where they put the correct answer.** A 2026 study of question
  generation finds option D systematically underrepresented across nearly all models and tasks,
  LLaMA favoring A, and Qwen3 and DeepSeek favoring B. Removing the letter labels doesn't remove
  the skew — [source: arXiv 2605.01846, Tang, Duan and Cai; search result only] (confidence:
  medium)
- **External: generated reading questions are often guessable.** Säuberli and Clematide (2024)
  measure "text informativity": how many items are answered with the text, minus how many are
  guessed without it. Many generated items were overly guessable from world knowledge, and GPT-4
  as the test taker came closest to human annotators — [source: arXiv 2404.07720; search result
  only] (confidence: medium). The probe's open- and closed-book checks follow the same protocol.

## Market & Context

- **What the owner can do today**:
  - **Ask the Chat tab for questions about a chapter.** Chat answers from 5 reranked passages, so
    on Capítulo 6 it would see 5 of 40 chunks, and nothing scores the answers — [source:
    `config/retrieval.yaml` `reranker.top_k: 5`; probe chunk counts] (confidence: high)
  - **Use a cloud service such as NotebookLM.** That means uploading the book, which this project
    exists to avoid — [source: constitution I] (confidence: high)
  - **Write the questions by hand**, or use flashcards — [ASSUMPTION] (confidence: medium)
- **What the project is for.** The constitution describes a research environment for open-weight
  models: its point is to compare LLMs, embedding models and retrieval strategies under controlled
  conditions. A quiz serves the reader of a book rather than that comparison, though it would also
  exercise a new task on the configured model — [source: constitution I, Why] (confidence: high)
- **The cost of doing nothing**: no feature, workflow or measurement breaks. The owner keeps
  studying without a quiz, or with an outside tool — [source: `intake.md`, current state]
  (confidence: high)

## Data & Constraints

**Probe: format and speed**
- **2 of 10 replies weren't valid JSON**, and lost their batch: 6 of 30 requested questions.
  - One closed a question's options, then opened a new object with its `answer`.
  - One added an empty fifth string to the options (`"E": "…", ""`).

  All 10 stopped on their own (`finish=stop`), at 466 to 765 tokens of the 3,000 allowed — [source:
  `probe/results.json`] (confidence: high)
- **Ollama's JSON-schema mode returned valid JSON 2 times in 2**, but once with 1 question of the 3
  asked: the schema set no count. The app's provider (llama-index's `Ollama`) exposes `json_mode`,
  plain JSON, not a schema — [source: `probe/results.json`; field list of the installed class]
  (confidence: medium: two calls)
- **Fast, for chapter-length work.**
  - Each call took 5.2 to 9.2 s, with 42 to 112 characters of reasoning.
  - Generation per chapter: 15.2 s for Capítulo 1 (2 calls), 18.9 s for Capítulo 3 (3 calls) and
    33.9 s for Capítulo 6 (5 calls).
  - The two checks per question added about 70%.
  - For comparison, a summary of one chapter took 48.6 to 104 s on average across the benchmark
    runs.

  [source: `probe/results.json`; `docs/benchmark-results.md`] (confidence: high for this book)
- **Chapters don't fit in one prompt.** The core chapters of this book run 4,706 to 14,898 tokens,
  against a 4,372-token prompt budget at the 8K window, so 2 to 5 calls per chapter — [source:
  probe chapter listing] (confidence: high)

**Probe: the questions, as read against their passages**

| Reading                                                    | Questions | Which                  |
| ---------------------------------------------------------- | --------- | ---------------------- |
| Key right, one defensible answer, clean stem               | 16        |                        |
| Key right, but the stem flawed                             | 4         | Q2, Q7, Q9, Q13        |
| Key wrong                                                  | 1         | Q17                    |
| Key not supported by the passage                           | 1         | Q16                    |
| Two defensible answers                                     | 2         | Q18, Q22               |

- **4 of 24 (17%) would mark a reader wrong for a defensible answer, or reward one the book
  doesn't give.**
  - **Q17**: the passage ties the rice coast's Caribbean-like social structure to slave imports,
    which rose from 275 to 2,000 a year. The key says better farming techniques.
  - **Q16**: the passage says Jamaican planters repatriated their income to Britain, and gives no
    reason. The key supplies one: "colonial policy".
  - **Q18**: the passage's reason, that slaves wouldn't earn their cost, is close to option A. The
    key is the next sentence, about land and wages.
  - **Q22**: the passage gives two factors and doesn't rank them, and the question asks for "the
    principal" one.

  [source: `probe/results.json`, field `reading`] (confidence: medium: one reader, 24 questions)
- **The flawed stems:**
  - **Q2** credits Britain with policies that, in the passage, Western Europe and the US adopted
    to catch up with it.
  - **Q7** gives the answer away in the question.
  - **Q9** is muddled.
  - **Q13** asks what contributed "most", and the passage lists another factor first.
- **The model's own open-book check agreed with its key 23 times in 24**, so it caught 1 of the 4
  problem questions (Q17) — [source: `probe/results.json`] (confidence: high)
- **The passage each question named held its subject, 24 times in 24.** For Q16 it holds the fact,
  but not the reason asked for — [source: the reading] (confidence: medium)
- **Many questions could be answered without reading the chapter.**
  - **Without the passages**, the same model picked the key 18 times in 24 (75%).
  - **Position**: the key was A 4 times, B 13, C 7, and never D or E. Always answering B scores 54%.
  - **Length**: the key was the longest option 15 times in 24, against about 5 expected by chance.

  [source: `probe/results.json`] (confidence: high for the counts; medium for what they mean for a
  human reader, since the guesser is the model that wrote the options)
- **The questions bunch at the start of each batch.** In the 6 batches of 9–10 passages, 14 of 18
  questions came from passages 1–3.
  - On Capítulo 6, pages 79–110, the questions came from pages 79–81, 87–89, 101–103 and 109–110.
  - The batch at pages 94–101 was lost to broken JSON.

  [source: `probe/results.json`] (confidence: high)
- **The recommended count varies by run and grows less than the length.** Asked three times at
  temperature 0.2:
  - Capítulo 1 (3,115 words): 12, 12, 12.
  - Capítulo 3 (5,010 words): 18, 25, 20.
  - Capítulo 6 (9,757 words): 25, 25, 22.

  That is 2.3 to 5.0 questions per 1,000 words — [source: `probe/results.json`] (confidence: high)

**The book and the application**
- **Front and back matter are chapters too.** The catalog lists 15 chapters for this book, and 5
  are front or back matter: Agradecimentos, Referências bibliográficas, Leituras complementares,
  Lista de ilustrações and Lista de tabelas. Today's chapter dropdowns offer every catalog chapter
  — [source: probe chapter listing; `app/interface/formatting.py` `chapter_choices`]
  (confidence: high)
- **Nothing kept in the app container survives a rebuild.** `make up` recreates the app container
  after any change to the code or to `config/`, and it comes back with an empty library. No volume
  or host folder may hold data — [source: `README.md` § Running; constitution II] (confidence:
  high)
- **Constitution rules that apply as the idea stands:**
  - the generating model named only in configuration, and any new task settings validated at
    startup (I);
  - the logic in a service, with the tab only reading input and showing output (IV);
  - parsing what the model really writes, and checking the prompt and parser on the real models
    (V);
  - a judge, if the LLM grades answers or checks questions, proving itself first (VI);
  - claims traceable to passages (VII);
  - `README.md` and `docs/decisions.md` updated (VIII).

  [source: constitution] (confidence: high)

## Evidence Against the Idea

- **About 1 question in 6 had a flawed key in the probe, and the self-check missed 3 of the 4.** A
  reader can't tell a wrong key from their own mistake. So the score, and the chapter the
  suggestions send them to reread, can be wrong without any sign. The literature reports flaws of
  this kind persisting, at rates of 22–30% in one preliminary review — [source: probe; Patel poster]
- **The score may measure test-taking more than reading.**
  - The model that wrote the questions answered 75% of them without the text.
  - Always answering B would have scored 54%, and always taking the longest option 62%.

  How far a human reader would get without reading wasn't measured — [source: probe; Säuberli and
  Clematide]
- **The quiz would mostly test the start of each batch.** Most of each batch's passages produced
  no question. A per-chapter score would reflect only part of the chapter — [source: probe]
- **It sits off the project's stated purpose.** The project exists to compare models and
  retrieval under controlled conditions. A quiz adds a prompt and a parser, and possibly a judge,
  each needing real-model checks and, for a judge, proof (V, VI). It doesn't serve that purpose
  directly — [source: constitution I, V and VI]
- **The demand is one stated want, with no observed use**, and its purpose is still unstated —
  [source: `intake.md`]
- **Progress over time doesn't fit the current setup.** If the idea needs scores kept, everything
  in the app container goes with each rebuild — [source: `README.md` § Running]
- **The probe is small and untuned.** One book, one seed, a first prompt and one reader. It cuts
  both ways: the problems might shrink with work on the prompt, or grow on other books — [source:
  probe Limits]

## Gaps & Open Questions

- [NEEDS CLARIFICATION: What is the quiz for, and what prompted it? This decides what the score has
  to mean.]
- [NEEDS CLARIFICATION: Chapters from one book, or from several?]
- [NEEDS CLARIFICATION: Are quizzes and scores kept, to show progress? If so, how does that square
  with nothing surviving a rebuild of the app container?]
- [NEEDS CLARIFICATION: What should a suggestion contain: the chapter, its sections and pages, why
  each wrong answer was wrong?]
- [NEEDS CLARIFICATION: Are the key errors, position skew, length cue and bunching properties of
  gpt-oss, or of this first prompt? Untested: other prompts, other seeds, gemma4:12b, which isn't
  on the machine now.]
- [NEEDS CLARIFICATION: How would a human reader do on these questions without reading the
  chapter? The 75% is the model guessing its own questions.]
- [NEEDS CLARIFICATION: What check could catch keys like Q16, Q18 and Q22, which the model's own
  open-book check accepted? How would that check prove itself (constitution VI)?]
- [NEEDS CLARIFICATION: Does the probe hold on other kinds of book? The novel and the programming
  book of the benchmark dataset aren't in the library now.]
- [NEEDS CLARIFICATION: Should front and back matter be offered as quiz chapters?]

## Sources

Repository (read on `57f9929`):
- `.specify/memory/constitution.md` (principles I, II, IV–VIII)
- `docs/decisions.md` § Generation, § Evaluation
- `docs/benchmark-results.md` (summary timings)
- `README.md` § Running, § Interface
- `config/models.yaml`, `config/generation.yaml`, `config/retrieval.yaml`
- `app/interface/formatting.py`, `app/interface/summarization.py`, `app/interface/chat.py`
- `.specify/assessments/chapter-quiz/intake.md`
- `.specify/assessments/chapter-quiz/probe/quiz_probe.py` and `probe/results.json`

Web (search results only, none fetched: these hosts aren't on the URL allowlist):
- https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2019.00005/full (host:
  www.frontiersin.org, policy: search result, not fetched)
- https://www.learningandthebrain.com/blog/getting-the-details-just-right-retrieval-practice-2
  (host: www.learningandthebrain.com, policy: search result, not fetched)
- https://workspaceupdates.googleblog.com/2025/09/flashcards-quizzes-reports-notebook-lm-google-education.html
  (host: workspaceupdates.googleblog.com, policy: search result, not fetched)
- https://9to5google.com/2025/09/08/notebooklm-flashcards-quizzes/ (host: 9to5google.com,
  policy: search result, not fetched)
- https://tomanet.memberclicks.net/assets/docs/2026Convention/Posters/Patel.Yash.pdf (host:
  tomanet.memberclicks.net, policy: search result, not fetched)
- https://medicine.nus.edu.sg/taps/wp-content/uploads/sites/10/2026/03/LE3898_Hidden-pitfalls-in-AI-generated-MCQs_A-call-for-caution.pdf
  (host: medicine.nus.edu.sg, policy: search result, not fetched)
- https://arxiv.org/pdf/2605.01846 (host: arxiv.org, policy: search result, not fetched)
- https://www.arxiv.org/abs/2404.07720 (host: www.arxiv.org, policy: search result, not fetched)
