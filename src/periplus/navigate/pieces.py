"""``periplus pieces``: a set of ids split into the groups that edges among them join."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.grouping import joined
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import first_location, marked_text, place, problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.source import place_key, places
from periplus.report import _escape, _json_problem, amount

__all__ = ["RENDERERS", "PiecesReport", "Thing", "listed", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class Thing:
    """One id of a piece: the short name it prints, type, state, its own first place, its marks
    and whether it is in supporting code."""

    id: str
    name: str
    type: str
    state: str
    location: str | None
    marks: tuple[str, ...] = ()
    supporting: bool = False


@dataclass(frozen=True, slots=True)
class PiecesReport:
    """The pieces, largest first, then by smallest id; each piece's things by place, then id."""

    pieces: tuple[tuple[Thing, ...], ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], map_path: Path | None
) -> PiecesReport:
    """Split the things ``ids`` name into pieces: two share a piece when an edge of any kind
    joins them directly, or a chain of such edges does through other things of the set."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            things, notes = resolve_all(index, ids)
            top = joined(index, things)
            names = Names(index)
            groups: dict[str, list[Thing]] = {}
            for node_id in things:
                groups.setdefault(top[node_id], []).append(_thing(index, names, node_id))
    except HarnessError as error:
        return PiecesReport(problems=(error.problem(),))
    pieces = sorted(groups.items(), key=lambda p: (-len(p[1]), p[0]))
    return PiecesReport(
        tuple(
            tuple(sorted(group, key=lambda t: (place_key(t.location), t.id))) for _, group in pieces
        ),
        tuple(notes),
    )


def _thing(index: MapIndex, names: Names, node_id: str) -> Thing:
    node = index.nodes[node_id]
    loc = first_location(node)
    return Thing(
        node_id,
        names.short(node_id),
        as_text(node["type"]),
        as_text(node["state"]),
        place(loc) if loc else None,
        index.marks(node_id),
        index.supporting(node_id) is not None,
    )


def render_text(report: PiecesReport) -> str:
    """A count line, then each piece: its header and one row a thing: name, type, state, place."""
    lines = ["periplus pieces"]
    if report.pieces:
        total = sum(len(p) for p in report.pieces)
        lines.append(f"{amount(total, 'thing')} in {amount(len(report.pieces), 'piece')}")
    for number, piece in enumerate(report.pieces, 1):
        lines.append(f"piece {number}: {amount(len(piece), 'thing')}")
        at = places([t.location for t in piece])
        lines += [
            f"  {_escape(t.name)}  {_escape(t.type)}  {_escape(t.state)}  {_escape(where)}"
            f"{marked_text(t.marks, t.supporting)}"
            for t, where in zip(piece, at, strict=True)
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _json_thing(thing: Thing) -> dict[str, Any]:
    return {
        "id": thing.id,
        "type": thing.type,
        "state": thing.state,
        "location": thing.location,
        "marks": list(thing.marks),
        "supporting": thing.supporting,
    }


def render_json(report: PiecesReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "pieces",
            "pieces": [[_json_thing(t) for t in piece] for piece in report.pieces],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: PiecesReport) -> tuple[tuple[str, ...], ...]:
    """The ids ``--ids`` prints, piece by piece, in the text's order."""
    return tuple(tuple(t.id for t in piece) for piece in report.pieces)


RENDERERS = {"text": render_text, "json": render_json}
