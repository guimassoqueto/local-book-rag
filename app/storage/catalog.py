"""The book catalog: the source of truth for which books exist, kept in SQLite outside ChromaDB."""

from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import ForeignKey, String, create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.errors import BookNotFoundError


class BookStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    REINDEXING = "REINDEXING"
    REMOVING = "REMOVING"


@dataclass(frozen=True)
class Book:
    book_id: str
    title: str
    author: str | None
    original_filename: str
    original_path: str
    checksum: str
    format: str
    language: str | None
    chapter_count: int
    chunk_count: int
    embedding_model: str | None
    index_version: int | None
    status: BookStatus
    status_detail: str | None
    revision: int
    created_at: str
    indexed_at: str | None


@dataclass(frozen=True)
class IndexRecord:
    """One version of the vector index, and everything that shaped its vectors.

    Attributes:
        version: increases with every rebuild.
        collection: the ChromaDB collection that holds it.
        embedding_model: the model that produced its vectors.
        embedding_digest: that model's exact weights.
        dimensions: the size of its vectors, as read from the model.
        configuration: the settings it was built with, as JSON.
        fingerprint: tells whether a configuration is compatible with this index.
        active: whether queries use it. Exactly one version is active at a time.
        created_at: when it was created.
    """

    version: int
    collection: str
    embedding_model: str
    embedding_digest: str | None
    dimensions: int
    configuration: str
    fingerprint: str
    active: bool
    created_at: str


class _Base(DeclarativeBase):
    pass


class _BookRow(_Base):
    __tablename__ = "books"

    book_id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    author: Mapped[str | None]
    original_filename: Mapped[str]
    original_path: Mapped[str]
    checksum: Mapped[str] = mapped_column(index=True)
    format: Mapped[str]
    language: Mapped[str | None]
    chapter_count: Mapped[int]
    chunk_count: Mapped[int]
    embedding_model: Mapped[str | None]
    index_version: Mapped[int | None]
    status: Mapped[str] = mapped_column(String)
    status_detail: Mapped[str | None]
    revision: Mapped[int]
    created_at: Mapped[str]
    indexed_at: Mapped[str | None]


class _ChapterRow(_Base):
    """The chapters of a book, for the interface's selectors."""

    __tablename__ = "chapters"

    book_id: Mapped[str] = mapped_column(ForeignKey("books.book_id", ondelete="CASCADE"), primary_key=True)
    number: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]


class _CounterRow(_Base):
    """IDs are never reused: a removed book's ID could otherwise reach another book."""

    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[int]


class _IndexRow(_Base):
    __tablename__ = "indexes"

    version: Mapped[int] = mapped_column(primary_key=True)
    collection: Mapped[str]
    embedding_model: Mapped[str]
    embedding_digest: Mapped[str | None]
    dimensions: Mapped[int]
    configuration: Mapped[str]
    fingerprint: Mapped[str]
    active: Mapped[bool]
    created_at: Mapped[str]


_BOOK_COUNTER = "book"
_INDEX_COUNTER = "index"
_BOOK_FIELDS = tuple(field.name for field in fields(Book))
_INDEX_FIELDS = tuple(field.name for field in fields(IndexRecord))


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _enable_foreign_keys(connection: Any, _: Any) -> None:
    connection.execute("PRAGMA foreign_keys=ON")


def _to_index(row: _IndexRow) -> IndexRecord:
    return IndexRecord(**{name: getattr(row, name) for name in _INDEX_FIELDS})


def _to_book(row: _BookRow) -> Book:
    values = {name: getattr(row, name) for name in _BOOK_FIELDS}
    return Book(**(values | {"status": BookStatus(row.status)}))


class BookCatalog:
    def __init__(self, database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(f"sqlite:///{database}")
        event.listen(self._engine, "connect", _enable_foreign_keys)
        _Base.metadata.create_all(self._engine)

    def next_book_id(self) -> str:
        return f"book_{self._next(_BOOK_COUNTER):03d}"

    def next_index_version(self) -> int:
        return self._next(_INDEX_COUNTER)

    def _next(self, name: str) -> int:
        with Session(self._engine) as session, session.begin():
            counter = session.get(_CounterRow, name)
            if counter is None:
                counter = _CounterRow(name=name, value=0)
                session.add(counter)
            counter.value += 1
            return counter.value

    def add_index(self, record: IndexRecord) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(_IndexRow(**{name: getattr(record, name) for name in _INDEX_FIELDS}))

    def active_index(self) -> IndexRecord | None:
        with Session(self._engine) as session:
            row = session.scalars(select(_IndexRow).where(_IndexRow.active)).first()
            return _to_index(row) if row else None

    def add(self, book: Book) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(_BookRow(**{name: getattr(book, name) for name in _BOOK_FIELDS}))

    def get(self, book_id: str) -> Book:
        with Session(self._engine) as session:
            row = session.get(_BookRow, book_id)
            if row is None:
                raise BookNotFoundError(f"There is no book with ID {book_id}.")
            return _to_book(row)

    def find_by_checksum(self, checksum: str) -> Book | None:
        with Session(self._engine) as session:
            row = session.scalars(select(_BookRow).where(_BookRow.checksum == checksum)).first()
            return _to_book(row) if row else None

    def list_books(self) -> list[Book]:
        with Session(self._engine) as session:
            return [_to_book(row) for row in session.scalars(select(_BookRow).order_by(_BookRow.book_id))]

    def update(self, book_id: str, **changes: Any) -> Book:
        with Session(self._engine) as session, session.begin():
            row = session.get(_BookRow, book_id)
            if row is None:
                raise BookNotFoundError(f"There is no book with ID {book_id}.")
            for name, value in changes.items():
                setattr(row, name, value)
            session.flush()
            return _to_book(row)

    def set_chapters(self, book_id: str, chapters: list[tuple[int, str]]) -> None:
        with Session(self._engine) as session, session.begin():
            for row in session.scalars(select(_ChapterRow).where(_ChapterRow.book_id == book_id)):
                session.delete(row)
            session.flush()
            session.add_all(_ChapterRow(book_id=book_id, number=number, title=title) for number, title in chapters)

    def chapters(self, book_id: str) -> list[tuple[int, str]]:
        with Session(self._engine) as session:
            query = select(_ChapterRow).where(_ChapterRow.book_id == book_id).order_by(_ChapterRow.number)
            return [(row.number, row.title) for row in session.scalars(query)]

    def delete(self, book_id: str) -> None:
        with Session(self._engine) as session, session.begin():
            row = session.get(_BookRow, book_id)
            if row is not None:
                session.delete(row)
