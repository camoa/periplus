"""The cut-list envelope every list-returning navigation command shares."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["NONE", "Listing", "cut", "footer", "kind_warnings", "payload", "place"]


@dataclass(frozen=True, slots=True)
class Listing:
    """Some items of a longer list: what is shown, how many there were, and whether it was cut."""

    items: tuple[Any, ...]
    total: int
    shown: int
    truncated: bool


#: The listing of a report that stopped before it listed anything.
NONE = Listing((), 0, 0, False)


def place(location: Mapping[str, Any]) -> str:
    """A location as ``file:line``."""
    return f"{location['file']}:{location['line']}"


def kind_warnings(kinds: Collection[str], held: set[str]) -> tuple[str, ...]:
    """One warning for each asked kind the map holds no edge of, in sorted order."""
    return tuple(f"the map holds no edge of kind {kind!r}" for kind in sorted(set(kinds) - held))


def cut(items: Sequence[Any], limit: int) -> Listing:
    """The first ``limit`` items, in the order given. A limit of 0 keeps every item."""
    if limit < 0:
        raise ValueError(f"limit must be 0 or more, not {limit}")
    kept = tuple(items) if limit == 0 else tuple(items[:limit])
    return Listing(items=kept, total=len(items), shown=len(kept), truncated=len(kept) < len(items))


def payload(listing: Listing) -> dict[str, Any]:
    """The JSON fragment for a listing: ``items``, ``total``, ``shown`` and ``truncated``."""
    return {
        "items": list(listing.items),
        "total": listing.total,
        "shown": listing.shown,
        "truncated": listing.truncated,
    }


def footer(listing: Listing) -> str | None:
    """``showing N of M`` when the list was cut, and ``None`` when nothing was left out."""
    return f"showing {listing.shown} of {listing.total}" if listing.truncated else None
