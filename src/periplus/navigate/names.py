"""Short names a reader can paste back: the shortest tail of an id that names that node alone."""

from __future__ import annotations

import re
from collections import Counter

from periplus.navigate.mapfile import MapIndex, as_text

__all__ = ["Names"]

#: A character other than a letter, digit or underscore, before one: a short name starts after it.
_CUT = re.compile(r"\W(?=\w)")


class Names:
    """The shortest name ``resolve`` takes back to each node: the tail of its id after its first
    ``::``, starting after a character other than a letter, digit or underscore, that no other
    node's id ends with in the same way; the full id when none is unique. Also each node's owner
    and the node it nests inside.
    Each table is built once a run, on first use."""

    def __init__(self, index: MapIndex) -> None:
        self.index = index
        self._count: Counter[str] | None = None
        self._short: dict[str, str] = {}
        self._owners: dict[str, str] | None = None

    def owner(self, node_id: str) -> str | None:
        """The node whose id, after its first ``::``, is ``node_id``'s name before its last
        ``::``, a mapped one first, then the smallest id; ``None`` when there is none."""
        name = node_id.split("::", 1)[-1]
        if "::" not in name:
            return None
        return self._by_name().get(name.rsplit("::", 1)[0])

    def holder(self, node_id: str) -> str | None:
        """The node ``node_id`` nests inside: the owner of the longest part of its name before one
        of its ``::`` that names a node, chosen as ``owner`` chooses; ``None`` when none does."""
        parts = node_id.split("::", 1)[-1].split("::")
        names = self._by_name()
        for cut in range(len(parts) - 1, 0, -1):
            found = names.get("::".join(parts[:cut]))
            if found is not None:
                return found
        return None

    def _by_name(self) -> dict[str, str]:
        """Each name, an id after its first ``::``, to its node: a mapped one first, then the
        smallest id."""
        if self._owners is None:
            best: dict[str, tuple[bool, str]] = {}
            for i, node in self.index.nodes.items():
                key = (node["state"] != "mapped", i)
                bare = as_text(i).split("::", 1)[-1]
                if bare not in best or key < best[bare]:
                    best[bare] = key
            self._owners = {bare: key[1] for bare, key in best.items()}
        return self._owners

    @staticmethod
    def _tail_set(node_id: str) -> set[str]:
        """Each tail of the id's name that a short name may be."""
        name = node_id.split("::", 1)[-1]
        return {name, *(name[cut.end() :] for cut in _CUT.finditer(name))}

    @classmethod
    def _tails(cls, node_id: str) -> list[str]:
        """Each tail of the id's name that a short name may be, shortest first."""
        return sorted(cls._tail_set(node_id), key=lambda t: (len(t), t))

    def short(self, node_id: str) -> str:
        """The shortest unique tail of ``node_id``, or ``node_id`` itself."""
        if node_id not in self._short:
            if self._count is None:
                self._count = Counter(
                    t.casefold() for i in self.index.nodes for t in self._tail_set(as_text(i))
                )
            self._short[node_id] = next(
                (
                    tail
                    for tail in self._tails(node_id)
                    if self._count[tail.casefold()] == 1
                    and (tail not in self.index.nodes or tail == node_id)
                ),
                node_id,
            )
        return self._short[node_id]
