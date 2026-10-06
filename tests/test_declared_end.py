"""Tests for the edge end ``{declared: <type>}`` of a tree declaration rule: the id of the node of
that type a rule of the pack or a pack it depends on declares at the same match."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.engine import packload
from periplus.engine.packload import EdgeKind, TypeInfo
from periplus.errors import ExitCode
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: tagger
version: 0.0.1
depends: [php_basic]
folders:
  code: ./**
  sub: sub/**
files:
  extends: php_basic
  add_extensions: [module]
"""

RULES = """\
node_types:
- {name: tag.task, id_namespace: tag.task}
edge_kinds:
- {kind: runs_task, from: php.function, to: tag.task}
rules:
- rule: task
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^mymod_(?<task>.+)$', template: '{task}'}
  emits: [{node: {type: tag.task}}]
  confidence: declared
- rule: runs
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  emits: [{edge: {kind: runs_task, from: FROM, to: TO}}]
  confidence: declared
"""

SOURCE = "<?php\n\nfunction mymod_cron()\n{\n}\n\nfunction helper()\n{\n}\n"


def _map(
    root: Path, start: str, finish: str, rules: str = RULES, source: str = SOURCE
) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "tagger@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [tagger@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "tag.yaml").write_text(rules.replace("FROM", start).replace("TO", finish))
    (root / "mymod.module").write_text(source)
    return report_of(root)


def report_of(root: Path) -> tuple[MapReport, Any]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


def test_both_ends_take_the_node_another_rule_declared_at_the_match(tmp_path: Path) -> None:
    """The function's id comes from php_basic's rule and the task's from this pack's own rule;
    helper declares no task, so it makes no edge and leaves one row that names the end."""
    report, document = _map(tmp_path, "{declared: php.function}", "{declared: tag.task}")
    assert report.problems == (), report
    edges = [(e["kind"], e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("runs_task", "php.function::mymod_cron", "tag.task::cron")]
    rows = [(line, rule, reason) for _, line, rule, reason in report.skipped]
    assert rows == [(7, "runs", "edge runs_task: no value for {declared: tag.task}")]


def test_a_second_rule_gives_the_id_where_the_first_that_fires_gives_none(tmp_path: Path) -> None:
    """Two rules declare tag.task; at other_init the first fires and its pattern does not fit, so
    the second gives the id."""
    second = (
        "- rule: other_task\n  reads: file\n  in: [code]\n"
        "  match: {declaration: function_definition, name_child: name, filetype: php}\n"
        "  id: {from: declared_name, pattern: '^other_(?<task>.+)$', template: '{task}'}\n"
        "  emits: [{node: {type: tag.task}}]\n  confidence: declared\n"
    )
    source = "<?php\n\nfunction mymod_cron()\n{\n}\n\nfunction other_init()\n{\n}\n"
    report, document = _map(
        tmp_path, "{declared: php.function}", "{declared: tag.task}", RULES + second, source
    )
    assert report.problems == (), report
    assert report.skipped == ()
    edges = [(e["kind"], e["from"], e["to"]) for e in document["edges"]]
    assert edges == [
        ("runs_task", "php.function::mymod_cron", "tag.task::cron"),
        ("runs_task", "php.function::other_init", "tag.task::init"),
    ]


CALLS = """\
node_types:
- {name: tag.route, id_namespace: tag.route}
- {name: tag.site, id_namespace: tag.site}
edge_kinds:
- {kind: at_route, from: tag.site, to: tag.route}
rules:
- rule: route
  reads: file
  in: [code]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: get}]
  id: {from: {argument: 0}}
  emits: [{node: {type: tag.route}}]
  confidence: declared
- rule: site
  reads: file
  in: [code]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: get}]
  id: {from: declared_name}
  emits: [{edge: {kind: at_route, from: FROM, to: TO}}]
  confidence: declared
"""


def test_an_id_from_a_call_argument_fills_the_end(tmp_path: Path) -> None:
    source = '<?php\n\nRoute::get("/home", "x");\n'
    report, document = _map(tmp_path, "this_node", "{declared: tag.route}", CALLS, source)
    assert report.problems == (), report
    edges = [(e["kind"], e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("at_route", "tag.site::get", "tag.route::/home")]


def test_an_end_no_rule_maps_takes_its_named_type_alone(tmp_path: Path) -> None:
    """The kind's to end lists tag.task and tag.job, which lie on no one chain. The rule declaring
    tag.task reads only sub, so tag.task::cron is referenced, and of the type the end names."""
    rules = RULES.replace("to: tag.task}", "to: [tag.task, tag.job]}").replace(
        "- {name: tag.task, id_namespace: tag.task}\n",
        "- {name: tag.task, id_namespace: tag.task}\n- {name: tag.job, id_namespace: tag.job}\n",
    )
    rules = rules.replace("in: [code]", "in: [sub]", 1)
    report, document = _map(tmp_path, "{declared: php.function}", "{declared: tag.task}", rules)
    assert report.problems == (), report
    nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
    assert nodes["tag.task::cron"] == ("tag.task", "referenced"), nodes


@pytest.mark.parametrize(
    ("start", "finish", "side", "named"),
    [
        ("{declared: tag.task}", "{declared: tag.task}", "from", "tag.task"),
        ("{declared: php.function}", "{declared: php.function}", "to", "php.function"),
    ],
)
def test_an_end_of_a_type_the_kind_does_not_allow_there_stops_with_22(
    tmp_path: Path, start: str, finish: str, side: str, named: str
) -> None:
    report, document = _map(tmp_path, start, finish)
    assert [p.code for p in report.problems] == [ExitCode.EDGE_ILLEGAL], report
    stated = f"the rule runs names its {side} end {{declared: {named}}}"
    assert stated in report.problems[0].message, report.problems[0].message
    assert document is None


def test_a_type_no_reachable_pack_declares_is_refused_as_undeclared(tmp_path: Path) -> None:
    """nope.thing is declared nowhere; other.fn by a pack that tagger does not depend on."""
    nowhere, _ = _map(tmp_path / "a", "{declared: nope.thing}", "{declared: tag.task}")
    assert [p.code for p in nowhere.problems] == [ExitCode.UNDECLARED_TYPE], nowhere
    assert "nope.thing" in nowhere.problems[0].message
    root = tmp_path / "b"
    _map(root, "{declared: other.fn}", "{declared: tag.task}")
    other = root / ".periplus" / "packs" / "other@0.0.1"
    (other / "rules").mkdir(parents=True)
    (other / "pack.yaml").write_text(
        "pack: other\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  ocode: ./**\n"
    )
    (other / "rules" / "o.yaml").write_text(
        "node_types:\n- {name: other.fn, parent: php.function}\nrules:\n- rule: fn\n"
        "  reads: file\n  in: [ocode]\n"
        "  match: {declaration: function_definition, name_child: name, filetype: php}\n"
        "  id: {from: declared_name}\n  emits: [{node: {type: other.fn}}]\n"
        "  confidence: declared\n"
    )
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [other@0.0.1, tagger@0.0.1]\n"
    )
    elsewhere, _ = report_of(root)
    assert [p.code for p in elsewhere.problems] == [ExitCode.UNDECLARED_TYPE], elsewhere
    assert "other.fn" in elsewhere.problems[0].message


TYPES = {name: TypeInfo(name, name, None, "p") for name in ("own.fn", "own.method", "own.tag")}

KINDS = {
    "tags": EdgeKind("tags", ("own.fn", "own.method"), ("own.tag",)),
    "tagged": EdgeKind("tagged", ("own.tag",), ("own.fn", "own.method")),
}


def _read(match: dict[str, Any], start: object, finish: object, kind: str) -> packload.Rule:
    item = {
        "rule": "r",
        "reads": "file",
        "in": ["code"],
        "match": match,
        "id": {"from": {"attribute_argument": 0} if "attribute" in match else "declared_name"},
        "emits": [{"edge": {"kind": kind, "from": start, "to": finish}}],
        "confidence": "declared",
    }
    return packload._read_rule("p", item)


def _checked(
    match: dict[str, Any], start: object, finish: object, kind: str = "tags"
) -> packload.Rule:
    return packload._check_edges(_read(match, start, finish, kind), TYPES, KINDS)


ATTRIBUTE = {"attribute": "A", "filetype": "php", "where": [{"applies_to": "method_declaration"}]}
ANNOTATION = {"annotation": "A", "filetype": "php", "where": [{"applies_to": "method_declaration"}]}
DECLARATION = {"declaration": "function_definition", "name_child": "name", "filetype": "php"}


def test_an_end_of_whole_ids_may_list_types_of_two_namespaces() -> None:
    """The from types of the kind have two id namespaces; an end that takes a whole id keeps the
    rule executed, and this_node, which needs one namespace, does not."""
    method = _checked(ATTRIBUTE, "enclosing_method", "this_node")
    declared = _checked(DECLARATION, {"declared": "own.fn"}, "this_node")
    named = _checked(DECLARATION, "this_node", {"declared": "own.tag"})
    assert method.supported, method.reason
    assert declared.supported, declared.reason
    assert not named.supported
    assert "do not share one id namespace" in named.reason


def test_a_to_end_of_whole_ids_may_list_types_of_two_namespaces() -> None:
    """The same at the to end: the kind's to types have two id namespaces."""
    method = _checked(ATTRIBUTE, "this_node", "enclosing_method", "tagged")
    declared = _checked(DECLARATION, "this_node", {"declared": "own.fn"}, "tagged")
    named = _checked(DECLARATION, {"declared": "own.tag"}, "this_node", "tagged")
    assert method.supported, method.reason
    assert declared.supported, declared.reason
    assert not named.supported
    assert "do not share one id namespace" in named.reason


@pytest.mark.parametrize(
    ("match", "start", "id_from"),
    [
        (ATTRIBUTE, {"declared": "own.fn"}, {"attribute_argument": 0}),
        (ANNOTATION, {"declared": "own.fn"}, {"annotation_key": "id"}),
        (DECLARATION, {"template": "x"}, "declared_name"),
    ],
)
def test_a_mapping_end_a_reader_does_not_run_is_refused(
    match: dict[str, Any], start: object, id_from: object
) -> None:
    item = {
        "rule": "r",
        "reads": "file",
        "in": ["code"],
        "match": match,
        "id": {"from": id_from},
        "emits": [{"edge": {"kind": "tags", "from": start, "to": "this_node"}}],
        "confidence": "declared",
    }
    rule = packload._read_rule("p", item)
    assert not rule.supported
    assert "does not run from" in rule.reason


METHODS = """\
pack: marks
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  attribute:
    node: attribute
    list: attribute_list
    arguments: parameters
    argument: argument
    argument_name: name
    literals: [string, encapsed_string]
    literal_content: string_content
"""

MARKS = """\
node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.method, id_namespace: own.method}
- {name: own.mark, id_namespace: own.mark}
edge_kinds:
- {kind: marked, from: own.method, to: own.mark}
rules:
- rule: find_class
  reads: file
  in: [source]
  match:
    declaration: class_declaration
    name_child: name
    body_child: declaration_list
    filetype: php
  id: {from: qualified_name}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: prefixed_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^zzz(?<rest>.+)$', template: '{enclosing_type}::{rest}'}
  emits: [{node: {type: own.method}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: own.method}}]
  confidence: declared
- rule: mark
  reads: file
  in: [source]
  match: {attribute: Mark, filetype: php, where: [{applies_to: method_declaration}]}
  id: {from: {attribute_argument: '0'}}
  emits: [{edge: {kind: marked, from: enclosing_method, to: this_node}}]
  confidence: declared
"""


def test_enclosing_method_takes_the_next_rule_where_the_first_that_fires_mints_none(
    tmp_path: Path,
) -> None:
    """prefixed_method fires first on bar and its pattern does not fit, so find_method gives the
    method's id, as it gives a declared end's."""
    pack = tmp_path / ".periplus" / "packs" / "marks@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [marks@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(METHODS)
    (pack / "rules" / "marks.yaml").write_text(MARKS)
    (tmp_path / "a.php").write_text(
        '<?php\n\nclass Foo\n{\n    #[Mark("x")]\n    public function bar()\n    {\n    }\n}\n'
    )
    report, document = report_of(tmp_path)
    assert report.problems == (), report
    assert report.skipped == ()
    edges = [(e["kind"], e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("marked", "own.method::Foo::bar", "own.mark::x")]
