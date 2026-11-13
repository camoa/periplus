"""Where a row's edge is written, and the source line there, read from the project's files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from periplus.navigate.listing import first_location, place
from periplus.navigate.mapfile import _locate
from periplus.report import _escape
from periplus.settings import find_project_root

__all__ = ["SOURCE_WIDTH", "SourceLines", "located", "source_line", "where"]

#: The most characters of a source line a row carries.
SOURCE_WIDTH = 160


def where(edge: Mapping[str, Any] | None, node: Mapping[str, Any]) -> str | None:
    """The edge's first location as ``file:line``, else the node's, else ``None``."""
    loc = (first_location(edge) if edge is not None else None) or first_location(node)
    return place(loc) if loc else None


def located(location: str | None) -> str:
    """A row's location as the text form prints it."""
    return location or "no location"


def source_line(source: str | None) -> list[str]:
    """The text line that shows a row's source line, deeper than any row; none when absent."""
    return [] if source is None else [f"      | {_escape(source)}"]


class SourceLines:
    """The source lines of the project a map was made from, each file read at most once.

    Files are found under the project root above the map file, or beside the map file when no
    project is found, as the descriptions file is.
    """

    def __init__(self, start: Path, map_path: Path | None) -> None:
        """Find the root ``map_path``'s locations are relative to."""
        folder = _locate(start, map_path).absolute().parent
        self._root = find_project_root(folder) or folder
        self._files: dict[str, list[str] | None] = {}

    def at(self, location: str | None) -> str | None:
        """The stripped line at ``file:line``, cut to ``SOURCE_WIDTH``; ``None`` when unreadable.

        The map may be older than the tree, so a missing file or a line past its end is no error.
        """
        if location is None:
            return None
        file, _, number = location.rpartition(":")
        if not number.isdecimal():
            return None
        if file not in self._files:
            try:
                text = (self._root / file).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                self._files[file] = None
            else:
                self._files[file] = text.split("\n")
        lines = self._files[file]
        line = int(number)
        if lines is None or not 1 <= line <= len(lines):
            return None
        return lines[line - 1].strip()[:SOURCE_WIDTH]
