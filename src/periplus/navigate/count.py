"""``periplus count``: how many things a set of ids names, by type and state, and the edges among
them."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import NodeNotFound, as_json, as_text, load_map, reading_fields
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "CountReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class CountReport:
    """How many ids were given, the things they name, the ids given more than once in effect,
    those named by a short name, the counts by type, by state and of the edges among the things
    by kind, and the ids that name no node, each with how many nodes it fits (0 or several)."""

    given: int = 0
    things: int = 0
    repeated: int = 0
    short: int = 0
    by_type: tuple[tuple[str, int], ...] = ()
    by_state: tuple[tuple[str, int], ...] = ()
    edges: tuple[tuple[str, int], ...] = ()
    missing: tuple[tuple[str, int], ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _most(counted: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(counted.items(), key=lambda p: (-p[1], p[0])))


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], map_path: Path | None
) -> CountReport:
    """Count what ``ids`` name. An id that names no node, or a short name that fits several, is
    listed, not a problem."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            found: list[str] = []
            missing: list[tuple[str, int]] = []
            short = 0
            for text in ids:
                try:
                    node_id, said = resolve(index, text, close=False)
                except NodeNotFound as error:
                    missing.append((text, int(error.detail.get("total", 0))))
                    continue
                found.append(node_id)
                short += bool(said)
            things = set(found)
            nodes = [index.nodes[i] for i in things]
            edges = Counter(
                as_text(e["kind"]) for i in things for e in index.outgoing(i) if e["to"] in things
            )
            report = CountReport(
                len(ids),
                len(things),
                len(found) - len(things),
                short,
                _most(Counter(as_text(n["type"]) for n in nodes)),
                _most(Counter(as_text(n["state"]) for n in nodes)),
                _most(edges),
                tuple(missing),
            )
    except HarnessError as error:
        return CountReport(problems=(error.problem(),))
    return report


def _counted(pairs: Sequence[tuple[str, int]]) -> str:
    return ", ".join(f"{_escape(k)} {n}" for k, n in pairs) or "none"


def render_text(report: CountReport) -> str:
    """One line each: the ids, the things, by type, by state, the edges among them by kind; then
    the ids that name no node."""
    lines = ["periplus count"]
    if not report.problems:
        head = f"{report.given} ids given: {report.things} things in the map"
        head += f", {len(report.missing)} not" if report.missing else ""
        head += f"; {report.repeated} repeated" if report.repeated else ""
        head += f"; {report.short} by a short name" if report.short else ""
        total = sum(n for _, n in report.edges)
        lines += [
            head,
            f"by type: {_counted(report.by_type)}",
            f"by state: {_counted(report.by_state)}",
            f"edges among them: {total}" + (f" ({_counted(report.edges)})" if total else ""),
        ]
        if report.missing:
            lines.append("not in the map:")
            lines += [
                f"  {_escape(text)}" + (f"  (fits {fits} nodes)" if fits else "")
                for text, fits in report.missing
            ]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: CountReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "count",
            "given": report.given,
            "things": report.things,
            "repeated": report.repeated,
            "short_names": report.short,
            "by_type": dict(report.by_type),
            "by_state": dict(report.by_state),
            "edges": dict(report.edges),
            "not_found": [{"id": text, "fits": fits} for text, fits in report.missing],
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
