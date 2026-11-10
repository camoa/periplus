"""A node type marked internal serves map rules and is left out of the written map."""

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
- {{name: site.function, id_namespace: site.function}}
- {{name: site.hidden, id_namespace: site.hidden{hidden}}}
- {{name: site.callsite, id_namespace: site.callsite{marks}}}
edge_kinds:
- {{kind: calls, from: site.function, to: site.function}}
- {{kind: within, from: {within}, to: site.function}}
- {{kind: reaches, from: site.function, to: site.hidden}}
rules:
- rule: function_line
  reads: file
  in: [src]
  match: {{file: '*', filetype: code, text: '\\bfn (?<name>\\w+)'}}
  id: {{from: {{capture: name}}}}
  emits: [{{node: {{type: site.function}}}}]
  confidence: declared
- rule: call_site
  reads: file
  in: [src]
  match: {{file: '*', filetype: code, text: '(?m)^(?<caller>\\w+) calls (?<callee>\\w+)'}}
  id: {{template: '{{caller}}.{{callee}}'}}
  emits: [{{node: {{type: site.callsite}}}}]
  confidence: declared
- rule: call_edge
  reads: map
  match:
    node_type: site.callsite
    follow:
    - id_matches: '::(?<caller>\\w+)\\.(?<callee>\\w+)$'
    - node: 'site.function::{{caller}}'
  emits:
  - edge:
      kind: calls
      from: matched_node
      to: {{template: 'site.function::{{callee}}'}}
  confidence: declared
- rule: call_within
  reads: map
  match:
    node_type: site.callsite
    follow:
    - id_matches: '::(?<caller>\\w+)\\.(?<callee>\\w+)$'
    - node: 'site.function::{{caller}}'
  emits: [{{edge: {{kind: within, from: this_node, to: matched_node}}}}]
  confidence: declared
{reach}"""

REACH = """\
- rule: call_reach
  reads: map
  match:
    node_type: site.function
    follow:
    - id_matches: '::(?<callee>\\w+)$'
  emits:
  - edge:
      kind: reaches
      from: this_node
      to: {template: 'site.callsite::absent_{callee}', type: site.callsite, on_miss: unresolved}
  confidence: declared
"""

SOURCE = "# header\nfn alpha\nalpha calls beta\nfn beta\nbeta calls gamma\nfn gamma\n"


def _map(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    marks: str,
    hidden: str = "",
    reach: str = "",
) -> dict:
    """Plant the pack, run ``periplus map`` once, and give the written map ({} when none)."""
    rules = RULES.format(
        marks=marks,
        reach=reach,
        hidden=hidden,
        within="site.hidden" if "parent" in marks else "site.callsite",
    )
    rutter(root, "site", MANIFEST, {"site.yaml": rules})
    pin(root, "site@0.0.1")
    plant(root, {"src/one.sx": SOURCE})
    capsys.readouterr()
    main(["map", "--output", str(root / "out.json")])
    out = root / "out.json"
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


@pytest.mark.criterion(id="c3")
def test_an_internal_call_site_type_serves_the_map_rule_and_is_left_out_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _map(tmp_path, capsys, ", internal: true")
    summary = capsys.readouterr().out
    edges = {(e["from"], e["to"]): e for e in written.get("edges", [])}
    edge = edges.get(("site.function::alpha", "site.function::beta"))
    assert edge is not None, sorted(edges)
    assert [loc["line"] for loc in edge["locations"]] == [3]
    assert not [n for n in written["nodes"] if n["type"] == "site.callsite"]
    assert not [e for e in written["edges"] if "site.callsite" in (e["from"] + e["to"])]
    assert "internal: 2 nodes and 2 edges left out" in summary


@pytest.mark.criterion(id="c3")
def test_an_internal_type_below_a_parent_and_an_unresolved_end_of_it_leave_the_map_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _map(tmp_path, capsys, ", parent: site.hidden", ", internal: true", REACH)
    nodes = written.get("nodes", [])
    assert nodes, "the map was not written"
    assert not [n["id"] for n in nodes if n["type"] == "site.callsite"]
    ids = {n["id"] for n in nodes}
    assert not [e for e in written["edges"] if e["from"] not in ids or e["to"] not in ids]
    assert not [n["id"] for n in nodes if "absent_" in n["id"]]
    assert ("site.function::alpha", "site.function::beta") in {
        (e["from"], e["to"]) for e in written["edges"]
    }
