"""Where a row's edge is written, and the source line there, read from the project's files."""

from __future__ import annotations

import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from periplus.engine.source import SourceUnreadable, load_text
from periplus.navigate.listing import first_location, place
from periplus.navigate.mapfile import _locate
from periplus.report import _escape
from periplus.settings import find_project_root

__all__ = [
    "MAX_SOURCE_BYTES",
    "SOURCE_WIDTH",
    "SourceLines",
    "description_line",
    "located",
    "place_key",
    "places",
    "source_line",
    "where",
]

#: The most characters of a source line a row carries.
SOURCE_WIDTH = 160
#: The largest file a source line is read from, in bytes; a larger one shows none.
MAX_SOURCE_BYTES = 5 * 1024 * 1024


def where(edge: Mapping[str, Any] | None, node: Mapping[str, Any]) -> str | None:
    """The edge's first location as ``file:line``, else the node's, else ``None``."""
    loc = (first_location(edge) if edge is not None else None) or first_location(node)
    return place(loc) if loc else None


def located(location: str | None) -> str:
    """A row's location as the text form prints it."""
    return location or "no location"


def place_key(location: str | None) -> tuple[bool, str, int]:
    """A ``file:line`` as a sort key: by file, line 9 before line 10, no location last."""
    file, _, line = (location or "").rpartition(":")
    return location is None, file, int(line) if line.isdecimal() else 0


def places(locations: Sequence[str | None]) -> list[str]:
    """Each row's location as a list of rows prints it: ``file:line``, but ``:line`` when the row
    just above is in the same file, and ``no location`` for none."""
    shown: list[str] = []
    above = None
    for location in locations:
        file, _, line = (location or "").rpartition(":")
        shown.append(f":{line}" if location and file == above else located(location))
        above = file if location else None
    return shown


def source_line(source: str | None) -> list[str]:
    """The text line that shows a row's source line, deeper than any row; none when absent or
    when it holds fewer than two letters, digits or underscores, such as ``{#``."""
    if source is None or sum(c.isalnum() or c == "_" for c in source) < 2:
        return []
    return [f"      | {_escape(source)}"]


def description_line(text: str | None) -> list[str]:
    """The text line that shows a row's node description, marked ``#`` so it is not read as code.

    Only the first line, stripped and cut to ``SOURCE_WIDTH``; none when the node has no entry.
    """
    if text is None:
        return []
    first = text.strip().partition("\n")[0].strip()[:SOURCE_WIDTH]
    return [f"      # {_escape(first)}"]


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
            self._files[file] = self._read(file)
        lines = self._files[file]
        line = int(number)
        if lines is None or not 1 <= line <= len(lines):
            return None
        return lines[line - 1].strip()[:SOURCE_WIDTH]

    def _read(self, file: str) -> list[str] | None:
        """The file's lines as the engine counts them, or ``None`` when it is not a regular file
        of at most ``MAX_SOURCE_BYTES`` whose resolved path stays inside the resolved root.

        A map is a reviewed file a pull request can change, so its locations are not trusted to
        name only project files: an absolute path, a ``..`` or a link out of the root reads nothing.
        """
        try:
            path = (self._root / file).resolve()
            if not path.is_relative_to(self._root.resolve()):
                return None
            status = path.stat()
            if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_SOURCE_BYTES:
                return None
            return load_text(path, file).split("\n")
        except (OSError, SourceUnreadable, ValueError, RuntimeError):
            return None
