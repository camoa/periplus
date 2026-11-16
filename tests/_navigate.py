"""Map builders the navigation tests share: one provenance record, one node, one edge."""

from __future__ import annotations

from typing import Any


def _prov(confidence: str, rule: str = "r", pack: str = "php") -> dict[str, Any]:
    return {"pack": pack, "rule": rule, "confidence": confidence, "sets": []}


PROV = _prov("declared")


def _node(
    id: str,
    type: str = "t.x",
    state: str = "mapped",
    line: int | None = None,
    file: str = "src/a.php",
    confidence: str = "declared",
    pack: str = "php",
    **extra: Any,
) -> dict[str, Any]:
    where = [{"file": file, "line": line}] if line else []
    return {
        "id": id,
        "type": type,
        "state": state,
        "locations": where,
        "provenance": [_prov(confidence, pack=pack)],
        **extra,
    }


def _edge(
    kind: str,
    source: str,
    target: str,
    line: int | None = None,
    *prov: dict[str, Any],
    file: str = "src/a.php",
    confidence: str = "inferred",
    pack: str = "php",
    occurrences: int | None = 2,
) -> dict[str, Any]:
    where = [{"file": file, "line": line}] if line else []
    edge = {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": where,
        "provenance": list(prov) or [_prov(confidence, pack=pack)],
    }
    if occurrences is not None:
        edge["occurrences"] = occurrences
    return edge


def _document(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    causes: dict[str, list[str]] | None = None,
    **header: Any,
) -> dict[str, Any]:
    """A map document; ``causes`` maps ``from``, ``to``, ``none`` or ``touch`` to the kinds the
    header lists under ``cause_<that>_kinds``."""
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": nodes,
        "edges": edges,
        **header,
    }
    for cause, kinds in (causes or {}).items():
        document[f"cause_{cause}_kinds"] = sorted(kinds)
    return document
