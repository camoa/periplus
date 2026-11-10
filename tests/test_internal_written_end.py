"""An end claimed by a written type and by an internal type below it stays in the map."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import pin, plant, rutter

from periplus.cli import main

MANIFEST = """\
pack: site
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
- {name: site.function, id_namespace: site.function}
- {name: site.inner, id_namespace: site.function, parent: site.function, internal: true}
edge_kinds:
- {kind: calls, from: site.function, to: site.function}
- {kind: peeks, from: site.function, to: site.inner}
rules:
- rule: function_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '\\bfn (?<name>\\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: site.function}}]
  confidence: declared
- rule: call_ghost
  reads: map
  match:
    node_type: site.function
    follow:
    - id_matches: '::alpha$'
  emits:
  - edge:
      kind: calls
      from: this_node
      to: {template: 'site.function::ghost', type: site.function, on_miss: unresolved}
  confidence: declared
- rule: peek_ghost
  reads: map
  match:
    node_type: site.function
    follow:
    - id_matches: '::alpha$'
  emits:
  - edge:
      kind: peeks
      from: this_node
      to: {template: 'site.function::ghost', type: site.inner, on_miss: unresolved}
  confidence: declared
"""


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


@pytest.mark.criterion(id="c3")
def test_an_end_a_written_type_also_claims_keeps_that_type_and_its_edge_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rutter(tmp_path, "site", MANIFEST, {"site.yaml": RULES})
    pin(tmp_path, "site@0.0.1")
    plant(tmp_path, {"src/one.sx": "fn alpha\n"})
    main(["map", "--output", str(tmp_path / "out.json")])
    out = capsys.readouterr().out
    written = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    ghost = [n for n in written["nodes"] if n["id"] == "site.function::ghost"]
    assert [n["type"] for n in ghost] == ["site.function"], out
    calls = {(e["from"], e["to"]) for e in written["edges"] if e["kind"] == "calls"}
    assert ("site.function::alpha", "site.function::ghost") in calls, out
