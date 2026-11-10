"""What ``periplus map`` and the navigation commands both need, defined once.

``periplus.map`` imports the engine and ``jsonschema``. A navigation command needs only these
three names, so they live here and it does not load the engine. ``periplus.map`` re-exports them
under the same names.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jsonschema.exceptions import ValidationError

__all__ = ["MAP_SCHEMA", "_DEFAULT_MAP", "_section", "first_error"]

#: The shipped schema the built document is checked against before anything is written.
MAP_SCHEMA = "schema/map.schema.json"

#: The map's default home, under the project root.
_DEFAULT_MAP = "map.json"


def _section(heading: str, rows: Sequence[str]) -> list[str]:
    """A blank line, a heading, and the rows indented under it; ``none`` when there are none."""
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]


def first_error(errors: Iterable[ValidationError]) -> ValidationError | None:
    """The first schema error by path, then message; ``None`` when there are none."""
    return min(
        errors, key=lambda found: (list(map(str, found.absolute_path)), found.message), default=None
    )
