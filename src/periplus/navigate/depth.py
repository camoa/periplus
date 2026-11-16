"""``periplus depth``: how far the walk by cause goes from some ids, each way, in a few lines."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, load_map, reading_fields
from periplus.navigate.walk import HUB, CauseRow, amount, cause_walk, head_line, summary, ways
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "DepthReport", "render_json", "render_text", "run"]

#: The most touching kinds the text names; the rest are counted.
KINDS_NAMED = 3


@dataclass(frozen=True, slots=True)
class DepthReport:
    """Both walks by cause from ``starts``: what they set off (``off``) and what sets them off
    (``by``), each row to the end; the touching edges at the starts, as (kind, edges) arriving
    (``pointed``, from ``pointers`` things) and leaving (``pointing``, to ``pointees`` things);
    the kinds walked undeclared; and whether the map lists any cause."""

    starts: tuple[str, ...] = ()
    off: tuple[CauseRow, ...] = ()
    by: tuple[CauseRow, ...] = ()
    pointed: tuple[tuple[str, int], ...] = ()
    pointers: int = 0
    pointing: tuple[tuple[str, int], ...] = ()
    pointees: int = 0
    undeclared: tuple[str, ...] = ()
    declares: bool = True
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    ids: Sequence[str],
    map_path: Path | None,
    hub: int = HUB,
    through: Sequence[str] = (),
) -> DepthReport:
    """Walk by cause from ``ids`` both ways to the end, with the hub limit and ``through``."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            notes: list[str] = []
            starts: list[str] = []
            passes: list[str] = []
            for text, into in [*((t, starts) for t in ids), *((t, passes) for t in through)]:
                found, note = resolve(index, text)
                into.append(found)
                notes += note
            starts = list(dict.fromkeys(starts))
            off = cause_walk(index, starts, "off", (), hub, passes)
            by = cause_walk(index, starts, "by", (), hub, passes)
            pointed, pointers = _touch(index, starts, False)
            pointing, pointees = _touch(index, starts, True)
    except HarnessError as error:
        return DepthReport(problems=(error.problem(),))
    return DepthReport(
        tuple(starts),
        off.rows,
        by.rows,
        pointed,
        pointers,
        pointing,
        pointees,
        tuple(sorted({*off.undeclared, *by.undeclared})),
        index.declares_causes,
        tuple(notes),
    )


def _touch(
    index: MapIndex, starts: Collection[str], off: bool
) -> tuple[tuple[tuple[str, int], ...], int]:
    """The touching edges at the starts that leave them (``off``) or arrive, counted by kind, most
    first; and how many things other than the starts are at their other ends."""
    kinds: Counter[str] = Counter()
    things: set[str] = set()
    for item in starts:
        for edge, end in ways(index, item, off, (), touch=True):
            if edge[end] not in starts:
                kinds[edge["kind"]] += 1
                things.add(edge[end])
    return tuple(sorted(kinds.items(), key=lambda p: (-p[1], p[0]))), len(things)


def _kinds(counted: Sequence[tuple[str, int]]) -> str:
    named = ", ".join(f"{_escape(k)} {n}" for k, n in counted[:KINDS_NAMED])
    left = len(counted) - KINDS_NAMED
    return named + (f", +{left} kinds" if left > 0 else "")


def render_text(report: DepthReport) -> str:
    """One line per direction, then the touching line and the undeclared line when there are any."""
    named = " ".join(_escape(s) for s in report.starts)
    lines = [head_line("depth", report.starts)]
    if report.starts:
        lines.append(summary("sets off:", report.off, True))
        lines.append(summary("set off by:", report.by, True))
        one = len(report.starts) == 1
        parts = []
        if report.pointers:
            verb = "points" if report.pointers == 1 else "point"
            parts.append(
                f"{amount(report.pointers, 'thing')} {verb} at {'it' if one else 'them'}"
                f" ({_kinds(report.pointed)}); see periplus affected {named} --touch"
            )
        if report.pointees:
            parts.append(
                f"{'it points' if one else 'they point'} at {amount(report.pointees, 'thing')}"
                f" ({_kinds(report.pointing)}); see periplus neighbors {named} --touch"
            )
        if parts:
            lines.append(f"{'touching:':<12}" + "; ".join(parts))
        if not report.declares:
            lines.append(
                "the map declares no cause directions; every kind was walked by raw direction"
            )
        elif report.undeclared:
            undeclared = ", ".join(_escape(k) for k in report.undeclared)
            lines.append(f"undeclared kinds, walked by raw direction: {undeclared}")
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _direction(rows: Sequence[CauseRow]) -> dict[str, Any]:
    last = max((r.hop for r in rows), default=0)
    return {
        "hops": last,
        "things": len(rows),
        "per_hop": [sum(r.hop == hop for r in rows) for hop in range(1, last + 1)],
        "hubs": [{"id": r.id, "hop": r.hop, "fan": r.hub} for r in rows if r.hub is not None],
    }


def render_json(report: DepthReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "starts": list(report.starts),
            "sets_off": _direction(report.off),
            "set_off_by": _direction(report.by),
            "touching": {
                "point_at_starts": {"things": report.pointers, "kinds": dict(report.pointed)},
                "starts_point_at": {"things": report.pointees, "kinds": dict(report.pointing)},
            },
            "undeclared": list(report.undeclared),
            "declares_causes": report.declares,
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
