"""An annotation rule with ``match.each`` fires once for each entry of a group nested in the
docblock annotation, at the entry's own line, with the entry's key and value to fill its id and
an edge end.

The pack is an invented one on the PHP grammar, so it is also the proof that a third-party pack
reads every entry of a nested group with no engine change. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, pin, plant, rutter

MANIFEST = """\
pack: acme
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./src
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
  comment: comment
"""

TYPES = """\
node_types:
- {name: acme.class, id_namespace: acme.class}
- {name: acme.entry, id_namespace: acme.entry}
- {name: acme.thing, id_namespace: acme.thing}
edge_kinds:
- {kind: path_of, from: acme.entry, to: acme.thing}
- {kind: entry_names_class, from: acme.entry, to: acme.class}
- {kind: entry_of, from: acme.entry, to: acme.class}
rules:
- rule: find_class
  reads: file
  in: [source]
  match:
    {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: acme.class}}]
  confidence: declared
"""


def each_rule(name: str, path: str, template: str = "{enclosing_type}|{key}", **extra: str) -> str:
    """A node rule over each entry of the group at the path, its id the template."""
    more = "".join(f"  {key}: {value}\n" for key, value in extra.items())
    return f"""\
- rule: {name}
  reads: file
  in: [source]
  match:
    annotation: Thing
    each: '{path}'
    filetype: php
    where: [{{applies_to: class_declaration}}]
  id: {{template: '{template}'}}
  emits: [{{node: {{type: acme.entry}}}}]
  confidence: declared
{more}"""


INVOICE = """\
<?php

namespace Acme;

/**
 * @Thing(
 *   id = "invoice",
 *   parts = {
 *     "list" = "Acme\\InvoiceList",
 *     "edit" = "Acme\\InvoiceEditor",
 *     "panel" = {
 *       "add" = "Acme\\InvoiceAddPanel",
 *       "edit" = "Acme\\InvoiceEditPanel",
 *     },
 *   },
 *   paths = {
 *     main = "/invoice/{id}",
 *     "edit" = "/invoice/{id}/edit"
 *   },
 *   weights = {"low" = 1, "high" = TRUE}
 * )
 */
class Invoice {}
"""

BROKEN = """\
<?php

namespace Acme;

/**
 * @Thing(
 *   id = "broken",
 *   parts = {
 *     "list" = "Acme\\BrokenList",
 *     "view" "Acme\\BrokenView",
 *     "edit" = "Acme\\BrokenEdit"
 *   },
 *   paths = {
 *     "main" = "/broken",
 *     "edit" = "/broken/edit"
 *   )
 * )
 */
class Broken {}
"""


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def project(root: Path, rules: str, sources: dict[str, str] | None = None) -> None:
    rutter(root, "acme", MANIFEST, {"types.yaml": TYPES, "each.yaml": f"rules:\n{rules}"})
    pin(root, "acme@0.0.1")
    plant(root, sources or {"src/Invoice.php": INVOICE})


def _mapped(root: Path) -> dict[str, Any]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def _entries(document: dict[str, Any], rule: str) -> dict[str, int]:
    """Each node the rule found, by id, with the line of its one place."""
    return {
        node["id"]: line
        for node in document["nodes"]
        if any(p["rule"] == rule for p in node["provenance"])
        for (line,) in [[place["line"] for place in node["locations"]]]
    }


def _refused(root: Path, rules: str) -> list[str]:
    """The message of each problem mapping the project gives: a rule of a project's own pack that
    cannot be executed stops the map."""
    project(root, rules)
    report, document = map_project(root)
    assert document == {}
    return [problem.message for problem in report.problems]


def test_each_entry_of_a_top_level_group_is_a_match_at_its_own_line(tmp_path: Path) -> None:
    project(tmp_path, each_rule("handler", "parts.*"))
    # panel holds a group, so it is not an entry of parts; parts.panel reaches inside it.
    assert _entries(_mapped(tmp_path), "handler") == {
        "acme.entry::Acme\\Invoice|list": 9,
        "acme.entry::Acme\\Invoice|edit": 10,
    }


def test_each_entry_of_a_nested_group_is_a_match_and_a_trailing_comma_adds_none(
    tmp_path: Path,
) -> None:
    project(tmp_path, each_rule("panel", "parts.panel.*", "{enclosing_type}|panel|{key}"))
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _entries(document, "panel") == {
        "acme.entry::Acme\\Invoice|panel|add": 12,
        "acme.entry::Acme\\Invoice|panel|edit": 13,
    }
    assert [row for row in report.skipped if row[2] == "panel"] == []


def test_the_same_key_at_two_depths_and_in_two_groups_is_three_entries(tmp_path: Path) -> None:
    rules = (
        each_rule("handler", "parts.*", "{enclosing_type}|parts|{key}")
        + each_rule("panel", "parts.panel.*", "{enclosing_type}|panel|{key}")
        + each_rule("link", "paths.*", "{enclosing_type}|paths|{key}")
    )
    project(tmp_path, rules)
    found = _mapped(tmp_path)
    rules_ = ("handler", "panel", "link")
    edits = {i: line for r in rules_ for i, line in _entries(found, r).items()}
    assert {i: line for i, line in edits.items() if i.endswith("|edit")} == {
        "acme.entry::Acme\\Invoice|parts|edit": 10,
        "acme.entry::Acme\\Invoice|panel|edit": 13,
        "acme.entry::Acme\\Invoice|paths|edit": 18,
    }


def test_a_value_is_quoted_text_without_its_quotes_and_a_bare_word_is_listed(
    tmp_path: Path,
) -> None:
    rules = each_rule("link", "paths.*", "{key}={value}")
    rules += each_rule("weight", "weights.*", "{key}={value}")
    project(tmp_path, rules)
    report, found = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    # An unquoted key is read as a quoted one.
    assert _entries(found, "link") == {
        "acme.entry::main=/invoice/{id}": 17,
        "acme.entry::edit=/invoice/{id}/edit": 18,
    }
    assert _entries(found, "weight") == {}
    assert sorted(row for row in report.skipped if row[2] == "weight") == [
        ("src/Invoice.php", 20, "weight", "entry high of group weights is not quoted text"),
        ("src/Invoice.php", 20, "weight", "entry low of group weights is not quoted text"),
    ]


def test_an_edge_runs_from_the_entry_to_the_node_its_value_names(tmp_path: Path) -> None:
    rule = """\
- rule: panel_class
  reads: file
  in: [source]
  match:
    annotation: Thing
    each: parts.panel.*
    filetype: php
    where: [{applies_to: class_declaration}]
  id: {template: '{enclosing_type}|panel|{key}'}
  emits:
  - edge: {kind: entry_names_class, from: this_node, to: {template: '{value}'}}
  - edge: {kind: entry_of, from: this_node, to: enclosing_class}
  confidence: declared
"""
    project(tmp_path, rule)
    found = {
        (e["kind"], e["from"], e["to"]): [place["line"] for place in e["locations"]]
        for e in _mapped(tmp_path)["edges"]
    }
    assert found == {
        (
            "entry_names_class",
            "acme.entry::Acme\\Invoice|panel|add",
            "acme.class::Acme\\InvoiceAddPanel",
        ): [12],
        (
            "entry_names_class",
            "acme.entry::Acme\\Invoice|panel|edit",
            "acme.class::Acme\\InvoiceEditPanel",
        ): [13],
        ("entry_of", "acme.entry::Acme\\Invoice|panel|add", "acme.class::Acme\\Invoice"): [12],
        ("entry_of", "acme.entry::Acme\\Invoice|panel|edit", "acme.class::Acme\\Invoice"): [13],
    }


def test_an_entry_that_is_not_key_and_value_is_skipped_with_a_row_and_the_rest_map(
    tmp_path: Path,
) -> None:
    project(tmp_path, each_rule("handler", "parts.*"), {"src/Broken.php": BROKEN})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _entries(document, "handler") == {
        "acme.entry::Acme\\Broken|list": 9,
        "acme.entry::Acme\\Broken|edit": 11,
    }
    assert [row for row in report.skipped if row[2] == "handler"] == [
        ("src/Broken.php", 10, "handler", "group parts holds an entry that is not key = value")
    ]


def test_a_group_closed_by_the_wrong_mark_keeps_the_entries_before_and_is_listed(
    tmp_path: Path,
) -> None:
    project(tmp_path, each_rule("link", "paths.*"), {"src/Broken.php": BROKEN})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    # The entry the wrong mark ends is not read; the one a comma ended before it is.
    assert _entries(document, "link") == {"acme.entry::Acme\\Broken|main": 14}
    assert [row for row in report.skipped if row[2] == "link"] == [
        ("src/Broken.php", 16, "link", "group paths does not close")
    ]


def test_a_path_the_annotation_does_not_hold_makes_nothing_and_lists_nothing(
    tmp_path: Path,
) -> None:
    project(tmp_path, each_rule("route", "parts.router.*"))
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _entries(document, "route") == {}
    assert [row for row in report.skipped if row[2] == "route"] == []


_EACH_REFUSED = (
    "match.each of an annotation rule is keys joined by dots that end in a star, as "
    "parts.inner.*, with at most one other star, which stands for any group's key"
)


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        (
            each_rule("no_star", "parts.panel"),
            _EACH_REFUSED,
        ),
        (
            each_rule("two_stars", "*.*.*"),
            _EACH_REFUSED,
        ),
        (
            each_rule("part_star", "parts.panel*.*"),
            _EACH_REFUSED,
        ),
        (
            each_rule("no_group", "parts.panel.*", "{enclosing_type}|{group}|{key}"),
            "a template or normalize step of an annotation rule with match.each names group, "
            "which is not key, "
            "value, enclosing_type, or group with a star before the last one",
        ),
        (
            each_rule("empty", "parts.*", ""),
            "the id template of an annotation rule with match.each is empty",
        ),
        (
            each_rule("step_names", "parts.*").replace(
                "  emits: [{node: {type: acme.entry}}]\n",
                "  emits:\n  - edge:\n      kind: entry_names_class\n      from: this_node\n"
                "      to: {template: '{value}', normalize: [{replace: x, with: '{nothing}'}]}\n",
            ),
            "a template or normalize step of an annotation rule with match.each names nothing, "
            "which is not key, value, enclosing_type, or group with a star before the last one",
        ),
        (
            each_rule("unknown", "parts.*.*", "{enclosing_type}|{owner}"),
            "a template or normalize step of an annotation rule with match.each names owner, "
            "which is not key, "
            "value, enclosing_type, or group with a star before the last one",
        ),
        (
            each_rule("plain", "parts.*").replace("    each: 'parts.*'\n", ""),
            "the id block of an annotation rule is not from one annotation_key, or a template "
            "with match.each",
        ),
        (
            """\
- rule: plain_edge
  reads: file
  in: [source]
  match: {annotation: Thing, filetype: php, where: [{applies_to: class_declaration}]}
  id: {from: {annotation_key: id}}
  emits: [{edge: {kind: entry_names_class, from: this_node, to: {template: '{value}'}}}]
  confidence: declared
""",
            "an annotation rule's edge runs between this_node and enclosing_class, to "
            "{from: {annotation_key: ...}}, or with match.each to {template: ...}",
        ),
        (
            """\
- rule: attribute_each
  reads: file
  in: [source]
  match:
    attribute: 'Acme\\Thing'
    each: parts.*
    filetype: php
    where: [{applies_to: class_declaration}]
  id: {from: {attribute_argument: id}}
  emits: [{node: {type: acme.entry}}]
  confidence: declared
""",
            "an attribute rule is not a file rule with in, match.filetype and one where "
            "condition, applies_to",
        ),
    ],
)
def test_a_wrong_use_of_each_is_refused_before_any_file_is_read(
    tmp_path: Path, rules: str, reason: str
) -> None:
    name = rules.split("\n", 1)[0].removeprefix("- rule: ")
    assert _refused(tmp_path, rules) == [
        f"acme/rules/each.yaml: the rule {name} cannot be executed: {reason}"
    ]


ORDER = """\
<?php

namespace Acme;

/**
 * @Thing(
 *   id = "order",
 *   parts = {
 *     "list" = "\\Acme\\OrderList",
 *     "panel" = {
 *       "add" = "Acme\\OrderAddPanel"
 *     },
 *     "router" = {
 *       "html" = "\\Acme\\OrderRoutes",
 *     },
 *   },
 *   paths = {
 *     "edit-page" = "/order/{id}/edit",
 *   },
 *   api_paths = {
 *     "main" = "/api/order/{id}",
 *   },
 *   outside = {"x" = {"y" = "Acme\\Nope"}}
 * )
 */
class Order {}
"""


def test_a_star_before_the_last_reads_every_group_there_and_names_it_group(
    tmp_path: Path,
) -> None:
    project(
        tmp_path,
        each_rule("grouped", "parts.*.*", "{enclosing_type}|{group}|{key}"),
        {"src/Order.php": ORDER},
    )
    assert _entries(_mapped(tmp_path), "grouped") == {
        "acme.entry::Acme\\Order|panel|add": 11,
        "acme.entry::Acme\\Order|router|html": 14,
    }


def test_normalize_reshapes_the_id_and_the_template_end_as_on_other_ids(tmp_path: Path) -> None:
    rules = each_rule(
        "link",
        "paths.*",
        "{enclosing_type}|paths|{key}|{key}",
    ).replace(
        "  id: {template: '{enclosing_type}|paths|{key}|{key}'}\n",
        "  id:\n    template: '{enclosing_type}|paths|{key}|{key}'\n"
        "    normalize: [{replace: '-(?=[^|]*$)', with: _}]\n",
    )
    rules += """\
- rule: handler_class
  reads: file
  in: [source]
  match:
    annotation: Thing
    each: parts.*.*
    filetype: php
    where: [{applies_to: class_declaration}]
  id: {template: '{enclosing_type}|{group}|{key}'}
  emits:
  - edge:
      kind: entry_names_class
      from: this_node
      to: {template: '{value}', normalize: [{replace: '^\\\\', with: ''}]}
  confidence: declared
"""
    project(tmp_path, rules, {"src/Order.php": ORDER})
    found = _mapped(tmp_path)
    assert _entries(found, "link") == {"acme.entry::Acme\\Order|paths|edit-page|edit_page": 18}
    assert {(e["from"], e["to"]) for e in found["edges"]} == {
        ("acme.entry::Acme\\Order|panel|add", "acme.class::Acme\\OrderAddPanel"),
        ("acme.entry::Acme\\Order|router|html", "acme.class::Acme\\OrderRoutes"),
    }


DOTTED = """\
- rule: {name}
  reads: file
  in: [source]
  match: {{annotation: Thing, filetype: php, where: [{{applies_to: class_declaration}}]}}
  id: {{from: {{annotation_key: {key}}}}}
  emits:
  - node: {{type: acme.entry}}
  - attribute: {{name: list, from: {{annotation_key: parts.list}}}}
  confidence: declared
"""


def test_a_dotted_annotation_key_reads_one_nested_entry(tmp_path: Path) -> None:
    rules = DOTTED.format(name="main", key="api_paths.main")
    rules += DOTTED.format(name="create", key="api_paths.create")
    rules += DOTTED.format(name="panel", key="parts.panel")
    project(tmp_path, rules, {"src/Order.php": ORDER})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    node = next(n for n in document["nodes"] if n["id"] == "acme.entry::/api/order/{id}")
    assert (node["locations"][0]["line"], node["attributes"]["list"]) == (6, "\\Acme\\OrderList")
    assert sorted(row for row in report.skipped if row[2] in ("create", "panel")) == [
        ("src/Order.php", 6, "create", "key api_paths.create is missing"),
        ("src/Order.php", 6, "panel", "key parts.panel is not quoted text"),
    ]


def test_normalize_on_an_edge_end_of_a_text_rule_is_refused(tmp_path: Path) -> None:
    manifest = MANIFEST.replace(
        "  extensions: [php]\n",
        "  extensions: [php]\n  types:\n    acme_text: {endings: [php], reader: text}\n",
    )
    rule = """\
- rule: text_end
  reads: file
  in: [source]
  match: {file: '*', filetype: acme_text, text: 'new (?<name>\\w+)'}
  id: {template: '{name}'}
  emits:
  - edge:
      kind: entry_of
      from: this_node
      to: {template: '{name}', normalize: [{replace: a, with: b}]}
  confidence: declared
"""
    rutter(tmp_path, "acme", manifest, {"types.yaml": TYPES, "each.yaml": f"rules:\n{rule}"})
    pin(tmp_path, "acme@0.0.1")
    plant(tmp_path, {"src/Order.php": ORDER})
    report, document = map_project(tmp_path)
    assert document == {}
    assert [p.message for p in report.problems] == [
        "acme/rules/each.yaml: the rule text_end cannot be executed: an edge of a text rule does "
        "not run between this_node and a capture or a template"
    ]


EXTRA = """\
<?php

namespace Acme;

/**
 * @Thing(
 *   dups = {
 *     "a" = "one",
 *     "a" = "two"
 *   },
 *   "sub-parts" = {"x" = "Acme\\X"},
 *   names = {"id", "label"},
 *   api_paths = {"main" = FOO},
 *   parts = {"a" = "Acme\\A", "b" = "Acme\\B", "f" = {"p" = "q" ), "z" = "Acme\\Late"}
 * )
 */
class Extra {}
"""


def test_a_break_inside_a_group_below_the_path_keeps_what_was_read_and_is_listed(
    tmp_path: Path,
) -> None:
    project(tmp_path, each_rule("part", "parts.*", "{key}"), {"src/Extra.php": EXTRA})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _entries(document, "part") == {"acme.entry::a": 14, "acme.entry::b": 14}
    assert [row for row in report.skipped if row[2] == "part"] == [
        ("src/Extra.php", 14, "part", "group parts.f does not close")
    ]


def test_a_repeated_key_is_an_entry_each_time_and_a_dotted_key_reads_the_last(
    tmp_path: Path,
) -> None:
    rules = each_rule("dup", "dups.*", "{key}")
    rules += DOTTED.format(name="dotted", key="dups.a").replace(
        "  - attribute: {name: list, from: {annotation_key: parts.list}}\n", ""
    )
    project(tmp_path, rules, {"src/Extra.php": EXTRA})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    places = {
        n["id"]: [place["line"] for place in n["locations"]]
        for n in document["nodes"]
        if n["type"] == "acme.entry"
    }
    # The dotted key's node sits at the annotation's line, as any annotation rule's node does.
    assert places == {"acme.entry::a": [8, 9], "acme.entry::two": [6]}


def test_a_key_with_a_hyphen_is_a_path_part_and_a_list_group_unread_gives_no_row(
    tmp_path: Path,
) -> None:
    rules = each_rule("sub", "sub-parts.*", "{key}") + each_rule("named", "names.*", "{key}")
    project(tmp_path, rules, {"src/Extra.php": EXTRA})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _entries(document, "sub") == {"acme.entry::x": 11}
    # A list group the path reads lists each item; the rule that does not read it lists none.
    rows = sorted(row for row in report.skipped if row[2] in ("sub", "named"))
    row = ("src/Extra.php", 12, "named", "group names holds an entry that is not key = value")
    assert rows == [row, row]


def test_a_dotted_key_must_be_quoted_text_as_a_key_at_the_top_level(tmp_path: Path) -> None:
    rule = DOTTED.format(name="main", key="api_paths.main").replace(
        "  - attribute: {name: list, from: {annotation_key: parts.list}}\n", ""
    ).replace("  emits:", "  must_be_placeholder:")
    rule = rule.replace(
        "  id: {from: {annotation_key: api_paths.main}}\n",
        "  id: {from: {annotation_key: api_paths.main}, must_be: string_literal}\n",
    ).replace("  must_be_placeholder:", "  emits:")
    project(tmp_path, rule, {"src/Extra.php": EXTRA})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert [n for n in document["nodes"] if n["type"] == "acme.entry"] == []
    assert [row for row in report.skipped if row[2] == "main"] == [
        ("src/Extra.php", 6, "main", "key api_paths.main is not quoted text")
    ]


def test_normalize_steps_name_the_entry_on_the_id_and_on_the_end(tmp_path: Path) -> None:
    rules = each_rule("link", "paths.*", "{value}").replace(
        "  id: {template: '{value}'}\n",
        "  id: {template: '{value}', normalize: [{replace: '^/', with: '{key}:'}]}\n",
    )
    rules += """\
- rule: grouped_class
  reads: file
  in: [source]
  match:
    {annotation: Thing, each: 'parts.*.*', filetype: php, where: [{applies_to: class_declaration}]}
  id: {template: '{key}'}
  emits:
  - edge:
      kind: entry_names_class
      from: this_node
      to: {template: '{value}', normalize: [{replace: '^\\\\', with: '{group}.'}]}
  confidence: declared
"""
    project(tmp_path, rules, {"src/Order.php": ORDER})
    found = _mapped(tmp_path)
    assert _entries(found, "link") == {"acme.entry::edit-page:order/{id}/edit": 18}
    assert {(e["from"], e["to"]) for e in found["edges"]} == {
        ("acme.entry::add", "acme.class::Acme\\OrderAddPanel"),
        ("acme.entry::html", "acme.class::router.Acme\\OrderRoutes"),
    }


def test_a_file_with_crlf_line_ends_reads_the_same_entries_at_the_same_lines(
    tmp_path: Path,
) -> None:
    rule = each_rule("grouped", "parts.*.*", "{enclosing_type}|{group}|{key}")
    project(tmp_path, rule, {"src/Order.php": ORDER.replace("\n", "\r\n")})
    assert _entries(_mapped(tmp_path), "grouped") == {
        "acme.entry::Acme\\Order|panel|add": 11,
        "acme.entry::Acme\\Order|router|html": 14,
    }


THINGS = """\
<?php

namespace Acme;

/**
 * @Thing(
 *   id = "invoice",
 *   paths = {
 *     "main" = "/invoice/{id}",
 *     "make" = "/invoice"
 *   },
 *   owner = {"name" = "billing"}
 * )
 */
class Invoice {}

/**
 * @Thing(
 *   id = NAMED,
 *   paths = {"main" = "/named"}
 * )
 */
class Named {}

/**
 * @Thing(
 *   paths = {"main" = "/orphan"}
 * )
 */
class Orphan {}
"""

TO_KEY = """\
- rule: {name}
  reads: file
  in: [source]
  match: {{annotation: Thing, {each}filetype: php, where: [{{applies_to: class_declaration}}]}}
  id: {id}
  emits: [{{edge: {{kind: path_of, from: this_node, to: {{from: {{annotation_key: {key}}}}}}}}}]
  confidence: declared
"""


def test_an_edge_runs_to_the_node_another_key_of_the_annotation_names(tmp_path: Path) -> None:
    each = "each: 'paths.*', "
    rules = TO_KEY.format(name="path", each=each, id="{template: '{value}'}", key="id")
    rules += TO_KEY.format(
        name="plain", each="", id="{from: {annotation_key: paths.make}}", key="owner.name"
    )
    # The twin node rule: the edge rule still lists the key it alone reads.
    rules += each_rule("path_node", "paths.*", "{value}")
    project(tmp_path, rules, {"src/Things.php": THINGS})
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    found = {
        (e["from"], e["to"], e["provenance"][0]["rule"], e["locations"][0]["line"])
        for e in document["edges"]
    }
    assert found == {
        ("acme.entry::/invoice/{id}", "acme.thing::invoice", "path", 9),
        ("acme.entry::/invoice", "acme.thing::invoice", "path", 10),
        ("acme.entry::/invoice", "acme.thing::billing", "plain", 6),
    }
    # A key that is missing, or whose value is not quoted text, gives the key's row at the entry.
    assert sorted(row for row in report.skipped if row[2] in ("path", "path_node")) == [
        ("src/Things.php", 20, "path", "key id is not quoted text"),
        ("src/Things.php", 27, "path", "key id is missing"),
    ]
