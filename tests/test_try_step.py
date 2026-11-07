"""A map rule's try step, and the fallback on the name as written."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _own_pack import plant
from ruamel.yaml import YAML

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

RULE = r"""node_types: []
edge_kinds:
- kind: reaches
  from: [php.method]
  to: [php.method]
rules:
- rule: reaches_declaring_method
  reads: map
  match:
    node_type: php.call_site
    where: [{id_matches: '^php\.call_site::(?<site>(?<class>[^:]+)::[^:]+::\$this->(?<member>\w+)->(?<method>\w+))$'}]
    follow:
    - node: 'php.type::{class}'
    - ancestors: [inherits]
    - id_matches: '^php\.type::(?<owner>.+)$'
    - node: 'php.property::{owner}::${member}'
    - edge: property_typed_as
    - id_matches: '^php\.property_type::[^:]+::\$\w+::(?<declarer>\\?[A-Za-z_][\w\\]*)$'
    - TRYSTEP
    - node: 'php.call_site::{site}'
    - edge: call_site_in
  emits: [{edge: {kind: reaches, from: matched_node, to: {template: "{declarer}::{method}", types: [php.method], on_miss: unresolved}}}]
  confidence: inferred
"""  # noqa: E501

TRY_OK = r"""try:
      - node: 'php.type::{declarer}'
      - ancestors: [inherits]
      - id_matches: '^php\.type::(?<declarer>.+)$'
      - node: 'php.method::{declarer}::{method}'"""

BASE = "class Base {\n    public function go() {}\n}\n"
BASE_EMPTY = "class Base {\n}\n"
CHILD = "class Child extends Base {\n}\n"
HOLDER = (
    "class Holder {\n"
    "    private %s $child;\n"
    "    public function act() {\n"
    "        $this->child->go();\n"
    "    }\n"
    "}\n"
)


def _map(root: Path, rules: str, files: dict[str, str]):
    (root / ".periplus").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0, own@0.0.1]\n"
    )
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(
        "pack: own\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  code: ./src\n"
    )
    (pack / "rules" / "own.yaml").write_text(rules)
    (root / "src").mkdir()
    for name, text in files.items():
        (root / "src" / name).write_text("<?php\nnamespace App;\n\n" + text)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=root / "map.json",
    )
    document = json.loads(Path(report.map_path).read_text()) if report.map_path else {}
    return report, document


def _reaches(document):
    return [e for e in document.get("edges", []) if e["kind"] == "reaches"]


def _node(document, node_id):
    return next((n for n in document.get("nodes", []) if n["id"] == node_id), None)


def _field(node, key):
    return node.get(key, node.get("attributes", {}).get(key))


def test_try_reaching_an_ancestor_method_lands_on_the_ancestor_wo3(tmp_path):
    rules = RULE.replace("TRYSTEP", TRY_OK)
    _, doc = _map(
        tmp_path,
        rules,
        {"a.php": BASE, "b.php": CHILD, "c.php": HOLDER % "Child"},
    )
    ends = [(e["from"], e["to"]) for e in _reaches(doc)]
    assert ends == [("php.method::App\\Holder::act", "php.method::App\\Base::go")]
    assert _field(_node(doc, "php.method::App\\Base::go"), "state") != "unresolved"


def test_try_reaching_nothing_lands_unresolved_under_the_class_wo3(tmp_path):
    # The step after the try only holds at the property_type node, so the edge
    # appears only when the walk resumes from where the try began.
    resume_here = TRY_OK + "\n    - id_matches: '^php\\.property_type::(?<resumed>.+)$'"
    rules = RULE.replace("TRYSTEP", resume_here)
    _, doc = _map(
        tmp_path,
        rules,
        {"a.php": BASE_EMPTY, "b.php": CHILD, "c.php": HOLDER % "Child"},
    )
    edges = _reaches(doc)
    assert [e["to"] for e in edges] == ["php.method::App\\Child::go"]
    missing = _node(doc, "php.method::App\\Child::go")
    assert missing is not None
    assert _field(missing, "state") == "unresolved"
    assert _field(missing, "unresolved_detail")["searched_for"] == "App\\Child::go"


def test_try_on_a_type_absent_from_the_map_lands_unresolved_under_the_type_wo3(tmp_path):
    rules = RULE.replace("TRYSTEP", TRY_OK)
    _, doc = _map(tmp_path, rules, {"c.php": HOLDER % "Mailer"})
    edges = _reaches(doc)
    assert [e["to"] for e in edges] == ["php.method::App\\Mailer::go"]
    missing = _node(doc, "php.method::App\\Mailer::go")
    assert missing is not None
    assert _field(missing, "state") == "unresolved"


@pytest.mark.parametrize("value", ["'not a list'", "[]"])
def test_try_that_is_not_a_list_of_steps_refuses_the_rule_wo3(tmp_path, value):
    rules = RULE.replace("TRYSTEP", "try: " + value)
    report, _ = _map(tmp_path, rules, {"c.php": HOLDER % "Mailer"})
    assert "reaches_declaring_method" not in [r for _, r, _ in report.executed]
    messages = [p.message for p in report.problems]
    assert any(
        "reaches_declaring_method" in m and m.endswith("try is not a list of follow steps")
        for m in messages
    )


FALLBACK_RULES = """node_types:
- {name: own.function, id_namespace: own.function}
edge_kinds:
- {kind: calls, from: [own.function], to: [own.function]}
rules:
- rule: function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.function}}]
  confidence: declared
- rule: calls_function
  reads: file
  in: [source]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [own.function], fallback: [as_written], on_miss: unresolved}}}]
  confidence: declared
"""  # noqa: E501


def test_fallback_as_written_gives_the_bare_function_under_a_prefixing_identity_wo3(tmp_path):
    caller = "<?php\nnamespace App;\n\nfunction caller() {\n  helper();\n}\n"
    plant(tmp_path, FALLBACK_RULES, caller)
    manifest = tmp_path / ".periplus" / "packs" / "own@0.0.1" / "pack.yaml"
    yaml = YAML()
    data = yaml.load(manifest.read_text())
    data["identity"]["resolve"] = [{"full_if_prefixed": "\\"}, {"prefix_with": "namespace"}]
    with manifest.open("w") as handle:
        yaml.dump(data, handle)
    (tmp_path / "src" / "helper.php").write_text("<?php\n\nfunction helper() {}\n")
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )
    doc = json.loads(Path(report.map_path).read_text())
    calls = [(e["from"], e["to"]) for e in doc["edges"] if e["kind"] == "calls"]
    assert calls == [("own.function::App\\caller", "own.function::helper")]
    assert _node(doc, "own.function::App\\helper") is None
