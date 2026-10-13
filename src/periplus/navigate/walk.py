"""``periplus neighbors`` and ``periplus affected``: the items reached along edges."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import Listing, cut, footer, payload
from periplus.navigate.mapfile import MapIndex, as_text, load_map, reading_fields
from periplus.report import _escape

__all__ = ["RENDERERS", "WalkReport", "render_json", "render_text", "run"]

_NONE = Listing((), 0, 0, False)


@dataclass(frozen=True, slots=True)
class WalkReport:
    """The items reached from ``start``, as a ``Listing`` of rows, with warnings and problems."""

    start: str = ""
    direction: str = "out"
    rows: Listing = _NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def walk(
    index: MapIndex, start: str, direction: str, depth: int, kinds: Collection[str]
) -> list[dict[str, Any]]:
    """Breadth-first rows, each item once at its nearest depth with the first edge that reached it.

    A layer's items are expanded in id order and each item's edges in (kind, other end) order, so
    the edge that wins a tie is the same on every run.
    """
    follow, end = (index.outgoing, "to") if direction == "out" else (index.incoming, "from")
    other = "from" if end == "to" else "to"
    seen = {start}
    frontier = [start]
    rows: list[dict[str, Any]] = []
    for level in range(1, depth + 1):
        reached: list[str] = []
        for item in sorted(frontier):
            edges = [e for e in follow(item) if not kinds or e["kind"] in kinds]
            for edge in sorted(edges, key=lambda e: (e["kind"], e[end])):
                target = edge[end]
                if target in seen:
                    continue
                seen.add(target)
                reached.append(target)
                # Indexed, not index.node: a dangling end is a damaged map, not an unknown id.
                node = index.nodes[target]
                rows.append(
                    {
                        "id": as_text(target),
                        "type": as_text(node["type"]),
                        "state": as_text(node["state"]),
                        "depth": level,
                        "kind": as_text(edge["kind"]),
                        "via": as_text(edge[other]),
                    }
                )
        frontier = reached
    return sorted(rows, key=lambda r: (r["depth"], r["id"]))


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
    warnings = tuple(
        f"the map holds no edge of kind {kind!r}" for kind in sorted(set(kinds) - held)
    )
    return WalkReport(node_id, direction, cut(rows, limit), warnings)


def render_text(report: WalkReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    verb = "neighbors" if report.direction == "out" else "affected"
    lines = [f"periplus {verb} {_escape(report.start)}" if report.start else f"periplus {verb}"]
    if report.start:
        lines.append(f"{report.rows.total} items")
    for row in report.rows.items:
        lines.append(
            f"  {row['depth']}  {_escape(row['id'])}  {_escape(row['type'])}"
            f"  {_escape(row['state'])}"
            f"  via {_escape(row['kind'])} from {_escape(row['via'])}"
        )
    note = footer(report.rows)
    if note:
        lines.append(note)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def render_json(report: WalkReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        "start": report.start,
        "direction": report.direction,
        "rows": payload(report.rows),
        "warnings": list(report.warnings),
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
