"""``periplus types``: the node types and edge kinds a map holds, with counts and parents."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.mapfile import as_text, load_map, reading_fields
from periplus.report import _escape

__all__ = ["RENDERERS", "TypesReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class TypesReport:
    """Node types as (type, count, parent) and edge kinds as (kind, count), each sorted."""

    node_types: tuple[tuple[str, int, str | None], ...] = ()
    edge_kinds: tuple[tuple[str, int], ...] = ()
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
                    (t, n, None if (p := index.parent(t)) is None else as_text(p))
                    for t, n in sorted(nodes.items())
                ),
                tuple(sorted(edges.items())),
            )
    except HarnessError as error:
        return TypesReport((), (), (error.problem(),))


def _section(heading: str, rows: list[str]) -> list[str]:
    """A blank line, a heading, and the rows indented under it; ``none`` when there are none."""
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]


def render_text(report: TypesReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus types"]
    lines += _section(
        "Node types",
        [
            f"{_escape(t)}  {n}  parent: {_escape(p) if p is not None else 'none'}"
            for t, n, p in report.node_types
        ],
    )
    lines += _section("Edge kinds", [f"{_escape(k)}  {n}" for k, n in report.edge_kinds])
    lines += _section("Problems", [f"{int(p.code)} {_escape(p.message)}" for p in report.problems])
    return "\n".join(lines) + "\n"


def render_json(report: TypesReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    payload = {
        "node_types": [{"type": t, "count": n, "parent": p} for t, n, p in report.node_types],
        "edge_kinds": [{"kind": k, "count": n} for k, n in report.edge_kinds],
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
