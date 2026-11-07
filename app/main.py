"""Command line entry point. Gradio and these commands call the same service layer."""

import argparse
import sys
from pathlib import Path

from app.container import Container, build_container
from app.errors import BookRagError
from app.generation.base import TextDelta
from app.generation.question_answering import Answer
from app.retrieval.base import RetrievalFilters
from app.services.reset_service import CONFIRM_RESET_EVERYTHING, CONFIRM_RESET_INDEX
from app.utils.huggingface import local_snapshot
from app.utils.tokenization import create_token_counter


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

    pull = commands.add_parser("pull-models", help="download the configured models")
    pull.add_argument("--all", action="store_true", help="also every model with a profile, for benchmarks")
    pull.set_defaults(handler=_pull_models)

    add_book = commands.add_parser("add-book", help="add a PDF, EPUB or Markdown file to the library")
    add_book.add_argument("path", type=Path, help="the file to add")
    add_book.set_defaults(handler=_add_book)

    list_books = commands.add_parser("list-books", help="list the books in the library")
    list_books.set_defaults(handler=_list_books)

    replace_book = commands.add_parser("replace-book", help="swap a book for a new document, keeping its ID")
    replace_book.add_argument("book", help="a book ID")
    replace_book.add_argument("path", type=Path, help="the new document")
    replace_book.set_defaults(handler=_replace_book)

    remove_book = commands.add_parser("remove-book", help="remove a book and everything derived from it")
    remove_book.add_argument("book", help="a book ID")
    remove_book.add_argument("--archive", action="store_true", help="keep the original in data/archive")
    remove_book.add_argument("--confirm", help="the book's ID again, instead of being asked")
    remove_book.set_defaults(handler=_remove_book)

    reindex_book = commands.add_parser("reindex-book", help="process a book again from its original")
    reindex_book.add_argument("book", help="a book ID")
    reindex_book.set_defaults(handler=_reindex_book)

    reindex_all = commands.add_parser("reindex-all", help="rebuild the index from the original documents")
    reindex_all.add_argument("--regenerate-summaries", action="store_true", help="also write the saved summaries again")
    reindex_all.set_defaults(handler=_reindex_all)

    reset_index = commands.add_parser("reset-index", help="delete everything derived, keeping the originals")
    reset_index.add_argument("--confirm", help=f"'{CONFIRM_RESET_INDEX}', instead of being asked")
    reset_index.set_defaults(handler=_reset_index)

    reset_everything = commands.add_parser("reset-everything", help="delete the library, originals included")
    reset_everything.add_argument("--confirm", help=f"'{CONFIRM_RESET_EVERYTHING}', instead of being asked")
    reset_everything.set_defaults(handler=_reset_everything)

    search = commands.add_parser("search", help="show the passages retrieved for a question")
    search.add_argument("question")
    search.add_argument("--book", action="append", default=[], help="a book ID; repeat for several")
    search.add_argument("--chapter", action="append", type=int, default=[], help="a chapter number; repeat for several")
    search.add_argument("--section", action="append", default=[], help="a section title; repeat for several")
    search.add_argument("--language", action="append", default=[], help="an ISO 639-1 code; repeat for several")
    search.add_argument("--page-start", type=int, help="first page of a range")
    search.add_argument("--page-end", type=int, help="last page of a range")
    search.set_defaults(handler=_search)

    ask = commands.add_parser("ask", help="answer a question from the library")
    ask.add_argument("question")
    ask.add_argument("--book", action="append", default=[], help="a book ID; repeat for several")
    ask.add_argument("--chapter", action="append", type=int, default=[], help="a chapter number; repeat for several")
    ask.add_argument("--language", help="the language to answer in, such as Portuguese")
    ask.set_defaults(handler=_ask)

    summarize = commands.add_parser("summarize", help="summarize a chapter")
    summarize.add_argument("book", help="a book ID")
    summarize.add_argument("chapter", type=int, help="the chapter's number")
    summarize.add_argument("--type", default="standard", help="brief, standard, comprehensive or analytical")
    summarize.add_argument("--language", help="the language to write in, such as Portuguese")
    summarize.add_argument("--save", action="store_true", help="keep the summary in data/summaries")
    summarize.set_defaults(handler=_summarize)

    fetch = commands.add_parser("fetch-benchmark-books", help="download the benchmark's books")
    fetch.set_defaults(handler=_fetch_benchmark_books)

    validate = commands.add_parser("validate-benchmark", help="check the benchmark's questions against its books")
    validate.set_defaults(handler=_validate_benchmark)

    benchmark = commands.add_parser("benchmark", help="run an experiment from benchmarks/experiments")
    benchmark.add_argument("experiment", type=Path, help="the experiment's YAML file")
    benchmark.add_argument("--limit", type=int, help="questions per book and category, for a quick pass")
    benchmark.set_defaults(handler=_benchmark)

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


def _pull_models(container: Container, arguments: argparse.Namespace) -> None:
    settings = container.settings
    models = {settings.llm.model, settings.embedding.model}
    if arguments.all:
        models |= set(settings.llm_profiles) | set(settings.embedding_profiles)
    for model in sorted(models):
        print(f"{model}:")
        last_status = None
        for progress in container.runtime.pull(model):
            if progress.status != last_status:
                print(f"  {progress.status}")
                last_status = progress.status

    print(f"{settings.reranker.model}:\n  {local_snapshot(settings.reranker.model)}")
    for tokenizer in (settings.embedding_profile.tokenizer, settings.llm_profile.tokenizer):
        create_token_counter(tokenizer).count("downloads the tokenizer once")
        print(f"tokenizer {tokenizer.name}: ready")


def _add_book(container: Container, arguments: argparse.Namespace) -> None:
    book = container.books.add_book(arguments.path, arguments.path.name)
    print(f"{book.book_id}: {book.title} ({book.chapter_count} chapters, {book.chunk_count} chunks, {book.status})")


def _replace_book(container: Container, arguments: argparse.Namespace) -> None:
    book = container.books.replace_book(arguments.book, arguments.path, arguments.path.name)
    print(f"{book.book_id}: {book.title} ({book.chapter_count} chapters, {book.chunk_count} chunks, {book.status})")


def _remove_book(container: Container, arguments: argparse.Namespace) -> None:
    confirmation = arguments.confirm or input(f"Type {arguments.book} to remove it: ")
    container.books.remove_book(arguments.book, confirmation, archive_original=arguments.archive)
    print(f"{arguments.book} removed.")


def _reindex_book(container: Container, arguments: argparse.Namespace) -> None:
    book = container.books.reindex_book(arguments.book)
    print(f"{book.book_id}: {book.title} ({book.chapter_count} chapters, {book.chunk_count} chunks, {book.status})")


def _reindex_all(container: Container, arguments: argparse.Namespace) -> None:
    report = container.library.reindex_all(arguments.regenerate_summaries, on_progress=print)
    print(f"Index v{report.index_version} ({report.collection}) is active, built with {report.embedding_model}:")
    print(f"  {report.books} books, {report.chunks} chunks")
    if report.adopted:
        print(f"  brought back from their originals: {', '.join(report.adopted)}")
    if report.failed:
        print(f"  still failing: {', '.join(report.failed)}")
    if report.summaries_regenerated:
        print(f"  {report.summaries_regenerated} summaries written again")
    for failure in report.summaries_failed:
        print(f"  summary not written: {failure}")


def _reset_index(container: Container, arguments: argparse.Namespace) -> None:
    prompt = f"This deletes the index, summaries and catalog, keeping the originals. Type {CONFIRM_RESET_INDEX}: "
    container.resets.reset_index(arguments.confirm or input(prompt))
    print("The index is gone and the originals are kept. reindex-all rebuilds the library from them.")


def _reset_everything(container: Container, arguments: argparse.Namespace) -> None:
    prompt = f"This deletes the whole library, original documents included. Type {CONFIRM_RESET_EVERYTHING}: "
    container.resets.reset_everything(arguments.confirm or input(prompt))
    print("The library is empty.")


def _list_books(container: Container, _: argparse.Namespace) -> None:
    for book in container.books.list_books():
        print(f"{book.book_id}  {book.status:<10} {book.format:<8} {book.chunk_count:>5} chunks  {book.title}")


def _ask(container: Container, arguments: argparse.Namespace) -> None:
    filters = RetrievalFilters(book_ids=tuple(arguments.book), chapter_numbers=tuple(arguments.chapter))
    for event in container.questions.stream(arguments.question, filters, arguments.language):
        if isinstance(event, TextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, Answer):
            _print_sources(event)


def _print_sources(answer: Answer) -> None:
    print("\n\nSources:")
    for citation in answer.citations:
        print(f"  [{citation.number}] {citation.reference}")
    if answer.invented_citations:
        print(f"  The model cited sources that don't exist: {list(answer.invented_citations)}")
    if answer.insufficient_evidence:
        print("  The model found no answer in the sources.")
    stats = answer.generation.stats if answer.generation else None
    timing = f"{answer.total_seconds:.1f}s in total"
    if stats:
        speed = f"{stats.prompt_tokens} + {stats.completion_tokens} tokens at {stats.tokens_per_second:.0f} tokens/s"
        timing = f"{timing}, {speed}"
    print(timing)


def _summarize(container: Container, arguments: argparse.Namespace) -> None:
    summaries = container.summaries
    summary = summaries.summarize(
        arguments.book,
        arguments.chapter,
        arguments.type,
        arguments.language,
        on_progress=lambda message: print(message, file=sys.stderr),
    )
    print(summary.text)
    print(
        f"\n{summary.strategy}: {summary.chunks_covered}/{summary.chunks_total} chunks in {summary.steps} steps, "
        f"{len(summary.citations)} cited, {summary.statements_without_source} statements without a source, "
        f"{summary.total_seconds:.1f}s",
        file=sys.stderr,
    )
    if arguments.save:
        print(f"Saved to {summaries.save(summary)}", file=sys.stderr)


def _fetch_benchmark_books(container: Container, _: argparse.Namespace) -> None:
    from app.evaluation.dataset import fetch_books, load_dataset  # needs nothing the other commands load

    root = container.environment.benchmarks_dir
    for line in fetch_books(load_dataset(root / "datasets"), root / "books"):
        print(line)


def _validate_benchmark(container: Container, _: argparse.Namespace) -> None:
    from app.evaluation.benchmark import BenchmarkRunner  # loads the evaluation stack

    problems = BenchmarkRunner(container.settings, container.environment).validate()
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problems")
    if problems:
        sys.exit(1)


def _benchmark(container: Container, arguments: argparse.Namespace) -> None:
    from app.evaluation.benchmark import BenchmarkRunner, load_experiment  # loads the evaluation stack

    runner = BenchmarkRunner(container.settings, container.environment)
    print(f"Results: {runner.run(load_experiment(arguments.experiment), arguments.limit)}")


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
