"""Load a written map and index it in memory.

The map is read whole on every call: a 15 MB map loads in about 0.2 s, so there is no index file
and no cache to go stale.
"""

from __future__ import annotations

import difflib
import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError
from periplus.layout import PROJECT_MARKER
from periplus.settings import find_project_root

__all__ = [
    "MapIndex",
    "MapNotFound",
    "NodeNotFound",
    "NotAMap",
    "as_text",
    "damaged",
    "load_map",
    "reading_fields",
]

#: The shipped schema ``periplus check-map`` checks a map against; ``periplus map`` checks its
#: output with the same one.
MAP_SCHEMA = "schema/map.schema.json"

_DEFAULT_MAP = "map.json"


class MapNotFound(HarnessError):
    """No map file is there to read."""

    code = ExitCode.MAP_NOT_FOUND


class NotAMap(HarnessError):
    """The file is not JSON, or is JSON without a map's outline."""

    code = ExitCode.NOT_A_MAP


class NodeNotFound(HarnessError):
    """An id names no node in the map."""

    code = ExitCode.NODE_NOT_FOUND


class MapIndex:
    """A loaded map with its edges indexed by end and its type hierarchy by parent."""

    def __init__(self, document: Mapping[str, Any]) -> None:
        """Index ``document``, which has the map outline ``load_map`` checks."""
        self.nodes: dict[str, dict[str, Any]] = {n["id"]: n for n in document["nodes"]}
        self._outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in document["edges"]:
            self._outgoing[edge["from"]].append(edge)
            self._incoming[edge["to"]].append(edge)
        self._parents: dict[str, str | None] = {}
        self._subtypes: dict[str, list[str]] = defaultdict(list)
        for row in document.get("type_hierarchy", []):
            self._parents[row["type"]] = row["parent"]
            if row["parent"] is not None:
                self._subtypes[row["parent"]].append(row["type"])
        self.edges: list[dict[str, Any]] = list(document["edges"])

    def outgoing(self, id: str) -> list[dict[str, Any]]:
        """The edges leaving ``id``, in map order."""
        return list(self._outgoing.get(id, ()))

    def incoming(self, id: str) -> list[dict[str, Any]]:
        """The edges arriving at ``id``, in map order."""
        return list(self._incoming.get(id, ()))

    def parent(self, type: str) -> str | None:
        """The type ``type`` descends from, or ``None`` for a root or an unlisted type."""
        return self._parents.get(type)

    def subtypes(self, type: str) -> list[str]:
        """The types whose parent is ``type``, sorted."""
        return sorted(self._subtypes.get(type, ()))

    def node(self, id: str) -> dict[str, Any]:
        """The node with this id, or ``NodeNotFound`` naming the id and the closest ids."""
        found = self.nodes.get(id)
        if found is not None:
            return found
        close = difflib.get_close_matches(id, sorted(self.nodes), n=5)
        hint = f"; close ids: {', '.join(close)}" if close else ""
        raise NodeNotFound(
            f"no node has the id {id!r}{hint}; periplus find searches the ids",
            {"id": id},
        )


def load_map(start: Path, env: Mapping[str, str], map_path: Path | None) -> MapIndex:
    """Read the map at ``map_path``, or at ``<root>/.periplus/map.json`` when none is given.

    Only the outline is checked: the full schema check took 3.1 s of a 3.8 s run on a real site's
    map, and ``periplus check-map`` runs it. ``env`` is accepted so every navigation entry point
    has one signature; the map's place does not depend on it.
    """
    path, document = _read(start, map_path)
    version = document.get("periplus_map_version") if isinstance(document, dict) else None
    if not (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version >= 0
        and isinstance(document.get("nodes"), list)
        and isinstance(document.get("edges"), list)
    ):
        raise NotAMap(
            f"{path} is not a periplus map: it needs periplus_map_version, nodes and edges",
            {"path": str(path)},
        )
    try:
        return MapIndex(document)
    except (KeyError, TypeError) as error:
        raise NotAMap(
            f"{path} is not a periplus map: a node, edge or type_hierarchy row is malformed "
            f"({type(error).__name__}: {error})",
            {"path": str(path)},
        ) from error


def damaged(start: Path, map_path: Path | None, error: Exception) -> NotAMap:
    """The ``NotAMap`` for a field a navigation command read from a map ``load_map`` accepted."""
    path = _locate(start, map_path)
    return NotAMap(
        f"{path} is damaged: a node or edge field is missing or malformed "
        f"({type(error).__name__}: {error}); run periplus check-map for the exact error",
        {"path": str(path)},
    )


@contextmanager
def reading_fields(start: Path, map_path: Path | None) -> Iterator[None]:
    """Raise ``damaged``'s ``NotAMap`` for what a missing or malformed map field raises inside.

    ``load_map`` checks only the outline, so a command building its report from node and edge
    fields wraps that building in this, and nothing else.
    """
    try:
        yield
    except (KeyError, TypeError, AttributeError) as error:
        raise damaged(start, map_path, error) from error


def as_text(value: Any) -> str:
    """``value``, which a report prints as text; a ``TypeError`` when the map holds a non-string."""
    if not isinstance(value, str):
        raise TypeError(f"expected a string, got {type(value).__name__} {value!r}")
    return value


def _locate(start: Path, map_path: Path | None) -> Path:
    """``map_path``, or the default map under the project root above ``start``."""
    if map_path is not None:
        return map_path
    root = find_project_root(start)
    if root is None:
        raise MapNotFound(
            f"no {PROJECT_MARKER}/ directory at or above {start}; "
            "run periplus map first or pass --map",
            {"start": str(start)},
        )
    return root / PROJECT_MARKER / _DEFAULT_MAP


def _read(start: Path, map_path: Path | None) -> tuple[Path, Any]:
    """Find the map as ``load_map`` does and parse it as JSON, unchecked."""
    map_path = _locate(start, map_path)
    if not map_path.is_file():
        raise MapNotFound(f"no map at {map_path}; run periplus map", {"path": str(map_path)})
    try:
        return map_path, json.loads(map_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise MapNotFound(f"cannot read {map_path}: {error}", {"path": str(map_path)}) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NotAMap(f"{map_path} is not JSON: {error}", {"path": str(map_path)}) from error
