"""Command line entry point. Gradio and these commands call the same service layer."""

import argparse
import sys

from app.container import Container, build_container
from app.errors import BookRagError


def main(argv: list[str] | None = None) -> None:
    arguments = _build_parser().parse_args(argv)
    try:
        arguments.handler(build_container(), arguments)
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


if __name__ == "__main__":
    main()
