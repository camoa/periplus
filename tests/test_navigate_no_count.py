"""An edge that carries no occurrences count shows without one: no ``xN`` in text, null in JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from _navigate import _edge, _node

from periplus.cli import main

SOURCE = "x::a"
COUNTED = "x::counted"
UNCOUNTED = "x::uncounted"


def _show(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, fmt: str
) -> str:
    uncounted = _edge("calls", SOURCE, UNCOUNTED, 3, occurrences=None)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "p", "version": "0.1.0"}],
        "roots": ["."],
        "type_hierarchy": [{"type": "t.x", "parent": None}],
        "nodes": [_node(n, line=1) for n in (SOURCE, COUNTED, UNCOUNTED)],
        "edges": [uncounted, _edge("calls", SOURCE, COUNTED, 4)],
    }
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["periplus", "show", SOURCE, "--map", str(map_path)] + ["--format", fmt]
    )
    assert main() == 0
    return capsys.readouterr().out


def test_c2_an_edge_without_occurrences_prints_no_count_in_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = _show(monkeypatch, capsys, tmp_path, "text")
    lines = {line.split()[0]: line for line in out.splitlines() if line.strip().startswith("x::")}

    assert lines[UNCOUNTED].split() == [
        UNCOUNTED,
        "t.x",
        "mapped",
        "src/a.php:3",
        "inferred",
        "php:r",
    ]
    assert re.search(r"\sx2(\s|$)", lines[COUNTED])


def test_c2_an_edge_without_occurrences_emits_occurrences_null_in_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = _show(monkeypatch, capsys, tmp_path, "json")
    items = {row["other"]: row for row in json.loads(out)["outgoing"]["items"]}

    assert "occurrences" in items[UNCOUNTED]
    assert items[UNCOUNTED]["occurrences"] is None
    assert items[COUNTED]["occurrences"] == 2
