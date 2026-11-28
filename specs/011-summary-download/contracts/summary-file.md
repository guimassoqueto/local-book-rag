# Contract: the downloaded summary

What `ChapterSummarizer.summary_file(summary)` returns, and so what the browser saves. `research.md`
R4 and R5 give the reasons.

## The text

UTF-8, `\n` line ends, ending with one newline. Five blocks, each separated from the next by one
blank line:

```markdown
# <book title>, chapter <number>: <chapter title>

<Type> summary[, in <language>].

<the summary's text, as the tab shows it: its ## sections, its [n] citations, its ## References>

---

Written by `<model>`, a local model.
```

| Block       | Rule                                                                                         |
| ----------- | -------------------------------------------------------------------------------------------- |
| Title       | `# ` + book title + `, chapter ` + number, then `: ` + chapter title unless it is empty      |
| Type line   | the type with its first letter capitalized + ` summary`, then `, in <language>` if one was asked, then `.` |
| Summary     | `summary.text.strip()`, character for character                                              |
| Rule        | `---`                                                                                        |
| Note, local | ``Written by `<model>`, a local model.``                                                     |
| Note, cloud | ``Written by `<model>`, a cloud model from <label>.``, `<label>` being `ModelChoices.label_of(provider)` |

- **The titles** go in as the catalog holds them, unescaped.
- **`<model>`** is `summary.model`, the model that wrote the summary as its provider reported it.
  The models that failed before it aren't named.
- **A local or a cloud model** is told by `ModelChoices.is_cloud_provider(summary.provider)`, as
  `summary_report` and `save` tell it.
- **Nothing else** is added: no report, no warning, no date, no token count.

### Examples

A local summary in the book's language:

```markdown
# 02_a_era_das_revolucoes, chapter 4: A paz

Standard summary.

## Visão geral do capítulo

… [1] … [2]

## References

- [1] A paz: “…”
- [2] A paz: “…”

---

Written by `gpt-oss:20b`, a local model.
```

A cloud summary in another language, of a chapter without a title, after a failed attempt:

```markdown
# Quincas Borba, chapter 12

Brief summary, in English.

## Chapter overview

…

---

Written by `claude-sonnet-5-5`, a cloud model from Anthropic.
```

## The name

`<book>_chapter_<NN>_<type>[_<language>].md`, at most 100 characters.

| Part         | Rule                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------ |
| `<book>`     | the book title, lowercased, NFC, each run of characters that are neither alphanumeric (`str.isalnum`) nor combining marks (Unicode category `M`) replaced by `-`, `-` stripped at both ends; the book ID if that leaves nothing |
| `<NN>`       | the chapter number, zero-padded to two digits (`04`, `12`, `123`)                          |
| `<type>`     | the summary type, made safe as `<book>` is                                                 |
| `<language>` | the language asked for, made safe as `<book>` is; absent when none was asked               |
| Length       | at most 100 characters with `.md`; only `<book>` is cut, at its last `-` within what fits if it has one, else at the limit, and never to nothing |

| Book title                         | Chapter | Type     | Language   | Name                                                        |
| ---------------------------------- | ------- | -------- | ---------- | ----------------------------------------------------------- |
| `02_a_era_das_revolucoes`          | 4       | standard | none       | `02-a-era-das-revolucoes_chapter_04_standard.md`            |
| `Memórias Póstumas de Brás Cubas`  | 12      | brief    | English    | `memórias-póstumas-de-brás-cubas_chapter_12_brief_english.md` |
| `What? A "Title": Part 1/2`        | 3       | analytical | none     | `what-a-title-part-1-2_chapter_03_analytical.md`            |
| `!!!` (book `book_007`)            | 1       | standard | none       | `book-007_chapter_01_standard.md`                           |

The last row's ID is made safe too, so its underscore becomes a hyphen and the parts stay
separated by underscores alone.
