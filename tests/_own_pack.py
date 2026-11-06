"""One third-party pack, `own@0.0.1`, planted into a project for the tests that mark a node."""

from __future__ import annotations

from pathlib import Path

PACK = ".periplus/packs/own@0.0.1"
SETTINGS = "periplus_version: 0\npacks:\n  - own@0.0.1\n"
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
    note:
      endings: [txt]
      reader: text
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


def plant(root: Path, rules: str, source: str = SOURCE) -> None:
    """Write the settings, the pack with `rules` as its one rule file, and one PHP source."""
    files = {
        ".periplus/settings.yml": SETTINGS,
        f"{PACK}/pack.yaml": MANIFEST,
        f"{PACK}/rules/own.yaml": rules,
        "src/Thing.php": source,
    }
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
