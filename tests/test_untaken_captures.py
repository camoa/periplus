"""A template naming a capture of an optional group that took no part fills it as empty text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import pin, plant, rutter

from periplus.cli import main

MANIFEST = """\
pack: opt
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    code:
      endings: [sx]
      reader: text
"""

RULES = """\
node_types:
- {name: opt.caller, id_namespace: opt.caller}
- {name: opt.thing, id_namespace: opt.thing}
edge_kinds:
- {kind: makes, from: opt.caller, to: opt.thing}
- {kind: marks, from: opt.caller, to: opt.thing}
rules:
- rule: maker
  reads: file
  in: [src]
  match:
    file: '*'
    filetype: code
    text: '(?m)^(?<who>\\w+) create\\("(?<pkg>\\w+)(?:\\.(?<sub>\\w+))?"\\)'
  id: {from: {capture: who}}
  emits:
  - edge: {kind: makes, from: this_node, to: {template: '{pkg}{sub}', types: [opt.thing]}}
  - edge: {kind: marks, from: this_node, to: {template: 'x{sub}', types: [opt.thing]}}
  confidence: declared
- rule: thing
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^thing (?<pkg>\\w+)(?:\\.(?<sub>\\w+))?$'}
  values:
    full: {template: '{pkg}{sub}', case: upper}
  id: {template: '{pkg}-{sub}'}
  emits:
  - node: {type: opt.thing}
  - attribute: {name: full, from: {value: full}}
  confidence: declared
"""

SOURCE = 'one create("alpha")\ntwo create("alpha.beta")\nthing gamma\nthing gamma.delta\n'


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _map(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[dict, dict]:
    rutter(root, "opt", MANIFEST, {"opt.yaml": RULES})
    pin(root, "opt@0.0.1")
    plant(root, {"src/one.sx": SOURCE})
    capsys.readouterr()
    status = main(["map", "--format", "json", "--output", str(root / "out.json")])
    report = json.loads(capsys.readouterr().out)
    assert (status, report["problems"]) == (0, []), report
    return report, json.loads((root / "out.json").read_text(encoding="utf-8"))


def _edges(document: dict, kind: str) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == kind}


def test_an_edge_template_fills_a_capture_that_took_no_part_as_empty_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, document = _map(tmp_path, capsys)

    assert _edges(document, "makes") == {
        ("opt.caller::one", "opt.thing::alpha"),
        ("opt.caller::two", "opt.thing::alphabeta"),
    }


def test_an_id_and_a_value_template_fill_a_capture_that_took_no_part_as_empty_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, document = _map(tmp_path, capsys)

    things = {
        n["id"]: n.get("attributes", {}).get("full")
        for n in document["nodes"]
        if n["type"] == "opt.thing" and n["id"].startswith("opt.thing::gamma")
    }
    assert things == {"opt.thing::gamma-": "GAMMA", "opt.thing::gamma-delta": "GAMMADELTA"}


def test_a_template_whose_every_name_took_no_part_makes_nothing_and_leaves_no_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report, document = _map(tmp_path, capsys)

    assert _edges(document, "marks") == {("opt.caller::two", "opt.thing::xbeta")}
    skipped = report["skipped"]
    assert [row for row in skipped if "marks" in row["reason"]] == [], skipped
