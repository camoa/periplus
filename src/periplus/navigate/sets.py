"""``periplus join``, ``common`` and ``minus``: map files read as sets of things and edges.

A thing is the same thing in two maps when its id is the same; an edge is the same edge when its
kind, from and to are. Two copies of one thing or edge that differ in any other field are still
one thing or edge: the result keeps the copy whose JSON, keys sorted, sorts first, and a warning
counts them. ``diff`` compares with the same ``load``, ``edge_key`` and ``differing``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar

from periplus.engine.emit import counts, hierarchy
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate.count import _counted, _most
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import as_json, as_text, load_document, reading_fields
from periplus.report import _escape, _json_problem

__all__ = [
    "RENDERERS",
    "Loaded",
    "SetReport",
    "differing",
    "edge_key",
    "listed",
    "load",
    "render_json",
    "render_text",
    "run",
    "sub_document",
]

#: The header fields a result computes from its own nodes and edges, never takes from an input.
_DERIVED = frozenset({"nodes", "edges", "counts", "type_hierarchy"})
#: The text fields of a header; several inputs' values are joined with this.
_JOIN = "; "
#: How many ids of differing things a warning names.
_NAMED = 3

EdgeKey = tuple[str, str, str]
K = TypeVar("K", str, EdgeKey)


class MixedVersions(HarnessError):
    """The inputs are maps of different ``periplus_map_version``."""

    code = ExitCode.USAGE


def sub_document(
    header: Mapping[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    parent: Callable[[str], str | None],
) -> dict[str, Any]:
    """A map holding ``nodes`` and ``edges`` under ``header``'s fields: its counts and type
    hierarchy made from them, and its legend cut to the kinds and types they hold."""
    piece: dict[str, Any] = {
        **header,
        "counts": counts(nodes, edges),
        "nodes": nodes,
        "edges": edges,
        "type_hierarchy": hierarchy({str(node["type"]) for node in nodes}, parent),
    }
    texts = piece.pop("legend", {})
    held_names = {
        "edge_kinds": {edge["kind"] for edge in edges},
        "node_types": {node["type"] for node in nodes},
    }
    legend = {
        section: given
        for section, names in held_names.items()
        if (given := {k: v for k, v in texts.get(section, {}).items() if k in names})
    }
    if legend:
        piece["legend"] = legend
    return piece


def edge_key(edge: Mapping[str, Any]) -> EdgeKey:
    """What makes two edges the same edge: kind, from and to."""
    return as_text(edge["kind"]), as_text(edge["from"]), as_text(edge["to"])


_MISSING = object()


def differing(old: Mapping[str, Any], new: Mapping[str, Any]) -> tuple[str, ...]:
    """The fields whose values differ between two copies, a field one copy lacks among them,
    sorted."""
    return tuple(
        sorted(k for k in old.keys() | new.keys() if old.get(k, _MISSING) != new.get(k, _MISSING))
    )


def _canonical(item: Any) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class Loaded:
    """One input map: the path as given, the document, its nodes by id and its edges by key."""

    path: str
    document: Mapping[str, Any]
    nodes: Mapping[str, dict[str, Any]]
    edges: Mapping[EdgeKey, dict[str, Any]]


def load(start: Path, env: Mapping[str, str], path: Path) -> Loaded:
    """Read the map at ``path``; ``NotAMap`` when it has no map's outline or a malformed row."""
    _, document = load_document(start, env, path)
    with reading_fields(start, path):
        nodes = {as_text(node["id"]): node for node in document["nodes"]}
        edges = {edge_key(edge): edge for edge in document["edges"]}
    return Loaded(str(path), document, nodes, edges)


def one_version(maps: Sequence[Loaded]) -> None:
    """``MixedVersions`` unless every map has the same ``periplus_map_version``."""
    versions = {m.document["periplus_map_version"] for m in maps}
    if len(versions) > 1:
        said = ", ".join(f"{m.path} {m.document['periplus_map_version']}" for m in maps)
        raise MixedVersions(f"the maps are of different versions ({said}); give maps of one", {})


@dataclass(frozen=True, slots=True)
class SetReport:
    """One ``join``, ``common`` or ``minus`` run: each input as (path, things, edges), the
    result's counts, its ids, and the file written, ``None`` when none was."""

    command: str
    inputs: tuple[tuple[str, int, int], ...] = ()
    things: int = 0
    edges: int = 0
    by_type: tuple[tuple[str, int], ...] = ()
    by_state: tuple[tuple[str, int], ...] = ()
    by_kind: tuple[tuple[str, int], ...] = ()
    ids: tuple[str, ...] = ()
    out: str | None = None
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path, env: Mapping[str, str], command: str, paths: Sequence[Path], out: Path | None
) -> SetReport:
    """``join`` (in any input), ``common`` (in every input) or ``minus`` (in the first input and
    in no other) of the maps at ``paths``; write the result to ``out`` when given.

    ``minus`` keeps the first map's header and the edges among the things it keeps. ``join`` and
    ``common`` merge the headers and list the inputs by path, so their order changes nothing.
    """
    if len(paths) < 2:
        message = f"{command} takes two map files or more"
        return SetReport(command, problems=(Problem(ExitCode.USAGE, message, {}),))
    rest = sorted(paths[1:], key=str)
    ordered = [paths[0], *rest] if command == "minus" else sorted(paths, key=str)
    try:
        maps = [load(start, env, path) for path in ordered]
        one_version(maps)
        target = None if out is None else start / out
        if target is not None and any(target.resolve() == Path(m.path).resolve() for m in maps):
            message = f"--out {target} is one of the maps being read; choose another file"
            problem = Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)})
            return SetReport(command, problems=(problem,))
        with reading_fields(start, ordered[0]):
            document, warnings = _combine(command, maps)
    except HarnessError as error:
        return SetReport(command, problems=(error.problem(),))
    nodes, edges = document["nodes"], document["edges"]
    report = SetReport(
        command,
        tuple((m.path, len(m.nodes), len(m.edges)) for m in maps),
        len(nodes),
        len(edges),
        _most(Counter(str(n["type"]) for n in nodes)),
        _most(Counter(str(n["state"]) for n in nodes)),
        _most(Counter(str(e["kind"]) for e in edges)),
        tuple(str(n["id"]) for n in nodes),
        None,
        warnings,
    )
    if target is None:
        return report
    problems = write_document(document, target)
    if problems:
        return SetReport(command, problems=problems)
    return replace(report, out=str(target))


def _combine(command: str, maps: Sequence[Loaded]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """The result document and the warning that counts differing copies, if any."""
    if command == "minus":
        first = maps[0]
        gone = set().union(*(m.nodes for m in maps[1:]))
        nodes = [node for i, node in sorted(first.nodes.items()) if i not in gone]
        kept = {as_text(node["id"]) for node in nodes}
        edges = [e for k, e in sorted(first.edges.items()) if k[1] in kept and k[2] in kept]
        parents = _parents([first.document])
        return sub_document(first.document, nodes, edges, parents.get), ()
    every = command == "common"
    node_ids = _keys([m.nodes for m in maps], every)
    edge_keys = _keys([m.edges for m in maps], every)
    nodes, split_nodes = _picked([m.nodes for m in maps], node_ids)
    edges, split_edges = _picked([m.edges for m in maps], edge_keys)
    documents = [m.document for m in maps]
    document = sub_document(_header(documents), nodes, edges, _parents(documents).get)
    warnings: tuple[str, ...] = ()
    if split_nodes or split_edges:
        named = ", ".join(split_nodes[:_NAMED]) or " ".join(split_edges[0])
        warnings = (
            f"{len(split_nodes)} things and {len(split_edges)} edges differ between the maps, "
            f"as {named}; the result keeps the copy whose JSON sorts first; periplus diff names "
            "the fields",
        )
    return document, warnings


def _keys(held: Sequence[Mapping[K, Any]], every: bool) -> list[K]:
    """The keys in every one of ``held`` when ``every``, else in any, sorted."""
    sets = [set(h) for h in held]
    return sorted(set.intersection(*sets) if every else set.union(*sets))


def _picked(
    held: Sequence[Mapping[K, dict[str, Any]]], keys: Sequence[K]
) -> tuple[list[dict[str, Any]], list[K]]:
    """For each key, the one copy the result keeps, and the keys whose copies differ."""
    kept: list[dict[str, Any]] = []
    split: list[K] = []
    for key in keys:
        copies = [h[key] for h in held if key in h]
        if any(differing(copies[0], copy) for copy in copies[1:]):
            split.append(key)
            kept.append(min(copies, key=_canonical))
        else:
            kept.append(copies[0])
    return kept, split


def _parents(documents: Sequence[Mapping[str, Any]]) -> dict[str, str | None]:
    """Each type's parent by the documents' ``type_hierarchy``; of different parents, the one
    whose JSON sorts first."""
    given: dict[str, list[str | None]] = {}
    for document in documents:
        for row in document.get("type_hierarchy", []):
            given.setdefault(as_text(row["type"]), []).append(row.get("parent"))
    return {name: min(parents, key=_canonical) for name, parents in given.items()}


def _header(documents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The inputs' header fields merged: a list field's items, each once, sorted by JSON; a text
    field's values, each once, sorted and joined with ``; ``; an object field merged by key; any
    other field the value whose JSON sorts first."""
    names = sorted(set().union(*documents) - _DERIVED)
    return {name: _merged([d[name] for d in documents if name in d]) for name in names}


def _merged(values: Sequence[Any]) -> Any:
    if all(isinstance(v, list) for v in values):
        items = {_canonical(item): item for value in values for item in value}
        return [items[text] for text in sorted(items)]
    if all(isinstance(v, str) for v in values):
        return _JOIN.join(sorted({part for v in values for part in v.split(_JOIN)}))
    if all(isinstance(v, dict) for v in values):
        keys = sorted(set().union(*values))
        return {k: _merged([v[k] for v in values if k in v]) for k in keys}
    return min(values, key=_canonical)


def listed(report: SetReport) -> list[str]:
    """The ids of the result, as ``--ids`` prints them."""
    return list(report.ids)


def render_text(report: SetReport) -> str:
    """The inputs, the result's size, its things by type and state and its edges by kind, then
    the file written."""
    lines = [f"periplus {report.command}"]
    if not report.problems:
        shown = [f"{_escape(path)} ({n} things, {e} edges)" for path, n, e in report.inputs]
        given = ", ".join(shown)
        if report.command == "minus":
            given = f"{shown[0]} minus {', '.join(shown[1:])}"
        lines += [
            f"inputs: {given}",
            f"result: {report.things} things, {report.edges} edges",
            f"by type: {_counted(report.by_type)}",
            f"by state: {_counted(report.by_state)}",
            f"edges by kind: {_counted(report.by_kind)}",
        ]
        if report.out is not None:
            wrote = f"wrote {_escape(report.out)}: {report.things} nodes, {report.edges} edges"
            lines.append(wrote)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: SetReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": report.command,
            "inputs": [{"path": p, "things": t, "edges": e} for p, t, e in report.inputs],
            "things": report.things,
            "edges": report.edges,
            "by_type": dict(report.by_type),
            "by_state": dict(report.by_state),
            "by_kind": dict(report.by_kind),
            "out": report.out,
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


RENDERERS = {"text": render_text, "json": render_json}
