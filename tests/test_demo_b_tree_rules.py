"""Abilities of a tree rule that were once proved by demo scripts: ``has_child``, settings values
in templates, ``normalize`` on an id, import names from a whole path, and a call's arguments on
a second grammar. Each test plants a small rutter and maps it in-process."""

from __future__ import annotations

from pathlib import Path

from test_demo_b_support import (
    clean_map,
    edge_set,
    fires,
    line_of,
    map_site,
    plant,
    settings,
)

from periplus.errors import ExitCode

PHP_GRAMMAR = """\
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
"""

# --- has_child ---------------------------------------------------------------------------------

KINDS_PACK = (
    """\
pack: kinds
version: 0.0.1
depends: []
"""
    + PHP_GRAMMAR
    + r"""folders:
  source: ./src/**
files:
  types:
    code:
      endings: [php]
      reader: tree
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""
)

KINDS_RULES = """\
node_types:
- name: kinds.class
  id_namespace: kinds.class
- name: kinds.derived
  parent: kinds.class
  id_namespace: kinds.derived
- name: kinds.method
  id_namespace: kinds.method
edge_kinds:
- kind: member_of
  from: kinds.method
  to: kinds.class
rules:
- rule: every_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: kinds.class}}]
  confidence: declared
- rule: derived_class
  reads: file
  in: [source]
  match:
    declaration: class_declaration
    name_child: name
    body_child: declaration_list
    filetype: code
    where: [{has_child: base_clause}]
  id: {from: qualified_name}
  emits: [{node: {type: kinds.derived}}]
  confidence: declared
- rule: method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: code}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}.{declared_name}'}
  emits: [{node: {type: kinds.method}}]
  confidence: declared
- rule: method_of
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: code}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}.{declared_name}'}
  emits: [{edge: {kind: member_of, from: this_node, to: enclosing_class}}]
  confidence: declared
"""  # noqa: E501

SHAPES = """\
<?php

namespace App;

class Base
{
}

class Kid extends Base
{
    public function run()
    {
    }
}

class Lone implements Shown
{
    public function run()
    {
    }
}

class Plain
{
    public function make()
    {
        return new class extends Base {};
    }
}

class Grand extends Kid implements Shown
{
}
"""


def test_a_has_child_condition_fires_only_on_a_class_with_that_child(tmp_path: Path) -> None:
    """Of five classes, Kid and Grand have a base_clause child; Lone only implements, and Plain's
    only base_clause sits in an anonymous class in a method body, so neither fires the rule. A
    method's member_of edge ends at the node the rule that fired on its class made."""
    plant(
        tmp_path,
        {
            **settings("kinds@0.0.1"),
            ".periplus/packs/kinds@0.0.1/pack.yaml": KINDS_PACK,
            ".periplus/packs/kinds@0.0.1/rules/kinds.yaml": KINDS_RULES,
            "src/Shapes.php": SHAPES,
        },
    )
    report, document = clean_map(tmp_path)
    assert sorted(n["id"] for n in document["nodes"]) == [
        "kinds.class::App\\Base",
        "kinds.class::App\\Grand",
        "kinds.class::App\\Kid",
        "kinds.class::App\\Lone",
        "kinds.class::App\\Plain",
        "kinds.derived::App\\Grand",
        "kinds.derived::App\\Kid",
        "kinds.method::App\\Kid.run",
        "kinds.method::App\\Lone.run",
        "kinds.method::App\\Plain.make",
    ]
    assert edge_set(document) == {
        ("member_of", "kinds.method::App\\Kid.run", "kinds.derived::App\\Kid"),
        ("member_of", "kinds.method::App\\Lone.run", "kinds.class::App\\Lone"),
        ("member_of", "kinds.method::App\\Plain.make", "kinds.class::App\\Plain"),
    }
    assert fires(report) == {
        ("kinds", "every_class"): 5,
        ("kinds", "derived_class"): 2,
        ("kinds", "method"): 3,
        ("kinds", "method_of"): 3,
    }
    assert report.skipped == ()


# --- settings values in templates --------------------------------------------------------------

MODULES_PACK = (
    """\
pack: modules
version: 0.0.1
depends: []
"""
    + PHP_GRAMMAR
    + r"""folders:
  source: ./**
files:
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        pkg:
          pattern: '^(?<path>(?:.*/)?)[^/]+$'
          template: '{module}/{path}'
          normalize: [{replace: '/$', with: ''}]
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: '{d}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "."}
  namespace: {path_value: pkg}
  written_names: [name]
"""
)

MODULES_RULES = """\
node_types:
- name: modules.class
  id_namespace: modules.class
- name: modules.qualified
  id_namespace: modules.qualified
- name: modules.literal
  id_namespace: modules.literal
rules:
- rule: by_template
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [pkg, declared_name], template: '{pkg}.{declared_name}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
- rule: by_qualified_name
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: modules.qualified}}]
  confidence: declared
- rule: by_setting
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [module, dir, declared_name], template: '{module}/{dir}.{declared_name}'}
  emits: [{node: {type: modules.literal}}]
  confidence: declared
"""


def _modules_site(root: Path, values: str) -> None:
    plant(
        root,
        {
            **settings("modules@0.0.1", values=values),
            ".periplus/packs/modules@0.0.1/pack.yaml": MODULES_PACK,
            ".periplus/packs/modules@0.0.1/rules/modules.yaml": MODULES_RULES,
            "Root.php": "<?php\n\nclass Root\n{\n}\n",
            "sub/inner/Leaf.php": "<?php\n\nclass Leaf\n{\n}\n",
        },
    )


def test_a_settings_value_fills_a_path_value_and_an_id_template(tmp_path: Path) -> None:
    """The path value pkg is '{module}/{path}' less a trailing slash, so a root file gives
    '{module}' and a subfolder file '{module}/<folder>'. A template id and a qualified name built
    from that namespace agree. The third rule names the setting in its own id and the subfolder
    path value dir, which a root file lacks: that file gives a skipped row naming dir."""
    _modules_site(tmp_path, "values:\n  module: example.com/app\n")
    report, document = clean_map(tmp_path)
    assert sorted(n["id"] for n in document["nodes"]) == [
        "modules.class::example.com/app.Root",
        "modules.class::example.com/app/sub/inner.Leaf",
        "modules.literal::example.com/app/sub/inner.Leaf",
        "modules.qualified::example.com/app.Root",
        "modules.qualified::example.com/app/sub/inner.Leaf",
    ]
    assert report.skipped == (("Root.php", 3, "by_setting", "the id source dir is absent"),)


def test_a_template_naming_a_setting_nobody_gives_is_refused_at_load(tmp_path: Path) -> None:
    _modules_site(tmp_path, "")
    report, document = map_site(tmp_path)
    assert document is None
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    messages = [p.message for p in report.problems]
    assert len(messages) == 2, messages
    assert "path value pkg" in messages[0] and "{module}/{path}" in messages[0], messages
    assert "rule by_setting" in messages[1] and "{module}/{dir}.{declared_name}" in messages[1]
    assert all("module" in message for message in messages), messages


def test_a_setting_named_like_a_path_value_is_refused_at_load(tmp_path: Path) -> None:
    _modules_site(tmp_path, "values:\n  module: example.com/app\n  pkg: example.com/other\n")
    report, document = map_site(tmp_path)
    assert document is None
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    [problem] = report.problems
    assert "path value pkg" in problem.message and "settings.yml" in problem.message, problem


# --- id patterns that only filter --------------------------------------------------------------

HOOKS_PACK = (
    """\
pack: hooks
version: 0.0.1
depends: []
"""
    + PHP_GRAMMAR
    + r"""folders:
  source: ./**
files:
  types:
    module_file:
      endings: [module]
      reader: tree
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""
)

HOOKS_RULES = r"""node_types:
- name: hooks.callback
  id_namespace: hooks.callback
rules:
- rule: find_callback
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: module_file}
  id: {from: declared_name, pattern: '_callback$'}
  emits: [{node: {type: hooks.callback}}]
  confidence: declared
"""


def test_an_id_pattern_with_no_template_only_filters_and_keeps_the_name(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {
            **settings("hooks@0.0.1"),
            ".periplus/packs/hooks@0.0.1/pack.yaml": HOOKS_PACK,
            ".periplus/packs/hooks@0.0.1/rules/hooks.yaml": HOOKS_RULES,
            "src/mymod.module": "<?php\n\nfunction helper()\n{\n}\n\n"
            "function build_callback()\n{\n}\n",
        },
    )
    report, document = clean_map(tmp_path)
    assert [(n["id"], n["locations"][0]["line"]) for n in document["nodes"]] == [
        ("hooks.callback::build_callback", 7)
    ]
    assert report.skipped == ()
    assert fires(report) == {("hooks", "find_callback"): 1}


# --- normalize on an id ------------------------------------------------------------------------

SHAPES_PACK = (
    """\
pack: shapes
version: 0.0.1
depends: []
"""
    + PHP_GRAMMAR
    + r"""folders:
  source: ./**
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\"
  - bound_first_segment
  - prefix_with: namespace
  attribute:
    node: attribute
    list: attribute_list
    arguments: parameters
    argument: argument
    argument_name: name
    literals: [string, encapsed_string]
    literal_content: string_content
"""
)

SHAPES_RULES = r"""node_types:
- name: shapes.class
  id_namespace: shapes.class
- name: shapes.method
  id_namespace: shapes.method
- name: shapes.function
  id_namespace: shapes.function
- name: shapes.mark
  id_namespace: shapes.mark
edge_kinds:
- kind: contains
  from: shapes.class
  to: shapes.method
- kind: calls
  from: shapes.method
  to: shapes.function
- kind: marks
  from: shapes.method
  to: shapes.mark
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id:
    from: qualified_name
    normalize: [{replace: '\\', with: '.'}]
  emits: [{node: {type: shapes.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: &method_id
    from: [enclosing_type, declared_name, parameters]
    template: '{enclosing_type}::{declared_name}{parameters}'
    normalize: [{replace: ' ?\$\w+', with: ''}, {replace: ', ', with: ','}, {replace: '\\', with: '.'}]
  emits: [{node: {type: shapes.method}}]
  confidence: declared
- rule: contains_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: *method_id
  emits: [{edge: {kind: contains, from: enclosing_class, to: this_node}}]
  confidence: declared
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: shapes.function}}]
  confidence: declared
- rule: calls_function
  reads: file
  in: [source]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [shapes.function], on_miss: unresolved}}}]
  confidence: declared
- rule: marks_from_attribute
  reads: file
  in: [source]
  match: {attribute: App\Mark, filetype: php, where: [{applies_to: method_declaration}]}
  emits: [{edge: {kind: marks, from: enclosing_method, to: {from: {attribute_argument: '0'}}}}]
  confidence: declared
"""  # noqa: E501

THING = """\
<?php

namespace App;

class Thing
{
    #[Mark('tick')]
    public function run(int $times, string $label): void
    {
        helper();
    }
}

function helper()
{
}
"""


def _shapes(root: Path, rules: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    plant(
        root,
        {
            **settings("shapes@0.0.1"),
            ".periplus/packs/shapes@0.0.1/pack.yaml": SHAPES_PACK,
            ".periplus/packs/shapes@0.0.1/rules/shapes.yaml": rules,
            "src/Thing.php": THING,
        },
    )
    report, document = clean_map(root)
    assert report.skipped == ()
    # Only the attribute's argument is a node no rule declares; a raw edge end would be another.
    assert [n["id"] for n in document["nodes"] if n["state"] == "referenced"] == [
        "shapes.mark::tick"
    ]
    nodes = sorted(n["id"] for n in document["nodes"])
    edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
    return nodes, edges


def test_normalize_cleans_an_id_and_every_edge_end_that_starts_at_it(tmp_path: Path) -> None:
    """The method id is '{enclosing_type}::{declared_name}{parameters}' with the variables, the
    space after each comma and each backslash taken out, so 'App.Thing::run(int,string)'; the
    contains, calls and marks edges start at that cleaned id."""
    nodes, edges = _shapes(tmp_path, SHAPES_RULES)
    method = "shapes.method::App.Thing::run(int,string)"
    assert nodes == [
        "shapes.class::App.Thing",
        "shapes.function::App\\helper",
        "shapes.mark::tick",
        method,
    ]
    assert edges == [
        ("calls", method, "shapes.function::App\\helper"),
        ("contains", "shapes.class::App.Thing", method),
        ("marks", method, "shapes.mark::tick"),
    ]


def test_the_same_rutter_without_normalize_gives_the_raw_text_in_each_id(tmp_path: Path) -> None:
    raw = "\n".join(line for line in SHAPES_RULES.splitlines() if "normalize:" not in line)
    nodes, edges = _shapes(tmp_path, raw + "\n")
    method = "shapes.method::App\\Thing::run(int $times, string $label)"
    assert nodes == [
        "shapes.class::App\\Thing",
        "shapes.function::App\\helper",
        "shapes.mark::tick",
        method,
    ]
    assert edges == [
        ("calls", method, "shapes.function::App\\helper"),
        ("contains", "shapes.class::App\\Thing", method),
        ("marks", method, "shapes.mark::tick"),
    ]


# --- import names from the whole path ----------------------------------------------------------

PORTER_PACK = (
    """\
pack: porter
version: 0.0.1
depends: []
"""
    + PHP_GRAMMAR
    + r"""folders:
  source: ./src/**
files:
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        pkg:
          pattern: '^src/(?<dir>.+)/[^/]+$'
          template: '{dir}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {path_value: pkg}
  written_names: [name, qualified_name, namespace_name, string_content, scoped_call_expression]
  resolve:
  - bound_first_segment
  - prefix_bare_with: namespace
"""
)

PORTER_IMPORTS = r"""imports:
- ast: argument
  clause: string
  facts: {alias: name}
  bind:
    name: [alias, path]
    normalize: [{replace: '^.*/', with: ''}, {replace: '_v\d+$', with: ''}]
    unbound_aliases: [_]
"""

PORTER_RULES = """\
node_types:
- name: porter.function
  id_namespace: porter.function
edge_kinds:
- kind: calls
  from: porter.function
  to: porter.function
rules:
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: porter.function}}]
  confidence: declared
- rule: call
  reads: file
  in: [source]
  match:
    reference: function_call_expression
    name_child: function
    filetype: code
    whole_written: true
    skip_names: [import]
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [porter.function], on_miss: unresolved}}}]
  confidence: declared
"""  # noqa: E501

PORTER_MAIN = """\
<?php

import('App/Util/Strings_v2');
import(W: 'App/Text/Words');
import(_: 'App/Hidden');

function run()
{
    Strings\\up();
    W\\tally();
    local();
    Missing\\thing();
    Strings::make()();
    _\\hide();
    Hidden\\hide();
}

function local()
{
}
"""


def test_an_import_binds_the_last_segment_of_its_whole_path_and_a_dotted_call_ends_on_it(
    tmp_path: Path,
) -> None:
    """The path 'App/Util/Strings_v2' binds Strings; the alias W binds W; the alias _ binds
    nothing. Strings\\up() and W\\tally() end on the functions under the full paths and local() on
    the caller's namespace. Missing\\thing(), _\\hide() and Hidden\\hide() have no step that holds,
    and Strings::make()() is not wholly written: each leaves a skipped row and no edge."""
    plant(
        tmp_path,
        {
            **settings("porter@0.0.1"),
            ".periplus/packs/porter@0.0.1/pack.yaml": PORTER_PACK,
            ".periplus/packs/porter@0.0.1/imports/imports.yaml": PORTER_IMPORTS,
            ".periplus/packs/porter@0.0.1/rules/porter.yaml": PORTER_RULES,
            "src/App/Util/Strings_v2/lib.php": "<?php\n\nfunction up()\n{\n}\n",
            "src/App/Text/Words/lib.php": "<?php\n\nfunction tally()\n{\n}\n",
            "src/App/Hidden/lib.php": "<?php\n\nfunction hide()\n{\n}\n",
            "src/App/Main/main.php": PORTER_MAIN,
        },
    )
    main = tmp_path / "src/App/Main/main.php"
    report, document = clean_map(tmp_path)

    assert {n["id"]: n["state"] for n in document["nodes"]} == {
        f"porter.function::{name}": "mapped"
        for name in (
            "App/Main\\run",
            "App/Main\\local",
            "App/Util/Strings_v2\\up",
            "App/Text/Words\\tally",
            "App/Hidden\\hide",
        )
    }
    run = "porter.function::App/Main\\run"
    found = {
        (e["from"], e["to"], place["line"]) for e in document["edges"] for place in e["locations"]
    }
    assert found == {
        (run, "porter.function::App/Util/Strings_v2\\up", line_of(main, "Strings\\up();")),
        (run, "porter.function::App/Text/Words\\tally", line_of(main, "W\\tally();")),
        (run, "porter.function::App/Main\\local", line_of(main, "local();")),
    }
    none_holds = "no resolution step holds for function"
    file = "src/App/Main/main.php"
    assert sorted(report.skipped) == sorted(
        [
            (file, line_of(main, "Missing\\thing();"), "call", none_holds),
            (file, line_of(main, "Strings::make()();"), "call", "function is not a written name"),
            (file, line_of(main, "_\\hide();"), "call", none_holds),
            (file, line_of(main, "Hidden\\hide();"), "call", none_holds),
        ]
    )
    assert fires(report)[("porter", "call")] == 3


# --- a call's arguments on a second grammar ----------------------------------------------------

SHOP_PACK = "pack: shop\nversion: 0.0.1\ndepends: [go_basic]\n"

SHOP_RULES = """\
node_types:
- name: shop.route
  id_namespace: shop.route
edge_kinds:
- kind: redirects
  from: go.function
  to: shop.route
rules:
- rule: route
  reads: file
  in: [source]
  match:
    declaration: call_expression
    name_child: function
    filetype: go
    where: [{name_matches: 'http\\.HandleFunc'}]
  id: {from: {argument: 0}}
  emits: [{node: {type: shop.route}}]
  confidence: declared
- rule: redirect
  reads: file
  in: [source]
  match:
    reference: call_expression
    name_child: function
    filetype: go
    where: [{name_matches: Redirect}]
  emits:
  - edge:
      kind: redirects
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [shop.route], on_miss: unresolved}
  confidence: declared
"""

SHOP_MAIN = """\
package main

func main() {
\thttp.HandleFunc("/x", h)
\thttp.HandleFunc(`/raw`, h)
\thttp.HandleFunc(p, h)
\thttp.HandleFunc()
\thttp.HandleFunc("", h)
\tmux.HandleFunc("/z", h)
}

func send() {
\tRedirect("/x")
\tRedirect(`/gone`)
\tRedirect(/* to */ "/raw")
\tRedirect(path)
\tRedirect()
\tRedirect("")
\tRedirectAll("/x")
}
"""


def test_a_call_argument_reads_on_a_grammar_with_two_literal_types_and_no_wrapper(
    tmp_path: Path,
) -> None:
    """Interpreted and raw strings each give a route node and a redirects edge, a comment before
    the argument is not one, and a route no declaration names stays unresolved. A variable, a
    missing and an empty argument each leave a skipped row and no node or edge. The name filter
    matches the whole name, so RedirectAll and mux.HandleFunc leave nothing."""
    plant(
        tmp_path,
        {
            **settings(
                "go_basic@0.0.3", "shop@0.0.1", values="values:\n  module: example.com/app\n"
            ),
            ".periplus/packs/shop@0.0.1/pack.yaml": SHOP_PACK,
            ".periplus/packs/shop@0.0.1/rules/shop.yaml": SHOP_RULES,
            "main.go": SHOP_MAIN,
        },
    )
    main = tmp_path / "main.go"
    report, document = clean_map(tmp_path)

    assert {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "shop.route"} == {
        "shop.route::/x": "mapped",
        "shop.route::/raw": "mapped",
        "shop.route::/gone": "unresolved",
    }
    send = "go.function::example.com/app.send"
    found = {
        (e["from"], e["to"], place["line"])
        for e in document["edges"]
        if e["kind"] == "redirects"
        for place in e["locations"]
    }
    assert found == {
        (send, "shop.route::/x", line_of(main, 'Redirect("/x")')),
        (send, "shop.route::/gone", line_of(main, "Redirect(`/gone`)")),
        (send, "shop.route::/raw", line_of(main, 'Redirect(/* to */ "/raw")')),
    }
    skipped = sorted(
        (line, rule, reason)
        for _, line, rule, reason in report.skipped
        if rule in ("route", "redirect")
    )
    assert skipped == sorted(
        [
            (line_of(main, "http.HandleFunc(p, h)"), "route", "argument 0 is not a text literal"),
            (line_of(main, "http.HandleFunc()"), "route", "argument 0 is missing"),
            (line_of(main, 'http.HandleFunc("", h)'), "route", "argument 0 is empty"),
            (line_of(main, "Redirect(path)"), "redirect", "argument 0 is not a text literal"),
            (line_of(main, "Redirect()"), "redirect", "argument 0 is missing"),
            (line_of(main, 'Redirect("")'), "redirect", "argument 0 is empty"),
        ]
    )
    assert fires(report)[("shop", "route")] == 2 and fires(report)[("shop", "redirect")] == 3
