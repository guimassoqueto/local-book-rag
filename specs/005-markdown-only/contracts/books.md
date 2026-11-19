# Contract: adding and reading a book

What the owner sees, and what the services guarantee, when a book is added or replaced. The tab
and the commands call the same methods, `BookService.add_book` and `replace_book`, and show what
they return or raise (principle IV).

## Accepted files

| Extension (compared without case) | Outcome |
| --------------------------------- | ------- |
| `.md`, `.markdown` | read as Markdown, after the checks below |
| `.pdf` | refused: "This is a PDF. Books are Markdown files: convert it to Markdown first, with MarkItDown for example, and add the .md file." |
| `.epub` | refused: the same, with "This is an EPUB." |
| anything else | refused: "Unsupported file type '.docx'. Books are Markdown files: .markdown, .md." |

The Markdown checks are today's, with today's messages:
- the file doesn't exist (a path typed at the command line);
- it is empty;
- it is over the upload limit (512 MB);
- it holds a null byte, so it is binary data;
- it isn't UTF-8.

A PDF or EPUB renamed `.md` fails the last two.

**When.** The checks run first inside `add_book` and `replace_book`, under the library lock and
before anything else: the duplicate check, the index check, the journal entry, storing. A refused
file leaves the catalog, the journal, the index, the originals and the processed files as they
were, and a book being replaced keeps its revision (SC-003). The library being busy is reported
as today, before the file is read.

## What is read from a Markdown file

| Book field | Comes from |
| ---------- | ---------- |
| title | the stem of the name the file arrived as: `01_historia_economica_global.md` becomes `01_historia_economica_global`. Never the front matter, never a heading. A replacement under another name retitles the book |
| author | nothing: always empty |
| language | front matter `language`, else `lang`, else detected from the text. Refused when it isn't in `languages.supported` |
| chapters, sections | the headings, by today's rules: one outermost heading is taken for the book's title and its children for chapters; a heading saying "Chapter N" outranks its depth when depth clearly got it wrong; parts are seen through; text before the first chapter is chapter 0, "Front matter" |
| a book without headings | one chapter, titled with the book's title |
| chunks | today's chunker and settings, minus pages |

The front matter, a YAML block between `---` lines at the top, is removed from the text whatever
it holds. Images add no text.

The same file and configuration give the same chapters, sections and chunk texts as on `main`
(SC-002, `research.md` R12).

## The Library tab

- **The pickers.** "Add a book" and "Change a book" each have a file picker labelled "Markdown
  book (.md, .markdown)", whose dialog offers only those types.
- **A note under "Add a book".** It says that books are Markdown files, that a PDF or an EPUB is
  converted to Markdown first, with MarkItDown for example, and that the file's name becomes the
  book's title.
- **A PDF or EPUB forced past the dialog**, by dropping it or choosing "all files", is refused by
  Gradio before the service runs. Gradio's message names the accepted types (`research.md`, R3).
  Nothing is stored.
- **The book list** keeps its columns. Author stays, empty, and Format reads `markdown`.

## The commands

```text
book-rag add-book PATH              help: "add a Markdown book (.md, .markdown) to the library"
book-rag replace-book BOOK PATH     help: "swap a book for a new Markdown file, keeping its ID"
```

The arguments stay as they are. A refusal prints the service's message as an error, as today, and
exits non-zero. The title is the stem of `PATH`'s own name. So a book copied into the container
keeps its name on the way: `docker compose cp "01_historia_economica_global.md" app:/tmp/` and not
`app:/tmp/book.md`, which would title it `book`. The README says so.

## Progress

An addition, a replacement or a reindex reports:
1. storing;
2. "Extracting the text", without a count, with a moving bar;
3. "Preparing the chunks";
4. "Embedding the chunks", counted;
5. saving, and for a replacement, the swap.

The stage lines in the log have no `ocr` field (FR-011).
