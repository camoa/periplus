"""``periplus extract``: the things some ids name and the edges among them, as a map file."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, load_document, reading_fields
from periplus.navigate.sets import sub_document
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "ExtractReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class ExtractReport:
    """One extract run: the file written, ``None`` when nothing was, and what it holds."""

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
    start: Path, env: Mapping[str, str], ids: Sequence[str], out: Path, map_path: Path | None
) -> ExtractReport:
    """Write the things ``ids`` name and the edges between two of them to ``out``, in the form
    ``slice --out`` writes. Nothing is walked; an id that names no node writes nothing."""
    try:
        path, document = load_document(start, env, map_path)
        target = start / out
        if target.resolve() == path.resolve():
            message = f"--out {target} is the map being read; choose another file"
            problem = Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)})
            return ExtractReport(problems=(problem,))
        with reading_fields(start, map_path):
            index = MapIndex(document, map_path)
            found, notes = resolve_all(index, ids)
            kept = set(found)
            nodes = [node for node in document["nodes"] if node["id"] in kept]
            edges = [e for e in document["edges"] if e["from"] in kept and e["to"] in kept]
            piece = sub_document(document, nodes, edges, index.parent)
    except HarnessError as error:
        return ExtractReport(problems=(error.problem(),))
    problems = write_document(piece, target)
    if problems:
        return ExtractReport(problems=problems)
    return ExtractReport(str(target), len(nodes), len(edges), tuple(notes))


def render_text(report: ExtractReport) -> str:
    """The file written and what it holds, then the warnings and problems."""
    lines = ["periplus extract"]
    if report.out is not None:
        lines.append(f"wrote {_escape(report.out)}: {report.nodes} nodes, {report.edges} edges")
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: ExtractReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "extract",
            "out": report.out,
            "nodes": report.nodes,
            "edges": report.edges,
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
