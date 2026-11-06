"""A third-party pack can mark a node as an unknown boundary (c4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from periplus.cli import main
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

PACK = ".periplus/packs/own@0.0.1"
MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  source: src
grammar:
  provider: tree-sitter
  provider_version: 0.26.0
  language: php
  grammar_version: 0.24.1
files:
  types:
    php:
      endings: [php]
      reader: tree
identity:
  qualified_name:
    parts: [namespace, declared_name]
    separator: "\\\\"
  namespace:
    declaration: namespace_definition
    name_child: name
  written_names: [name, qualified_name]
"""
SOURCE = "<?php\nclass Thing {\n  public function run() {\n    $this->go();\n  }\n}\n"
RULES = """\
node_types:
- name: own.call_site
  id_namespace: own.call_site
rules:
- rule: call_site_from_call
  reads: file
  in:
  - source
  match:
    declaration: member_call_expression
    name_child: name
    filetype: php
  id:
    from: declared_name
  emits:
  - node:
      type: own.call_site
  - attribute:
      name: resolution
      template: runtime
  confidence: declared
"""


def _plant(root: Path) -> None:
    files = {
        ".periplus/settings.yml": "periplus_version: 0\npacks:\n  - own@0.0.1\n",
        f"{PACK}/pack.yaml": MANIFEST,
        f"{PACK}/rules/own.yaml": RULES,
        "src/Thing.php": SOURCE,
    }
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


@pytest.mark.criterion(id="c4")
def test_third_party_pack_marks_a_node_and_validates_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(tmp_path)
    env = {"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-home")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", env["PERIPLUS_CONFIG_DIR"])
    assert main(["validate", "own@0.0.1"]) == 0
    report = run(
        start=tmp_path,
        env=env,
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert report.map_path is not None
    document = json.loads(Path(report.map_path).read_text())
    marked = [n for n in document["nodes"] if n["type"] == "own.call_site"]
    assert len(marked) == 1
    assert marked[0]["attributes"]["resolution"] == "runtime"
