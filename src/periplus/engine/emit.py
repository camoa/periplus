"""Step four: merge nodes and edges, then build the map document and its canonical text."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from periplus.engine.packload import BoundaryEntry, EdgeKind, TypeInfo
from periplus.engine.rules import FoundEdge, FoundNode, Skipped
from periplus.errors import ExitCode, HarnessError
from periplus.manifest import LoadedPack

__all__ = ["EdgeIllegal", "TypeCollision", "build_document", "render", "type_chain"]


class TypeCollision(HarnessError):
    """Rules found types for one id that do not lie on one ancestor chain."""

    code = ExitCode.TYPE_COLLISION


class EdgeIllegal(HarnessError):
    """An edge's end has a type its kind does not allow there."""

    code = ExitCode.EDGE_ILLEGAL


def build_document(
    nodes: Sequence[FoundNode],
    edges: Sequence[FoundEdge],
    types: Mapping[str, TypeInfo],
    edge_kinds: Mapping[str, EdgeKind],
    packs: Sequence[LoadedPack],
    tool_version: str,
    settings: str,
    boundary: Mapping[str, BoundaryEntry] | None = None,
    skipped: list[Skipped] | None = None,
) -> dict[str, Any]:
    """The map document.

    Nodes merge on id and the most specific type found wins. An attribute whose contributions
    differ is written as ``{"differs": [...]}``. Edges merge on kind, from and to, and an end no
    rule found becomes a referenced node, of the deepest type its edges claim, an edge's named
    ``target_type`` among them; an end written ``{declared: <type>}`` claims that type alone. An
    end no rule found that an edge declared ``on_miss`` for is
    unresolved instead, with the first such edge's rule, by pack and rule, in its detail, and the
    types that edge's end tried, in order. An end that lists none tried its one declared type,
    else its kind's types at that end. An end with candidate ids lands on the first a rule
    found, else on the first. An end no rule found whose id ``boundary`` lists is instead a
    declared node, its one provenance the group's pack, of the deepest type the group's type and
    its edges' claimed types that share a chain with it agree on, as for a referenced end; an edge
    whose kind has no type on a chain with the group's type at that end raises ``EdgeIllegal``.
    Then each mapped node whose ancestry reaches such a node with a classification is classified,
    as ``_classify`` says, and its rows join ``skipped``. Locations and provenance de-duplicate and
    sort.
    """
    groups: dict[str, list[FoundNode]] = {}
    for found in nodes:
        groups.setdefault(found.id, []).append(found)
    merged = {node_id: _merge_node(group, types) for node_id, group in groups.items()}
    edges = [_landed(edge, merged) for edge in edges]

    merged_edges: dict[tuple[str, str, str], list[FoundEdge]] = {}
    for edge in edges:
        merged_edges.setdefault((edge.kind, edge.source, edge.target), []).append(edge)
    referring: dict[str, set[tuple[str, str, str]]] = {}
    claimed: dict[str, set[str]] = {}
    for kind, source, target in sorted(merged_edges):
        allowed = edge_kinds[kind]
        group = merged_edges[(kind, source, target)]
        named = tuple(e.target_type for e in group if e.target_type)
        starts = tuple(e.source_type for e in group if e.source_type)
        # An end with candidate types, or written {declared: <type>}, takes the type it names, not
        # the kind's.
        listed = any(e.candidates for e in group)
        alone = {side for e in group for side in e.declared_ends}
        for at, end, ends, kind_types in (
            (
                "from",
                source,
                starts if (listed or "source" in alone) and starts else allowed.from_types + starts,
                allowed.from_types,
            ),
            (
                "to",
                target,
                named if (listed or "target" in alone) and named else allowed.to_types + named,
                allowed.to_types,
            ),
        ):
            if end not in merged and boundary and end in boundary:
                merged[end] = _declared(end, boundary[end])
            if end not in merged:
                merged[end] = {"id": end, "type": "", "state": "referenced", "locations": []}
            if boundary and end in boundary and merged[end]["state"] == "declared":
                entry = boundary[end]
                chain = type_chain(types, entry.type)
                fits = {
                    t
                    for t in {*kind_types, *ends}
                    if t in chain or entry.type in type_chain(types, t)
                }
                if not fits & set(kind_types):
                    raise EdgeIllegal(
                        f"the edge {kind} from {source} to {target} needs its {at} end to be one "
                        f"of {', '.join(kind_types)}, and the boundary group {entry.group} of "
                        f"{entry.pack} lists {end} as {entry.type}",
                        {"kind": kind, "from": source, "to": target, "group": entry.group},
                    )
                claimed.setdefault(end, {entry.type}).update(fits & set(ends))
            if merged[end]["state"] == "referenced":
                claimed.setdefault(end, set()).update(ends)
                referring.setdefault(end, set()).update(
                    (e.pack, e.rule, e.confidence) for e in merged_edges[(kind, source, target)]
                )
    for end, names in claimed.items():
        merged[end]["type"] = _referenced_type(names, types)
    for end, rules in referring.items():
        merged[end]["provenance"] = [
            {"pack": pack, "rule": rule, "confidence": confidence, "sets": ["id"]}
            for pack, rule, confidence in sorted(rules)
        ]
    if boundary:
        rows = _classify(merged, merged_edges, boundary, types)
        if skipped is not None:
            skipped.extend(rows)
    missed = sorted(
        (
            (edge.source if edge.on_miss == "source" else edge.target, edge.pack, edge.rule, edge)
            for edge in edges
            if edge.on_miss
        ),
        key=lambda item: (*item[:3], item[3].searched_for),
    )
    for end, pack, rule, edge in missed:
        if merged[end]["state"] == "referenced":
            allowed = edge_kinds[edge.kind]
            if edge.on_miss == "source":
                declared, kind_types = edge.source_type, allowed.from_types
            else:
                declared, kind_types = edge.target_type, allowed.to_types
            merged[end]["state"] = "unresolved"
            merged[end]["unresolved_detail"] = {
                "rule": f"{pack}/{rule}",
                "searched_for": edge.searched_for,
                "found": "no mapped node of this name",
                "types_tried": list(edge.types_tried or ((declared,) if declared else kind_types)),
            }
    ordered = [merged[node_id] for node_id in sorted(merged)]
    written = [
        _edge(key, group, merged, edge_kinds, types) for key, group in sorted(merged_edges.items())
    ]
    return {
        "periplus_map_version": 0,
        "generated_by": f"periplus {tool_version}",
        "packs": sorted(
            ({"pack": p.name.pack, "version": p.name.version} for p in packs),
            key=lambda entry: entry["pack"],
        ),
        "settings": settings,
        "roots": ["."],
        "type_hierarchy": _hierarchy({str(node["type"]) for node in ordered}, types),
        "counts": {
            "nodes": len(ordered),
            "edges": len(written),
            "edges_by_kind": dict(sorted(Counter(str(edge["kind"]) for edge in written).items())),
            "nodes_by_state": dict(sorted(Counter(str(n["state"]) for n in ordered).items())),
            "nodes_by_type": dict(sorted(Counter(str(node["type"]) for node in ordered).items())),
        },
        "nodes": ordered,
        "edges": written,
    }


def _landed(edge: FoundEdge, merged: Mapping[str, Any]) -> FoundEdge:
    """The edge with its composed end on the first candidate id a rule found, else the first."""
    if not edge.candidates:
        return edge
    chosen = next((c for c in edge.candidates if c in merged), edge.candidates[0])
    # A composed end that is the from end names its type in source_type.
    return replace(edge, source=chosen) if edge.source_type else replace(edge, target=chosen)


def _declared(node_id: str, entry: BoundaryEntry) -> dict[str, Any]:
    """The node a boundary group draws for a name an edge reached."""
    rule = f"boundary.{entry.group}"
    return {
        "id": node_id,
        "type": entry.type,
        "state": "declared",
        "locations": [],
        "provenance": [
            {"pack": entry.pack, "rule": rule, "confidence": "declared", "sets": ["id", "type"]}
        ],
    }


def _classify(
    merged: dict[str, dict[str, Any]],
    merged_edges: Mapping[tuple[str, str, str], Sequence[FoundEdge]],
    boundary: Mapping[str, BoundaryEntry],
    types: Mapping[str, TypeInfo],
) -> list[Skipped]:
    """Classify each mapped node whose ancestry reaches a declared boundary node that classifies.

    From each such boundary node the walk follows its entry's ancestry edges backwards, through
    mapped nodes only. A node reached takes the deepest classification that reaches it when its
    type is on that one's chain, and keeps a type equal to or below it; either way it gains an
    inferred provenance row per listing group. A node whose type, or whose classifications, do not
    lie on one chain keeps its type and gives one skipped row.
    """
    sources: dict[tuple[str, str], set[str]] = {}
    for kind, source, target in merged_edges:
        sources.setdefault((kind, target), set()).add(source)
    reached: dict[str, set[str]] = {}
    for start in sorted(boundary):
        entry = boundary[start]
        if not entry.classifies or start not in merged or merged[start]["state"] != "declared":
            continue
        seen, pending = {start}, [start]
        while pending:
            current = pending.pop(0)
            below = {s for kind in entry.ancestry for s in sources.get((kind, current), ())}
            for node_id in sorted(below):
                if node_id not in seen and merged[node_id]["state"] == "mapped":
                    seen.add(node_id)
                    reached.setdefault(node_id, set()).add(start)
                    pending.append(node_id)
    rows: list[Skipped] = []
    for node_id in sorted(reached):
        node, starts = merged[node_id], sorted(reached[node_id])
        deepest = max(starts, key=lambda s: len(type_chain(types, str(boundary[s].classifies))))
        target = str(boundary[deepest].classifies)
        chain = type_chain(types, target)
        off = [s for s in starts if boundary[s].classifies not in chain]
        if off or node["type"] not in chain and target not in type_chain(types, node["type"]):
            start = off[0] if off else deepest
            reason = (
                f"{node_id}: classification {boundary[start].classifies} from {start} "
                f"does not descend from {target if off else node['type']}"
            )
            place = node["locations"][0]
            rows.append((place["file"], place["line"], f"boundary.{boundary[start].group}", reason))
            continue
        if node["type"] in chain:
            node["type"] = target
        node["provenance"] += [
            {"pack": pack, "rule": f"boundary.{group}", "confidence": "inferred", "sets": ["type"]}
            for pack, group in sorted({(boundary[s].pack, boundary[s].group) for s in starts})
        ]
    return rows


def type_chain(types: Mapping[str, TypeInfo], name: str) -> list[str]:
    """The type and its ancestors, nearest first."""
    chain: list[str] = []
    while name in types and name not in chain:
        chain.append(name)
        parent = types[name].parent
        if parent is None:
            break
        name = parent
    return chain or [name]


def _referenced_type(names: set[str], types: Mapping[str, TypeInfo]) -> str:
    """The deepest of the types the edges claim when one chain holds them all, else the first."""
    deepest = max(sorted(names), key=lambda name: len(type_chain(types, name)))
    if all(name in type_chain(types, deepest) for name in names):
        return deepest
    return min(names)


def _merge_node(group: Sequence[FoundNode], types: Mapping[str, TypeInfo]) -> dict[str, Any]:
    found = sorted({node.type for node in group})
    deepest = max(found, key=lambda name: len(type_chain(types, name)))
    if any(name not in type_chain(types, deepest) for name in found):
        raise TypeCollision(
            f"{group[0].id} was found as {', '.join(found)}, which do not lie on one type chain",
            {"id": group[0].id, "types": ", ".join(found)},
        )
    values: dict[str, dict[tuple[str, int], Any]] = {}
    named: dict[tuple[str, str, str], set[str]] = {}
    for node in group:
        sets = named.setdefault((node.pack, node.rule, node.confidence), set())
        for name, value, line in node.attributes:
            values.setdefault(name, {})[(node.file, line)] = value
            sets.add(name)
    result: dict[str, Any] = {
        "id": group[0].id,
        "type": deepest,
        "state": "mapped",
        "locations": [
            {"file": f, "line": n} for f, n in sorted({(node.file, node.line) for node in group})
        ],
        "provenance": [
            {"pack": p, "rule": r, "confidence": c, "sets": ["id", "type", *sorted(names)]}
            for (p, r, c), names in sorted(named.items())
        ],
    }
    attributes = {name: _attribute(contributions) for name, contributions in values.items()}
    if attributes:
        result["attributes"] = dict(sorted(attributes.items()))
    return result


def _attribute(contributions: Mapping[tuple[str, int], Any]) -> Any:
    """The value when every contribution agrees; otherwise every contribution, none winning."""
    ordered = sorted(contributions.items(), key=lambda item: item[0])
    if len({json.dumps(value, sort_keys=True) for _, value in ordered}) == 1:
        return ordered[0][1]
    return {"differs": [{"file": f, "line": n, "value": value} for (f, n), value in ordered]}


def _edge(
    key: tuple[str, str, str],
    group: Sequence[FoundEdge],
    merged: Mapping[str, Mapping[str, Any]],
    edge_kinds: Mapping[str, EdgeKind],
    types: Mapping[str, TypeInfo],
) -> dict[str, Any]:
    kind, source, target = key
    for end, allowed in (
        (source, edge_kinds[kind].from_types),
        (target, edge_kinds[kind].to_types),
    ):
        if merged[end]["state"] != "mapped":
            continue
        if not set(allowed) & set(type_chain(types, merged[end]["type"])):
            raise EdgeIllegal(
                f"the edge {kind} from {source} to {target} needs {end} to be one of "
                f"{', '.join(allowed)}, and it is {merged[end]['type']}",
                {"kind": kind, "from": source, "to": target},
            )
    places = sorted({(edge.file, edge.line) for edge in group})
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "occurrences": len(places),
        "locations": [{"file": f, "line": n} for f, n in places],
        "provenance": [
            {"pack": p, "rule": r, "confidence": c}
            for p, r, c in sorted({(e.pack, e.rule, e.confidence) for e in group})
        ],
    }


def _hierarchy(used: set[str], types: Mapping[str, TypeInfo]) -> list[dict[str, str | None]]:
    """The used types and every ancestor of them, each with its parent, sorted by type."""
    closure: set[str] = set()
    pending = sorted(used)
    while pending:
        name = pending.pop()
        if name not in closure:
            closure.add(name)
            parent = types[name].parent
            if parent is not None:
                pending.append(parent)
    return [{"type": name, "parent": types[name].parent} for name in sorted(closure)]


def render(document: Mapping[str, object]) -> str:
    """The canonical text: sorted keys, two-space indent, ASCII, one trailing LF."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
