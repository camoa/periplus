"""What ``periplus map`` and the navigation commands both need, defined once.

``periplus.map`` imports the engine and ``jsonschema``. A navigation command needs only these
three names, so they live here and it does not load the engine. ``periplus.map`` re-exports them
under the same names.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["MAP_SCHEMA", "_DEFAULT_MAP", "_section"]

#: The shipped schema the built document is checked against before anything is written.
MAP_SCHEMA = "schema/map.schema.json"

#: The map's default home, under the project root.
_DEFAULT_MAP = "map.json"


def _section(heading: str, rows: Sequence[str]) -> list[str]:
    """A blank line, a heading, and the rows indented under it; ``none`` when there are none."""
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]
