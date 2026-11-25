"""The ``in_table`` follow step: a map rule tests a capture against a table, and may bring the
table's value for it into its captures."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  yard: ./yard
files:
  types:
    yard:
      endings: [yard]
      reader: text
tables:
  kinds: {red: Paint, blue: Ink}
"""

#: Adds green to own's table kinds.
EXTENDER = """\
pack: ext
version: 0.0.1
depends: [own]
add_table_rows:
  own:
    kinds: {green: Leaf}
"""

#: ``use <kind> <name>`` is a use, ``thing <sort> <name>`` a thing. FOLLOW is the follow of the
#: map rule ``joined``, which emits ``touches`` from the use to the node it reached.
RULES = r"""node_types:
- {name: own.use, id_namespace: own.use}
- {name: own.thing, id_namespace: own.thing}
edge_kinds:
- {kind: touches, from: own.use, to: [own.use, own.thing]}
rules:
- rule: use
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^use (?<k>\w+) (?<n>\w+)'}
  id: {template: '{k}.{n}'}
  emits: [{node: {type: own.use}}]
  confidence: declared
- rule: thing
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^thing (?<s>\w+) (?<n>\w+)'}
  id: {template: '{s}.{n}'}
  emits: [{node: {type: own.thing}}]
  confidence: declared
- rule: joined
  reads: map
  match:
    node_type: own.use
    where: [{id_matches: '^own\.use::(?<k>\w+)\.(?<n>\w+)$'}]
    follow: FOLLOW
  emits: [{edge: {kind: touches, from: this_node, to: matched_node}}]
  confidence: inferred
"""

YARD = (
    "use red apple\nuse blue sky\nuse green leaf\n"
    "thing Paint apple\nthing Ink sky\nthing Leaf leaf\n"
)

LOOKUP = "[{in_table: {table: kinds, capture: k, value: sort}}, {node: 'own.thing::{sort}.{n}'}]"


def _map(root: Path, follow: str, extender: bool = False):
    packs = ".periplus/packs"
    files = {
        f"{packs}/own@0.0.1/pack.yaml": MANIFEST,
        f"{packs}/own@0.0.1/rules/own.yaml": RULES.replace("FOLLOW", follow),
        "yard/a.yard": YARD,
    }
    pins = ["own@0.0.1"]
    if extender:
        files[f"{packs}/ext@0.0.1/pack.yaml"] = EXTENDER
        pins.append("ext@0.0.1")
    files[".periplus/settings.yml"] = f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    plant(root, files)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((root / "map.json").read_text()) if report.map_path else {}
    return report, document


def _touches(document) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "touches"}


def _refused(report, reason: str) -> bool:
    return any(
        p.message.endswith(f"the rule joined cannot be executed: {reason}") for p in report.problems
    )


def test_the_value_for_a_captured_key_names_the_next_node(tmp_path: Path) -> None:
    report, document = _map(tmp_path, LOOKUP)
    assert report.problems == () and report.not_executed == (), report
    assert _touches(document) == {
        ("own.use::red.apple", "own.thing::Paint.apple"),
        ("own.use::blue.sky", "own.thing::Ink.sky"),
    }


def test_a_row_a_loaded_dependent_adds_is_looked_up(tmp_path: Path) -> None:
    report, document = _map(tmp_path, LOOKUP, extender=True)
    assert report.problems == () and report.not_executed == (), report
    assert ("own.use::green.leaf", "own.thing::Leaf.leaf") in _touches(document)


def test_without_value_the_step_passes_only_a_key_of_the_table(tmp_path: Path) -> None:
    report, document = _map(tmp_path, "[{in_table: {table: kinds, capture: k}}]")
    assert report.problems == () and report.not_executed == (), report
    assert _touches(document) == {
        ("own.use::red.apple", "own.use::red.apple"),
        ("own.use::blue.sky", "own.use::blue.sky"),
    }


def test_a_miss_inside_a_try_lets_the_later_steps_run(tmp_path: Path) -> None:
    follow = (
        "[{try: [{in_table: {table: kinds, capture: k, value: sort}},"
        " {node: 'own.thing::{sort}.{n}'}]}]"
    )
    report, document = _map(tmp_path, follow)
    assert report.problems == () and report.not_executed == (), report
    assert _touches(document) == {
        ("own.use::red.apple", "own.thing::Paint.apple"),
        ("own.use::blue.sky", "own.thing::Ink.sky"),
        ("own.use::green.leaf", "own.use::green.leaf"),
    }


def test_a_table_no_visible_pack_declares_is_refused(tmp_path: Path) -> None:
    follow = "[{in_table: {table: colours, capture: k, value: sort}}]"
    report, document = _map(tmp_path, follow)
    assert _refused(
        report,
        "the follow step in_table names the table colours, which no tables key of the pack or a "
        "pack it depends on declares",
    ), report.problems
    assert document == {}


def test_a_capture_no_step_before_it_makes_is_refused(tmp_path: Path) -> None:
    follow = "[{in_table: {table: kinds, capture: colour, value: sort}}]"
    report, _ = _map(tmp_path, follow)
    assert _refused(
        report,
        "the follow step in_table names the capture colour, which no id_matches captures before it",
    ), report.problems


def test_a_value_named_as_an_existing_capture_is_refused(tmp_path: Path) -> None:
    follow = "[{in_table: {table: kinds, capture: k, value: n}}]"
    report, _ = _map(tmp_path, follow)
    assert _refused(
        report,
        "the follow step in_table gives the capture n, which a step before it already captures",
    ), report.problems


TYPED_MANIFEST = MANIFEST.replace(
    "  kinds: {red: Paint, blue: Ink}\n", "  sorts: {red: own.paint, blue: own.ink}\n"
)

#: ``paint <name>`` and ``ink <name>`` are things of two types; the map rule ``joined`` gives the
#: end of its ``touches`` edge the type the table sorts holds for the use's kind. The kind allows
#: types of two id namespaces there, and two types of the namespace own.ink. END_TYPE is that
#: end's type, and EXTRA_TYPES room for more node types.
TYPED_RULES = r"""node_types:
- {name: own.use, id_namespace: own.use}
- {name: own.thing, id_namespace: own.thing, abstract: true}
- {name: own.paint, parent: own.thing, id_namespace: own.paint}
- {name: own.ink, parent: own.thing, id_namespace: own.ink}
- {name: own.dye, parent: own.thing, id_namespace: own.ink}
- {name: own.outside, id_namespace: own.outside, boundary: true}
EXTRA_TYPES
edge_kinds:
- {kind: touches, from: own.use, to: [own.dye, own.paint, own.ink]}
- {kind: next, from: own.use, to: own.use}
- {kind: backs, from: [own.dye, own.paint, own.ink], to: own.use}
- {kind: beyond, from: [own.dye, own.paint, own.ink], to: own.outside}
edge_attributes:
- {name: sort, on: [next], description: a sort a use passes on}
rules:
- rule: use
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^use (?<k>\w+) (?<n>\w+)'}
  id: {template: '{k}.{n}'}
  emits: [{node: {type: own.use}}]
  confidence: declared
- rule: paint
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^paint (?<n>\w+)'}
  id: {from: {capture: n}}
  emits: [{node: {type: own.paint}}]
  confidence: declared
- rule: joined
  reads: map
  match:
    node_type: own.use
    where: [{id_matches: '^own\.use::(?<k>\w+)\.(?<n>\w+)$'}]
    follow: FOLLOW
  emits: [EMITS]
  confidence: inferred
EXTRA_RULES"""

TYPED_YARD = "use red apple\nuse blue sky\nuse green leaf\npaint apple\n"


TYPED_FOLLOW = "[{in_table: {table: sorts, capture: k, value: sort}}]"
TYPED_EMITS = "{edge: {kind: touches, from: this_node, to: {template: '{n}', types: ['END_TYPE']}}}"


def _typed(
    root: Path,
    type_: str = "{sort}",
    follow: str = TYPED_FOLLOW,
    manifest: str = TYPED_MANIFEST,
    extra_types: str = "",
    extender: str | None = None,
    emits: str = TYPED_EMITS,
    extra_rules: str = "",
):
    packs = ".periplus/packs"
    rules = TYPED_RULES.replace("EMITS", emits).replace("EXTRA_RULES", extra_rules)
    rules = rules.replace("END_TYPE", type_).replace("EXTRA_TYPES\n", extra_types)
    rules = rules.replace("FOLLOW", follow)
    files = {
        f"{packs}/own@0.0.1/pack.yaml": manifest,
        f"{packs}/own@0.0.1/rules/own.yaml": rules,
        "yard/a.yard": TYPED_YARD,
    }
    pins = ["own@0.0.1"]
    if extender is not None:
        files[f"{packs}/ext@0.0.1/pack.yaml"] = extender
        pins.append("ext@0.0.1")
    files[".periplus/settings.yml"] = f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    plant(root, files)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((root / "map.json").read_text()) if report.map_path else {}
    return report, document


def _messages(report) -> list[str]:
    return [p.message for p in report.problems]


def test_an_end_takes_the_type_the_table_gives_for_the_key(tmp_path: Path) -> None:
    report, document = _typed(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _touches(document) == {
        ("own.use::red.apple", "own.paint::apple"),
        ("own.use::blue.sky", "own.ink::sky"),
    }
    states = {n["id"]: (n["type"], n.get("state")) for n in document["nodes"]}
    assert states["own.ink::sky"] == ("own.ink", "referenced")


def test_a_row_naming_an_undeclared_type_is_refused(tmp_path: Path) -> None:
    manifest = TYPED_MANIFEST.replace("blue: own.ink", "blue: own.paste")
    report, document = _typed(tmp_path, manifest=manifest)
    assert (
        "own/rules/own.yaml: the rule joined takes the type of its to end from the table sorts, "
        "whose row blue: own.paste names a type neither own nor a pack it depends on declares"
    ) in _messages(report), report.problems
    assert document == {}


def test_a_row_naming_a_type_the_edge_does_not_allow_there_is_refused(tmp_path: Path) -> None:
    manifest = TYPED_MANIFEST.replace("blue: own.ink", "blue: own.other")
    extra = "- {name: own.other, id_namespace: own.other}\n"
    report, document = _typed(tmp_path, manifest=manifest, extra_types=extra)
    assert (
        "own/rules/own.yaml: the rule joined takes the type of its to end from the table sorts, "
        "whose row blue: own.other is a type the edge touches does not allow there; it allows "
        "own.dye, own.ink, own.paint"
    ) in _messages(report), report.problems
    assert document == {}


def test_a_bad_row_a_loaded_dependent_adds_is_refused_naming_that_pack(tmp_path: Path) -> None:
    extender = (
        "pack: ext\nversion: 0.0.1\ndepends: [own]\n"
        "add_table_rows:\n  own:\n    sorts: {green: own.use}\n"
    )
    report, document = _typed(tmp_path, extender=extender)
    assert (
        "own/rules/own.yaml: the rule joined takes the type of its to end from the table sorts, "
        "whose row green: own.use, added by ext under add_table_rows, is a type the edge touches "
        "does not allow there; it allows own.dye, own.ink, own.paint"
    ) in _messages(report), report.problems
    assert document == {}


def test_a_type_from_a_capture_no_table_gives_is_refused(tmp_path: Path) -> None:
    for type_ in ("{k}", "own.{sort}"):
        report, _ = _typed(tmp_path / type_.strip("{}."), type_=type_)
        assert _refused(
            report,
            f"the to end's type {type_} is not one {{name}} that an in_table step's value gives, "
            "as the one item of types; an end takes a type from a capture only through a table",
        ), (type_, report.problems)



def test_a_later_step_that_captures_the_type_s_name_is_refused(tmp_path: Path) -> None:
    given = "{in_table: {table: sorts, capture: k, value: sort}}"
    for name, later, step in (
        ("idm", r"{id_matches: '^(?<sort>own\.use)::'}", r"id_matches ^(?<sort>own\.use)::"),
        ("word", r"{id_matches: '(?<sort>\w+)'}", r"id_matches (?<sort>\w+)"),
        ("attr", "{edge: next}, {edge_attribute: sort}", "edge_attribute sort"),
        ("try", r"{try: [{id_matches: '(?<sort>\w+)'}]}", r"id_matches (?<sort>\w+) inside try"),
    ):
        report, document = _typed(tmp_path / name, follow=f"[{given}, {later}]")
        assert _refused(
            report,
            f"the follow step {step} captures sort, which an in_table step before it gives "
            "from a table",
        ), (name, report.problems)
        assert document == {}, name


def test_a_type_from_an_in_table_step_inside_a_try_is_refused(tmp_path: Path) -> None:
    follow = "[{try: [{in_table: {table: sorts, capture: k, value: sort}}]}]"
    report, document = _typed(tmp_path, follow=follow)
    assert _refused(
        report,
        "the to end's type {sort} comes from an in_table step inside a try, which can leave it "
        "unset; an end takes a type only from an in_table step outside any try",
    ), report.problems
    assert document == {}


TREE_MANIFEST = """\
pack: own
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  call_arguments: arguments
  call_argument: argument
  call_literals: [string, encapsed_string]
  call_literal_content: [string_content]
"""

TREE_RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.view, id_namespace: own.view}
edge_kinds:
- {kind: shows, from: own.fn, to: own.view}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: own.fn}}]
  confidence: declared
- rule: static
  reads: file
  in: [code]
  match:
    reference: scoped_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: scope, pattern: Reg}
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: ['{x}'], on_miss: unresolved}
  confidence: declared
"""


def test_a_reference_rule_type_placeholder_is_refused_at_load(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": TREE_MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": TREE_RULES,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "src/a.php": "<?php\nfunction f() { Reg::get('home'); }\n",
        },
    )
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    messages = _messages(report)
    assert (
        "own/rules/own.yaml: the rule static names its to end a {x}, and the edge shows allows "
        "own.view there"
    ) in messages, report.problems
    assert any(
        m.endswith("the rule static cannot be executed: a type the end of shows lists has no id "
        "namespace")
        for m in messages
    ), report.problems


def test_a_from_end_takes_its_type_checked_against_the_kind_s_from_types(tmp_path: Path) -> None:
    emits = "{edge: {kind: backs, from: {template: '{n}', types: ['{sort}']}, to: this_node}}"
    report, document = _typed(tmp_path / "ok", emits=emits)
    assert report.problems == () and report.not_executed == (), report
    backs = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "backs"}
    assert backs == {
        ("own.paint::apple", "own.use::red.apple"),
        ("own.ink::sky", "own.use::blue.sky"),
    }
    manifest = TYPED_MANIFEST.replace("blue: own.ink", "blue: own.outside")
    report, document = _typed(tmp_path / "bad", emits=emits, manifest=manifest)
    assert (
        "own/rules/own.yaml: the rule joined takes the type of its from end from the table "
        "sorts, whose row blue: own.outside is a type the edge backs does not allow there; it "
        "allows own.dye, own.ink, own.paint"
    ) in _messages(report), report.problems
    assert document == {}


def test_a_table_type_beside_another_type_or_as_type_is_refused(tmp_path: Path) -> None:
    for name, end in (
        ("pair", "types: ['{sort}', own.paint]"),
        ("scalar", "type: '{sort}'"),
    ):
        emits = f"{{edge: {{kind: touches, from: this_node, to: {{template: '{{n}}', {end}}}}}}}"
        report, document = _typed(tmp_path / name, emits=emits)
        assert _refused(
            report,
            "the to end's type {sort} is not one {name} that an in_table step's value gives, as "
            "the one item of types; an end takes a type from a capture only through a table",
        ), (name, report.problems)
        assert document == {}, name


def test_a_table_typed_end_with_a_boundary_is_refused(tmp_path: Path) -> None:
    emits = (
        "{edge: {kind: touches, from: this_node, to: {template: '{n}', types: ['{sort}'],"
        " boundary: {kind: beyond, into: {template: Edge, type: own.outside}}}}}"
    )
    report, document = _typed(tmp_path, emits=emits)
    assert _refused(
        report, "the to end's type {sort} comes from a table, and such an end takes no boundary"
    ), report.problems
    assert document == {}


def test_a_type_placeholder_on_a_file_rule_is_refused_at_load(tmp_path: Path) -> None:
    rule = (
        "- rule: fe\n  reads: file\n  in: [yard]\n"
        "  match: {file: '*', filetype: yard, text: '(?m)^use (?<k>\\w+) (?<n>\\w+)'}\n"
        "  id: {template: '{k}.{n}'}\n"
        "  emits: [{edge: {kind: touches, from: {template: '{k}.{n}', type: own.use},"
        " to: {template: '{n}', types: ['{k}']}}}]\n"
        "  confidence: declared\n"
    )
    report, document = _typed(tmp_path, extra_rules=rule)
    messages = _messages(report)
    assert (
        "own/rules/own.yaml: the rule fe names its to end a {k}, and the edge touches allows "
        "own.dye, own.ink, own.paint there"
    ) in messages, report.problems
    assert document == {}
