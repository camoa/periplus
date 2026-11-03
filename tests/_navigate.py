"""Map builders the navigation tests share: one provenance record, one node, one edge."""

from __future__ import annotations

from typing import Any


def _prov(confidence: str, rule: str = "r") -> dict[str, Any]:
    return {"pack": "php", "rule": rule, "confidence": confidence, "sets": []}


PROV = _prov("declared")


def _node(
    id: str, type: str = "t.x", state: str = "mapped", line: int | None = None, **extra: Any
) -> dict[str, Any]:
    where = [{"file": "src/a.php", "line": line}] if line else []
    return {
        "id": id,
        "type": type,
        "state": state,
        "locations": where,
        "provenance": [PROV],
        **extra,
    }


def _edge(
    kind: str, source: str, target: str, line: int | None = None, *prov: dict[str, Any]
) -> dict[str, Any]:
    where = [{"file": "src/a.php", "line": line}] if line else []
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": where,
        "provenance": list(prov) or [_prov("inferred")],
        "occurrences": 2,
    }
