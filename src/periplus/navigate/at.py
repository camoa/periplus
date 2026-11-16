"""``periplus at``: the mapped thing at a file and line, or nearest above it, and what holds it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import as_json, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places, Thing, json_thing, thing, thing_line
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "At", "AtReport", "listed", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class At:
    """One place asked: the file and line, the mapped line found at or above it (``None`` when
    there is none), the things on that line, innermost first, then what holds them, outward,
    and whether the file holds any node at all."""

    file: str
    line: int
    found: int | None
    things: tuple[Thing, ...]
    containers: tuple[Thing, ...]
    mapped_file: bool


@dataclass(frozen=True, slots=True)
class AtReport:
    """Each place asked, in the order asked."""

    places: tuple[At, ...] = ()
    problems: tuple[Problem, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    places: Sequence[tuple[str, int]],
    map_path: Path | None,
) -> AtReport:
    """For each (file, line): the mapped things on the last line at or above ``line`` that holds
    one, and what holds them, by ``Places.outward``."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            names = Names(index)
            where = Places(index, names)
            found = tuple(_at(index, names, where, file, line) for file, line in places)
    except HarnessError as error:
        return AtReport(problems=(error.problem(),))
    return AtReport(found)


def _at(index: Any, names: Names, where: Places, file: str, line: int) -> At:
    file = file.removeprefix("./")
    rows = where.in_file(file)
    mapped = [(n, i) for n, i in rows if index.nodes[i]["state"] == "mapped" and n <= line]
    if not mapped:
        return At(file, line, None, (), (), bool(rows))
    top = max(n for n, _ in mapped)
    here = sorted((i for n, i in mapped if n == top), key=lambda i: (-len(where.outward(i)), i))
    held: dict[str, None] = {}
    for node_id in here:
        held.update((h, None) for h in where.outward(node_id) if h not in here)
    return At(
        file,
        line,
        top,
        tuple(thing(index, names, i, f"{file}:{top}") for i in here),
        tuple(thing(index, names, h) for h in held),
        True,
    )


def _where(row: Thing, file: str) -> str:
    """``:LINE`` for a row in ``file``, else its ``file:line``, or ``no location``."""
    if row.location is None:
        return "no location"
    path, _, line = row.location.rpartition(":")
    return f":{line}" if path == file else row.location


def render_text(report: AtReport) -> str:
    """For each place: ``FILE:LINE``, with ``nearest above: :N`` when the things are above it,
    then a row a thing on that line, then ``in`` and a row for each thing that holds them."""
    lines = ["periplus at"]
    for asked in report.places:
        head = f"{_escape(asked.file)}:{asked.line}"
        if asked.found is None:
            reason = "at or above this line" if asked.mapped_file else "in this file"
            lines.append(f"{head}  nothing mapped {reason}")
            continue
        near = "" if asked.found == asked.line else f"  nearest above: :{asked.found}"
        lines.append(head + near)
        lines += [thing_line(row, _where(row, asked.file)) for row in asked.things]
        lines += [
            "  in " + thing_line(row, _where(row, asked.file)).removeprefix("  ")
            for row in asked.containers
        ]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: AtReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "at",
            "places": [
                {
                    "file": asked.file,
                    "line": asked.line,
                    "found_line": asked.found,
                    "things": [json_thing(row) for row in asked.things],
                    "containers": [json_thing(row) for row in asked.containers],
                }
                for asked in report.places
            ],
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: AtReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: each place's things, then what holds them."""
    return tuple(dict.fromkeys(row.id for a in report.places for row in (*a.things, *a.containers)))


RENDERERS = {"text": render_text, "json": render_json}
