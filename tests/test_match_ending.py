"""A rule's ``match.ending`` keeps only the files whose claimed ending it names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: ends
version: 0.0.1
depends: []
folders:
  src: ./src/**
files:
  types:
    code:
      endings: [inc, theme]
      reader: text
"""

RULES = """\
node_types:
- {{name: ends.item, id_namespace: ends.item}}
rules:
- rule: item
  reads: file
  in: [src]
  match: {{file: '*', filetype: code, text: 'item (?<name>\\w+)'{ending}}}
  id: {{from: {{capture: name}}}}
  emits: [{{node: {{type: ends.item}}}}]
  confidence: declared
"""


def _map(root: Path, ending: str) -> tuple[MapReport, dict[str, Any]]:
    pack = root / ".periplus" / "packs" / "ends@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [ends@0.0.1]\n")
    (pack / "pack.yaml").write_text(MANIFEST)
    (pack / "rules" / "ends.yaml").write_text(RULES.format(ending=ending))
    (root / "src").mkdir()
    (root / "src" / "a.inc").write_text("item one\n")
    (root / "src" / "a.theme").write_text("item two\n")
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((root / "map.json").read_text()) if report.map_path else {}
    return report, document


def _items(document: dict[str, Any]) -> set[str]:
    return {n["id"] for n in document["nodes"] if n["type"] == "ends.item"}


def test_an_ending_reads_the_file_it_names_and_not_another_in_the_same_folder(
    tmp_path: Path,
) -> None:
    report, document = _map(tmp_path, ", ending: inc")
    assert report.problems == () and report.not_executed == (), report
    assert _items(document) == {"ends.item::one"}, document


def test_a_list_of_endings_reads_each(tmp_path: Path) -> None:
    report, document = _map(tmp_path, ", ending: [inc, theme]")
    assert report.problems == () and report.not_executed == (), report
    assert _items(document) == {"ends.item::one", "ends.item::two"}, document


def test_no_ending_reads_every_claimed_file(tmp_path: Path) -> None:
    report, document = _map(tmp_path, "")
    assert report.problems == () and report.not_executed == (), report
    assert _items(document) == {"ends.item::one", "ends.item::two"}, document


def test_an_ending_no_pack_claims_is_refused_naming_the_claimed_endings(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, ", ending: module")
    assert report.map_path is None
    assert [p.code for p in report.problems] == [ExitCode.RULE_NOT_EXECUTABLE], report
    message = report.problems[0].message
    assert "names module" in message and "claimed endings are inc, theme" in message, message


TREE_MANIFEST = """\
pack: ends
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  src: ./src/**
files:
  types:
    code:
      endings: [inc, theme]
      reader: tree
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""

DECLARATION_RULES = """\
node_types:
- {name: ends.item, id_namespace: ends.item}
rules:
- rule: item
  reads: file
  in: [src]
  match: {declaration: function_definition, name_child: name, filetype: code, ending: inc}
  id: {from: declared_name}
  emits: [{node: {type: ends.item}}]
  confidence: declared
"""


def test_a_declaration_rule_ending_reads_the_file_it_names_and_not_another(
    tmp_path: Path,
) -> None:
    pack = tmp_path / ".periplus" / "packs" / "ends@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [ends@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(TREE_MANIFEST)
    (pack / "rules" / "ends.yaml").write_text(DECLARATION_RULES)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.inc").write_text("<?php\n\nfunction one()\n{\n}\n")
    (tmp_path / "src" / "a.theme").write_text("<?php\n\nfunction two()\n{\n}\n")
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    assert _items(document) == {"ends.item::one"}, document
