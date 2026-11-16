"""``periplus order``: a set of things, each after the things of the set it calls or uses."""

from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.nesting import Thing, json_thing, thing, thing_line
from periplus.navigate.source import place_key, places
from periplus.report import _escape, _json_problem

__all__ = ["NO_CAUSES", "RENDERERS", "OrderReport", "listed", "render_json", "render_text", "run"]

#: The warning on a map with no cause list.
NO_CAUSES = (
    "the map declares no cause directions; each edge puts its to end first, grouping kinds aside"
)


@dataclass(frozen=True, slots=True)
class OrderReport:
    """The things in order, each with the number of the loop it is in, or ``None``."""

    things: tuple[tuple[Thing, int | None], ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], map_path: Path | None
) -> OrderReport:
    """Order the things ``ids`` name so that each comes after those of the set it uses.

    ``a`` uses ``b`` when an edge between them is of a kind whose cause is ``from`` (``a`` its from
    end) or ``to`` (``a`` its to end). A ``none`` or ``touch`` kind orders nothing; a kind under no
    cause list goes by its raw direction, its from end the user, but a grouping kind orders nothing.
    Things that use each other through a chain are a loop and print together. Ties go by the
    first file and line of each thing, or of a loop's first thing, then id.
    """
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            things, notes = resolve_all(index, ids)
            uses, undeclared = _uses(index, set(things))
            names = Names(index)
            rows = {i: thing(index, names, i) for i in things}
            key = {i: (place_key(rows[i].location), i) for i in things}
            ordered = _ordered(sorted(things, key=key.__getitem__), uses, key)
    except HarnessError as error:
        return OrderReport(problems=(error.problem(),))
    warnings = list(notes)
    if not index.declares_causes:
        warnings.append(NO_CAUSES)
    elif undeclared:
        named = ", ".join(sorted(undeclared))
        warnings.append(f"kinds under no cause list, ordered by their raw direction: {named}")
    return OrderReport(tuple((rows[i], loop) for i, loop in ordered), tuple(warnings))


def _uses(index: MapIndex, inside: set[str]) -> tuple[dict[str, set[str]], set[str]]:
    """What each thing uses among ``inside``, and the kinds that ordered undeclared."""
    uses: dict[str, set[str]] = {i: set() for i in inside}
    undeclared: set[str] = set()
    for user in inside:
        for edge in index.outgoing(user):
            far, kind = as_text(edge["to"]), as_text(edge["kind"])
            if far not in inside or far == user:
                continue
            cause = index.cause(kind)
            if cause is None and kind not in index.grouping:
                undeclared.add(kind)
                cause = "from"
            if cause == "from":
                uses[user].add(far)
            elif cause == "to":
                uses[far].add(user)
    return uses, undeclared if index.declares_causes else set()


def _loops(nodes: list[str], uses: Mapping[str, set[str]]) -> list[list[str]]:
    """The strongly connected groups of ``uses``, by Tarjan's method, without recursion."""
    number: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    groups: list[list[str]] = []
    for root in nodes:
        if root in number:
            continue
        work = [(root, iter(sorted(uses[root])))]
        number[root] = low[root] = len(number)
        stack.append(root)
        on.add(root)
        while work:
            node, ahead = work[-1]
            step = next(ahead, None)
            if step is not None:
                if step not in number:
                    number[step] = low[step] = len(number)
                    stack.append(step)
                    on.add(step)
                    work.append((step, iter(sorted(uses[step]))))
                elif step in on:
                    low[node] = min(low[node], number[step])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == number[node]:
                group = []
                while True:
                    member = stack.pop()
                    on.discard(member)
                    group.append(member)
                    if member == node:
                        break
                groups.append(group)
    return groups


def _ordered(
    nodes: list[str], uses: Mapping[str, set[str]], key: Mapping[str, tuple[object, ...]]
) -> list[tuple[str, int | None]]:
    """The things, each group after the groups it uses, the readiest group with the smallest key
    first; a loop's members by key, numbered in the order they print."""
    groups = [sorted(g, key=key.__getitem__) for g in _loops(nodes, uses)]
    group_of = {member: n for n, g in enumerate(groups) for member in g}
    needs = [{group_of[v] for u in g for v in uses[u]} - {n} for n, g in enumerate(groups)]
    needed_by: list[list[int]] = [[] for _ in groups]
    for n, wanted in enumerate(needs):
        for m in wanted:
            needed_by[m].append(n)
    waiting = [len(wanted) for wanted in needs]
    ready = [(key[g[0]], n) for n, g in enumerate(groups) if not waiting[n]]
    heapq.heapify(ready)
    found: list[tuple[str, int | None]] = []
    loops = 0
    while ready:
        _, n = heapq.heappop(ready)
        loop = None
        if len(groups[n]) > 1:
            loops += 1
            loop = loops
        found += [(member, loop) for member in groups[n]]
        for m in needed_by[n]:
            waiting[m] -= 1
            if not waiting[m]:
                heapq.heappush(ready, (key[groups[m][0]], m))
    return found


def render_text(report: OrderReport) -> str:
    """The count line, then one row a thing, ``[loop N]`` after a thing in a loop."""
    lines = ["periplus order"]
    if not report.problems:
        loops = len({loop for _, loop in report.things if loop is not None})
        lines.append(
            f"{len(report.things)} things, {loops} loop{'' if loops == 1 else 's'}; "
            "each after what it calls or uses"
        )
        at = places([row.location for row, _ in report.things])
        lines += [
            thing_line(row, where) + (f"  [loop {loop}]" if loop is not None else "")
            for (row, loop), where in zip(report.things, at, strict=True)
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: OrderReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "order",
            "things": [{**json_thing(row), "loop": loop} for row, loop in report.things],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: OrderReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints, in order."""
    return tuple(row.id for row, _ in report.things)


RENDERERS = {"text": render_text, "json": render_json}
