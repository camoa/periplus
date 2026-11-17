"""A count of one prints its noun singular, in the shared helper and in the reports that use it."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from _navigate import _document, _edge, _node

from periplus.navigate import count, files, path
from periplus.navigate import find as finding
from periplus.report import amount


def test_amount_is_singular_for_one_and_plural_otherwise() -> None:
    assert [amount(n, "edge") for n in (0, 1, 2)] == ["0 edges", "1 edge", "2 edges"]


def _map(root: Path) -> Path:
    nodes = [_node("t.x::a", line=1), _node("t.x::b", line=2)]
    target = root / "m.json"
    document = _document(nodes, [_edge("calls", "t.x::a", "t.x::b", 1)])
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_reports_print_a_count_of_one_singular(tmp_path: Path) -> None:
    given = _map(tmp_path)

    chains = path.render_text(path.run(tmp_path, {}, "t.x::a", "t.x::b", (), 0, given))
    held = files.render_text(files.run(tmp_path, {}, ["t.x::a"], given))
    counted = count.render_text(count.run(tmp_path, {}, ["t.x::a"], given))

    assert "1 shortest chain\n" in chains
    assert "1 thing in 1 file\n" in held
    assert "1 id given: 1 thing in the map\n" in counted


def test_the_kinds_past_the_named_ones_are_counted_singular_or_plural() -> None:
    one = Counter({f"k{n}": 1 for n in range(finding._FOOTER_TYPES + 1)})
    two = Counter({f"k{n}": 1 for n in range(finding._FOOTER_TYPES + 2)})

    assert finding._counted(one, "kind").endswith(", and 1 more kind")
    assert finding._counted(two, "kind").endswith(", and 2 more kinds")
