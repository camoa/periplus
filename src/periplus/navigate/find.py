"""``periplus find``: the nodes whose id or description holds a text, closest match first."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import NONE, Listing, cut, first_location, footer, payload, place
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import SourceLines, description_line, source_line
from periplus.report import _escape, _json_problem

__all__ = ["RENDERERS", "FindReport", "FindRow", "render_json", "render_text", "run"]

#: The most types a cut list's footer counts by name.
_FOOTER_TYPES = 8
#: The most type names a warning about an unknown type suggests.
_SUGGESTED = 5


@dataclass(frozen=True, slots=True)
class FindRow:
    """One matching node: its id, type, state, first location as ``file:line``, and the line.

    ``matched`` is ``id`` or ``description``, and ``description`` the node's descriptions entry.
    """

    id: str
    type: str
    state: str
    location: str | None
    source: str | None = None
    matched: str = "id"
    description: str | None = None


@dataclass(frozen=True, slots=True)
class FindReport:
    """The matching nodes as rows, every match counted by type, and what went wrong."""

    matches: Listing[FindRow] = NONE
    by_type: Mapping[str, int] | None = None
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
    loc = first_location(node)
    return place(loc) if loc else None


def _suggestions(index: MapIndex, type_name: str) -> list[str]:
    """Node types near ``type_name``: those of ids starting ``type_name::``, then by name."""
    held = sorted({as_text(node["type"]) for node in index.nodes.values()})
    prefixed = sorted(
        {as_text(n["type"]) for i, n in index.nodes.items() if i.startswith(f"{type_name}::")}
    )
    folded = type_name.casefold()
    near = [t for t in held if folded in t.casefold() or t.casefold() in folded]
    return list(dict.fromkeys(prefixed + near))[:_SUGGESTED]


def _unknown(index: MapIndex, type_name: str) -> str:
    """The warning for a type the map does not hold, with the types it may have meant."""
    warning = f"no type named {type_name!r} is in the map; periplus types lists them"
    suggested = _suggestions(index, type_name)
    return f"{warning}; did you mean: {', '.join(suggested)}" if suggested else warning


def _strip(file: str) -> str:
    return file.removeprefix("./")


def run(
    start: Path,
    env: Mapping[str, str],
    text: str,
    types: Collection[str],
    limit: int,
    map_path: Path | None,
    paths: Collection[str] = (),
) -> FindReport:
    """Find the nodes whose id or description holds ``text``; a load failure is a problem.

    ``types`` keeps a node of any of them or their subtypes, and ``paths`` a node with a location
    whose file starts with any of them; empty keeps every node.
    """
    try:
        index = load_map(start, env, map_path)
        described, problems = node_descriptions(start, map_path)
        with reading_fields(start, map_path):
            report = _find(index, text, types, paths, described, limit)
    except HarnessError as error:
        return FindReport(problems=(error.problem(),))
    lines = SourceLines(start, map_path)
    items = tuple(replace(row, source=lines.at(row.location)) for row in report.matches.items)
    return replace(report, matches=replace(report.matches, items=items), problems=problems)


def _find(
    index: MapIndex,
    text: str,
    types: Collection[str],
    paths: Collection[str],
    described: Mapping[str, str],
    limit: int,
) -> FindReport:
    """``run``'s report, read from the map's node fields and the node descriptions."""
    warnings: list[str] = []
    wanted: set[str] | None = None
    if types:
        wanted = set()
        for type_name in sorted(set(types)):
            below = _with_subtypes(index, type_name)
            wanted |= below
            if not any(node["type"] in below for node in index.nodes.values()) and not (
                index.parent(type_name) or index.subtypes(type_name)
            ):
                warnings.append(_unknown(index, type_name))
    prefixes = sorted({_strip(p) for p in paths})
    files = {_strip(as_text(loc["file"])) for n in index.nodes.values() for loc in n["locations"]}
    for prefix in prefixes:
        if not any(file.startswith(prefix) for file in files):
            warnings.append(f"no file in the map starts with {prefix!r}")
    needle = text.casefold()
    ranked = []
    for node_id, node in index.nodes.items():
        if wanted is not None and node["type"] not in wanted:
            continue
        held = [_strip(as_text(loc["file"])) for loc in node["locations"]]
        if prefixes and not any(file.startswith(p) for file in held for p in prefixes):
            continue
        rank = _rank(as_text(node_id), needle)
        if rank is None and needle in described.get(node_id, "").casefold():
            rank = 5
        if rank is not None:
            ranked.append((rank, node_id, node))
    ranked.sort(key=lambda row: (row[0], row[1]))
    rows = [
        FindRow(
            i,
            as_text(n["type"]),
            as_text(n["state"]),
            _location(n),
            matched="description" if rank == 5 else "id",
            description=described.get(i),
        )
        for rank, i, n in ranked
    ]
    by_type = dict(sorted(Counter(row.type for row in rows).items()))
    return FindReport(cut(rows, limit), by_type, tuple(warnings))


def _narrow(report: FindReport) -> list[str]:
    """The lines that follow a cut list's footer: the match count by type, and how to narrow."""
    counts = sorted((report.by_type or {}).items(), key=lambda pair: (-pair[1], pair[0]))
    named = ", ".join(f"{_escape(t)} {n}" for t, n in counts[:_FOOTER_TYPES])
    more = len(counts) - _FOOTER_TYPES
    named += f", and {more} more types" if more > 0 else ""
    return [f"by type: {named}", "narrow with --type T or --path P"]


def render_text(report: FindReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus find", ""]
    for row in report.matches.items:
        where = row.location or "no location"
        marked = "  [description]" if row.matched == "description" else ""
        lines.append(
            f"{_escape(row.id)}  {_escape(row.type)}  {_escape(row.state)}  {_escape(where)}"
            + marked
        )
        lines += source_line(row.source)
        lines += description_line(row.description)
    if not report.matches.items:
        lines.append("no matches")
    note = footer(report.matches)
    lines += [note, *_narrow(report)] if note else []
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def _json_row(row: FindRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "location": row.location,
        "source": row.source,
        "matched": row.matched,
        "description": row.description,
    }


def render_json(report: FindReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        **payload(report.matches, _json_row),
        "by_type": dict(report.by_type or {}),
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


RENDERERS = {"text": render_text, "json": render_json}
