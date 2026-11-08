"""Hugging Face models on local disk: the network is only ever used for the first download."""

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

_SKIPPED_FILES = ["*.onnx", "onnx/*", "openvino/*", "*.h5", "*.msgpack"]


def local_snapshot(repository: str) -> str:
    """Return the path of a model's files, downloading them if they are not here yet."""
    try:
        return snapshot_download(repository, local_files_only=True, ignore_patterns=_SKIPPED_FILES)
    except LocalEntryNotFoundError:
        return snapshot_download(repository, ignore_patterns=_SKIPPED_FILES)
