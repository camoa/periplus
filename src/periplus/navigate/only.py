"""``periplus only``: the things the ids set off that nothing else sets off."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import first_location, marked_text, place, problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.source import places
from periplus.navigate.walk import CauseRow, cause_walk, head_line, summary, ways
from periplus.report import _escape, _json_problem

__all__ = [
    "RENDERERS",
    "OnlyReport",
    "Thing",
    "listed",
    "only_through",
    "render_json",
    "render_text",
    "run",
]


@dataclass(frozen=True, slots=True)
class Thing:
    """A thing reached only through the starts: its row of the walk, the short name it prints,
    its own first ``file:line``, its marks and whether it is in supporting code."""

    row: CauseRow
    name: str
    location: str | None
    marks: tuple[str, ...] = ()
    supporting: bool = False


@dataclass(frozen=True, slots=True)
class OnlyReport:
    """The starts, every row their walk by cause sets off, and the things among them reached
    only through the starts."""

    starts: tuple[str, ...] = ()
    walked: tuple[CauseRow, ...] = ()
    things: tuple[Thing, ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def only_through(index: MapIndex, starts: Collection[str], rows: Sequence[CauseRow]) -> set[str]:
    """The ids of ``rows``, what ``starts`` set off, that nothing sets off at any distance
    without passing through a start, unless the starts set it off too.

    It begins with every row and takes out, until nothing changes, a thing set off directly by
    something that is neither a start nor still in; taking one out sends what it sets off to be
    looked at again.
    """
    left = {r.id for r in rows}
    pending = sorted(left)
    while pending:
        item = pending.pop()
        if item not in left:
            continue
        setters = (as_text(edge[end]) for edge, end in ways(index, item, False, ()))
        if any(s not in starts and s not in left for s in setters):
            left.discard(item)
            pending += [as_text(e[end]) for e, end in ways(index, item, True, ()) if e[end] in left]
    return left


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], map_path: Path | None
) -> OnlyReport:
    """Walk by cause from ``ids`` toward what they set off, with the default hub limit, and keep
    what ``only_through`` keeps."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            starts, notes = resolve_all(index, ids)
            walked = cause_walk(index, starts, "off").rows
            kept = only_through(index, set(starts), walked)
            names = Names(index)
            things = tuple(
                Thing(
                    r,
                    names.short(r.id),
                    _place(index, r.id),
                    index.marks(r.id),
                    index.supporting(r.id) is not None,
                )
                for r in walked
                if r.id in kept
            )
    except HarnessError as error:
        return OnlyReport(problems=(error.problem(),))
    return OnlyReport(tuple(starts), walked, things, tuple(notes))


def _place(index: MapIndex, node_id: str) -> str | None:
    loc = first_location(index.nodes[node_id])
    return place(loc) if loc else None


def render_text(report: OnlyReport) -> str:
    """The command, the walk's line, the count, then one row a thing: name, type, state, hop and
    its own place."""
    lines = [head_line("only", report.starts)]
    if report.starts:
        lines.append(summary("sets off:", report.walked, False))
        lines.append(f"only through the starts: {len(report.things)} of {len(report.walked)}")
        at = places([t.location for t in report.things])
        lines += [
            f"  {_escape(t.name)}  {_escape(t.row.type)}  {_escape(t.row.state)}"
            f"  hop {t.row.hop}  {_escape(where)}{marked_text(t.marks, t.supporting)}"
            for t, where in zip(report.things, at, strict=True)
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: OnlyReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "only",
            "starts": list(report.starts),
            "reached": len(report.walked),
            "only": [_json_thing(t) for t in report.things],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def _json_thing(thing: Thing) -> dict[str, Any]:
    return {
        "id": thing.row.id,
        "type": thing.row.type,
        "state": thing.row.state,
        "hop": thing.row.hop,
        "location": thing.location,
        "marks": list(thing.marks),
        "supporting": thing.supporting,
    }


def listed(report: OnlyReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: each thing, by hop and id."""
    return tuple(t.row.id for t in report.things)


RENDERERS = {"text": render_text, "json": render_json}
