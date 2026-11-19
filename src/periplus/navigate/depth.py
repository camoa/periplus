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
from periplus.navigate.mapfile import MapIndex, as_json, load_map, map_flag, reading_fields
from periplus.navigate.walk import (
    HUB,
    CauseRow,
    cause_walk,
    head_line,
    start_args,
    summary,
    ways,
)
from periplus.report import _escape, _json_problem, amount

__all__ = [
    "RENDERERS",
    "DepthReport",
    "entrances",
    "listed",
    "measure",
    "render_json",
    "render_text",
    "run",
]

#: The most touching kinds the text names; the rest are counted.
KINDS_NAMED = 3


@dataclass(frozen=True, slots=True)
class DepthReport:
    """Both walks by cause from ``starts``: what they set off (``off``) and what sets them off
    (``by``), each row to the end; the same two walks from each start alone (``alone``), in the
    order given, with ``entrances`` only for the entrances and the separate pieces; the touching
    edges at the starts, as (kind, edges) arriving
    (``pointed``, from ``pointers`` things) and leaving (``pointing``, to ``pointees`` things);
    the kinds walked undeclared; and whether the map lists any cause. ``entrances`` asks for the
    entrances, the starts that set something off and that nothing sets off, in place of the
    report."""

    starts: tuple[str, ...] = ()
    off: tuple[CauseRow, ...] = ()
    by: tuple[CauseRow, ...] = ()
    alone: tuple[tuple[str, tuple[CauseRow, ...], tuple[CauseRow, ...]], ...] = ()
    pointed: tuple[tuple[str, int], ...] = ()
    pointers: int = 0
    pointing: tuple[tuple[str, int], ...] = ()
    pointees: int = 0
    undeclared: tuple[str, ...] = ()
    declares: bool = True
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    piped: bool = False
    map_path: Path | None = None
    entrances: bool = False

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
    piped: bool = False,
    entrances: bool = False,
) -> DepthReport:
    """Walk by cause from ``ids`` both ways to the end, with the hub limit and ``through``;
    ``piped`` says the ids came from standard input."""
    try:
        index = load_map(start, env, map_path)
    except HarnessError as error:
        return DepthReport(problems=(error.problem(),), entrances=entrances)
    return measure(start, index, ids, map_path, hub, through, piped, entrances)


def measure(
    start: Path,
    index: MapIndex,
    ids: Sequence[str],
    map_path: Path | None,
    hub: int = HUB,
    through: Sequence[str] = (),
    piped: bool = False,
    entrances: bool = False,
) -> DepthReport:
    """``run`` on a map already loaded."""
    try:
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
            # One start alone is the whole walk; it is not walked twice. With ``entrances`` an id
            # one hop shows set off is neither an entrance nor a separate piece, so it is not
            # walked: walking every id to the end grows with the square of the ids.
            alone = (
                [(starts[0], off.rows, by.rows)]
                if len(starts) == 1
                else [
                    (
                        item,
                        cause_walk(index, [item], "off", (), hub, passes).rows,
                        cause_walk(index, [item], "by", (), hub, passes).rows,
                    )
                    for item in starts
                    if not entrances or not _set_off(index, item)
                ]
            )
            pointed, pointers = _touch(index, starts, False)
            pointing, pointees = _touch(index, starts, True)
    except HarnessError as error:
        return DepthReport(problems=(error.problem(),), entrances=entrances)
    return DepthReport(
        tuple(starts),
        off.rows,
        by.rows,
        tuple(alone),
        pointed,
        pointers,
        pointing,
        pointees,
        tuple(sorted({*off.undeclared, *by.undeclared})),
        index.declares_causes,
        tuple(notes),
        piped=piped,
        map_path=map_path,
        entrances=entrances,
    )


def entrances(report: DepthReport) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The starts that set something off and that nothing sets off, alone; and the starts with
    nothing either way, the separate pieces; each in the order given."""
    return (
        tuple(item for item, off, by in report.alone if off and not by),
        tuple(item for item, off, by in report.alone if not off and not by),
    )


def listed(report: DepthReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the entrances."""
    return entrances(report)[0]


def _set_off(index: MapIndex, item: str) -> bool:
    """Whether the walk by cause from ``item`` alone reaches anything ``by``: an edge it follows
    one hop to another thing. A start is always walked from, so the hub limit plays no part."""
    return any(edge[end] != item for edge, end in ways(index, item, False, ()))


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
    return named + (f", +{amount(left, 'kind')}" if left > 0 else "")


def _alone(label: str, rows: Sequence[CauseRow]) -> str:
    last = max((r.hop for r in rows), default=0)
    hubs = sum(r.hub is not None for r in rows)
    return (
        f"{label} {amount(last, 'hop')}, {amount(len(rows), 'thing')},"
        f" {amount(hubs, 'hub')} stopped"
    )


def _entrance_lines(report: DepthReport) -> list[str]:
    found, separate = entrances(report)
    rows = {item: (off, by) for item, off, by in report.alone}
    width = max((len(_escape(item)) for item in found), default=0)
    one = len(found) == 1
    named = ", ".join(_escape(s) for s in separate[:KINDS_NAMED])
    left = len(separate) - KINDS_NAMED
    return [
        f"{len(found)} of {amount(len(report.starts), 'id')}"
        f" {'is an entrance' if one else 'are entrances'}",
        *(
            f"  {_escape(item):<{width}}  {_alone('sets off', rows[item][0])};"
            f" {_alone('set off by', rows[item][1])}"
            for item in found
        ),
        f"{amount(len(separate), 'separate piece')}, nothing either way"
        + (f": {named}" if named else "")
        + (f", +{left}" if left > 0 else ""),
    ]


def render_text(report: DepthReport) -> str:
    """One line per direction; with several starts a row per start walked alone; then the touching
    line and the undeclared line when there are any. With ``entrances``, a count line, a row per
    entrance and the separate pieces line in their place."""
    if report.entrances:
        lines = _entrance_lines(report)
        lines += [f"warning: {_escape(w)}" for w in report.warnings]
        lines += problem_lines(report.problems)
        return "\n".join(lines) + "\n"
    args, note = start_args(report.starts, report.piped)
    named = " ".join(_escape(s) for s in args)
    on = _escape(map_flag(report.map_path))
    lines = [head_line("depth", report.starts)]
    if report.starts:
        lines.append(summary("sets off:", report.off, True))
        lines.append(summary("set off by:", report.by, True))
        one = len(report.starts) == 1
        if not one:
            width = max(len(_escape(item)) for item, _, _ in report.alone)
            lines.append("each start alone:")
            lines += [
                f"  {_escape(item):<{width}}  {_alone('sets off', off)}; {_alone('set off by', by)}"
                for item, off, by in report.alone
            ]
        parts = []
        if report.pointers:
            verb = "points" if report.pointers == 1 else "point"
            parts.append(
                f"{amount(report.pointers, 'thing')} {verb} at {'it' if one else 'them'}"
                f" ({_kinds(report.pointed)}); see periplus affected {named} --touch{on}{note}"
            )
        if report.pointees:
            parts.append(
                f"{'it points' if one else 'they point'} at {amount(report.pointees, 'thing')}"
                f" ({_kinds(report.pointing)}); see periplus neighbors {named} --touch{on}{note}"
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
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``; with ``entrances``,
    ``entrances`` and ``separate_pieces`` too."""
    found, separate = entrances(report)
    return as_json(
        {
            **(
                {"entrances": list(found), "separate_pieces": list(separate)}
                if report.entrances
                else {}
            ),
            "starts": list(report.starts),
            "sets_off": _direction(report.off),
            "set_off_by": _direction(report.by),
            "each_start": [
                {
                    "id": item,
                    **{
                        key: {k: v for k, v in _direction(rows).items() if k != "per_hop"}
                        for key, rows in (("sets_off", off), ("set_off_by", by))
                    },
                }
                for item, off, by in report.alone
            ],
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
