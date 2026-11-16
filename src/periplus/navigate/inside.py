"""``periplus in``: the things the map holds in each file, in line order."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate import find
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import as_json, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places, Thing, json_thing, thing, thing_line
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "InReport", "listed", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class InReport:
    """Each file asked, in the order asked, with its things by line, then id."""

    files: tuple[tuple[str, tuple[Thing, ...]], ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    paths: Sequence[str],
    types: Collection[str],
    map_path: Path | None,
) -> InReport:
    """The things located in each of ``paths``, each at its smallest line there; ``types`` keeps
    those types and their subtypes. A leading ``./`` is taken off a path."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            wanted, _, warnings = find.narrowing(index, types, ())
            names = Names(index)
            places = Places(index, names)
            held = []
            for path in dict.fromkeys(p.removeprefix("./") for p in paths):
                rows = tuple(
                    thing(index, names, node_id, f"{path}:{line}")
                    for line, node_id in places.in_file(path)
                    if wanted is None or index.nodes[node_id]["type"] in wanted
                )
                held.append((path, rows))
    except HarnessError as error:
        return InReport(problems=(error.problem(),))
    return InReport(tuple(held), tuple(warnings))


def render_text(report: InReport) -> str:
    """For each file: ``FILE: N things``, then one row a thing with ``:LINE``; ``FILE: nothing
    mapped`` for a file that holds none."""
    lines = ["periplus in"]
    for path, rows in report.files:
        if not rows:
            lines.append(f"{_escape(path)}: nothing mapped")
            continue
        lines.append(f"{_escape(path)}: {len(rows)} thing{'' if len(rows) == 1 else 's'}")
        lines += [thing_line(row, ":" + (row.location or "").rpartition(":")[2]) for row in rows]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: InReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "in",
            "files": [
                {"file": path, "things": [json_thing(row) for row in rows]}
                for path, rows in report.files
            ],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: InReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: every thing, file by file, in the text's order."""
    return tuple(dict.fromkeys(row.id for _, rows in report.files for row in rows))


RENDERERS = {"text": render_text, "json": render_json}
