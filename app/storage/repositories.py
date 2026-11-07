"""The library's files: original documents, and everything derived from them."""

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunk
from app.ingestion.pipeline import ProcessedDocument

_ORIGINAL_NAMES = {
    DocumentFormat.PDF: "original.pdf",
    DocumentFormat.EPUB: "original.epub",
    DocumentFormat.MARKDOWN: "original.md",
}


class OriginalDocuments:
    """The source of truth: everything else in the library can be rebuilt from these files."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def store(self, source: Path, book_id: str, document_format: DocumentFormat) -> Path:
        """Copy an upload into the library, leaving it complete or not at all.

        Args:
            source: the upload.
            book_id: the book it belongs to.
            document_format: decides the stored name. The upload's own name is never used.

        Returns:
            Where the document is now.
        """
        directory = self._root / book_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / _ORIGINAL_NAMES[document_format]
        partial = target.with_suffix(target.suffix + ".partial")
        shutil.copyfile(source, partial)
        partial.replace(target)
        return target

    def delete(self, book_id: str) -> None:
        shutil.rmtree(self._root / book_id, ignore_errors=True)


class ProcessedDocuments:
    """Each stage's output, per revision of a book.

    A replacement is processed next to the revision in use, so that a failure leaves that
    revision untouched.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _directory(self, book_id: str, revision: int) -> Path:
        return self._root / book_id / f"r{revision}"

    def save(self, book_id: str, revision: int, processed: ProcessedDocument) -> None:
        directory = self._directory(book_id, revision)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "extracted.json").write_text(_to_json(processed.extracted), encoding="utf-8")
        (directory / "normalized.json").write_text(_to_json(processed.normalized), encoding="utf-8")
        with (directory / "chunks.jsonl").open("w", encoding="utf-8") as file:
            for chunk in processed.chunks:
                file.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

    def load_chunks(self, book_id: str, revision: int) -> list[Chunk]:
        path = self._directory(book_id, revision) / "chunks.jsonl"
        with path.open(encoding="utf-8") as file:
            return [Chunk(**json.loads(line)) for line in file]

    def delete_revision(self, book_id: str, revision: int) -> None:
        shutil.rmtree(self._directory(book_id, revision), ignore_errors=True)

    def delete(self, book_id: str) -> None:
        shutil.rmtree(self._root / book_id, ignore_errors=True)


def _to_json(document: object) -> str:
    return json.dumps(asdict(document), ensure_ascii=False, indent=1)
