"""``periplus hubs``: the hubs the walk by cause from some ids stops at."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import marked_text, problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.walk import HUB, CauseRow, cause_walk, head_line, marked
from periplus.report import _escape, _json_problem, amount

__all__ = ["RENDERERS", "HubsReport", "listed", "render_json", "render_text", "run", "stopped"]


@dataclass(frozen=True, slots=True)
class HubsReport:
    """The hubs the walk from ``starts``, ``toward`` ``off`` or ``by``, stopped at within
    ``depth`` hops (``None``: all), with the short name each prints, and the hub limit."""

    starts: tuple[str, ...] = ()
    toward: str = "off"
    depth: int | None = None
    hub: int = HUB
    hubs: tuple[CauseRow, ...] = ()
    names: Mapping[str, str] | None = None
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
    toward: str,
    depth: int | None,
    hub: int,
    map_path: Path | None,
    through: Sequence[str] = (),
) -> HubsReport:
    """Walk by cause from ``ids`` as ``neighbors`` (``off``) or ``affected`` (``by``) do, walking
    from the hubs ``through`` names, and keep the things listed as hubs within ``depth`` hops."""
    try:
        index = load_map(start, env, map_path)
    except HarnessError as error:
        return HubsReport(toward=toward, problems=(error.problem(),))
    return stopped(start, index, ids, toward, depth, hub, map_path, through)


def stopped(
    start: Path,
    index: MapIndex,
    ids: Sequence[str],
    toward: str,
    depth: int | None,
    hub: int,
    map_path: Path | None,
    through: Sequence[str] = (),
) -> HubsReport:
    """``run`` on a map already loaded."""
    try:
        with reading_fields(start, map_path):
            starts, notes = resolve_all(index, ids)
            passes, passed = resolve_all(index, through)
            notes += passed
            rows = cause_walk(index, starts, toward, (), hub, passes).rows
            hubs = tuple(
                marked(index, r)
                for r in rows
                if r.hub is not None and (depth is None or r.hop <= depth)
            )
            names = Names(index)
            shorts = {r.id: names.short(r.id) for r in hubs}
    except HarnessError as error:
        return HubsReport(toward=toward, problems=(error.problem(),))
    return HubsReport(tuple(starts), toward, depth, hub, hubs, shorts, tuple(notes))


def render_text(report: HubsReport) -> str:
    """The command, a count line, then one line a hub: name, type, hop and fan."""
    lines = [head_line("hubs", report.starts)]
    if report.starts:
        label = "sets off:" if report.toward == "off" else "set off by:"
        within = "" if report.depth is None else f" within {amount(report.depth, 'hop')}"
        lines.append(
            f"{label} {amount(len(report.hubs), 'hub')}{within}"
            f" (more than {amount(report.hub, 'link')} to follow)"
        )
        names = report.names or {}
        lines += [
            f"  {_escape(names.get(r.id, r.id))}  {_escape(r.type)}  hop {r.hop}  fan {r.hub}"
            f"{marked_text(r.marks, r.supporting)}"
            for r in report.hubs
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: HubsReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "hubs",
            "direction": report.toward,
            "starts": list(report.starts),
            "depth": report.depth,
            "hub": report.hub,
            "hubs": [
                {
                    "id": r.id,
                    "type": r.type,
                    "hop": r.hop,
                    "fan": r.hub,
                    "marks": list(r.marks),
                    "supporting": r.supporting,
                }
                for r in report.hubs
            ],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: HubsReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: each hub, by hop and id."""
    return tuple(r.id for r in report.hubs)


RENDERERS = {"text": render_text, "json": render_json}
