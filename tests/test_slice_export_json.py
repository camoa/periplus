"""The JSON report of `slice` and of `export`: one parsable document per command."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from _navigate import PROV, _edge, _node

from periplus.cli import main
from periplus.navigate import export
from periplus.navigate import slice as slicing

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)


def _validate(document: Any) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(document, schema)


def _plant(tmp_path: Path, edges: int = 1) -> Path:
    nodes = [_node("php::a", line=1), _node("php::b", line=2)]
    wires = [_edge("calls", "php::a", "php::b", i + 1, PROV) for i in range(edges)]
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "1"}],
        "roots": ["."],
        "nodes": nodes,
        "edges": wires,
    }
    path = tmp_path / "site.map.json"
    path.write_text(json.dumps(document))
    return path


def _run(argv: list[str]) -> int:
    try:
        return int(main(argv) or 0)
    except SystemExit as stop:
        return int(stop.code or 0)


def _choices(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[str, ...]:
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(argv)
    err = capsys.readouterr().err
    listed = re.search(r"choose from (.*?)\)", err)
    assert listed, err
    return tuple(part.strip().strip("'") for part in listed.group(1).split(","))


@pytest.mark.criterion(id="c1")
def test_slice_json_for_a_written_slice_holds_the_report_c1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _plant(tmp_path)
    out = tmp_path / "cut.map.json"
    code = _run(["slice", "php::a", "--out", str(out), "--format", "json", "--map", str(source)])
    printed = capsys.readouterr().out
    assert printed.lstrip().startswith("{"), "slice --format json printed no JSON document"
    document = json.loads(printed)
    assert code == 0
    assert document["problems"] == []
    assert document["out"] == str(out)
    assert document["nodes"] >= 1
    assert document["edges"] >= 1
    assert sorted(document) == ["edges", "nodes", "out", "problems", "warnings"]


@pytest.mark.criterion(id="c1")
def test_slice_json_for_a_usage_problem_holds_code_2_c1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _plant(tmp_path)
    out = tmp_path / "cut.map.json"
    code = _run(["slice", "--out", str(out), "--format", "json", "--map", str(source)])
    printed = capsys.readouterr().out
    assert printed.lstrip().startswith("{"), "a usage problem printed no JSON document"
    document = json.loads(printed)
    assert code == 2
    assert document["out"] is None
    assert [problem["code"] for problem in document["problems"]] == [2]


@pytest.mark.criterion(id="c1")
def test_slice_format_choices_match_the_renderer_table_c1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tuple(slicing.RENDERERS) == ("text", "json")
    assert _choices(["slice", "--format", "bogus"], capsys) == tuple(slicing.RENDERERS)


@pytest.mark.criterion(id="c2")
def test_export_report_json_goes_to_stderr_beside_the_graph_c2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _plant(tmp_path, edges=501)
    _run(["export", "--format", "mermaid", "--report", "json", "--map", str(source)])
    captured = capsys.readouterr()
    assert captured.err.lstrip().startswith("{"), "no JSON report on stderr"
    document = json.loads(captured.err)
    assert captured.out.startswith("flowchart")
    assert document["warnings"] != []
    assert document["problems"] == []
    assert document["format"] == "mermaid"
    assert not captured.out.lstrip().startswith("{")


@pytest.mark.criterion(id="c2")
def test_export_report_json_for_a_missing_map_holds_a_problem_c2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "none.map.json"
    argv = ["export", "--format", "mermaid", "--map", str(missing)]
    text_code = _run(argv)
    capsys.readouterr()
    code = _run([*argv, "--report", "json"])
    reported = capsys.readouterr().err
    assert text_code != 0
    assert code == text_code
    assert reported.lstrip().startswith("{"), "a missing map gave no JSON problem on stderr"
    document = json.loads(reported)
    assert len(document["problems"]) == 1


@pytest.mark.criterion(id="c2")
def test_export_report_choices_match_the_renderer_table_c2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tuple(export.RENDERERS) == ("text", "json")
    assert _choices(["export", "--format", "mermaid", "--report", "bogus"], capsys) == tuple(
        export.RENDERERS
    )


@pytest.mark.criterion(id="c3")
def test_slice_and_export_documents_validate_against_the_schema_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _plant(tmp_path, edges=501)
    out = tmp_path / "cut.map.json"
    _run(["slice", "php::a", "--out", str(out), "--format", "json", "--map", str(source)])
    sliced_out = capsys.readouterr().out
    assert sliced_out.lstrip().startswith("{"), "slice printed no JSON"
    sliced = json.loads(sliced_out)
    _run(["slice", "--out", str(out), "--format", "json", "--map", str(source)])
    refused_out = capsys.readouterr().out
    assert refused_out.lstrip().startswith("{"), "refused slice printed no JSON"
    refused = json.loads(refused_out)
    _run(["export", "--format", "mermaid", "--report", "json", "--map", str(source)])
    exported_err = capsys.readouterr().err
    assert '"format"' in exported_err, "export printed no JSON report"
    exported = json.loads(exported_err)
    _run(["export", "--format", "mermaid", "--report", "json", "--map", str(tmp_path / "x")])
    broken_err = capsys.readouterr().err
    assert '"problems"' in broken_err, "broken export printed no JSON report"
    broken = json.loads(broken_err)
    for document in (sliced, refused, exported, broken):
        _validate(document)
    assert "out" in sliced and "format" in exported


@pytest.mark.criterion(id="c3")
def test_schema_rejects_a_slice_without_out_and_an_export_without_problems_c3() -> None:
    slice_report = {"out": None, "nodes": 0, "edges": 0, "warnings": [], "problems": []}
    export_report = {"format": "mermaid", "warnings": [], "problems": []}
    _validate(slice_report)
    _validate(export_report)
    without_out = {key: value for key, value in slice_report.items() if key != "out"}
    without_problems = {k: v for k, v in export_report.items() if k != "problems"}
    for broken in (without_out, without_problems):
        with pytest.raises(jsonschema.ValidationError):
            _validate(broken)
