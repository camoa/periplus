"""A printed slice ends with the descriptions of the edge kinds its links show, within a small
byte allowance, and drops them first when the piece is over its bytes.

    X (t.method) -uses-> C1, C2 (t.class);  C1 -calls-> S (t.service)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus.navigate import slice as slicing

C1, C2 = "t.class::app.C1", "t.class::app.C2"
S = "t.service::app.s"
X = "t.method::app.X::run"

NODES = [
    _node(C1, "t.class", line=1, file="src/C1.php"),
    _node(C2, "t.class", line=1, file="src/C2.php"),
    _node(S, "t.service", line=1, file="app.services"),
    _node(X, "t.method", line=1, file="src/X.php"),
]
EDGES = [
    _edge("uses", X, C1, 2, file="src/X.php"),
    _edge("uses", X, C2, 3, file="src/X.php"),
    _edge("calls", C1, S, 4, file="src/C1.php"),
]
TEXTS = {
    "uses": "the method uses that class",
    "calls": "the class calls that service",
    "absent": "no edge of the piece has it",
}


def _piece(root: Path, *ids: str, texts: dict[str, str] = TEXTS, **kw: Any) -> slicing.SliceReport:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        **({"legend": {"edge_kinds": texts}} if texts else {}),
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    args: dict[str, Any] = {
        "prefixes": (),
        "direction": "both",
        "depth": None,
        "kinds": (),
        "limit": None,
        "out": None,
        "map_path": None,
    }
    args.update(kw)
    return slicing.run(root, {}, ids, **args)


def test_the_piece_ends_with_the_texts_of_its_link_kinds_alone(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, X))

    assert text.endswith(
        "\nlegend:\n  calls: the class calls that service\n  uses: the method uses that class\n"
    )
    assert "absent" not in text


def test_the_legend_keeps_within_its_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(slicing, "LEGEND_BYTES", 60)
    text = slicing.render_text(_piece(tmp_path, X))

    assert "  calls: the class calls that service\n" in text
    assert "uses: the method" not in text
    assert "  +1 more: periplus legend --kind K\n" in text


def test_the_legend_goes_before_any_row_when_over_the_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long = {kind: f"{text}, {'and more words ' * 8}" for kind, text in TEXTS.items()}
    whole = slicing.render_text(_piece(tmp_path, X, texts=long))
    monkeypatch.setattr(slicing, "BYTE_LIMIT", len(whole.encode()) - 10)
    report = _piece(tmp_path, X, texts=long)
    text = slicing.render_text(report)

    assert "legend:" not in text
    assert report.rows.shown == report.rows.total
    assert "legend left out" in text


def test_a_map_without_texts_prints_no_legend(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, X, texts={}))

    assert "legend" not in text


def test_a_written_slice_keeps_the_texts_of_its_own_kinds_and_types(tmp_path: Path) -> None:
    types = {"t.method": "a method", "t.class": "a class", "t.service": "a service"}
    (tmp_path / ".periplus").mkdir(parents=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "legend": {"edge_kinds": TEXTS, "node_types": types},
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (tmp_path / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    common = {"prefixes": (), "kinds": (), "limit": None, "map_path": None, "depth": None}
    slicing.run(tmp_path, {}, [X], direction="out", out=Path("piece.json"), **common)
    piece = json.loads((tmp_path / "piece.json").read_text())

    assert piece["legend"] == {
        "edge_kinds": {"uses": "the method uses that class"},
        "node_types": {"t.class": "a class", "t.method": "a method"},
    }
    slicing.run(tmp_path, {}, [S], direction="out", out=Path("lone.json"), **common)
    assert json.loads((tmp_path / "lone.json").read_text())["legend"] == {
        "node_types": {"t.service": "a service"}
    }
