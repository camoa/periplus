"""``periplus legend``: what each edge kind and node type the map holds means, how often it
occurs, and which types its edges join, most frequent first."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import kind_warnings, problem_lines
from periplus.navigate.mapfile import as_json, as_text, causes, load_document, reading_fields
from periplus.report import _escape, _json_problem

__all__ = [
    "BYTE_LIMIT",
    "RENDERERS",
    "KindRow",
    "LegendReport",
    "TypeRow",
    "render_json",
    "render_text",
    "run",
]

#: The bytes the default text aims at; the least frequent rows are left out past it.
BYTE_LIMIT = 3 * 1024
#: The types one end of a kind's line names before it counts the rest.
END_TYPES = 2

Counted = tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class KindRow:
    """An edge kind the map holds: its edges, the types at each end by count, its text, and the
    end that sets off the other, ``None`` when the map lists none."""

    kind: str
    count: int
    from_types: Counted
    to_types: Counted
    description: str | None
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class TypeRow:
    """A node type the map holds: its nodes, its parent, its text, and the kinds of the edges
    leaving and reaching its nodes by count."""

    type: str
    count: int
    parent: str | None
    description: str | None
    outgoing: Counted
    incoming: Counted


@dataclass(frozen=True, slots=True)
class LegendReport:
    """The kinds and types, most frequent first; ``full`` when one was asked for by name, and
    ``left_out`` the rows the byte budget dropped."""

    edge_kinds: tuple[KindRow, ...] = ()
    node_types: tuple[TypeRow, ...] = ()
    full: bool = False
    left_out: int = 0
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _ranked(counter: Counter[str]) -> Counted:
    return tuple(sorted(counter.items(), key=lambda p: (-p[1], p[0])))


def run(
    start: Path,
    env: Mapping[str, str],
    map_path: Path | None,
    kinds: Collection[str] = (),
    types: Collection[str] = (),
    everything: bool = False,
) -> LegendReport:
    """The legend of the map. ``kinds`` and ``types`` print only those, in full; otherwise the
    least frequent rows are left out past ``BYTE_LIMIT`` unless ``everything``."""
    try:
        document = load_document(start, env, map_path)[1]
        with reading_fields(start, map_path):
            texts = document.get("legend", {})
            kind_texts: Mapping[str, Any] = texts.get("edge_kinds", {})
            type_texts: Mapping[str, Any] = texts.get("node_types", {})
            parents = {row["type"]: row.get("parent") for row in document.get("type_hierarchy", [])}
            type_of = {as_text(n["id"]): as_text(n["type"]) for n in document["nodes"]}
            nodes = Counter(type_of.values())
            edges: Counter[str] = Counter()
            ends: dict[str, tuple[Counter[str], Counter[str]]] = {}
            links: dict[str, tuple[Counter[str], Counter[str]]] = {}
            for edge in document["edges"]:
                kind = as_text(edge["kind"])
                source, target = type_of[edge["from"]], type_of[edge["to"]]
                edges[kind] += 1
                at = ends.setdefault(kind, (Counter(), Counter()))
                at[0][source] += 1
                at[1][target] += 1
                links.setdefault(source, (Counter(), Counter()))[0][kind] += 1
                links.setdefault(target, (Counter(), Counter()))[1][kind] += 1
            cause = causes(document)
            kind_rows = [
                KindRow(
                    k, n, _ranked(ends[k][0]), _ranked(ends[k][1]), kind_texts.get(k), cause.get(k)
                )
                for k, n in _ranked(edges)
                if not (kinds or types) or k in kinds
            ]
            type_rows = [
                TypeRow(
                    t,
                    n,
                    parents.get(t),
                    type_texts.get(t),
                    *(_ranked(c) for c in links.get(t, (Counter(), Counter()))),
                )
                for t, n in _ranked(nodes)
                if not (kinds or types) or t in types
            ]
    except HarnessError as error:
        return LegendReport(problems=(error.problem(),))
    warnings = kind_warnings(kinds, set(edges)) + tuple(
        f"the map holds no node of type {t!r}" for t in sorted(set(types) - set(nodes))
    )
    report = LegendReport(tuple(kind_rows), tuple(type_rows), bool(kinds or types), 0, warnings)
    while not (report.full or everything) and len(render_text(report).encode()) > BYTE_LIMIT:
        if not (kind_rows or type_rows):
            break
        # The row with the fewest edges or nodes goes first; a type before a kind on a tie.
        if type_rows and (not kind_rows or type_rows[-1].count <= kind_rows[-1].count):
            type_rows.pop()
        else:
            kind_rows.pop()
        report = replace(
            report,
            edge_kinds=tuple(kind_rows),
            node_types=tuple(type_rows),
            left_out=report.left_out + 1,
        )
    return report


def _short(counted: Counted) -> str:
    names = ", ".join(_escape(name) for name, _ in counted[:END_TYPES])
    return names + (f" +{len(counted) - END_TYPES}" if len(counted) > END_TYPES else "")


def _all(counted: Counted) -> str:
    return ", ".join(f"{_escape(name)} {n}" for name, n in counted) or "none"


def _said(description: str | None) -> list[str]:
    return [f"      {_escape(description)}"] if description else []


def render_text(report: LegendReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus legend"]
    if report.edge_kinds or not report.full:
        lines += ["", "Edge kinds, most edges first:"]
    for k in report.edge_kinds:
        ends = f"{_short(k.from_types)} -> {_short(k.to_types)}"
        cause = f"  cause: {k.cause}" if k.cause else ""
        lines.append(f"  {_escape(k.kind)}  {k.count}  {ends}{cause}")
        lines += _said(k.description)
        if report.full:
            lines += [f"      from: {_all(k.from_types)}", f"      to: {_all(k.to_types)}"]
    if report.node_types or not report.full:
        lines += ["", "Node types, most nodes first:"]
    for t in report.node_types:
        parent = _escape(t.parent) if t.parent is not None else "none"
        lines.append(f"  {_escape(t.type)}  {t.count}  parent: {parent}")
        lines += _said(t.description)
        if report.full:
            lines += [f"      out: {_all(t.outgoing)}", f"      in: {_all(t.incoming)}"]
    if report.left_out:
        lines += [
            "",
            f"{report.left_out} left out, the fewest edges or nodes first; --all prints every "
            "one, --kind K or --type T prints one in full",
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: LegendReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "edge_kinds": [
                {
                    "kind": k.kind,
                    "count": k.count,
                    "from": dict(k.from_types),
                    "to": dict(k.to_types),
                    "description": k.description,
                    "cause": k.cause,
                }
                for k in report.edge_kinds
            ],
            "node_types": [
                {
                    "type": t.type,
                    "count": t.count,
                    "parent": t.parent,
                    "description": t.description,
                    "out": dict(t.outgoing),
                    "in": dict(t.incoming),
                }
                for t in report.node_types
            ],
            "left_out": report.left_out,
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
