"""Tree rules: references, a skip list, ids of a dependent rutter, and ids from path values."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from test_demo_a_support import edges, map_project, mapped, nodes, pin, plant, rutter

import periplus.map
from periplus.errors import ExitCode
from periplus.map import MapReport
from periplus.validate import _schema

# --- references in a planted PHP project ---------------------------------------------------------

CALLS = """\
pack: calls
version: 0.0.1
depends: [php_basic]
folders:
  code: ./src/**
"""

CALLS_RULES = """\
edge_kinds:
- {kind: calls_planted, from: php.callable, to: [php.function, php.method]}
rules:
- rule: call_function
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits:
  - edge:
      kind: calls_planted
      from: enclosing_declaration
      to: {types: [php.function], on_miss: unresolved}
  confidence: declared
- rule: call_static
  reads: file
  in: [code]
  match: {reference: scoped_call_expression, name_child: [scope, name], filetype: php}
  emits:
  - edge:
      kind: calls_planted
      from: enclosing_declaration
      to: {types: [php.method], separator: '::', on_miss: unresolved}
  confidence: declared
"""

UTIL = """\
<?php

namespace App\\Lib;

class Util
{
    public static function make()
    {
    }
}

function helper()
{
}
"""

MAIN_HEAD = "<?php\n\nnamespace App;\n\nuse App\\Lib\\Util;\nuse App\\Lib as L;\n\n"

MAIN_TAIL = """\
function run()
{
    local();
    L\\helper();
    Util::make();
    missing();
}

class Runner
{
    public function go()
    {
        local();
    }
}

function local()
{
}

local();
"""

# The file runs past line 300, so the tree is read above line 256.
MAIN = MAIN_HEAD + "".join(f"// filler {i}\n" for i in range(1, 301)) + MAIN_TAIL


@pytest.fixture(scope="module")
def references(tmp_path_factory: pytest.TempPathFactory) -> tuple[MapReport, dict[str, Any]]:
    root = tmp_path_factory.mktemp("references")
    rutter(root, "calls", CALLS, {"calls.yaml": CALLS_RULES})
    pin(root, "php_basic@0.2.0", "calls@0.0.1")
    plant(root, {"src/Lib/Util.php": UTIL, "src/App/Main.php": MAIN})
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def _line(text: str, after: int = 0) -> int:
    """The 1-based line of the first line after ``after`` that is exactly ``text``, stripped."""
    lines = MAIN.splitlines()
    return next(n for n, each in enumerate(lines, 1) if n > after and each.strip() == text)


def test_a_call_is_an_edge_from_the_enclosing_declaration_to_the_name_the_file_gives_it(
    references: tuple[MapReport, dict[str, Any]],
) -> None:
    """The namespace, an alias import and a class import each give the full name, and the calls
    sit on lines past 256, where the tree reads a point's row by index."""
    run, go = "php.function::App\\run", "php.method::App\\Runner::go"
    expected = {
        (run, "php.function::App\\local", _line("local();")),
        (run, "php.function::App\\Lib\\helper", _line("L\\helper();")),
        (run, "php.method::App\\Lib\\Util::make", _line("Util::make();")),
        (run, "php.function::App\\missing", _line("missing();")),
        (go, "php.function::App\\local", _line("local();", _line("public function go()"))),
    }
    found = {
        (edge["from"], edge["to"], place["line"])
        for edge in references[1]["edges"]
        if edge["kind"] == "calls_planted"
        for place in edge["locations"]
    }
    assert found == expected
    assert min(line for _, _, line in expected) > 256


def test_a_called_name_no_file_defines_is_an_unresolved_node_of_the_listed_type(
    references: tuple[MapReport, dict[str, Any]],
) -> None:
    found = nodes(references[1])
    assert found["php.function::App\\local"]["state"] == "mapped"
    assert found["php.method::App\\Lib\\Util::make"]["state"] == "mapped"
    missing = found["php.function::App\\missing"]
    assert missing["state"] == "unresolved" and missing["type"] == "php.function"
    assert missing["unresolved_detail"]["rule"] == "calls/call_function"
    assert missing["unresolved_detail"]["searched_for"] == "App\\missing"
    assert missing["unresolved_detail"]["types_tried"] == ["php.function"]


def test_a_call_outside_any_declaration_makes_nothing_and_is_listed_as_skipped(
    references: tuple[MapReport, dict[str, Any]],
) -> None:
    report = references[0]
    top = len(MAIN.splitlines()) - 1  # the final call, written on the last line
    assert MAIN.splitlines()[top].strip() == "local();"
    fires = {(pack, rule): count for pack, rule, count in report.executed}
    assert fires[("calls", "call_function")] == 4 and fires[("calls", "call_static")] == 1
    # php_basic states calls too, so its own rule skips the same line beside the planted rule.
    skipped = {(file, line, rule) for file, line, rule, _ in report.skipped}
    assert skipped == {
        ("src/App/Main.php", top + 1, "call_function"),
        ("src/App/Main.php", top + 1, "calls_function"),
    }


# --- a reference rule's skip list ----------------------------------------------------------------

SKIPS = """\
pack: skips
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src/**
files:
  extensions: [php]
identity:
  qualified_name:
    parts: [namespace, declared_name]
    separator: "\\\\"
  namespace:
    declaration: namespace_definition
    name_child: name
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
"""

SKIPS_RULES = """\
node_types:
- {name: skips.function, id_namespace: skips.function}
edge_kinds:
- {kind: calls, from: skips.function, to: skips.function}
rules:
- {rule: function, reads: file, in: [code],
   match: {declaration: function_definition, name_child: name, filetype: php},
   id: {from: qualified_name}, emits: [{node: {type: skips.function}}], confidence: declared}
- rule: call
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php,
          skip_names: [isset, empty]}
  emits:
  - edge:
      kind: calls
      from: enclosing_declaration
      to: {types: [skips.function], on_miss: unresolved}
  confidence: declared
"""

RUN_PHP = """\
<?php

namespace App;

function f()
{
}

function run($a, $b)
{
    isset($a);
    empty($b);
    f();
}

isset($z);
"""


def test_a_name_on_a_reference_rules_skip_list_makes_no_edge_no_node_and_no_skipped_row(
    tmp_path: Path,
) -> None:
    """The isset at the top level, outside any function, adds no skipped row either: the skip runs
    before the enclosing declaration is sought."""
    rutter(tmp_path, "skips", SKIPS, {"skips.yaml": SKIPS_RULES})
    pin(tmp_path, "skips@0.0.1")
    plant(tmp_path, {"src/run.php": RUN_PHP})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert edges(document, "calls") == {
        ("calls", "skips.function::App\\run", "skips.function::App\\f")
    }
    assert not [i for i in nodes(document) if i.rsplit("\\", 1)[-1] in ("isset", "empty")]
    assert report.skipped == ()
    assert {(rule, fires) for _, rule, fires in report.executed if rule == "call"} == {("call", 1)}


# --- a dependent rutter's rules on php_basic's class node ---------------------------------------

MODELS = """\
pack: models
version: 0.0.1
depends: [php_basic]
folders:
  models: ./src/Models/**
"""

MODELS_RULES = """\
node_types:
- {name: models.model, id_namespace: models.model}
edge_kinds:
- {kind: implemented_by, from: models.model, to: php.class}
rules:
- rule: model_class
  reads: file
  in: [models]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
          filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: models.model}}]
  confidence: inferred
- rule: model_is_class
  reads: file
  in: [models]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
          filetype: php}
  id: {from: qualified_name}
  emits: [{edge: {kind: implemented_by, from: this_node, to: {from: qualified_name}}}]
  confidence: inferred
"""

USER = """\
<?php

namespace App\\Models;

class Base
{
}

class User extends Base implements Shown
{
    use Named;

    public function save()
    {
    }
}
"""


def _models(root: Path, pins: tuple[str, ...]) -> dict[str, Any]:
    rutter(root, "models", MODELS, {"models.yaml": MODELS_RULES})
    pin(root, *pins)
    plant(root, {"src/Models/User.php": USER})
    return mapped(root)


def _basic(document: dict[str, Any]) -> tuple[set[str], set[tuple[str, str, str]]]:
    """php_basic's node ids and the kind and ends of each edge it states."""
    ids = {n["id"] for n in document["nodes"] if n["type"].startswith("php.")}
    stated = {
        (e["kind"], e["from"], e["to"])
        for e in document["edges"]
        if any(p["pack"] == "php_basic" for p in e["provenance"])
    }
    return ids, stated


def test_a_rutter_depending_on_php_basic_changes_none_of_php_basics_ids_or_edges(
    tmp_path: Path,
) -> None:
    alone = _models(tmp_path / "alone", ("php_basic@0.2.0",))
    both = _models(tmp_path / "both", ("php_basic@0.2.0", "models@0.0.1"))
    ids, stated = _basic(alone)
    assert {"php.type::App\\Models\\User", "php.method::App\\Models\\User::save"} <= ids
    assert ("inherits", "php.type::App\\Models\\User", "php.type::App\\Models\\Base") in stated
    assert _basic(both) == (ids, stated)


def test_the_dependent_rutters_own_rules_state_their_node_and_edge_on_the_class(
    tmp_path: Path,
) -> None:
    both = _models(tmp_path, ("php_basic@0.2.0", "models@0.0.1"))
    assert "models.model::App\\Models\\User" in nodes(both)
    assert (
        "implemented_by",
        "models.model::App\\Models\\User",
        "php.type::App\\Models\\User",
    ) in edges(both)


def test_no_id_in_the_map_starts_with_none(tmp_path: Path) -> None:
    both = _models(tmp_path, ("php_basic@0.2.0", "models@0.0.1"))
    named = [n["id"] for n in both["nodes"]]
    named += [end for e in both["edges"] for end in (e["from"], e["to"])]
    assert not [i for i in named if i.startswith("None::")]


@pytest.mark.parametrize("bad", ["None::X", "::X"])
def test_the_map_schema_rejects_a_node_whose_id_has_no_namespace(tmp_path: Path, bad: str) -> None:
    document = _models(tmp_path, ("php_basic@0.2.0", "models@0.0.1"))
    validator = Draft202012Validator(_schema(periplus.map.MAP_SCHEMA))
    validator.validate(document)
    planted = copy.deepcopy(document)
    planted["nodes"].append({**planted["nodes"][0], "id": bad})
    errors = [e for e in validator.iter_errors(planted) if list(e.absolute_path)[-1:] == ["id"]]
    assert errors


def test_the_write_guard_refuses_an_id_whose_namespace_no_pack_declares_and_writes_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No pack can now make the engine build such an id, so the document builder is wrapped to add
    one."""
    built = periplus.map.build_document

    def planted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        document: dict[str, Any] = built(*args, **kwargs)
        document["nodes"].append({**document["nodes"][0], "id": "None::X"})
        return document

    monkeypatch.setattr(periplus.map, "build_document", planted)
    rutter(tmp_path, "models", MODELS, {"models.yaml": MODELS_RULES})
    pin(tmp_path, "php_basic@0.2.0", "models@0.0.1")
    plant(tmp_path, {"src/Models/User.php": USER})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.MAP_INVALID
    assert [dict(p.detail) for p in report.problems] == [
        {"problem": "UNDECLARED_ID_NAMESPACE", "id": "None::X"}
    ]


# --- an id from a path value and from a field of the matched node ---------------------------------

SHAPES = """\
pack: shapes
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
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        dir:
          pattern: '^src/(?<d>[^/]+)/[^/]+$'
          template: '{d}'
identity:
  qualified_name: {parts: [dir, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""

SHAPES_RULES = """\
node_types:
- {name: shapes.class, id_namespace: shapes.class}
- {name: shapes.function, id_namespace: shapes.function}
- {name: shapes.qualified, id_namespace: shapes.qualified}
rules:
- {rule: find_class, reads: file, in: [source],
   match: {declaration: class_declaration, name_child: name, filetype: code},
   id: {from: [dir, declared_name], template: '{dir}.{declared_name}'},
   emits: [{node: {type: shapes.class}}], confidence: declared}
- {rule: find_function, reads: file, in: [source],
   match: {declaration: function_definition, filetype: code},
   id: {from: [dir, name, return_type], template: '{dir}.{name}:{return_type}'},
   emits: [{node: {type: shapes.function}}], confidence: declared}
- {rule: find_qualified, reads: file, in: [source],
   match: {declaration: class_declaration, name_child: name, filetype: code},
   id: {from: qualified_name}, emits: [{node: {type: shapes.qualified}}], confidence: declared}
"""

ALPHA = """\
<?php

class Thing extends Base
{
}

class Other
{
}

function count(): int
{
}

function loose()
{
}
"""


def _shapes(root: Path, rules: str = SHAPES_RULES) -> tuple[MapReport, dict[str, Any]]:
    rutter(root, "shapes", SHAPES, {"shapes.yaml": rules})
    pin(root, "shapes@0.0.1")
    plant(
        root,
        {
            "src/alpha/Thing.php": ALPHA,
            "src/beta/Thing.php": "<?php\n\nclass Thing\n{\n}\n",
            "Root.php": "<?php\n\nclass Loose\n{\n}\n\nclass Lost\n{\n}\n",
        },
    )
    return map_project(root)


@pytest.fixture(scope="module")
def shapes(tmp_path_factory: pytest.TempPathFactory) -> tuple[MapReport, dict[str, Any]]:
    report, document = _shapes(tmp_path_factory.mktemp("shapes"))
    assert report.problems == (), report.problems
    return report, document


def test_a_tree_rules_id_from_a_path_value_and_a_field_names_two_classes_of_one_name_apart(
    shapes: tuple[MapReport, dict[str, Any]],
) -> None:
    found = nodes(shapes[1])
    assert {i for i in found if i.startswith("shapes.class::")} == {
        "shapes.class::alpha.Other",
        "shapes.class::alpha.Thing",
        "shapes.class::beta.Thing",
    }
    assert [loc["file"] for loc in found["shapes.class::alpha.Thing"]["locations"]] == [
        "src/alpha/Thing.php"
    ]
    assert [loc["file"] for loc in found["shapes.class::beta.Thing"]["locations"]] == [
        "src/beta/Thing.php"
    ]


def test_a_file_outside_the_folder_the_path_value_needs_gives_no_node_and_a_row_per_rule(
    shapes: tuple[MapReport, dict[str, Any]],
) -> None:
    """Root.php holds two classes, and the rows name the first only: the rule is skipped there."""
    rows = {(file, line, rule): reason for file, line, rule, reason in shapes[0].skipped}
    assert {key for key in rows if key[0] == "Root.php"} == {
        ("Root.php", 3, "find_class"),
        ("Root.php", 3, "find_qualified"),
    }
    assert all("dir" in reason for key, reason in rows.items() if key[0] == "Root.php")
    assert not [i for i in nodes(shapes[1]) if "Loose" in i or "Lost" in i]


def test_a_function_without_a_return_type_gives_no_node_and_one_skipped_row(
    shapes: tuple[MapReport, dict[str, Any]],
) -> None:
    assert [i for i in nodes(shapes[1]) if i.startswith("shapes.function::")] == [
        "shapes.function::alpha.count:int"
    ]
    rows = [
        (file, line, reason)
        for file, line, rule, reason in shapes[0].skipped
        if rule == "find_function"
    ]
    assert len(rows) == 1 and rows[0][:2] == ("src/alpha/Thing.php", 15)
    assert "return_type" in rows[0][2]


def test_the_grammars_qualified_name_is_built_from_the_parts_it_declares(
    shapes: tuple[MapReport, dict[str, Any]],
) -> None:
    assert {i for i in nodes(shapes[1]) if i.startswith("shapes.qualified::")} == {
        "shapes.qualified::alpha\\Other",
        "shapes.qualified::alpha\\Thing",
        "shapes.qualified::beta\\Thing",
    }


def test_an_id_template_naming_a_field_no_source_holds_is_refused_at_load(tmp_path: Path) -> None:
    report, _ = _shapes(tmp_path, SHAPES_RULES.replace("return_type", "retrun_type"))
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    assert [p.message for p in report.problems if "retrun_type" in p.message]
    message = report.problems[0].message
    assert "find_function" in message and "{dir}.{name}:{retrun_type}" in message, message
