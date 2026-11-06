"""A pack may not give the resolution mark a value the map schema rejects (c4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.cli import main

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
      template: static
  confidence: declared
"""


@pytest.mark.criterion(id="c4")
def test_validate_refuses_a_resolution_value_other_than_runtime_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        ".periplus/settings.yml": "periplus_version: 0\npacks:\n  - own@0.0.1\n",
        f"{PACK}/pack.yaml": MANIFEST,
        f"{PACK}/rules/own.yaml": RULES,
        "src/Thing.php": (
            "<?php\nclass Thing {\n  public function run() {\n    $this->go();\n  }\n}\n"
        ),
    }
    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-home"))
    assert main(["validate", "own@0.0.1"]) != 0
