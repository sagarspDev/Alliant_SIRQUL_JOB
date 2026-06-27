"""Helpers for writing generated SQL artifacts to disk."""

from __future__ import annotations

from pathlib import Path


def write_sql_file(path: Path, content: str) -> Path:
    """Write SQL content to ``path`` and return the file path."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path

