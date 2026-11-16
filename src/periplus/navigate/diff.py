"""``periplus diff``: what changed between two maps, thing by thing and edge by edge.

It reads and compares with ``sets``: a thing is matched by id, an edge by kind, from and to, and a
matched pair changed when ``differing`` names a field.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate import find
from periplus.navigate.count import _counted, _most
from periplus.navigate.listing import NONE, Listing, cut, footer, payload, problem_lines
from periplus.navigate.mapfile import as_json, as_text, reading_fields
from periplus.navigate.sets import EdgeKey, Loaded, differing, load, one_version
from periplus.report import _escape, _json_problem

__all__ = ["CHANGES", "LIMIT", "RENDERERS", "DiffReport", "listed", "render_json", "render_text"]

#: The three ways a thing can change, in the order the report gives them.
CHANGES = ("added", "removed", "changed")
#: The most rows each list prints, unless ``limit`` says otherwise.
LIMIT = 50
#: The header fields a map computes from its nodes and edges, which ``diff`` does not compare.
_DERIVED = frozenset({"nodes", "edges", "counts"})

K = TypeVar("K", str, EdgeKey)
Row = TypeVar("Row")


@dataclass(frozen=True, slots=True)
class ThingRow:
    """A thing added, removed or changed: its id, its type (the old one when removed) and the
    fields that changed, empty when added or removed."""

    id: str
    type: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EdgeRow:
    """An edge added, removed or changed: its kind, ends and the fields that changed."""

    kind: str
    source: str
    target: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiffReport:
    """One diff: each map as (path, things, edges), the header fields that differ, and for things
    and edges each list added, removed and changed, cut to ``limit`` rows, with its counts by
    type or kind; ``ids`` are the things of the changes asked, uncut. ``limit`` 0 names every
    type and kind in the count lines."""

    maps: tuple[tuple[str, int, int], ...] = ()
    header: tuple[str, ...] = ()
    things: Mapping[str, Listing[ThingRow]] | None = None
    edges: Mapping[str, Listing[EdgeRow]] | None = None
    thing_counts: Mapping[str, tuple[tuple[str, int], ...]] | None = None
    edge_counts: Mapping[str, tuple[tuple[str, int], ...]] | None = None
    ids: tuple[str, ...] = ()
    limit: int = LIMIT
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    old: Path,
    new: Path,
    limit: int = LIMIT,
    changes: Collection[str] = CHANGES,
) -> DiffReport:
    """Compare the map at ``old`` with the map at ``new``. A limit of 0 keeps every row."""
    try:
        before, after = load(start, env, old), load(start, env, new)
        one_version([before, after])
        with reading_fields(start, new):
            header = differing(_header(before), _header(after))
            node_changes = _compare(before.nodes, after.nodes)
            edge_changes = _compare(before.edges, after.edges)
            things = {
                change: [ThingRow(i, _type(before, after, change, i), f) for i, f in rows]
                for change, rows in node_changes.items()
            }
            edges = {
                change: [EdgeRow(*key, f) for key, f in rows]
                for change, rows in edge_changes.items()
            }
    except HarnessError as error:
        return DiffReport(problems=(error.problem(),))
    return DiffReport(
        (_size(before), _size(after)),
        header,
        {change: cut(rows, limit) for change, rows in things.items()},
        {change: cut(rows, limit) for change, rows in edges.items()},
        {c: _most(Counter(r.type for r in rows)) for c, rows in things.items()},
        {c: _most(Counter(r.kind for r in rows)) for c, rows in edges.items()},
        tuple(sorted(r.id for c in changes for r in things[c])),
        limit,
    )


def _type(before: Loaded, after: Loaded, change: str, node_id: str) -> str:
    """The thing's type in the map that holds it: the old one when it was removed."""
    return as_text((before if change == "removed" else after).nodes[node_id]["type"])


def _size(loaded: Loaded) -> tuple[str, int, int]:
    return loaded.path, len(loaded.nodes), len(loaded.edges)


def _header(loaded: Loaded) -> dict[str, Any]:
    return {k: v for k, v in loaded.document.items() if k not in _DERIVED}


def _compare(
    old: Mapping[K, Mapping[str, Any]], new: Mapping[K, Mapping[str, Any]]
) -> dict[str, list[tuple[K, tuple[str, ...]]]]:
    """The keys only ``new`` holds, only ``old`` holds, and those both hold whose copies differ,
    with the fields that do; each sorted."""
    both = sorted(old.keys() & new.keys())
    return {
        "added": [(k, ()) for k in sorted(new.keys() - old.keys())],
        "removed": [(k, ()) for k in sorted(old.keys() - new.keys())],
        "changed": [(k, f) for k in both if (f := differing(old[k], new[k]))],
    }


def listed(report: DiffReport) -> list[str]:
    """The ids of the things of the changes asked, as ``--ids`` prints them."""
    return list(report.ids)


def _total(listing: Listing[Any]) -> int:
    return listing.total


def _thing_line(row: ThingRow) -> str:
    fields = f"  ({', '.join(row.fields)})" if row.fields else ""
    return f"  {_escape(row.id)}  {_escape(row.type)}{fields}"


def _edge_line(row: EdgeRow) -> str:
    fields = f"  ({', '.join(row.fields)})" if row.fields else ""
    return f"  {_escape(row.kind)}  {_escape(row.source)} -> {_escape(row.target)}{fields}"


def _list_lines(title: str, listing: Listing[Row], line: Callable[[Row], str]) -> list[str]:
    """A list under its title, then how many it showed when it was cut; nothing when empty."""
    if not listing.items:
        return []
    said = footer(listing)
    return [f"{title}:", *(line(row) for row in listing.items), *([f"  {said}"] if said else [])]


def render_text(report: DiffReport) -> str:
    """The two maps, the header fields that differ, the counts of things by type and of edges by
    kind for each change, then each list, a cut one ending with how many it showed."""
    lines = ["periplus diff"]
    if not report.problems and report.things is not None and report.edges is not None:
        for name, (path, things, edges) in zip(("old", "new"), report.maps, strict=True):
            lines.append(f"{name}: {_escape(path)} ({things} things, {edges} edges)")
        lines.append(f"header: {', '.join(report.header) or 'same'}")
        sections: Sequence[tuple[str, Mapping[str, Listing[Any]], Any, str]] = (
            ("things", report.things, report.thing_counts or {}, "type"),
            ("edges", report.edges, report.edge_counts or {}, "kind"),
        )
        for noun, lists, counted, by in sections:
            lines.append(f"{noun}: " + ", ".join(f"{_total(lists[c])} {c}" for c in CHANGES))
            lines += [
                f"  {c} by {by}: "
                + (
                    find._counted(Counter(dict(counted[c])), f"{by}s")
                    if report.limit
                    else _counted(counted[c])
                )
                for c in CHANGES
                if counted[c]
            ]
        for change in CHANGES:
            lines += _list_lines(f"things {change}", report.things[change], _thing_line)
        for change in CHANGES:
            lines += _list_lines(f"edges {change}", report.edges[change], _edge_line)
        cut_any = any(x.truncated for x in [*report.things.values(), *report.edges.values()])
        lines += ["--limit 0 prints every row"] if cut_any else []
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _json_thing(row: ThingRow) -> dict[str, Any]:
    return {"id": row.id, "type": row.type, "fields": list(row.fields)}


def _json_edge(row: EdgeRow) -> dict[str, Any]:
    return {"kind": row.kind, "from": row.source, "to": row.target, "fields": list(row.fields)}


def render_json(report: DiffReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    things = report.things or {c: NONE for c in CHANGES}
    edges = report.edges or {c: NONE for c in CHANGES}
    return as_json(
        {
            "command": "diff",
            "maps": [{"path": p, "things": t, "edges": e} for p, t, e in report.maps],
            "header": list(report.header),
            "things": {c: payload(things[c], _json_thing) for c in CHANGES},
            "edges": {c: payload(edges[c], _json_edge) for c in CHANGES},
            "things_by_type": {c: dict((report.thing_counts or {}).get(c, ())) for c in CHANGES},
            "edges_by_kind": {c: dict((report.edge_counts or {}).get(c, ())) for c in CHANGES},
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
