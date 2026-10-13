"""The cut-list envelope every list-returning navigation command shares."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["Listing", "cut", "footer", "payload"]


@dataclass(frozen=True, slots=True)
class Listing:
    """Some items of a longer list: what is shown, how many there were, and whether it was cut."""

    items: tuple[Any, ...]
    total: int
    shown: int
    truncated: bool


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
