"""What a file holds, what holds a thing, which things are main, and the lines a thing spans.

A node's location is a file and a start line, never a span, so each answer here is built from
start lines and from what holds what. A thing is held by the node its id nests inside
(``Names.holder``), else by the container its first grouping edge names.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from periplus.navigate.listing import first_location, marked_text, place
from periplus.navigate.mapfile import MapIndex, as_text
from periplus.navigate.names import Names
from periplus.report import _escape

__all__ = ["Places", "Thing", "json_thing", "thing", "thing_line"]


@dataclass(frozen=True, slots=True)
class Thing:
    """A row of a set: its id, the short name it prints, type, state, a ``file:line``, its marks
    and whether it is in supporting code."""

    id: str
    name: str
    type: str
    state: str
    location: str | None
    marks: tuple[str, ...] = ()
    supporting: bool = False


def thing(index: MapIndex, names: Names, node_id: str, location: str | None = None) -> Thing:
    """``node_id`` as a row, at ``location``, else at its own first ``file:line``."""
    node = index.nodes[node_id]
    if location is None and (loc := first_location(node)) is not None:
        location = place(loc)
    return Thing(
        node_id,
        names.short(node_id),
        as_text(node["type"]),
        as_text(node["state"]),
        location,
        index.marks(node_id),
        index.supporting(node_id) is not None,
    )


def _file(text: str) -> str:
    return text.removeprefix("./")


class Places:
    """The places of one map's nodes, indexed on first use."""

    def __init__(self, index: MapIndex, names: Names) -> None:
        self.index = index
        self.names = names
        self._files: dict[str, list[tuple[int, str]]] | None = None
        self._outward: dict[str, tuple[str, ...]] = {}
        self._parts: dict[str, int] | None = None

    def in_file(self, file: str) -> list[tuple[int, str]]:
        """Each node located in ``file`` as (its smallest line there, id), by line, then id."""
        if self._files is None:
            lowest: dict[tuple[str, str], int] = {}
            for node_id, node in self.index.nodes.items():
                for loc in node["locations"]:
                    key = (_file(as_text(loc["file"])), node_id)
                    lowest[key] = min(loc["line"], lowest.get(key, loc["line"]))
            files: dict[str, list[tuple[int, str]]] = defaultdict(list)
            for (name, node_id), line in lowest.items():
                files[name].append((line, node_id))
            self._files = {name: sorted(rows) for name, rows in files.items()}
        return self._files.get(_file(file), [])

    def container(self, node_id: str) -> str | None:
        """The to end of ``node_id``'s first edge of a grouping kind, by kind, then to end."""
        ends = sorted(
            (as_text(e["kind"]), as_text(e["to"]))
            for e in self.index.outgoing(node_id)
            if e["kind"] in self.index.grouping
        )
        return ends[0][1] if ends else None

    def outward(self, node_id: str) -> tuple[str, ...]:
        """What holds ``node_id``, innermost first: its holder, else its container, and so on out,
        each once."""
        if node_id not in self._outward:
            chain: list[str] = []
            at = node_id
            while (up := self.names.holder(at) or self.container(at)) is not None:
                if up == node_id or up in chain:
                    break
                chain.append(up)
                at = up
            self._outward[node_id] = tuple(chain)
        return self._outward[node_id]

    def part_types(self) -> dict[str, int]:
        """The part types and how many mapped, located nodes each has.

        A type is a part type when more than half of its mapped, located nodes nest inside
        another node and hold none: a parameter or a call site, read as part of what holds it.
        """
        if self._parts is None:
            held = Counter(
                h for i in self.index.nodes if (h := self.names.holder(as_text(i))) is not None
            )
            total: Counter[str] = Counter()
            leaves: Counter[str] = Counter()
            for node_id, node in self.index.nodes.items():
                if node["state"] != "mapped" or not node["locations"]:
                    continue
                total[node["type"]] += 1
                if not held[node_id] and self.names.holder(node_id) is not None:
                    leaves[node["type"]] += 1
            self._parts = {t: n for t, n in sorted(total.items()) if 2 * leaves[t] > n}
        return self._parts

    def why_not_main(self, node_id: str) -> str | None:
        """``None`` for a main thing; else why not: ``unplaced`` (not mapped, or no location),
        ``supporting`` (in supporting code) or ``part`` (of a part type)."""
        node = self.index.nodes[node_id]
        if node["state"] != "mapped" or not node["locations"]:
            return "unplaced"
        if self.index.supporting(node_id) is not None:
            return "supporting"
        if node["type"] in self.part_types():
            return "part"
        return None

    def span(self, node_id: str) -> tuple[str, int, int | None] | None:
        """The file, first line and last line of the code ``node_id`` stands for, the last line
        ``None`` for the end of the file; ``None`` for a node with no location.

        It runs from the node's first location to the line before the next mapped node of that
        file, on a later line, that ``node_id`` does not hold, at any depth.
        """
        loc = first_location(self.index.nodes[node_id])
        if loc is None:
            return None
        file, first = _file(as_text(loc["file"])), loc["line"]
        for line, other in self.in_file(file):
            if (
                line > first
                and self.index.nodes[other]["state"] == "mapped"
                and node_id not in self.outward(other)
            ):
                return file, first, line - 1
        return file, first, None


def json_thing(row: Thing) -> dict[str, Any]:
    """A row as the navigation schema's ``set_thing``."""
    return {
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "location": row.location,
        "marks": list(row.marks),
        "supporting": row.supporting,
    }


def thing_line(row: Thing, where: str) -> str:
    """A row as text: short name, type, state, ``where`` and its marks."""
    return (
        f"  {_escape(row.name)}  {_escape(row.type)}  {_escape(row.state)}  {_escape(where)}"
        f"{marked_text(row.marks, row.supporting)}"
    )
