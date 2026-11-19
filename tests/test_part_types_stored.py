"""``periplus map`` writes the part types it finds over the whole map, every map file made from it
carries them, and a command reading a map file uses them instead of counting over that file.

The hand-made map: container ``Crate`` holds members ``alpha`` and ``beta``, and each member holds
one parameter. Over the whole map the parameter type is the part type; a file that keeps the
members without their parameters would, counted over itself, make the members parts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _node
from _own_pack import plant

from periplus.cli import main

MEMBERS = ["t.c::Crate", "t.m::Crate::alpha", "t.m::Crate::beta"]
STORED = {"t.p": 100}


def _full(root: Path, **header: Any) -> Path:
    nodes = [
        _node("t.c::Crate", "t.c", line=1),
        _node("t.m::Crate::alpha", "t.m", line=2),
        _node("t.p::Crate::alpha::xin", "t.p", line=2),
        _node("t.m::Crate::beta", "t.m", line=5),
        _node("t.p::Crate::beta::yin", "t.p", line=5),
    ]
    path = root / "full.json"
    path.write_text(json.dumps(_document(nodes, [], **header)), encoding="utf-8")
    return path


def _json(capsys: pytest.CaptureFixture[str], *argv: str) -> Any:
    capsys.readouterr()
    assert main([*argv, "--format", "json"]) == 0
    return json.loads(capsys.readouterr().out)


def _extract(root: Path, full: Path, name: str = "piece.json", ids: list[str] = MEMBERS) -> Path:
    out = root / name
    assert main(["extract", *ids, "--map", str(full), "--out", str(out)]) == 0
    return out


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_map_writes_the_part_types_the_same_on_each_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = """
node_types:
  - {name: own.fn, id_namespace: fn}
  - {name: own.box, id_namespace: box}
  - {name: own.arg, id_namespace: arg}
rules:
  - rule: box
    reads: file
    in: [source]
    match:
      declaration: class_declaration
      name_child: name
      body_child: declaration_list
      filetype: php
    id: {from: qualified_name}
    emits: [{node: {type: own.box}}]
    confidence: declared
  - rule: fn
    reads: file
    in: [source]
    match: {declaration: method_declaration, name_child: name, filetype: php}
    id: {from: [enclosing_type, declared_name], template: "{enclosing_type}::{declared_name}"}
    emits: [{node: {type: own.fn}}]
    confidence: declared
  - rule: arg
    reads: file
    in: [source]
    match: {declaration: simple_parameter, name_child: name, filetype: php}
    id:
      from: [enclosing_type, enclosing_method, declared_name]
      template: "{enclosing_type}::{enclosing_method}::{declared_name}"
    emits: [{node: {type: own.arg}}]
    confidence: declared
"""
    source = "<?php\nclass Box {\n  function alpha($x) {}\n  function beta($y) {}\n}\n"
    plant(tmp_path, rules, source)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config"))

    assert main(["map", "--output", "one.json"]) == 0
    assert main(["map", "--output", "two.json"]) == 0
    assert main(["check-map", "--map", "one.json"]) == 0

    assert _read(tmp_path / "one.json")["part_types"] == {"own.arg": 100}
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()

    plant(tmp_path, rules, "<?php\nclass Box {\n}\n")
    assert main(["map", "--output", "none.json"]) == 0
    assert _read(tmp_path / "none.json")["part_types"] == {}


def test_a_piece_keeps_its_members_main_by_the_stored_part_types(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    piece = _extract(tmp_path, _full(tmp_path, part_types=STORED))

    told = _json(capsys, "undescribed", "--map", str(piece))
    found = _json(capsys, "find", "alpha", "--map", str(piece))

    assert (told["main"], told["left_out"]["parts"], told["part_types"]) == (3, {}, [])
    groups = {row["id"]: row["group"] for row in found["items"]}
    assert groups["t.m::Crate::alpha"] == "main"


def test_undescribed_prints_the_whole_maps_share_not_a_recount(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    full = _full(tmp_path, part_types={"t.m": 75, "t.p": 100})
    piece = _extract(tmp_path, full, ids=[*MEMBERS, "t.p::Crate::alpha::xin"])

    told = _json(capsys, "undescribed", "--map", str(piece))

    assert told["part_types"] == [{"type": "t.m", "share": 75}, {"type": "t.p", "share": 100}]


def test_a_map_file_without_the_field_counts_over_itself(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    piece = _extract(tmp_path, _full(tmp_path))

    told = _json(capsys, "undescribed", "--map", str(piece))

    assert "part_types" not in _read(piece)
    assert (told["main"], told["left_out"]["parts"]) == (1, {"t.m": 2})
    assert told["part_types"] == [{"type": "t.m", "share": 100}]


def test_slice_extract_join_common_and_minus_carry_the_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    full = _full(tmp_path, part_types=STORED)
    one = _extract(tmp_path, full, "one.json", MEMBERS[:2])
    two = _extract(tmp_path, full, "two.json", MEMBERS[1:])
    sliced = tmp_path / "sliced.json"
    assert main(["slice", "--from", MEMBERS[1], "--map", str(full), "--out", str(sliced)]) == 0
    written = {"extract": one, "slice": sliced}
    for command in ("join", "common", "minus"):
        out = tmp_path / f"{command}.json"
        assert main([command, str(one), str(two), "--out", str(out)]) == 0
        written[command] = out

    assert {name: _read(path)["part_types"] for name, path in written.items()} == dict.fromkeys(
        written, STORED
    )


def test_join_keeps_the_field_when_one_input_lacks_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    one = _extract(tmp_path, _full(tmp_path, part_types=STORED), "one.json")
    two = _extract(tmp_path, _full(tmp_path), "two.json")
    out = tmp_path / "joined.json"

    assert main(["join", str(one), str(two), "--out", str(out)]) == 0
    assert _read(out)["part_types"] == STORED


@pytest.mark.parametrize("header", [{}, {"part_types": {}}, {"part_types": STORED}])
def test_check_map_accepts_a_map_with_or_without_the_field(
    tmp_path: Path, header: dict[str, Any]
) -> None:
    assert main(["check-map", "--map", str(_full(tmp_path, **header))]) == 0


def test_check_map_refuses_a_share_that_is_not_a_whole_percent(tmp_path: Path) -> None:
    assert main(["check-map", "--map", str(_full(tmp_path, part_types={"t.p": 0.5}))]) != 0


@pytest.mark.parametrize("stored", [{"t.p": "a"}, {"t.p": 49}, ["t.p"]])
def test_a_malformed_stored_field_is_a_damaged_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stored: Any
) -> None:
    full = _full(tmp_path, part_types=stored)

    assert main(["undescribed", "--map", str(full)]) == 30
    assert "is damaged" in capsys.readouterr().out
