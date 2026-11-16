"""``periplus undescribed``: the main things the descriptions file does not describe.

A main thing is what the ``periplus-describe`` skill describes: a mapped node with a location,
not in supporting code, whose type is not a part type (``Places.part_types``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import first_location, place, problem_lines
from periplus.navigate.mapfile import as_json, as_text, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places
from periplus.navigate.show import read_descriptions
from periplus.navigate.source import place_key
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "UndescribedReport", "listed", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class UndescribedReport:
    """The main things counted, how many have an entry, the undescribed counted by ``by``, most
    first (a key of ``None`` is no container), their ids by place, and what was left out: the
    part types with their counts, most first, and the things in supporting code and those not
    mapped or with no location. ``names`` prints a container's short name."""

    by: str = "file"
    main: int = 0
    described: int = 0
    counts: tuple[tuple[str | None, int], ...] = ()
    ids: tuple[str, ...] = ()
    parts: tuple[tuple[str, int], ...] = ()
    supporting: int = 0
    unplaced: int = 0
    names: Mapping[str, str] | None = None
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _most(counted: Counter[Any]) -> tuple[tuple[Any, int], ...]:
    return tuple(sorted(counted.items(), key=lambda p: (-p[1], p[0] is None, p[0] or "")))


def run(
    start: Path, env: Mapping[str, str], ids: Sequence[str], by: str, map_path: Path | None
) -> UndescribedReport:
    """Count the main things among ``ids``, or in the whole map when there are none, and those
    with no entry under ``nodes`` in the descriptions file, by ``file``, ``type`` or
    ``container``."""
    try:
        index = load_map(start, env, map_path)
        _, document, problems = read_descriptions(start, map_path)
        if problems:
            return UndescribedReport(by, problems=problems)
        with reading_fields(start, map_path):
            things, notes = resolve_all(index, ids) if ids else (sorted(index.nodes), [])
            names = Names(index)
            places = Places(index, names)
            described = set(document.get("nodes") or {})
            why: Counter[str] = Counter()
            parts: Counter[str] = Counter()
            main: list[str] = []
            for node_id in things:
                reason = places.why_not_main(node_id)
                if reason is None:
                    main.append(node_id)
                else:
                    why[reason] += 1
                    if reason == "part":
                        parts[as_text(index.nodes[node_id]["type"])] += 1
            bare = [i for i in main if i not in described]
            keys = [_key(index, places, i, by) for i in bare]
            shown = {k: names.short(k) for k in keys if k is not None and by == "container"}
            located = {i: first_location(index.nodes[i]) for i in bare}
            ordered = sorted(
                bare, key=lambda i: (place_key(place(loc) if (loc := located[i]) else None), i)
            )
    except HarnessError as error:
        return UndescribedReport(by, problems=(error.problem(),))
    return UndescribedReport(
        by,
        len(main),
        len(main) - len(bare),
        _most(Counter(keys)),
        tuple(ordered),
        _most(parts),
        why["supporting"],
        why["unplaced"],
        shown,
        tuple(notes),
    )


def _key(index: Any, places: Places, node_id: str, by: str) -> str | None:
    """What ``node_id`` counts under: the file of its first location, its type, or the first
    grouping container of it or of what holds it."""
    if by == "type":
        return as_text(index.nodes[node_id]["type"])
    if by == "file":
        return as_text(index.nodes[node_id]["locations"][0]["file"]).removeprefix("./")
    for held in (node_id, *places.outward(node_id)):
        if (container := places.container(held)) is not None:
            return container
    return None


def render_text(report: UndescribedReport) -> str:
    """The count line, the left-out line when anything was left out, then ``by KEY:`` and one
    row a key, ``count  key``."""
    lines = ["periplus undescribed"]
    if not report.problems:
        bare = report.main - report.described
        lines.append(
            f"described {report.described} of {report.main} main things; {bare} undescribed"
        )
        left = []
        if report.parts:
            counted = ", ".join(f"{_escape(t)} {n}" for t, n in report.parts)
            left.append(f"{sum(n for _, n in report.parts)} parts ({counted})")
        if report.supporting:
            left.append(f"{report.supporting} in supporting code")
        if report.unplaced:
            left.append(f"{report.unplaced} not mapped or with no location")
        lines += [f"left out: {', '.join(left)}"] if left else []
        if report.counts:
            lines.append(f"by {report.by}:")
            names = report.names or {}
            lines += [
                f"  {n}  {_escape(names.get(key, key)) if key is not None else '(no container)'}"
                for key, n in report.counts
            ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: UndescribedReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "undescribed",
            "by": report.by,
            "main": report.main,
            "described": report.described,
            "counts": [{"key": key, "count": n} for key, n in report.counts],
            "undescribed": list(report.ids),
            "left_out": {
                "parts": dict(report.parts),
                "supporting": report.supporting,
                "unplaced": report.unplaced,
            },
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: UndescribedReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the undescribed main things, by file, line, then id."""
    return report.ids


RENDERERS = {"text": render_text, "json": render_json}
