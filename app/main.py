"""Command line entry point. Gradio and these commands call the same service layer."""

import argparse
import sys
from pathlib import Path

from app.container import Container, build_container
from app.errors import BookRagError
from app.retrieval.base import RetrievalFilters
from app.utils.huggingface import local_snapshot


def main(argv: list[str] | None = None) -> None:
    arguments = _build_parser().parse_args(argv)
    try:
        arguments.handler(build_container(console_logs=arguments.handler is _serve), arguments)
    except BookRagError as exc:
        sys.exit(f"error: {exc}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-rag", description="Local book RAG research platform")
    commands = parser.add_subparsers(required=True, metavar="command")

    serve = commands.add_parser("serve", help="start the Gradio interface")
    serve.set_defaults(handler=_serve)

    doctor = commands.add_parser("doctor", help="check the services, models and GPU")
    doctor.add_argument("--inference", action="store_true", help="also run the models, which loads them into memory")
    doctor.set_defaults(handler=_doctor)

    pull = commands.add_parser("pull-models", help="download the configured models into Ollama")
    pull.set_defaults(handler=_pull_models)

    add_book = commands.add_parser("add-book", help="add a PDF, EPUB or Markdown file to the library")
    add_book.add_argument("path", type=Path, help="the file to add")
    add_book.set_defaults(handler=_add_book)

    list_books = commands.add_parser("list-books", help="list the books in the library")
    list_books.set_defaults(handler=_list_books)

    search = commands.add_parser("search", help="show the passages retrieved for a question")
    search.add_argument("question")
    search.add_argument("--book", action="append", default=[], help="a book ID; repeat for several")
    search.add_argument("--chapter", action="append", type=int, default=[], help="a chapter number; repeat for several")
    search.add_argument("--section", action="append", default=[], help="a section title; repeat for several")
    search.add_argument("--language", action="append", default=[], help="an ISO 639-1 code; repeat for several")
    search.add_argument("--page-start", type=int, help="first page of a range")
    search.add_argument("--page-end", type=int, help="last page of a range")
    search.set_defaults(handler=_search)

    return parser


def _serve(container: Container, _: argparse.Namespace) -> None:
    from app.interface.gradio_app import serve  # gradio is slow to import, and only this command needs it

    serve(container)


def _doctor(container: Container, arguments: argparse.Namespace) -> None:
    results = container.health.run(inference=arguments.inference)
    for result in results:
        print(f"[{' ok ' if result.ok else 'FAIL'}] {result.name:<20} {result.detail}")
    if not all(result.ok for result in results):
        sys.exit(1)


def _pull_models(container: Container, _: argparse.Namespace) -> None:
    settings = container.settings
    for model in (settings.llm.model, settings.embedding.model):
        print(f"{model}:")
        last_status = None
        for progress in container.runtime.pull(model):
            if progress.status != last_status:
                print(f"  {progress.status}")
                last_status = progress.status

    tokenizer = settings.embedding_profile.tokenizer
    repositories = [settings.reranker.model] + ([tokenizer.name] if tokenizer.kind == "huggingface" else [])
    for repository in repositories:
        print(f"{repository}:\n  {local_snapshot(repository)}")


def _add_book(container: Container, arguments: argparse.Namespace) -> None:
    book = container.books.add_book(arguments.path, arguments.path.name)
    print(f"{book.book_id}: {book.title} ({book.chapter_count} chapters, {book.chunk_count} chunks, {book.status})")


def _list_books(container: Container, _: argparse.Namespace) -> None:
    for book in container.books.list_books():
        print(f"{book.book_id}  {book.status:<10} {book.format:<8} {book.chunk_count:>5} chunks  {book.title}")


def _search(container: Container, arguments: argparse.Namespace) -> None:
    filters = RetrievalFilters(
        book_ids=tuple(arguments.book),
        chapter_numbers=tuple(arguments.chapter),
        section_titles=tuple(arguments.section),
        languages=tuple(arguments.language),
        page_start=arguments.page_start,
        page_end=arguments.page_end,
    )
    result = container.retrieval.search(arguments.question, filters)
    print(f"{len(result.candidates)} candidates in {result.retrieval_seconds:.2f}s, ", end="")
    print(f"reranked in {result.rerank_seconds:.2f}s")
    for passage in result.passages:
        chunk = passage.chunk
        pages = f"p. {chunk.page_start}-{chunk.page_end}" if chunk.page_start else "no pages"
        scores = {"dense": passage.dense_score, "bm25": passage.bm25_score, "rerank": passage.rerank_score}
        shown = " ".join(f"{name}={value:.3f}" for name, value in scores.items() if value is not None)
        print(f"\n{chunk.chunk_id} ({chunk.chapter_title}, {pages}) {shown}")
        print(f"  {chunk.text[:200]!r}")


if __name__ == "__main__":
    main()
