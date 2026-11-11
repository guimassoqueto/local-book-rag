# Contract: what the models are sent and must reply

The prompts live in `app/generation/prompts.py`, with the others. Their exact wording is the
implementation's, measured on real models (constitution V). This contract fixes what they carry
and the replies the readers accept. Readers accept what models really write; they don't assume
the prompt was obeyed (research R4).

## The writer

**Sent**: a system message, then one user message holding:
- **The passage**, without a number, section or pages, under the book's title and author. In a
  one-chapter quiz, the chapter's title is added. The question then has nothing to point at: in
  the probe, numbered passages under such headers gave "segundo o trecho 7" in 20 of 24 questions
  (FR-004).
- **The language**, named: "Write the question, the answers and the explanation in Portuguese."
- **The rules**:
  - one question, answered by this passage alone;
  - about the author's arguments, explanations and evidence, not page numbers or general knowledge
    (FR-005);
  - one right answer, stated by the passage, or reached by steps the passage states (FR-005);
  - four wrong answers, wrong according to the passage, plausible to someone who hasn't read it,
    and of about the same length and form as the right one (FR-004);
  - an explanation that says only what the passage says (FR-004);
  - the question and options written as an exam would ask about the book. They may say "the
    author" or "the book", never "the passage", "the excerpt" or "the text above", a number, a
    section or a page. In a whole-book quiz they don't name the chapter (FR-004);
  - no answer may refer to the others, as "all of the above" does (FR-009);
  - a skip, when the passage holds nothing to ask about (FR-007).
- **The reply format**, below, with field names only. There are no sample values, which a judge
  once copied instead of reading (`docs/decisions.md` § Evaluation).

The parameters are `generation.quiz.temperature` and `max_tokens`. The measurement sets
`seed + attempt`. The whole message has to fit `context_size × (1 − safety_margin) − max_tokens`,
or the passage is refused before sending. With 500-token chunks this doesn't happen (FR-011).

**Reply**: a JSON object, alone or with text or code fences around it. One of:

```json
{"question": "…", "correct": "…", "wrong": ["…", "…", "…", "…"], "explanation": "…"}
```

```json
{"skip": "…"}
```

**Read**: the first `{…}` in the reply, parsed as JSON.
- An object with `skip` is a skip.
- Otherwise it has to pass the draft's rules (`data-model.md` § Draft), or it is a refusal of that
  kind.
- `cut_off` is decided before reading: the reply stopped at its length limit.
- `repeated_option` compares the five options casefolded, with spacing collapsed and final
  punctuation removed.
- `wrong_language` joins the question, the options and the explanation, and identifies their
  language with `reply_language`. The draft is refused only when the result is another of the six
  interface languages than the one named.
- `passage_reference` looks at the question and the options, not the explanation, for three
  things:
  - **A word for the passage with a number**, in the six languages: "trecho 3", "passagem 2",
    "passage 4", "excerpt 1", "fragmento 2", "Abschnitt 3", "brano 2".
  - **A word for the passage after a pointer.** In Portuguese: "segundo o", "de acordo com o",
    "conforme o", "no", "neste", "deste" or "o … acima", before "trecho", "passagem", "excerto",
    "fragmento" or "texto". Likewise "according to the passage", "in this excerpt", "the text
    above", "selon le passage", "según el fragmento", "laut dem Abschnitt", "secondo il brano".
  - **"página", "page", "p." with a number**, a section's title from the passage's metadata, and,
    in a whole-book quiz, the chapter's title. A title counts when it is quoted, follows a word for
    a chapter or section ("no capítulo", "na seção sobre"), or comes with its number ("Capítulo 3"):
    titles are mostly subjects, such as "Japão" or "A Revolução Industrial", which a question may
    well ask about.

  "Trecho" also means a stretch of road or railway in Portuguese, so the bare word, without a
  pointer or a number, doesn't count. The lists live with the reader, and grow from what the
  measurement's reading notes.
- `cross_reference` is decided by phrases and by letters:
  - **Phrases**: "all of the above", "none of the above", and their equivalents in Portuguese,
    Spanish, French, German and Italian, such as "todas as anteriores", "nenhuma das anteriores",
    "ninguna de las anteriores", "toutes les réponses", "keine der genannten", "nessuna delle
    precedenti". In German and Italian the phrase counts only before a word for the options or
    answers, since "keine der Kolonien" is an ordinary option. The list lives with the reader, and
    grows from what the measurement finds.
  - **Letters**: an option naming another by letter, such as "A e B", "both A and B" or "option
    C". A standalone capital letter A to E counts only next to a word for "option", "answer",
    "and" or "or", so "vitamin A" or Portuguese's article "a" don't trip it.

## The checker (when `generation.quiz.check.enabled`)

**Sent**: the passage, as above, and the question with its five options lettered A to E, as the
reader will see them. The checker is asked which options the passage supports as an answer to the
question, judging only from the passage.

The parameters are temperature 0, `check.max_tokens`, and `check.reasoning` replacing the
checker's profile setting. The model is `check.model`, or the writer.

**Reply**: a JSON object, alone or with text around it:

```json
{"supported": ["C"]}
```

**Read**:
- `supported` is a list of letters A to E, each counted once; anything else in the list is
  ignored.
- The question is **accepted** only when the list is exactly its key. An empty list, another
  letter, or several letters reject it.
- A reply that can't be read, or has no `supported` list, is asked again once, at temperature 0.5
  with a new seed. If it is still unreadable, the question is accepted, and the event is logged as
  `quiz check unreadable` and counted (research R11).

## The comparator (measurement only)

**Sent**: the passage and the lettered question, asking for the letter of the right answer as
JSON, with the field name only. The parameters are temperature 0 and the writer's `max_tokens`.

**Reply**: a JSON object, alone or with text around it:

```json
{"answer": "C"}
```

**Read**: the first `{…}` in the reply, parsed as JSON. `answer` has to be one letter A to E,
once trimmed and upper-cased. Anything else is unreadable: left out and counted, never scored as
a wrong answer (constitution VI). The letter isn't searched for in free text, which would misread
Portuguese: "A resposta é C" starts with the article "A".

- **Without the passage** (`kind: quiz`), the answer gives `closed_book_correct`.
- **With the passage** (`kind: quiz_check`), it gives `open_book_caught`: the answer differs from
  the key.
