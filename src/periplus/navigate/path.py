"""``periplus path``: every shortest directed chain of edges between two items."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import Listing, footer, payload
from periplus.navigate.mapfile import MapIndex, as_text, load_map, reading_fields
from periplus.report import _escape

__all__ = ["RENDERERS", "PathReport", "render_json", "render_text", "run"]

_NONE = Listing((), 0, 0, False)

Step = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class PathReport:
    """The shortest chains from ``source`` to ``target`` as a ``Listing`` of step lists."""

    source: str = ""
    target: str = ""
    chains: Listing = _NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _steps(index: MapIndex, node: str, kinds: Collection[str]) -> list[Step]:
    """The steps leaving ``node`` as (from, kind, to), distinct and sorted."""
    return sorted(
        {
            (node, as_text(e["kind"]), as_text(e["to"]))
            for e in index.outgoing(node)
            if not kinds or e["kind"] in kinds
        },
        key=lambda s: (s[1], s[2]),
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
            for _, _, other in _steps(index, item, kinds):
                if other not in distance:
                    distance[other] = distance[item] + 1
                    reached.append(other)
        layer = reached
        layers.append(layer)
    if target not in distance:
        return [], 0
    # ways[x]: the shortest chains from x on to the target, counted from the far layer back.
    ways = {target: 1}
    for layer in reversed(layers[: distance[target]]):
        for item in layer:
            ways[item] = sum(
                ways.get(other, 0)
                for _, _, other in _steps(index, item, kinds)
                if distance.get(other) == distance[item] + 1
            )
    chains: list[list[Step]] = []

    def extend(node: str, head: list[Step]) -> None:
        if limit and len(chains) >= limit:
            return
        if node == target:
            chains.append(list(head))
            return
        for step in _steps(index, node, kinds):
            if distance.get(step[2]) == distance[node] + 1 and ways.get(step[2]):
                head.append(step)
                extend(step[2], head)
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
    warnings = tuple(
        f"the map holds no edge of kind {kind!r}" for kind in sorted(set(kinds) - held)
    )
    listing = Listing(tuple(chains), total, len(chains), len(chains) < total)
    return PathReport(from_id, to_id, listing, warnings)


def _chain_lines(chain: list[Step]) -> list[str]:
    if not chain:
        return ["    (same item)"]
    return [f"    {_escape(a)} --{_escape(kind)}--> {_escape(b)}" for a, kind, b in chain]


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


def render_json(report: PathReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    chains = Listing(
        tuple(
            [{"from": a, "kind": k, "to": b} for a, k, b in chain] for chain in report.chains.items
        ),
        report.chains.total,
        report.chains.shown,
        report.chains.truncated,
    )
    document: dict[str, Any] = {
        "from": report.source,
        "to": report.target,
        "chains": payload(chains),
        "warnings": list(report.warnings),
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
