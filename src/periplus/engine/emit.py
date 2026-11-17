"""Step four: merge nodes and edges, then build the map document and its canonical text."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from periplus.engine.packload import Attribute, BoundaryEntry, EdgeKind, TypeInfo
from periplus.engine.rules import FoundEdge, FoundNode, Skipped
from periplus.errors import ExitCode, HarnessError
from periplus.manifest import LoadedPack

__all__ = [
    "TYPE_CONFLICT",
    "EdgeIllegal",
    "LeftOut",
    "TypeCollision",
    "build_document",
    "counts",
    "hierarchy",
    "render",
    "type_chain",
]


#: The attribute the engine, and no rule, writes on a node that rules type as conflicting types.
TYPE_CONFLICT = "type_conflict"


class TypeCollision(HarnessError):
    """Rules found types for one id that share no ancestor type."""

    code = ExitCode.TYPE_COLLISION


class EdgeIllegal(HarnessError):
    """An edge's end has a type its kind does not allow there."""

    code = ExitCode.EDGE_ILLEGAL


@dataclass(frozen=True, slots=True)
class LeftOut:
    """How many nodes and edges of an internal type the written map leaves out, and how many
    edges it leaves out because a node of conflicting types cannot carry them."""

    nodes: int = 0
    edges: int = 0
    unclear_edges: int = 0


def build_document(
    nodes: Sequence[FoundNode],
    edges: Sequence[FoundEdge],
    types: Mapping[str, TypeInfo],
    edge_kinds: Mapping[str, EdgeKind],
    packs: Sequence[LoadedPack],
    tool_version: str,
    settings: str,
    boundary: Mapping[str, Sequence[BoundaryEntry]] | None = None,
    skipped: list[Skipped] | None = None,
    supporting: Sequence[str] = (),
    attributes: Mapping[str, Attribute] | None = None,
) -> tuple[dict[str, Any], LeftOut]:
    """The map document, and what it leaves out.

    Nodes merge on id and the most specific type found wins. Types on different branches of one
    ancestor give the nearest type every one descends from, and ``_merge_node`` names each
    candidate in the attribute ``type_conflict``; an edge an end of such a node cannot carry as
    that type is left out, and ``LeftOut`` counts it. Types that share no ancestor raise
    ``TypeCollision``. An attribute whose contributions
    differ is written as ``{"differs": [...]}``. Edges merge on kind, from and to, and an end no
    rule found becomes a referenced node, of the deepest type its edges claim that is not
    internal, an edge's named ``target_type`` among them; an end written ``{declared: <type>}``
    claims that type alone. An end no rule found that an edge declared ``on_miss`` for is
    unresolved instead, with the first such edge's rule, by pack and rule, in its detail, and the
    types that edge's end tried, in order. An end that lists none tried its one declared type,
    else its kind's types at that end. An end with candidate ids lands on the first a rule
    found, else on the first. An end no rule found whose id ``boundary`` lists is instead a
    boundary node, one provenance row per listing group, of the deepest type the groups' types and
    its edges' claimed types that share a chain with them agree on, as for a referenced end; an
    edge whose kind has no type on a chain with a group's type at that end raises ``EdgeIllegal``.
    Then each mapped node whose ancestry reaches such a node with a classification is classified,
    as ``_classify`` says, and its rows join ``skipped``.

    An end no rule found takes the strongest mark its edges and its type give, whatever the rule
    and file order: an edge whose end has ``boundary``, or a type at or below a boundary type,
    makes it boundary, which beats ``on_miss: unresolved``, which beats ``on_miss:
    unknown_boundary``; an end with no mark stays referenced. The detail of an unresolved or
    unknown boundary end names the first edge of that mark, by pack, rule and name searched for.
    An end that reads boundary by an edge's ``boundary`` also gets that edge's into edge, to the
    into node, which reads boundary by its type. A node a rule found is mapped, except one whose
    ``resolution`` attribute is runtime, which is an unknown boundary. Locations and provenance
    de-duplicate and sort. Then a node whose type is internal, or lies below an internal type, is
    left out with every edge that has an end on it; ``LeftOut`` counts each. Last, each declared
    ``attributes`` entry that spreads reaches members through grouping edges and the kinds it lists
    in ``spreads_along``, as ``_spread`` says, and the header ``marks`` names the mark of each
    declared attribute a written node holds.
    """
    groups: dict[str, list[FoundNode]] = {}
    for found in nodes:
        groups.setdefault(found.id, []).append(found)
    merged = {node_id: _merge_node(group, types) for node_id, group in groups.items()}
    edges = [_landed(edge, merged) for edge in edges]
    unclear = {
        (e.kind, e.source, e.target) for e in edges if not _carried(e, merged, edge_kinds, types)
    }
    edges = [e for e in edges if (e.kind, e.source, e.target) not in unclear]

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
                merged[end] = _listed(end, boundary[end])
            if end not in merged:
                merged[end] = {"id": end, "type": "", "state": "referenced", "locations": []}
            for entry in boundary.get(end, ()) if boundary and end not in groups else ():
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
    marks: dict[str, list[tuple[str, str, str, str, FoundEdge]]] = {}
    for edge in edges:
        if edge.on_miss:
            end = edge.source if edge.on_miss == "source" else edge.target
            mark = "boundary" if edge.into else edge.miss
            marks.setdefault(end, []).append((mark, edge.pack, edge.rule, edge.searched_for, edge))
    found_ids = set(groups)
    _enter(marks, merged, merged_edges, found_ids)
    for end, node in merged.items():
        if node["state"] == "referenced":
            _mark(node, marks.get(end, []), types, edge_kinds)
        elif node["state"] == "mapped" and _runtime(node):
            node["state"] = "unknown_boundary"
    ordered = [merged[node_id] for node_id in sorted(merged)]
    written = [
        _edge(key, group, merged, edge_kinds, types, found_ids)
        for key, group in sorted(merged_edges.items())
    ]
    hidden = {node["id"] for node in ordered if _internal(types, node["type"])}
    kept = [edge for edge in written if edge["from"] not in hidden and edge["to"] not in hidden]
    left_out = LeftOut(
        nodes=len(hidden), edges=len(written) - len(kept), unclear_edges=len(unclear)
    )
    ordered = [node for node in ordered if node["id"] not in hidden]
    written = kept
    declared = attributes or {}
    for name in sorted(n for n, attribute in declared.items() if attribute.spreads):
        _spread(name, declared[name], ordered, written, edge_kinds)
    held = {name for node in ordered for name in node.get("attributes", {})}
    marked = {name: a.mark for name, a in sorted(declared.items()) if a.mark and name in held}
    grouping = sorted({str(edge["kind"]) for edge in written if edge_kinds[edge["kind"]].groups})
    realizing, realizing_to = (
        sorted({str(e["kind"]) for e in written if edge_kinds[e["kind"]].realizes == end})
        for end in ("from", "to")
    )
    document = {
        "periplus_map_version": 0,
        "generated_by": f"periplus {tool_version}",
        "packs": sorted(
            ({"pack": p.name.pack, "version": p.name.version} for p in packs),
            key=lambda entry: entry["pack"],
        ),
        "settings": settings,
        "roots": ["."],
        "type_hierarchy": hierarchy(
            {str(node["type"]) for node in ordered}, lambda name: types[name].parent
        ),
        "counts": counts(ordered, written),
        "nodes": ordered,
        "edges": written,
    }
    if grouping:
        document["grouping_kinds"] = grouping
    texts = {
        "edge_kinds": {str(e["kind"]): edge_kinds[e["kind"]].description for e in written},
        "node_types": {str(n["type"]): types[n["type"]].description for n in ordered},
    }
    legend = {
        section: dict(sorted(given.items()))
        for section, named in texts.items()
        if (given := {name: text for name, text in named.items() if text})
    }
    if legend:
        document["legend"] = legend
    if realizing:
        document["realizing_kinds"] = realizing
    if realizing_to:
        document["realizing_to_kinds"] = realizing_to
    for cause in ("from", "to", "none", "touch"):
        causing = sorted({str(e["kind"]) for e in written if edge_kinds[e["kind"]].cause == cause})
        if causing:
            document[f"cause_{cause}_kinds"] = causing
    if supporting:
        document["supporting_paths"] = sorted(set(supporting))
    if marked:
        document["marks"] = marked
    return document, left_out


#: The confidences a provenance row may hold, strongest first.
_STRENGTH = ("declared", "inferred", "mentioned")


def _spread(
    name: str,
    attribute: Attribute,
    nodes: Sequence[dict[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    edge_kinds: Mapping[str, EdgeKind],
) -> None:
    """Write the attribute ``name`` on each member of a container that holds it, through grouping
    edges from their to end to their from end and through each kind the declaration's ``along``
    lists toward the end it names, transitively, with a provenance row of the declaring pack and
    the rule ``spread.<name>``.

    A node that holds a value of its own keeps it. Otherwise the nearest holders decide: one value
    when they agree, else ``differs`` with each holder's value at its first location, or each entry
    of a holder's own ``differs``. The row's confidence is the weakest along the way: the setting
    rows and each grouping edge, a node's rows and an edge's rows each counted at their strongest,
    and the weakest of several nearest holders.
    """
    toward = {kind: end for kind, end in attribute.along}
    members: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        end = "from" if edge_kinds[edge["kind"]].groups else toward.get(edge["kind"])
        if end:
            sure = _strongest(row["confidence"] for row in edge["provenance"])
            other = "to" if end == "from" else "from"
            members.setdefault(edge[other], []).append((edge[end], sure))
    by_id = {node["id"]: node for node in nodes}
    level: dict[str, tuple[frozenset[tuple[str, int, str]], str]] = {}
    for node in nodes:
        if name in node.get("attributes", {}):
            rows = (r["confidence"] for r in node["provenance"] if name in r.get("sets", ()))
            level[node["id"]] = (_holder_entries(node, name), _strongest(rows))
    held = set(level)
    while level:
        arrivals: dict[str, list[tuple[frozenset[tuple[str, int, str]], str]]] = {}
        for container in sorted(level):
            entries, sure = level[container]
            for member, edge_sure in members.get(container, ()):
                if member not in held:
                    arrivals.setdefault(member, []).append((entries, _weakest((sure, edge_sure))))
        level = {
            member: (frozenset().union(*(e for e, _ in came)), _weakest(c for _, c in came))
            for member, came in arrivals.items()
        }
        held.update(level)
        for member, (entries, sure) in sorted(level.items()):
            node = by_id[member]
            node.setdefault("attributes", {})[name] = _spread_value(entries)
            node["provenance"].append(
                {
                    "pack": attribute.pack,
                    "rule": f"spread.{name}",
                    "confidence": sure,
                    "sets": [name],
                }
            )


def _strongest(confidences: Iterable[str]) -> str:
    return min(confidences, key=_STRENGTH.index)


def _weakest(confidences: Iterable[str]) -> str:
    return max(confidences, key=_STRENGTH.index)


def _holder_entries(node: Mapping[str, Any], name: str) -> frozenset[tuple[str, int, str]]:
    """The holder's value of ``name`` as differs entries: file, line and the value as JSON."""
    value = node["attributes"][name]
    if isinstance(value, dict) and set(value) == {"differs"}:
        rows = [(e["file"], e["line"], e["value"]) for e in value["differs"]]
    else:
        rows = [(node["locations"][0]["file"], node["locations"][0]["line"], value)]
    return frozenset((f, n, json.dumps(v, sort_keys=True)) for f, n, v in rows)


def _spread_value(entries: frozenset[tuple[str, int, str]]) -> Any:
    """One value when the entries agree; otherwise each entry, sorted, as ``differs``."""
    if len({value for _, _, value in entries}) == 1:
        return json.loads(next(iter(entries))[2])
    return {
        "differs": [{"file": f, "line": n, "value": json.loads(v)} for f, n, v in sorted(entries)]
    }


def counts(
    nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The document's ``counts`` for these nodes and edges."""
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "edges_by_kind": dict(sorted(Counter(str(edge["kind"]) for edge in edges).items())),
        "nodes_by_state": dict(sorted(Counter(str(n["state"]) for n in nodes).items())),
        "nodes_by_type": dict(sorted(Counter(str(node["type"]) for node in nodes).items())),
    }


def _landed(edge: FoundEdge, merged: Mapping[str, Any]) -> FoundEdge:
    """The edge with its composed end on the first candidate id a rule found, else the one at
    ``miss_at``."""
    if not edge.candidates:
        return edge
    chosen = next((c for c in edge.candidates if c in merged), edge.candidates[edge.miss_at])
    # A composed end that is the from end names its type in source_type.
    return replace(edge, source=chosen) if edge.source_type else replace(edge, target=chosen)


#: The marks an end no rule found may take, strongest first.
_RANK = ("boundary", "unresolved", "unknown_boundary")


def _mark(
    node: dict[str, Any],
    rows: Sequence[tuple[str, str, str, str, FoundEdge]],
    types: Mapping[str, TypeInfo],
    edge_kinds: Mapping[str, EdgeKind],
) -> None:
    """Give the referenced node the strongest mark its type or its edges' rows give, and an
    unresolved or unknown boundary node the detail of its first row of that mark."""
    marked = [row for row in rows if row[0]]
    if _boundary_type(types, node["type"]):
        node["state"] = "boundary"
    if not marked or node["state"] == "boundary":
        return
    state = min((row[0] for row in marked), key=_RANK.index)
    node["state"] = state
    if state == "boundary":
        return
    _, pack, rule, _, edge = min((row for row in marked if row[0] == state), key=lambda r: r[:4])
    allowed = edge_kinds[edge.kind]
    if edge.on_miss == "source":
        declared, kind_types = edge.source_type, allowed.from_types
    else:
        declared, kind_types = edge.target_type, allowed.to_types
    node["unresolved_detail"] = {
        "rule": f"{pack}/{rule}",
        "searched_for": edge.searched_for,
        "found": "no mapped node of this name",
        "types_tried": list(edge.types_tried or ((declared,) if declared else kind_types)),
    }


def _enter(
    marks: Mapping[str, Sequence[tuple[str, str, str, str, FoundEdge]]],
    merged: dict[str, dict[str, Any]],
    merged_edges: dict[tuple[str, str, str], list[FoundEdge]],
    found: set[str],
) -> None:
    """Draw each into edge of an end no rule found that an edge's ``boundary`` marks, and the
    into node each reaches, with the rule in its provenance."""
    for end in sorted(marks):
        for _, _, _, _, edge in marks[end] if end not in found else ():
            if edge.into is None:
                continue
            into, kind, carrier = edge.into
            merged_edges.setdefault((carrier, end, into), []).append(
                FoundEdge(
                    carrier, end, into, edge.file, edge.line, edge.pack, edge.rule, edge.confidence
                )
            )
            node = merged.setdefault(
                into,
                {
                    "id": into,
                    "type": kind,
                    "state": "referenced",
                    "locations": [],
                    "provenance": [],
                },
            )
            if node["state"] == "referenced":
                rows = {(p["pack"], p["rule"], p["confidence"]) for p in node["provenance"]}
                rows.add((edge.pack, edge.rule, edge.confidence))
                node["provenance"] = [
                    {"pack": p, "rule": r, "confidence": c, "sets": ["id"]}
                    for p, r, c in sorted(rows)
                ]


def _runtime(node: Mapping[str, Any]) -> bool:
    """Whether a rule marked the found node's target as built at run time."""
    return bool(node.get("attributes", {}).get("resolution") == "runtime")


def _listed(node_id: str, entries: Sequence[BoundaryEntry]) -> dict[str, Any]:
    """The node the boundary groups listing a name draw for it once an edge reached it."""
    return {
        "id": node_id,
        "type": entries[0].type,
        "state": "boundary",
        "locations": [],
        "provenance": [
            {
                "pack": pack,
                "rule": f"boundary.{group}",
                "confidence": "declared",
                "sets": ["id", "type"],
            }
            for pack, group in sorted({(e.pack, e.group) for e in entries})
        ],
    }


def _classify(
    merged: dict[str, dict[str, Any]],
    merged_edges: Mapping[tuple[str, str, str], Sequence[FoundEdge]],
    boundary: Mapping[str, Sequence[BoundaryEntry]],
    types: Mapping[str, TypeInfo],
) -> list[Skipped]:
    """Classify each mapped node whose ancestry reaches a listed boundary node that classifies.

    From each such boundary node the walk follows each listing's ancestry edges backwards, through
    mapped nodes only. A node reached takes the deepest classification that reaches it when its
    type is on that one's chain, and keeps a type equal to or below it; either way it gains an
    inferred provenance row per listing group. A node whose type, or whose classifications, do not
    lie on one chain keeps its type and gives one skipped row.
    """
    sources: dict[tuple[str, str], set[str]] = {}
    for kind, source, target in merged_edges:
        sources.setdefault((kind, target), set()).add(source)
    reached: dict[str, set[tuple[str, BoundaryEntry]]] = {}
    for start in sorted(boundary):
        if start not in merged or merged[start]["state"] != "boundary":
            continue
        for entry in boundary[start]:
            if not entry.classifies:
                continue
            seen, pending = {start}, [start]
            while pending:
                current = pending.pop(0)
                below = {s for kind in entry.ancestry for s in sources.get((kind, current), ())}
                for node_id in sorted(below):
                    if node_id not in seen and merged[node_id]["state"] == "mapped":
                        seen.add(node_id)
                        reached.setdefault(node_id, set()).add((start, entry))
                        pending.append(node_id)
    rows: list[Skipped] = []
    for node_id in sorted(reached):
        node = merged[node_id]
        starts = sorted(reached[node_id], key=lambda s: (s[0], s[1].pack, s[1].group))
        deepest = max(starts, key=lambda s: len(type_chain(types, str(s[1].classifies))))
        target = str(deepest[1].classifies)
        chain = type_chain(types, target)
        off = [s for s in starts if s[1].classifies not in chain]
        conflict = node.get("attributes", {}).get(TYPE_CONFLICT)
        if conflict is not None:
            held = type_chain(types, node["type"])
            node["attributes"][TYPE_CONFLICT] = sorted(
                {
                    *conflict,
                    *(
                        f"{e.classifies} by {e.pack}/boundary.{e.group}"
                        for _, e in starts
                        if e.classifies not in held
                    ),
                }
            )
        elif off or node["type"] not in chain and target not in type_chain(types, node["type"]):
            start, entry = off[0] if off else deepest
            reason = (
                f"{node_id}: classification {entry.classifies} from {start} "
                f"does not descend from {target if off else node['type']}"
            )
            place = node["locations"][0]
            rows.append((place["file"], place["line"], f"boundary.{entry.group}", reason))
            continue
        elif node["type"] in chain:
            node["type"] = target
        node["provenance"] += [
            {"pack": pack, "rule": f"boundary.{group}", "confidence": "inferred", "sets": ["type"]}
            for pack, group in sorted({(e.pack, e.group) for _, e in starts})
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


def _internal(types: Mapping[str, TypeInfo], name: str) -> bool:
    """Whether the type is internal, or lies below an internal type."""
    return any(types[t].internal for t in type_chain(types, name) if t in types)


def _boundary_type(types: Mapping[str, TypeInfo], name: str) -> bool:
    """Whether the type is declared boundary, or lies below a boundary type."""
    return any(types[t].boundary for t in type_chain(types, name) if t in types)


def _referenced_type(names: set[str], types: Mapping[str, TypeInfo]) -> str:
    """The deepest of the types the edges claim when one chain holds them all, else the first.

    Either way a type not internal and not below an internal type wins, when one is claimed, so
    an end a written type also claims stays in the map.
    """
    hidden = {name for name in names if _internal(types, name)}
    deepest = max(sorted(names), key=lambda name: len(type_chain(types, name)))
    if all(name in type_chain(types, deepest) for name in names):
        return max(sorted(names - hidden) or [deepest], key=lambda n: len(type_chain(types, n)))
    return min(names, key=lambda name: (name in hidden, name))


def _carried(
    edge: FoundEdge,
    merged: Mapping[str, Mapping[str, Any]],
    edge_kinds: Mapping[str, EdgeKind],
    types: Mapping[str, TypeInfo],
) -> bool:
    """Whether each end of the edge that is a node of conflicting types may take the edge."""
    allowed = edge_kinds[edge.kind]
    return all(
        set(kinds) & set(type_chain(types, merged[end]["type"]))
        for end, kinds in ((edge.source, allowed.from_types), (edge.target, allowed.to_types))
        if TYPE_CONFLICT in merged.get(end, {}).get("attributes", {})
    )


def _merge_node(group: Sequence[FoundNode], types: Mapping[str, TypeInfo]) -> dict[str, Any]:
    """The node the records of one id make. A record that only writes attributes adds them and
    its row, which sets only them; it adds no type and no location."""
    attributed, group = group, [node for node in group if not node.attribute_only]
    found = sorted({node.type for node in group})
    deepest = max(found, key=lambda name: len(type_chain(types, name)))
    conflict: list[str] = []
    if any(name not in type_chain(types, deepest) for name in found):
        # A type found that is an ancestor of another found type is on that one's chain.
        leaves = [n for n in found if not any(n in type_chain(types, m)[1:] for m in found)]
        shared = [
            t for t in type_chain(types, deepest) if all(t in type_chain(types, n) for n in leaves)
        ]
        if not shared:
            raise TypeCollision(
                f"{group[0].id} was found as {', '.join(found)}, which do not lie on one type "
                "chain",
                {"id": group[0].id, "types": ", ".join(found)},
            )
        deepest = shared[0]
        conflict = sorted(
            {
                f"{n.type} by {n.pack}/{n.rule}"
                for n in group
                if n.type not in type_chain(types, deepest)
            }
        )
    values: dict[str, dict[tuple[str, int, str, str], Any]] = {}
    named: dict[tuple[str, str, str], set[str]] = {}
    minted = {(node.pack, node.rule, node.confidence) for node in group}
    for node in attributed:
        sets = named.setdefault((node.pack, node.rule, node.confidence), set())
        for name, value, line in node.attributes:
            values.setdefault(name, {})[(node.file, line, node.pack, node.rule)] = value
            sets.add(name)
    result: dict[str, Any] = {
        "id": group[0].id,
        "type": deepest,
        "state": "mapped",
        "locations": [
            {"file": f, "line": n} for f, n in sorted({(node.file, node.line) for node in group})
        ],
        "provenance": [
            {
                "pack": p,
                "rule": r,
                "confidence": c,
                "sets": [*(("id", "type") if (p, r, c) in minted else ()), *sorted(names)],
            }
            for (p, r, c), names in sorted(named.items())
        ],
    }
    attributes = {
        name: _attribute(contributions.items()) for name, contributions in values.items()
    }
    if conflict:
        attributes[TYPE_CONFLICT] = conflict
    if attributes:
        result["attributes"] = dict(sorted(attributes.items()))
    return result


def _attribute(contributions: Iterable[tuple[tuple[str, int, str, str], Any]]) -> Any:
    """The value when every contribution agrees; otherwise every contribution, none winning, in
    file, line, pack, rule and value order, one entry per place and value."""
    ordered = sorted(contributions, key=lambda item: (item[0], json.dumps(item[1], sort_keys=True)))
    if len({json.dumps(value, sort_keys=True) for _, value in ordered}) == 1:
        return ordered[0][1]
    entries: list[dict[str, Any]] = []
    for (f, n, _, _), value in ordered:
        entry = {"file": f, "line": n, "value": value}
        if entry not in entries:
            entries.append(entry)
    return {"differs": entries}


def _edge(
    key: tuple[str, str, str],
    group: Sequence[FoundEdge],
    merged: Mapping[str, Mapping[str, Any]],
    edge_kinds: Mapping[str, EdgeKind],
    types: Mapping[str, TypeInfo],
    found: set[str],
) -> dict[str, Any]:
    kind, source, target = key
    for end, allowed in (
        (source, edge_kinds[kind].from_types),
        (target, edge_kinds[kind].to_types),
    ):
        if end not in found:
            continue
        if not set(allowed) & set(type_chain(types, merged[end]["type"])):
            raise EdgeIllegal(
                f"the edge {kind} from {source} to {target} needs {end} to be one of "
                f"{', '.join(allowed)}, and it is {merged[end]['type']}",
                {"kind": kind, "from": source, "to": target},
            )
    places = sorted({(edge.file, edge.line) for edge in group})
    values: dict[str, list[tuple[tuple[str, int, str, str], str]]] = {}
    sets: dict[tuple[str, str, str], set[str]] = {}
    for e in group:
        row = sets.setdefault((e.pack, e.rule, e.confidence), set())
        for name, value in e.attributes:
            values.setdefault(name, []).append(((e.file, e.line, e.pack, e.rule), value))
            row.add(name)
    written: dict[str, Any] = {
        "kind": kind,
        "from": source,
        "to": target,
        "occurrences": len(places),
        "locations": [{"file": f, "line": n} for f, n in places],
        "provenance": [
            {"pack": p, "rule": r, "confidence": c, **({"sets": sorted(names)} if names else {})}
            for (p, r, c), names in sorted(sets.items())
        ],
    }
    if values:
        written["attributes"] = {name: _attribute(values[name]) for name in sorted(values)}
    return written


def hierarchy(
    used: set[str], parent_of: Callable[[str], str | None]
) -> list[dict[str, str | None]]:
    """The used types and every ancestor of them, each with its parent, sorted by type."""
    closure: set[str] = set()
    pending = sorted(used)
    while pending:
        name = pending.pop()
        if name not in closure:
            closure.add(name)
            parent = parent_of(name)
            if parent is not None:
                pending.append(parent)
    return [{"type": name, "parent": parent_of(name)} for name in sorted(closure)]


def render(document: Mapping[str, object]) -> str:
    """The canonical text: sorted keys, two-space indent, ASCII, one trailing LF."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
