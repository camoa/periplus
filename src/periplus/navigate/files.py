"""``periplus files``: the files that hold a set of things, each with its count, most first."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import as_json, as_text, load_map, reading_fields
from periplus.report import _escape, _json_problem, amount

__all__ = ["RENDERERS", "FilesReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class FilesReport:
    """How many things the ids name, each file with how many of them it holds, most first, then
    by file, and how many have no location."""

    things: int = 0
    files: tuple[tuple[str, int], ...] = ()
    unplaced: int = 0
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], map_path: Path | None
) -> FilesReport:
    """Count the things ``ids`` name by the files of their locations; a thing with locations in
    two files counts in each."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            things, notes = resolve_all(index, ids)
            counted: Counter[str] = Counter()
            unplaced = 0
            for node_id in things:
                locations = index.nodes[node_id]["locations"]
                held = {as_text(loc["file"]).removeprefix("./") for loc in locations}
                counted.update(held)
                unplaced += not held
    except HarnessError as error:
        return FilesReport(problems=(error.problem(),))
    ranked = tuple(sorted(counted.items(), key=lambda p: (-p[1], p[0])))
    return FilesReport(len(things), ranked, unplaced, tuple(notes))


def render_text(report: FilesReport) -> str:
    """``N things in M files``, one row a file, ``count  file``, then ``no location: N``."""
    lines = ["periplus files"]
    if not report.problems:
        lines.append(f"{amount(report.things, 'thing')} in {amount(len(report.files), 'file')}")
        lines += [f"  {n}  {_escape(file)}" for file, n in report.files]
        lines += [f"no location: {report.unplaced}"] if report.unplaced else []
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: FilesReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "files",
            "things": report.things,
            "files": [{"file": file, "count": n} for file, n in report.files],
            "no_location": report.unplaced,
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
