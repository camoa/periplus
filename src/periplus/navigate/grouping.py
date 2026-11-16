"""What a container holds by the map's grouping kinds, and the pieces edges join a set into."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from periplus.navigate.mapfile import MapIndex, as_text

__all__ = ["joined", "members"]


def members(
    index: MapIndex, container: str, grouping: Collection[str], only: Collection[str] | None = None
) -> list[tuple[dict[str, Any], str]]:
    """The edges of a ``grouping`` kind that arrive at ``container``, each with its member, the
    edge's from end, in map order; ``only`` keeps the members of those types."""
    found = []
    for edge in index.incoming(container):
        if edge["kind"] in grouping:
            member = as_text(edge["from"])
            if only is None or as_text(index.nodes[member]["type"]) in only:
                found.append((edge, member))
    return found


def joined(index: MapIndex, nodes: Collection[str], skip: Collection[str] = ()) -> dict[str, str]:
    """Each of ``nodes`` mapped to the smallest id of its piece: two nodes share a piece when an
    edge of the map joins them directly, of any kind but those in ``skip``, or a chain of such
    edges does through other ``nodes``."""
    root = {n: n for n in nodes}

    def top(node: str) -> str:
        while root[node] != node:
            root[node] = root[root[node]]
            node = root[node]
        return node

    for node in root:
        for edge in index.outgoing(node):
            far = as_text(edge["to"])
            if far in root and edge["kind"] not in skip:
                a, b = top(node), top(far)
                if a != b:
                    root[max(a, b)] = min(a, b)
    return {n: top(n) for n in root}
