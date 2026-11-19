r"""Write what Markdown books become: their chapters, sections and chunk texts, in order.

Making the library Markdown-only must leave Markdown reading as it was (specs/005-markdown-only, FR-005 and
SC-002). This script reads the same files on main's code and on the branch's, and the two outputs
must be identical. It leaves out what the feature changes on purpose: the title, the author and
pages. It calls the ingestion pipeline only, and touches neither the library nor the index.

It runs in the app container, which holds the tokenizer and the configuration, from /app:

    docker compose exec app mkdir -p /tmp/devtools
    docker compose cp devtools/dump_chunks.py app:/tmp/devtools/
    docker compose exec -w /app app sh -c \
        'python -I /tmp/devtools/dump_chunks.py --out /tmp/chunks-main /app/benchmarks/books/*.md'
    docker compose cp app:/tmp/chunks-main benchmarks/results/

Then, after the rebuild with the branch's code, the same into /tmp/chunks-branch, and compare each
file with `cmp` (specs/005-markdown-only/quickstart.md, § 3 and § 5).
"""

import argparse
import json
from pathlib import Path
from typing import Any


def dump(processed: Any) -> dict[str, list[dict[str, Any]]]:
    """What a processed book holds, read by name only.

    Main's chunks carry page fields and this branch's don't, so the fields are named one by one
    rather than taken all at once.
    """
    return {
        "chapters": [
            {
                "number": chapter.number,
                "title": chapter.title,
                "sections": [section.title for section in chapter.sections],
            }
            for chapter in processed.structure.chapters
        ],
        "chunks": [
            {
                "chapter_number": chunk.chapter_number,
                "chapter_title": chunk.chapter_title,
                "section_title": chunk.section_title,
                "text": chunk.text,
            }
            for chunk in processed.chunks
        ],
    }


def write(path: Path, content: dict[str, Any]) -> None:
    path.write_text(json.dumps(content, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="the directory to write one JSON file per book into")
    parser.add_argument("books", type=Path, nargs="+", help="the Markdown files")
    arguments = parser.parse_args()

    from app.config.loader import load_settings
    from app.config.settings import EnvironmentSettings
    from app.container import build_pipeline
    from app.ingestion.validation import validate_upload

    settings = load_settings(EnvironmentSettings().config_dir)
    pipeline = build_pipeline(settings)
    arguments.out.mkdir(parents=True, exist_ok=True)
    for path in arguments.books:
        # Positional: the fourth parameter is fallback_title on main and title on the branch.
        processed = pipeline.process(path, validate_upload(path, path.name, 2**30), "book", path.stem)
        content = dump(processed)
        write(arguments.out / f"{path.name}.json", content)
        print(f"{path.name}: {len(content['chapters'])} chapters, {len(content['chunks'])} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
