"""``periplus path``: every shortest directed chain of edges between two items."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import NONE, Listing, footer, kind_warnings, payload
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "PathReport", "Step", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class Step:
    """One edge of a chain: the item it leaves, its kind, and the item it reaches."""

    start: str
    kind: str
    end: str


@dataclass(frozen=True, slots=True)
class PathReport:
    """The shortest chains from ``source`` to ``target`` as a ``Listing`` of step tuples."""

    source: str = ""
    target: str = ""
    chains: Listing[tuple[Step, ...]] = NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _steps(index: MapIndex, node: str, kinds: Collection[str]) -> list[Step]:
    """The steps leaving ``node``, distinct and sorted by kind, then end."""
    return sorted(
        {
            Step(node, as_text(e["kind"]), as_text(e["to"]))
            for e in index.outgoing(node)
            if not kinds or e["kind"] in kinds
        },
        key=lambda s: (s.kind, s.end),
    )


def shortest_chains(
    index: MapIndex, source: str, target: str, kinds: Collection[str], limit: int
) -> tuple[list[list[Step]], int]:
    """The first ``limit`` shortest chains (0 = all) in step order, and the exact count of them."""
    if source == target:
        return [[]], 1
    distance = {source: 0}
    layer = [source]
    layers = [layer]
    while layer and target not in distance:
        reached: list[str] = []
        for item in layer:
            for step in _steps(index, item, kinds):
                if step.end not in distance:
                    distance[step.end] = distance[item] + 1
                    reached.append(step.end)
        layer = reached
        layers.append(layer)
    if target not in distance:
        return [], 0
    # ways[x]: the shortest chains from x on to the target, counted from the far layer back.
    ways = {target: 1}
    for layer in reversed(layers[: distance[target]]):
        for item in layer:
            ways[item] = sum(
                ways.get(step.end, 0)
                for step in _steps(index, item, kinds)
                if distance.get(step.end) == distance[item] + 1
            )
    chains: list[list[Step]] = []

    def extend(node: str, head: list[Step]) -> None:
        if limit and len(chains) >= limit:
            return
        if node == target:
            chains.append(list(head))
            return
        for step in _steps(index, node, kinds):
            if distance.get(step.end) == distance[node] + 1 and ways.get(step.end):
                head.append(step)
                extend(step.end, head)
                head.pop()

    extend(source, [])
    return chains, ways[source]


def run(
    start: Path,
    env: Mapping[str, str],
    from_id: str,
    to_id: str,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
) -> PathReport:
    """Find the shortest chains from ``from_id`` to ``to_id``; an unknown id is a problem."""
    try:
        index = load_map(start, env, map_path)
        from_id = resolve(index, from_id)
        to_id = resolve(index, to_id)
        with reading_fields(start, map_path):
            index.node(from_id)
            index.node(to_id)
            held = {edge["kind"] for edge in index.edges}
            chains, total = shortest_chains(index, from_id, to_id, set(kinds), limit)
    except HarnessError as error:
        return PathReport(problems=(error.problem(),))
    warnings = kind_warnings(kinds, held)
    listing = Listing(
        tuple(tuple(chain) for chain in chains), total, len(chains), len(chains) < total
    )
    return PathReport(from_id, to_id, listing, warnings)


def _chain_lines(chain: tuple[Step, ...]) -> list[str]:
    if not chain:
        return ["    (same item)"]
    return [f"    {_escape(s.start)} --{_escape(s.kind)}--> {_escape(s.end)}" for s in chain]


def render_text(report: PathReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus path"]
    if report.source:
        lines[0] += f" {_escape(report.source)} {_escape(report.target)}"
        if report.chains.total == 0:
            lines.append("no path")
        else:
            lines.append(f"{report.chains.total} shortest chains")
        for number, chain in enumerate(report.chains.items, 1):
            lines += [f"  chain {number}:", *_chain_lines(chain)]
        note = footer(report.chains)
        if note:
            lines.append(note)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def _json_chain(chain: tuple[Step, ...]) -> list[dict[str, str]]:
    return [{"from": s.start, "kind": s.kind, "to": s.end} for s in chain]


def render_json(report: PathReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document: dict[str, Any] = {
        "from": report.source,
        "to": report.target,
        "chains": payload(report.chains, _json_chain),
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


RENDERERS = {"text": render_text, "json": render_json}
