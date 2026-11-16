"""``periplus diff`` text: a count line by type or by kind names the most frequent and counts the
rest, unless ``--limit 0``; JSON keeps every count.

A tiny pair of maps: the old one is empty; the new one adds ten things of ten types, ``t.k0``
twice, joined by eleven edges of eleven kinds, ``k0`` twice.
"""

from __future__ import annotations

import json
from pathlib import Path

from _navigate import _document, _edge, _node

from periplus.navigate import diff


def _pair(root: Path) -> tuple[Path, Path]:
    nodes = [_node(f"n::{i}", f"t.k{i}", line=1) for i in range(10)] + [_node("n::x", "t.k0")]
    edges = [_edge(f"k{i}", "n::0", f"n::{i}", 1) for i in range(1, 10)]
    edges += [_edge("k0", "n::1", "n::2", 1), _edge("k0", "n::2", "n::3", 1)]
    edges += [_edge("k10", "n::3", "n::4", 1)]
    old, new = root / "old.json", root / "new.json"
    old.write_text(json.dumps(_document([], [])), encoding="utf-8")
    new.write_text(json.dumps(_document(nodes, edges)), encoding="utf-8")
    return old, new


def _counts(text: str) -> list[str]:
    return [line for line in text.splitlines() if " by type: " in line or " by kind: " in line]


def test_count_lines_name_the_most_frequent_then_count_the_rest(tmp_path: Path) -> None:
    text = diff.render_text(diff.run(tmp_path, {}, *_pair(tmp_path)))

    assert _counts(text) == [
        "  added by type: t.k0 2, t.k1 1, t.k2 1, t.k3 1, t.k4 1, t.k5 1, t.k6 1, t.k7 1,"
        " and 2 more types",
        "  added by kind: k0 2, k1 1, k10 1, k2 1, k3 1, k4 1, k5 1, k6 1, and 3 more kinds",
    ]


def test_limit_zero_names_every_type_and_kind(tmp_path: Path) -> None:
    text = diff.render_text(diff.run(tmp_path, {}, *_pair(tmp_path), limit=0))

    assert _counts(text)[0].endswith("t.k8 1, t.k9 1")
    assert _counts(text)[1].endswith("k8 1, k9 1")


def test_json_keeps_every_count(tmp_path: Path) -> None:
    document = json.loads(diff.render_json(diff.run(tmp_path, {}, *_pair(tmp_path))))

    assert len(document["things_by_type"]["added"]) == 10
    assert len(document["edges_by_kind"]["added"]) == 11
