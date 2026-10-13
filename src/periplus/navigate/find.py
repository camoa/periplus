"""``periplus find``: the nodes whose id holds a text, closest match first."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import Listing, cut, footer, payload
from periplus.navigate.mapfile import MapIndex, as_text, load_map, reading_fields
from periplus.report import _escape

__all__ = ["RENDERERS", "FindReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class FindReport:
    """The matching nodes as rows (id, type, state, first location), and what went wrong."""

    matches: Listing = Listing((), 0, 0, False)
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _rank(node_id: str, text: str) -> int | None:
    """0 the id is the text, 1 the name is, 2 it starts with it, 3 holds it, 4 the id holds it."""
    whole = node_id.casefold()
    name = whole.rsplit("::", 1)[-1]
    if whole == text:
        return 0
    if name == text:
        return 1
    if name.startswith(text):
        return 2
    if text in name:
        return 3
    return 4 if text in whole else None


def _with_subtypes(index: MapIndex, type_name: str) -> set[str]:
    """``type_name`` and every type below it in the map's hierarchy."""
    found = {type_name}
    pending = [type_name]
    while pending:
        for child in index.subtypes(pending.pop()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _location(node: Mapping[str, Any]) -> str | None:
    """The node's first location as ``file:line``, or ``None`` when it has none."""
    locations = node["locations"]
    return f"{locations[0]['file']}:{locations[0]['line']}" if locations else None


def run(
    start: Path,
    env: Mapping[str, str],
    text: str,
    type_name: str | None,
    limit: int,
    map_path: Path | None,
) -> FindReport:
    """Find the nodes whose id holds ``text``; a load failure is a problem, not a raise."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            return _find(index, text, type_name, limit)
    except HarnessError as error:
        return FindReport(problems=(error.problem(),))


def _find(index: MapIndex, text: str, type_name: str | None, limit: int) -> FindReport:
    """``run``'s report, read from the map's node fields."""
    warnings: tuple[str, ...] = ()
    wanted: set[str] | None = None
    if type_name is not None:
        wanted = _with_subtypes(index, type_name)
        if not any(node["type"] in wanted for node in index.nodes.values()) and not (
            index.parent(type_name) or index.subtypes(type_name)
        ):
            warnings = (f"no type named {type_name!r} is in the map; periplus types lists them",)
    needle = text.casefold()
    ranked = []
    for node_id, node in index.nodes.items():
        rank = _rank(as_text(node_id), needle)
        if rank is not None and (wanted is None or node["type"] in wanted):
            ranked.append((rank, node_id, node))
    ranked.sort(key=lambda row: (row[0], row[1]))
    rows = [
        {
            "id": i,
            "type": as_text(n["type"]),
            "state": as_text(n["state"]),
            "location": _location(n),
        }
        for _, i, n in ranked
    ]
    return FindReport(cut(rows, limit), warnings)


def render_text(report: FindReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus find", ""]
    for row in report.matches.items:
        where = row["location"] or "no location"
        lines.append(
            f"{_escape(row['id'])}  {_escape(row['type'])}"
            f"  {_escape(row['state'])}  {_escape(where)}"
        )
    if not report.matches.items:
        lines.append("no matches")
    note = footer(report.matches)
    lines += [note] if note else []
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def render_json(report: FindReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        **payload(report.matches),
        "warnings": list(report.warnings),
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
