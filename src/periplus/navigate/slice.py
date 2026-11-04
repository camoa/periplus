"""``periplus slice``: cut the items around a start set out of a map into a map file of its own."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.engine.emit import counts, hierarchy
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate.ids import resolve
from periplus.navigate.listing import first_location, kind_warnings
from periplus.navigate.mapfile import MapIndex, NodeNotFound, load_document, reading_fields
from periplus.navigate.walk import walk
from periplus.report import _escape

__all__ = ["RENDERERS", "SliceReport", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class SliceReport:
    """One slice run. ``out`` is ``None`` when nothing was written."""

    out: str | None = None
    nodes: int = 0
    edges: int = 0
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    ids: Collection[str],
    prefix: str | None,
    direction: str,
    depth: int,
    kinds: Collection[str],
    limit: int,
    out: Path,
    map_path: Path | None,
) -> SliceReport:
    """Write ``ids``, the nodes under ``prefix`` and what they reach to ``out``.

    ``direction`` is ``out``, ``in`` or ``both``. A limit of 0 keeps every item.
    """
    try:
        if not ids and prefix is None:
            return SliceReport(
                problems=(Problem(ExitCode.USAGE, "give at least one id or a path prefix", {}),)
            )
        path, document = load_document(start, env, map_path)
        target = start / out
        if target.resolve() == path.resolve():
            message = f"--out {target} is the map being read; choose another file"
            return SliceReport(
                problems=(Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)}),)
            )
        with reading_fields(start, map_path):
            index = MapIndex(document)
            starts = {index.node(resolve(index, text))["id"] for text in ids}
            if prefix is not None:
                under = {
                    node["id"]
                    for node in document["nodes"]
                    if (loc := first_location(node)) and loc["file"].startswith(prefix)
                }
                if not under:
                    raise NodeNotFound(f"no node's first location starts with {prefix!r}", {})
                starts |= under
            kept = set(starts)
            for item in sorted(starts):
                for way in ("out", "in") if direction == "both" else (direction,):
                    kept.update(row.id for row in walk(index, item, way, depth, set(kinds)))
            held = {edge["kind"] for edge in index.edges}
            if limit and len(kept) > limit:
                message = f"the slice reaches {len(kept)} items, over the limit of {limit}"
                return SliceReport(problems=(Problem(ExitCode.SLICE_TOO_LARGE, message, {}),))
            nodes = [node for node in document["nodes"] if node["id"] in kept]
            edges = [e for e in document["edges"] if e["from"] in kept and e["to"] in kept]
            piece: dict[str, Any] = {
                **document,
                "counts": counts(nodes, edges),
                "nodes": nodes,
                "edges": edges,
                "type_hierarchy": hierarchy({str(node["type"]) for node in nodes}, index.parent),
            }
    except HarnessError as error:
        return SliceReport(problems=(error.problem(),))
    problems = write_document(piece, target)
    if problems:
        return SliceReport(problems=problems)
    return SliceReport(str(target), len(nodes), len(edges), kind_warnings(kinds, held))


def render_text(report: SliceReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus slice"]
    if report.out is not None:
        lines.append(f"wrote {_escape(report.out)}: {report.nodes} nodes, {report.edges} edges")
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


RENDERERS = {"text": render_text}
