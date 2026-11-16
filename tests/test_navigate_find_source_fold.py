"""``periplus find`` text: edges matched by ``[source]`` at one code line fold into one row.

A tiny map: ``src/a.php`` line 2 holds one call that three edges share; line 4 holds a call
that five edges share; ``src/b.php`` line 1 holds a call one edge has.
"""

from __future__ import annotations

import json
from pathlib import Path

from _navigate import _document, _edge, _node

from periplus.navigate import find

A, B, C, D, CS = "t.f::a", "t.f::b", "t.f::c", "t.f::d", "t.site::cs"


def _site(root: Path) -> Path:
    (root / "src").mkdir()
    (root / "src/a.php").write_text("<?php\nzap();\n\nzip(); zip();\n", encoding="utf-8")
    (root / "src/b.php").write_text("zap();\n", encoding="utf-8")
    nodes = [_node(i, line=1) for i in (A, B, C, D)] + [_node(CS, "t.site", line=2)]
    edges = [
        _edge("calls", A, B, 2),
        _edge("call_site_in", CS, A, 2),
        _edge("has_call_site", A, CS, 2),
        *(_edge("calls", A, end, 4) for end in (B, C, D)),
        _edge("uses", A, B, 4),
        _edge("uses", A, C, 4),
        _edge("calls", B, C, 1, file="src/b.php"),
    ]
    (root / ".periplus").mkdir()
    map_path = root / ".periplus/map.json"
    map_path.write_text(json.dumps(_document(nodes, edges)), encoding="utf-8")
    return map_path


def _edge_text(report: find.FindReport) -> list[str]:
    lines = find.render_text(report).splitlines()
    return lines[lines.index("edges:") + 1 :]


def test_edges_at_one_code_line_print_as_one_row(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "zap", (), 0, _site(tmp_path), edges=True)

    assert find.render_text(report).splitlines()[0] == "periplus find: 0 things, 4 edges"
    assert _edge_text(report) == [
        "  src/a.php:2  [source]  call_site_in cs -> a; calls a -> b; has_call_site a -> cs",
        "      | zap();",
        "  calls  b -> c  src/b.php:1  [source]",
        "      | zap();",
    ]


def test_more_than_three_edges_at_one_line_print_their_count_by_kind(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "zip", (), 0, _site(tmp_path))

    assert find.render_text(report).splitlines()[0] == "periplus find: 0 things, 5 edges"
    assert _edge_text(report) == [
        "  src/a.php:4  [source]  5 edges: calls 3, uses 2",
        "      | zip(); zip();",
    ]


def test_json_and_ids_keep_every_edge(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "zap", (), 0, _site(tmp_path))

    assert len(json.loads(find.render_json(report))["edges"]) == 4
    assert find.listed(report) == [CS, A, B, C]
