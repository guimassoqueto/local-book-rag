"""Reads config/ into a validated Settings object."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.config.settings import Settings
from app.errors import ConfigurationError

CONFIG_FILES = ("application.yaml", "models.yaml", "ingestion.yaml", "retrieval.yaml", "generation.yaml")


def load_settings(config_dir: Path) -> Settings:
    """Load and validate every configuration file.

    Args:
        config_dir: the directory holding CONFIG_FILES.

    Raises:
        ConfigurationError: a file is missing or invalid, or two files define the same key.
    """
    merged: dict[str, Any] = {}
    for name in CONFIG_FILES:
        content = _read_mapping(config_dir / name)
        if duplicated := merged.keys() & content.keys():
            raise ConfigurationError(f"{name} repeats keys defined in another file: {sorted(duplicated)}")
        merged.update(content)

    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        problems = "; ".join(_describe(error) for error in exc.errors())
        raise ConfigurationError(f"Invalid configuration in {config_dir}: {problems}") from exc


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(content, dict):
        raise ConfigurationError(f"{path} must contain a mapping")
    return content


def _describe(error: Any) -> str:
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]
