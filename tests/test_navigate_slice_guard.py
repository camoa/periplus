"""periplus slice refuses an --out that is the map it reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from periplus.errors import ExitCode


def test_slice_refuses_an_out_that_is_the_map_it_reads_and_writes_nothing(tmp_path: Path) -> None:
    from periplus.navigate import slice as slicing

    node = {
        "id": "py::a",
        "type": "function",
        "state": "mapped",
        "locations": [{"file": "src/a.py", "line": 1}],
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }
    document = {
        "periplus_map_version": 3,
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [node],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    (tmp_path / "sub").mkdir()
    spelled = tmp_path / "sub" / ".." / "full-map.json"

    report = slicing.run(tmp_path, {}, ("py::a",), (), "both", 1, (), 500, spelled, path)

    assert report.exit_code == ExitCode.OUTPUT_UNWRITABLE
    assert len(report.problems) == 1
    assert "full-map.json" in report.problems[0].message
    assert report.out is None
    assert path.read_bytes() == before


def test_slice_with_no_ids_and_no_prefix_writes_nothing_and_exits_usage(tmp_path: Path) -> None:
    from periplus.navigate import slice as slicing

    document = {
        "periplus_map_version": 3,
        "type_hierarchy": [],
        "counts": {},
        "nodes": [],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "piece.json"

    report = slicing.run(tmp_path, {}, (), (), "both", 1, (), 500, out, path)

    assert report.exit_code == ExitCode.USAGE
    assert report.out is None
    assert not out.exists()


def test_slice_writes_a_relative_out_under_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from periplus.navigate import slice as slicing

    node = {
        "id": "py::a",
        "type": "function",
        "state": "mapped",
        "locations": [{"file": "src/a.py", "line": 1}],
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }
    document = {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src"],
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [node],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    report = slicing.run(
        tmp_path, {}, ("py::a",), (), "both", 1, (), 500, Path("piece.json"), path
    )

    assert report.out == str(tmp_path / "piece.json")
    assert (tmp_path / "piece.json").exists()


def _two_node_map(path: Path) -> Path:
    def node(id: str, line: int) -> dict[str, object]:
        return {
            "id": id,
            "type": "function",
            "state": "mapped",
            "locations": [{"file": "src/a.py", "line": line}],
            "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
        }

    document = {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src"],
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [node("py::a", 1), node("py::b", 2)],
        "edges": [],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_slice_out_creates_the_missing_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from periplus.cli import main
    from periplus.navigate.mapfile import load_document

    whole = _two_node_map(tmp_path / "full-map.json")
    monkeypatch.chdir(tmp_path)

    code = main(["slice", "--from", "py::a", "--out", "a/b/x.map.json", "--map", str(whole)])

    out = tmp_path / "a" / "b" / "x.map.json"
    assert code == 0
    assert [n["id"] for n in load_document(tmp_path, {}, out)[1]["nodes"]] == ["py::a"]


def test_slice_refused_over_its_limit_creates_no_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from periplus.cli import main

    whole = _two_node_map(tmp_path / "full-map.json")
    monkeypatch.chdir(tmp_path)
    argv = ["slice", "--from", "py::a", "py::b", "--out", "a/b/x.map.json", "--limit", "1"]

    code = main([*argv, "--map", str(whole)])

    assert code == ExitCode.SLICE_TOO_LARGE
    assert not (tmp_path / "a").exists()


@pytest.mark.parametrize("out", ["a/x.map.json", "a/b/x.map.json"])
def test_slice_out_under_a_regular_file_still_exits_27(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], out: str
) -> None:
    from periplus.cli import main

    whole = _two_node_map(tmp_path / "full-map.json")
    (tmp_path / "a").write_text("not a folder", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code = main(["slice", "--from", "py::a", "--out", out, "--map", str(whole)])

    assert code == ExitCode.OUTPUT_UNWRITABLE
    assert (tmp_path / "a").read_text(encoding="utf-8") == "not a folder"
    told = f"the map cannot be written to {tmp_path / out}: {tmp_path / 'a'} is not a folder"
    assert told in capsys.readouterr().out


def test_map_output_creates_the_missing_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from _own_pack import plant

    from periplus.cli import main

    rules = """
node_types:
  - {name: own.box, id_namespace: box}
rules:
  - rule: box
    reads: file
    in: [source]
    match: {declaration: class_declaration, name_child: name, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.box}}]
    confidence: declared
"""
    plant(tmp_path, rules)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config"))

    assert main(["map", "--output", "a/b/m.json"]) == 0
    assert [n["id"] for n in json.loads((tmp_path / "a/b/m.json").read_text())["nodes"]] == [
        "box::Thing"
    ]
