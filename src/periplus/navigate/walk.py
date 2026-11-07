"""``periplus neighbors`` and ``periplus affected``: the items reached along edges."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import NONE, Listing, cut, footer, kind_warnings, payload
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "WalkReport", "WalkRow", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class WalkRow:
    """One item reached: its id, type and state, the depth, and the edge kind and end it came by."""

    id: str
    type: str
    state: str
    depth: int
    kind: str
    via: str


@dataclass(frozen=True, slots=True)
class WalkReport:
    """The items reached from ``start``, as a ``Listing`` of rows, with warnings and problems."""

    start: str = ""
    direction: str = "out"
    rows: Listing[WalkRow] = NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def walk(
    index: MapIndex, start: str, direction: str, depth: int, kinds: Collection[str]
) -> list[WalkRow]:
    """Breadth-first rows, each item once at its nearest depth with the first edge that reached it.

    A layer's items are expanded in id order and each item's edges in (kind, other end) order, so
    the edge that wins a tie is the same on every run.
    """
    ways = {"out": (("to", index.outgoing),), "in": (("from", index.incoming),)}.get(
        direction, (("to", index.outgoing), ("from", index.incoming))
    )
    seen = {start}
    frontier = [start]
    rows: list[WalkRow] = []
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
                    )
                )
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
        node_id = resolve(index, node_id)
        with reading_fields(start, map_path):
            index.node(node_id)
            rows = walk(index, node_id, direction, depth, set(kinds))
            held = {edge["kind"] for edge in index.edges}
    except HarnessError as error:
        return WalkReport(problems=(error.problem(),))
    warnings = kind_warnings(kinds, held)
    return WalkReport(node_id, direction, cut(rows, limit), warnings)


def render_text(report: WalkReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    verb = "neighbors" if report.direction == "out" else "affected"
    lines = [f"periplus {verb} {_escape(report.start)}" if report.start else f"periplus {verb}"]
    if report.start:
        lines.append(f"{report.rows.total} items")
    # An affected row's edge points to the item the walk came from.
    toward = "from" if report.direction == "out" else "to"
    for row in report.rows.items:
        lines.append(
            f"  {row.depth}  {_escape(row.id)}  {_escape(row.type)}"
            f"  {_escape(row.state)}"
            f"  via {_escape(row.kind)} {toward} {_escape(row.via)}"
        )
    note = footer(report.rows)
    if note:
        lines.append(note)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def _json_row(row: WalkRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "depth": row.depth,
        "kind": row.kind,
        "via": row.via,
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
