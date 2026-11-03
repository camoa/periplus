"""``periplus types``: the node types and edge kinds a map holds, with counts and parents."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.mapshared import _section
from periplus.navigate.mapfile import as_text, load_map, reading_fields
from periplus.report import _escape, _json_problem

__all__ = [
    "RENDERERS",
    "EdgeKindRow",
    "NodeTypeRow",
    "TypesReport",
    "render_json",
    "render_text",
    "run",
]


@dataclass(frozen=True, slots=True)
class NodeTypeRow:
    """A node type the map holds, how many nodes have it, and the type it descends from."""

    type: str
    count: int
    parent: str | None


@dataclass(frozen=True, slots=True)
class EdgeKindRow:
    """An edge kind the map holds and how many edges have it."""

    kind: str
    count: int


@dataclass(frozen=True, slots=True)
class TypesReport:
    """The node types and edge kinds the map holds, each sorted."""

    node_types: tuple[NodeTypeRow, ...] = ()
    edge_kinds: tuple[EdgeKindRow, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(start: Path, env: Mapping[str, str], map_path: Path | None) -> TypesReport:
    """Count the node types and edge kinds present in the map; a load failure is a problem."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            nodes = Counter(as_text(node["type"]) for node in index.nodes.values())
            edges = Counter(as_text(edge["kind"]) for edge in index.edges)
            return TypesReport(
                tuple(
                    NodeTypeRow(t, n, None if (p := index.parent(t)) is None else as_text(p))
                    for t, n in sorted(nodes.items())
                ),
                tuple(EdgeKindRow(k, n) for k, n in sorted(edges.items())),
            )
    except HarnessError as error:
        return TypesReport((), (), (error.problem(),))


def render_text(report: TypesReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus types"]
    lines += _section(
        "Node types",
        [
            f"{_escape(row.type)}  {row.count}"
            f"  parent: {_escape(row.parent) if row.parent is not None else 'none'}"
            for row in report.node_types
        ],
    )
    lines += _section(
        "Edge kinds", [f"{_escape(row.kind)}  {row.count}" for row in report.edge_kinds]
    )
    lines += _section("Problems", [f"{int(p.code)} {_escape(p.message)}" for p in report.problems])
    return "\n".join(lines) + "\n"


def _json_node_type(row: NodeTypeRow) -> dict[str, Any]:
    return {"type": row.type, "count": row.count, "parent": row.parent}


def _json_edge_kind(row: EdgeKindRow) -> dict[str, Any]:
    return {"kind": row.kind, "count": row.count}


def render_json(report: TypesReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    payload = {
        "node_types": [_json_node_type(row) for row in report.node_types],
        "edge_kinds": [_json_edge_kind(row) for row in report.edge_kinds],
        "problems": [_json_problem(p) for p in report.problems],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
