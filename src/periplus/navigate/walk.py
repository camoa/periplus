"""``periplus neighbors`` and ``periplus affected``: the items reached along edges."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    cut,
    footer,
    kind_warnings,
    payload,
    problem_lines,
)
from periplus.navigate.mapfile import (
    STAND_INS,
    MapIndex,
    as_json,
    as_text,
    load_map,
    reading_fields,
)
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import SourceLines, description_line, located, source_line, where
from periplus.report import _escape, _json_problem

__all__ = [
    "RENDERERS",
    "WalkReport",
    "WalkRow",
    "render_json",
    "render_text",
    "run",
    "stand_in_line",
]


@dataclass(frozen=True, slots=True)
class WalkRow:
    """One item reached: its id, type and state, the depth, and the edge kind and end it came by.

    ``location`` is where that edge is written, or the item's own place when the edge has none,
    and ``source`` the line of code there. ``description`` is the item's descriptions entry.
    ``stands_for`` marks an item added because it stands for ``via`` across a realizing edge,
    at ``via``'s depth: a form of a declaration, or with ``in`` the declaration of a form.
    ``supporting`` marks an item in supporting code.
    """

    id: str
    type: str
    state: str
    depth: int
    kind: str
    via: str
    location: str | None = None
    source: str | None = None
    description: str | None = None
    stands_for: bool = False
    supporting: bool = False


@dataclass(frozen=True, slots=True)
class WalkReport:
    """The items reached from ``start``, as a ``Listing`` of rows, with warnings and problems.

    ``more`` counts, for each node, the nodes that stand for it past ``STAND_INS``."""

    start: str = ""
    direction: str = "out"
    rows: Listing[WalkRow] = NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    more: tuple[tuple[str, int], ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def walk(
    index: MapIndex,
    start: str,
    direction: str,
    depth: int,
    kinds: Collection[str],
    more: dict[str, int] | None = None,
) -> list[WalkRow]:
    """Breadth-first rows, each item once at its nearest depth with the first edge that reached it.

    A layer's items are expanded in id order and each item's edges in (kind, other end) order, so
    the edge that wins a tie is the same on every run. The start and each item reached are
    followed by the nodes that stand for them (``MapIndex.stand_ins``) at their own depth, whatever
    ``kinds`` says, but for an item reached along a realizing edge: the other forms of a
    declaration reached from one of them are siblings, not the code behind it. ``more`` gathers
    the count past the cap by node.
    """
    ways = {"out": (("to", index.outgoing),), "in": (("from", index.incoming),)}.get(
        direction, (("to", index.outgoing), ("from", index.incoming))
    )
    seen = {start}
    rows: list[WalkRow] = []

    def stand(item: str, level: int) -> list[str]:
        found, left = index.stand_ins(item, direction == "in")
        if left and more is not None:
            more[item] = left
        added = []
        for other, edge, via in found:
            if other in seen:
                continue
            seen.add(other)
            added.append(other)
            node = index.nodes[other]
            rows.append(
                WalkRow(
                    other,
                    as_text(node["type"]),
                    as_text(node["state"]),
                    level,
                    as_text(edge["kind"]),
                    via,
                    where(edge, node),
                    stands_for=True,
                )
            )
        return added

    frontier = [start, *stand(start, 0)]
    for level in range(1, depth + 1):
        reached: list[str] = []
        for item in sorted(frontier):
            edges = [
                (e, end)
                for end, follow in ways
                for e in follow(item)
                if not kinds or e["kind"] in kinds
            ]
            for edge, end in sorted(edges, key=lambda p: (p[0]["kind"], p[0][p[1]])):
                target = edge[end]
                if target in seen:
                    continue
                seen.add(target)
                reached.append(target)
                # Indexed, not index.node: a dangling end is a damaged map, not an unknown id.
                node = index.nodes[target]
                rows.append(
                    WalkRow(
                        as_text(target),
                        as_text(node["type"]),
                        as_text(node["state"]),
                        level,
                        as_text(edge["kind"]),
                        as_text(edge["from" if end == "to" else "to"]),
                        where(edge, node),
                    )
                )
                if edge["kind"] not in index.realizing:
                    reached += stand(as_text(target), level)
        frontier = reached
    return sorted(rows, key=lambda r: (r.depth, r.id))


def run(
    start: Path,
    env: Mapping[str, str],
    node_id: str,
    direction: str,
    depth: int,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
) -> WalkReport:
    """Walk from ``node_id`` along edges (``out``) or against them (``in``), ``depth`` levels."""
    try:
        index = load_map(start, env, map_path)
        described, problems = node_descriptions(start, map_path)
        with reading_fields(start, map_path):
            node_id, resolved = resolve(index, node_id)
            more: dict[str, int] = {}
            walked = walk(index, node_id, direction, depth, set(kinds), more)
            rows = [replace(r, supporting=index.supporting(r.id) is not None) for r in walked]
            # Supporting code after the rest, each part by depth and id.
            rows.sort(key=lambda row: row.supporting)
            held = {edge["kind"] for edge in index.edges}
    except HarnessError as error:
        return WalkReport(direction=direction, problems=(error.problem(),))
    shown = cut(rows, limit)
    lines = SourceLines(start, map_path)
    items = tuple(
        replace(row, source=lines.at(row.location), description=described.get(row.id))
        for row in shown.items
    )
    shown = replace(shown, items=items)
    return WalkReport(
        node_id,
        direction,
        shown,
        resolved + kind_warnings(kinds, held),
        problems,
        tuple(sorted(more.items())),
    )


def render_text(report: WalkReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    verb = "neighbors" if report.direction == "out" else "affected"
    lines = [f"periplus {verb} {_escape(report.start)}" if report.start else f"periplus {verb}"]
    if report.start:
        lines.append(f"{report.rows.total} items")
    # An affected row's edge points to the item the walk came from.
    toward = "from" if report.direction == "out" else "to"
    supporting = False
    for row in report.rows.items:
        if row.supporting and not supporting:
            supporting = True
            lines.append("  in supporting code:")
        how = f"via {_escape(row.kind)} {toward} {_escape(row.via)}"
        if row.stands_for:
            relation = "realized by" if report.direction == "in" else "realizes"
            how = f"{relation} {_escape(row.via)} by {_escape(row.kind)}"
        lines.append(
            f"  {row.depth}  {_escape(row.id)}  {_escape(row.type)}"
            f"  {_escape(row.state)}  {how}  {_escape(located(row.location))}"
        )
        lines += source_line(row.source)
        lines += description_line(row.description)
    lines += [stand_in_line(node, n) for node, n in report.more]
    note = footer(report.rows)
    if note:
        lines.append(note)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def stand_in_line(node: str, count: int) -> str:
    """The line that counts the nodes standing for ``node`` past the cap."""
    name = _escape(node)
    return f"  +{count} more stand for {name}, past the first {STAND_INS}; see periplus show {name}"


def _json_row(row: WalkRow) -> dict[str, Any]:
    return {
        "stands_for": row.stands_for,
        "supporting": row.supporting,
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "depth": row.depth,
        "kind": row.kind,
        "via": row.via,
        "location": row.location,
        "source": row.source,
        "description": row.description,
    }


def render_json(report: WalkReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        "start": report.start,
        "direction": report.direction,
        "rows": payload(report.rows, _json_row),
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


RENDERERS = {"text": render_text, "json": render_json}
