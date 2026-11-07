"""File checksums, which are what makes two uploads the same book."""

import hashlib
from pathlib import Path

_READ_SIZE = 1024 * 1024


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(_READ_SIZE):
            digest.update(block)
    return digest.hexdigest()
