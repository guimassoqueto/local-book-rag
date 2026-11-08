"""The library's files: original documents, and everything derived from them."""

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunk
from app.ingestion.pipeline import ProcessedDocument

_ORIGINAL_EXTENSIONS = {
    DocumentFormat.PDF: ".pdf",
    DocumentFormat.EPUB: ".epub",
    DocumentFormat.MARKDOWN: ".md",
}
_SOURCE_RECORD = "source.json"
_FIRST_REVISION = 1


@dataclass(frozen=True)
class OriginalRecord:
    """What a stored original says about itself.

    It lives next to the file, because resetting the index clears the catalog but keeps the
    originals: this is what a rebuild reads to bring them back.
    """

    book_id: str
    original_filename: str
    original_path: str
    checksum: str
    format: str
    created_at: str


class OriginalDocuments:
    """The source of truth: everything else in the library can be rebuilt from these files."""

    def __init__(self, root: Path, archive: Path) -> None:
        self._root = root
        self._archive = archive

    def store(self, source: Path, book_id: str, document_format: DocumentFormat, revision: int) -> Path:
        """Copy an upload into the library, leaving it complete or not at all.

        Args:
            source: the upload.
            book_id: the book it belongs to.
            document_format: decides the stored extension. The upload's own name is never used.
            revision: a replacement gets a name of its own, next to the original still in use.

        Returns:
            Where the document is now.
        """
        target = self.path_for(book_id, document_format, revision)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        shutil.copyfile(source, partial)
        partial.replace(target)
        return target

    def path_for(self, book_id: str, document_format: DocumentFormat, revision: int) -> Path:
        suffix = "" if revision == _FIRST_REVISION else f"_r{revision}"
        return self._root / book_id / f"original{suffix}{_ORIGINAL_EXTENSIONS[document_format]}"

    def record(self, record: OriginalRecord) -> None:
        path = self._root / record.book_id / _SOURCE_RECORD
        path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=1), encoding="utf-8")

    def discover(self) -> list[OriginalRecord]:
        """Find every stored original, whether the catalog knows about it or not."""
        records = [
            OriginalRecord(**json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self._root.glob(f"*/{_SOURCE_RECORD}"))
        ]
        return [record for record in records if Path(record.original_path).exists()]

    def delete_file(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def delete(self, book_id: str) -> None:
        shutil.rmtree(self._root / book_id, ignore_errors=True)

    def archive(self, book_id: str) -> None:
        """Move a book's originals out of the library, keeping them on disk."""
        source = self._root / book_id
        if source.exists():
            self._archive.mkdir(parents=True, exist_ok=True)
            shutil.move(source, self._archive / book_id)

    def delete_all(self) -> None:
        for root in (self._root, self._archive):
            _empty_directory(root)


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
        book_directory = self._root / book_id
        if book_directory.exists() and not any(book_directory.iterdir()):
            book_directory.rmdir()

    def delete(self, book_id: str) -> None:
        shutil.rmtree(self._root / book_id, ignore_errors=True)

    def delete_all(self) -> None:
        _empty_directory(self._root)


class SummaryDocuments:
    """Saved chapter summaries, in Markdown, each with a JSON file saying how it was made."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, book_id: str, name: str, text: str, metadata: dict[str, Any]) -> Path:
        directory = self._root / book_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        (directory / f"{name}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def saved(self) -> list[tuple[str, Path]]:
        """List every saved summary, as (book ID, path of its Markdown file)."""
        return [(path.parent.name, path) for path in sorted(self._root.glob("*/*.md"))]

    def metadata(self, path: Path) -> dict[str, Any]:
        """Read how a saved summary was made."""
        return json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))

    def delete(self, book_id: str) -> None:
        shutil.rmtree(self._root / book_id, ignore_errors=True)

    def delete_all(self) -> None:
        _empty_directory(self._root)


def _empty_directory(root: Path) -> None:
    """Delete what is in a directory, keeping the directory and the .gitkeep that tracks it."""
    if not root.exists():
        return
    for entry in root.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        elif entry.name != ".gitkeep":
            entry.unlink(missing_ok=True)


def _to_json(document: object) -> str:
    return json.dumps(asdict(document), ensure_ascii=False, indent=1)
