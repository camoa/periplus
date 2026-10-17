"""A reference rule's edge end written as a template, with no receiver condition: the template
reads ``enclosing_type``, ``enclosing_method`` and the named groups of the rule's own
``name_matches`` conditions, and the rutter writes every separator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.engine.packload import _read_rule
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

PAGE = """\
<?php
namespace App\\Web;

class Page
{
  public function run(): void
  {
    $this->mailer->send();
    $other->send();
  }
}
"""

RULES = """\
node_types:
- {name: own.member_call, id_namespace: own.member_call}
edge_kinds:
- {kind: calls_member, from: php.method, to: own.member_call}
rules:
- rule: member_call
  reads: file
  in: [source]
  match:
    reference: member_call_expression
    name_child: [object, name]
    filetype: php
    where:
    - name_matches: {child: object, pattern: '\\$this->(?<member>\\w+)'}
    - name_matches: {child: name, pattern: '(?<method>\\w+)'}
  emits:
  - edge:
      kind: calls_member
      from: enclosing_declaration
      to: {template: '{TEMPLATE}', types: [own.member_call], on_miss: unresolved}
  confidence: inferred
"""


def _map(root: Path, template: str) -> tuple[MapReport, dict[str, Any]]:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(
        "pack: own\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  source: ./src\n"
        "files:\n  extends: php_basic\n"
    )
    (pack / "rules" / "calls.yaml").write_text(RULES.replace("{TEMPLATE}", template))
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [own@0.0.1]\n")
    (root / "src").mkdir()
    (root / "src" / "Page.php").write_text(PAGE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    return report, json.loads((root / "map.json").read_text())


def _edges(document: dict[str, Any]) -> list[tuple[str, str, list[int]]]:
    return sorted(
        (e["from"], e["to"], [place["line"] for place in e["locations"]])
        for e in document["edges"]
        if e["kind"] == "calls_member"
    )


def test_a_template_of_the_enclosing_type_and_two_name_groups_makes_the_edge(
    tmp_path: Path,
) -> None:
    """$this->mailer->send() fits both conditions: one edge from run to the id the template
    writes, at the call's line. $other->send() fails the object's pattern and makes nothing."""
    report, document = _map(tmp_path, "{enclosing_type}::${member}::{method}")
    assert report.not_executed == (), report.not_executed
    assert _edges(document) == [
        ("php.method::App\\Web\\Page::run", "own.member_call::App\\Web\\Page::$mailer::send", [8])
    ], _edges(document)
    assert [row for row in report.skipped if row[2] == "member_call"] == [], report.skipped


def test_a_template_may_name_the_enclosing_method(tmp_path: Path) -> None:
    """enclosing_method is the declared name of the method holding the call."""
    _, document = _map(tmp_path, "{enclosing_type}::{enclosing_method}::{method}")
    assert [to for _, to, _ in _edges(document)] == [
        "own.member_call::App\\Web\\Page::run::send"
    ], _edges(document)


def test_a_template_naming_another_name_is_not_executed() -> None:
    """A name that is neither enclosing_type, enclosing_method nor a group of the rule's
    name_matches conditions leaves the rule not executed."""
    rule = _read_rule(
        "own",
        {
            "rule": "r",
            "reads": "file",
            "in": ["source"],
            "match": {
                "reference": "member_call_expression",
                "name_child": ["object", "name"],
                "filetype": "php",
                "where": [{"name_matches": {"child": "name", "pattern": "(?<method>\\w+)"}}],
            },
            "emits": [
                {
                    "edge": {
                        "kind": "calls",
                        "from": "enclosing_declaration",
                        "to": {"template": "{enclosing_type}::{member}::{method}"},
                    }
                }
            ],
            "confidence": "inferred",
        },
    )
    assert not rule.supported and "template end" in rule.reason, rule
