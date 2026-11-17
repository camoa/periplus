"""``periplus reach``: ``depth``, then ``neighbors`` and ``affected`` to the hops that fit a text
budget, with what ``only`` returns tagged and the hubs as ``hubs`` prints them.

A macro: each part is a small command's own report, built by the same function on the one map
loaded, so each is reproducible with that command; a shortened part names the command that prints
it in full.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate import depth as depth_
from periplus.navigate import hubs as hubs_
from periplus.navigate import walk
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import as_json, load_map
from periplus.navigate.only import kept
from periplus.navigate.walk import BUDGET, HUB, CauseReport, head_line, start_args
from periplus.report import _escape, _json_problem, amount

__all__ = ["DIRECTIONS", "RENDERERS", "ReachReport", "listed", "render_json", "render_text", "run"]

#: The walks each ``--direction`` takes, in the order the reply prints them.
DIRECTIONS = {"off": ("off",), "by": ("by",), "both": ("off", "by")}


@dataclass(frozen=True, slots=True)
class ReachReport:
    """The ``depth`` report of the starts, one walk by cause per direction asked with the things
    only the starts set off tagged, the ``hubs`` report of each walk, the ids ``only`` returns and
    the command that lists them, and the text budget (0: none)."""

    starts: tuple[str, ...] = ()
    measured: depth_.DepthReport | None = None
    walks: tuple[CauseReport, ...] = ()
    hubs: tuple[hubs_.HubsReport, ...] = ()
    only: tuple[str, ...] | None = None
    only_command: str = ""
    limit: int = BUDGET
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
    direction: str = "both",
    depth: int | None = None,
    hub: int = HUB,
    through: Sequence[str] = (),
    touch: bool = False,
    full: bool = False,
    limit: int | None = None,
    piped: bool = False,
) -> ReachReport:
    """Load the map once and build each part as its small command does: ``depth``, then for each
    walk of ``direction`` the walk by cause to ``depth`` hops (``None``: all), its hubs, and with
    the walk ``off`` what ``only`` returns. ``limit`` is the text budget (``None``: ``BUDGET``;
    0: none); ``piped`` says the ids came from standard input."""
    budget = BUDGET if limit is None else limit
    try:
        index = load_map(start, env, map_path)
    except HarnessError as error:
        return ReachReport(limit=budget, problems=(error.problem(),))
    measured = depth_.measure(start, index, ids, map_path, hub, through, piped)
    if measured.problems:
        return ReachReport(limit=budget, warnings=measured.warnings, problems=measured.problems)
    towards = DIRECTIONS[direction]
    alone: tuple[str, ...] | None = None
    command = ""
    if "off" in towards:
        alone = tuple(t.row.id for t in kept(start, index, ids, map_path, hub, through).things)
        named, note = start_args(measured.starts, piped)
        words = ["periplus", "only", *named]
        words += ["--hub", str(hub)] if hub != HUB else []
        words += [f for item in through for f in ("--through", item)]
        words += ["--map", str(map_path)] if map_path is not None else []
        command = " ".join(shlex.quote(w) for w in words) + note
    tagged = set(alone or ())
    walks = []
    for toward in towards:
        report = walk.cause_report(
            start, index, ids, toward, depth, (), 0, map_path, hub, through, touch, full, piped
        )
        rows = tuple(replace(r, only=r.id in tagged) for r in report.walked)
        walks.append(replace(report, walked=rows, warnings=()))
    stops = tuple(
        replace(hubs_.stopped(start, index, ids, t, None, hub, map_path, through), warnings=())
        for t in towards
    )
    return ReachReport(
        measured.starts,
        replace(measured, warnings=()),
        tuple(walks),
        stops,
        alone,
        command,
        budget,
        measured.warnings,
    )


def _fitted(report: ReachReport, fixed: int) -> list[str]:
    """Each walk's text in its share of what the budget leaves after ``fixed`` characters: an even
    share, and a walk that fits whole in less gives the rest to the other."""
    whole = [walk.render_text(w) for w in report.walks]
    if not report.limit:
        return whole
    left = max(report.limit - fixed, 0)
    shares = [left // len(whole)] * len(whole)
    if len(whole) == 2:
        for mine, other in ((0, 1), (1, 0)):
            if len(whole[mine]) <= shares[mine]:
                shares = [0, 0]
                shares[mine] = len(whole[mine])
                shares[other] = left - len(whole[mine])
                break
    # A share of 0 would mean no limit; 1 keeps the walk at its first hop.
    return [
        walk.render_text(replace(w, limit=max(share, 1)))
        for w, share in zip(report.walks, shares, strict=True)
    ]


def render_text(report: ReachReport) -> str:
    """``periplus reach`` and the starts, then, a blank line apart: the ``depth`` report, the line
    on what only the starts set off, each walk followed by its hubs when it stopped at any, and the
    warnings and problems."""
    lines = [head_line("reach", report.starts)]
    notes = [f"warning: {_escape(w)}" for w in report.warnings] + problem_lines(report.problems)
    if report.measured is None:
        return "\n".join(lines + notes) + "\n"
    blocks = ["\n".join(lines), depth_.render_text(report.measured).rstrip("\n")]
    if report.only is not None and report.walks:
        reached = len(report.walks[0].walked)
        blocks[-1] += (
            f"\nonly through the starts: {len(report.only)} of {amount(reached, 'thing')} set off,"
            f" tagged [only]; all: {_escape(report.only_command)}"
        )
    stops = [hubs_.render_text(h).rstrip("\n") if h.hubs else "" for h in report.hubs]
    tail = "\n".join(notes)
    fixed = sum(len(b) + 2 for b in [*blocks, *stops, tail] if b)
    for text, stop in zip(_fitted(report, fixed), stops, strict=True):
        blocks.append(text.rstrip("\n"))
        blocks += [stop] if stop else []
    blocks += [tail] if tail else []
    return "\n\n".join(blocks) + "\n"


def render_json(report: ReachReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``: each part as its small
    command prints it with ``--format json``, so every walk holds its rows within ``--depth``."""
    document: dict[str, Any] = {
        "command": "reach",
        "starts": list(report.starts),
        "depth": None,
        "only": None if report.only is None else list(report.only),
        "only_command": report.only_command or None,
        "walks": [json.loads(walk.render_json(w)) for w in report.walks],
        "hubs": [json.loads(hubs_.render_json(h)) for h in report.hubs],
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    if report.measured is not None:
        document["depth"] = json.loads(depth_.render_json(report.measured))
    return as_json(document)


def listed(report: ReachReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the starts, then what each walk lists with ``--ids``, each once."""
    return tuple(
        dict.fromkeys([*report.starts, *(i for w in report.walks for i in walk.listed(w))])
    )


RENDERERS = {"text": render_text, "json": render_json}
