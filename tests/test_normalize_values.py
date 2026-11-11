"""A ``{name}`` in a normalize step's ``replace`` pattern or ``with`` text is a path or settings
value, filled as literal text; one naming no such value is refused when the pack loads; a
quantifier stays one, and so does a brace after a backslash. A pattern that does not compile once
filled does not run, and says so under the skipped matches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant, rutter
from test_validate import Project, _run, elsewhere  # noqa: F401 - fixture

from periplus.cli import main

PACK_RULES_UNREADABLE = 19
RULE_NOT_EXECUTABLE = 26

MANIFEST = """\
pack: site
version: 0.0.1
depends: []
values:
  app_prefix: The prefix of the application's own names.
folders:
  src: ./src/**
files:
  types:
    code:
      endings: [sx]
      reader: text
      path_values:
        area: {pattern: '^src/(?<area>\\w+)/', template: '{area}'PATH_NORMALIZE}
"""

RULES = """\
node_types:
- {name: site.thing, id_namespace: site.thing}
rules:
- rule: thing_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^use (?<name>\\S+)$'}
  id: {from: {capture: name}, normalize: [{replace: 'REPLACE', with: 'WITH'}]}
  emits: [{node: {type: site.thing}}]
  confidence: declared
"""


def _plant(
    root: Path,
    replace: str,
    prefix: str,
    used: str,
    *,
    with_: str = "",
    file: str = "src/one.sx",
    path_normalize: str = "",
    rules: str = RULES,
) -> None:
    manifest = MANIFEST.replace("PATH_NORMALIZE", path_normalize)
    rules = rules.replace("REPLACE", replace).replace("WITH", with_)
    rutter(root, "site", manifest, {"site.yaml": rules})
    plant(
        root,
        {
            ".periplus/settings.yml": (
                f"periplus_version: 0\npacks:\n  - site@0.0.1\nvalues:\n  app_prefix: '{prefix}'\n"
            ),
            file: f"use {used}\n",
        },
    )


def _call(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    capsys.readouterr()
    status = main([*args, "--format", "json"])
    return status, json.loads(capsys.readouterr().out)


def _ids(root: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    status, report = _call(["map", "--output", str(root / "out.json")], capsys)
    assert (status, report["problems"]) == (0, [])
    document = json.loads((root / "out.json").read_text(encoding="utf-8"))
    return [node["id"] for node in document["nodes"]]


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


@pytest.mark.parametrize(
    ("prefix", "used", "expected"),
    [
        ("shop", "shop.cart.Basket", "site.thing::cart.Basket"),
        # Unescaped, the dot of s.op would let sxop fit.
        ("s.op", "sxop.cart.Basket", "site.thing::sxop.cart.Basket"),
    ],
)
def test_a_settings_value_in_a_replace_pattern_is_filled_as_literal_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prefix: str, used: str, expected: str
) -> None:
    _plant(tmp_path, "^{app_prefix}\\.", prefix, used)

    assert _ids(tmp_path, capsys) == [expected]


def test_a_replace_pattern_naming_no_value_is_refused_by_validate_and_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^{nowhere}\\.", "shop", "shop.cart.Basket")

    map_status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)
    status, validated = _call(["validate", "site"], capsys)

    problems = [(p["code"], p["message"]) for p in mapped["problems"]]
    assert map_status == RULE_NOT_EXECUTABLE
    assert [code for code, _ in problems] == [RULE_NOT_EXECUTABLE]
    assert "nowhere" in problems[0][1]
    assert (status, [(p["code"], p["message"]) for p in validated["problems"]]) == (
        map_status,
        problems,
    )


def test_a_quantifier_in_a_replace_pattern_stays_a_quantifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^\\w{2}\\.", "shop", "ab.cart.Basket")

    assert _ids(tmp_path, capsys) == ["site.thing::cart.Basket"]


def _skipped(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[list[str], list[dict]]:
    status, report = _call(["map", "--output", str(root / "out.json")], capsys)
    assert (status, report["problems"]) == (0, [])
    document = json.loads((root / "out.json").read_text(encoding="utf-8"))
    return [node["id"] for node in document["nodes"]], report["skipped"]


@pytest.mark.parametrize(
    ("replace", "used"),
    [
        # A route placeholder: the escaped brace is matched as itself, and shop is not filled in.
        ("^\\{app_prefix}\\.", "{app_prefix}.cart.Basket"),
        # An escaped brace around a name that is no value is not refused.
        ("^\\{node}\\.", "{node}.cart.Basket"),
    ],
)
def test_an_escaped_brace_in_a_replace_pattern_stays_literal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], replace: str, used: str
) -> None:
    _plant(tmp_path, replace, "shop", used)

    assert _ids(tmp_path, capsys) == ["site.thing::cart.Basket"]


def test_an_even_run_of_backslashes_still_fills_the_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^\\\\{app_prefix}\\.", "shop", "\\shop.cart.Basket")

    assert _ids(tmp_path, capsys) == ["site.thing::cart.Basket"]


@pytest.mark.parametrize("replace", ["^[{app_prefix}]\\.", "^[^{app_prefix}]\\."])
def test_an_empty_value_in_a_character_class_skips_the_step_and_lists_a_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], replace: str
) -> None:
    _plant(tmp_path, replace, "", "s.cart.Basket")

    ids, skipped = _skipped(tmp_path, capsys)

    assert ids == ["site.thing::s.cart.Basket"]
    assert [(row["file"], row["rule"]) for row in skipped] == [("src/one.sx", "thing_line")]
    assert "does not compile" in skipped[0]["reason"]


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("shop", "site.thing::shop-cart.Basket"), ("a\\b", "site.thing::a\\b-cart.Basket")],
)
def test_a_value_in_the_with_text_is_filled_as_literal_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prefix: str, expected: str
) -> None:
    _plant(tmp_path, "^x\\.", prefix, "x.cart.Basket", with_="{app_prefix}-")

    assert _ids(tmp_path, capsys) == [expected]


def test_a_with_text_naming_no_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^x\\.", "shop", "x.cart.Basket", with_="{nowhere}-")

    status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)

    assert status == RULE_NOT_EXECUTABLE
    assert [p["code"] for p in mapped["problems"]] == [RULE_NOT_EXECUTABLE]
    assert "nowhere" in mapped["problems"][0]["message"]


@pytest.mark.parametrize(
    ("file", "expected"),
    [
        ("src/shop/one.sx", "site.thing::cart.Basket"),
        # The file's path gives no area, so the step does not run on it.
        ("src/one.sx", "site.thing::shop.cart.Basket"),
    ],
)
def test_a_path_value_in_a_replace_pattern_is_filled_and_an_absent_one_skips_the_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], file: str, expected: str
) -> None:
    _plant(tmp_path, "^{area}\\.", "x", "shop.cart.Basket", file=file)

    assert _ids(tmp_path, capsys) == [expected]


def test_a_path_value_normalize_fills_a_settings_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_normalize = ", normalize: [{replace: '^{app_prefix}_', with: ''}]"
    _plant(
        tmp_path,
        "^{area}\\.",
        "my",
        "shop.cart.Basket",
        file="src/my_shop/one.sx",
        path_normalize=path_normalize,
    )

    assert _ids(tmp_path, capsys) == ["site.thing::cart.Basket"]


def test_a_path_value_normalize_naming_no_settings_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_normalize = ", normalize: [{replace: '^{nowhere}_', with: ''}]"
    _plant(tmp_path, "x", "my", "shop.cart.Basket", path_normalize=path_normalize)

    status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)

    assert status == PACK_RULES_UNREADABLE
    assert [p["code"] for p in mapped["problems"]] == [PACK_RULES_UNREADABLE]
    assert "nowhere" in mapped["problems"][0]["message"]
    assert (
        "normalize step '^{nowhere}_' with '', which names nowhere"
        in (mapped["problems"][0]["message"])
    )


@pytest.mark.parametrize(
    "path_value",
    [
        "{pattern: '^src/(?<area>\\w+)/', template: '{area}', "
        "normalize: [{replace: '^{app_prefix}_', with: ''}]}",
        "{pattern: '^src/(?<area>\\w+)/', template: '{app_prefix}{area}'}",
    ],
)
def test_a_path_value_relies_only_on_a_value_its_rutter_or_a_dependency_declares(
    elsewhere: Project,  # noqa: F811
    path_value: str,
) -> None:
    """Outside a project, a value an unrelated rutter declares does not satisfy a path value."""
    packs = elsewhere.config / "packs"
    bodies = {
        "pathfix": (
            "depends: []\nfiles:\n  types:\n    code:\n      endings: [sx]\n      reader: text\n"
            f"      path_values:\n        area: {path_value}\n"
        ),
        "valuesfix": "depends: []\nvalues:\n  app_prefix: A prefix.\n",
        "bothfix": "depends: [pathfix, valuesfix]\n",
    }
    for name, body in bodies.items():
        (packs / f"{name}@0.0.1").mkdir(parents=True)
        (packs / f"{name}@0.0.1" / "pack.yaml").write_text(
            f"pack: {name}\nversion: 0.0.1\n{body}", encoding="utf-8"
        )

    results = [
        _run(["validate", name, "--format", "json"], cwd=elsewhere.root, config=elsewhere.config)
        for name in ("pathfix", "bothfix")
    ]

    codes = [
        (result.returncode, [p["code"] for p in json.loads(result.stdout)["problems"]])
        for result in results
    ]
    assert codes == [(PACK_RULES_UNREADABLE, [PACK_RULES_UNREADABLE])] * 2


IMPORT_PACK = """\
pack: probe
version: 0.0.1
depends: []
values:
  app_prefix: The prefix of the application's aliases.
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
  comment: comment
  resolve:
  - full_if_prefixed: "\\\\"
BOUND  - prefix_with: namespace
"""

IMPORTS = """\
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts: {alias: alias, use_kind: type}
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\\\"
    skip_when_field_set: use_kind
    normalize: [{replace: 'REPLACE', with: ''}]
"""

IMPORT_RULES = """\
node_types:
- {name: probe.class, id_namespace: probe.class}
- {name: probe.property, id_namespace: probe.property}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
- rule: property
  reads: file
  in: [source]
  match: {declaration: property_declaration, name_child: [property_element, name], filetype: php}
  id:
    from: [declared_name, {qualified: {docblock: '@var\\s+(?<type>[\\w\\\\]+)'}}]
    template: '{declared_name}:{type}'
  emits: [{node: {type: probe.property}}]
  confidence: declared
"""

IMPORT_SOURCE = """\
<?php

namespace App\\Ctl;

use App\\Service\\Registration as ShopReg;

class Thing
{
    /** @var Reg */
    protected $reg;
}
"""


def _plant_imports(
    root: Path,
    replace: str,
    *,
    bound: bool = True,
    prefix: str = "Shop",
    rules: str = IMPORT_RULES,
    source: str = IMPORT_SOURCE,
) -> None:
    manifest = IMPORT_PACK.replace("BOUND", "  - bound_first_segment\n" if bound else "")
    imports = IMPORTS.replace("REPLACE", replace)
    rutter(root, "probe", manifest, {"imports.yaml": imports, "probe.yaml": rules})
    plant(
        root,
        {
            ".periplus/settings.yml": (
                f"periplus_version: 0\npacks:\n  - probe@0.0.1\nvalues:\n  app_prefix: '{prefix}'\n"
            ),
            "src/Thing.php": source,
        },
    )


def test_an_import_bind_normalize_fills_a_settings_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant_imports(tmp_path, "^{app_prefix}")

    assert _ids(tmp_path, capsys) == [
        "probe.class::App\\Ctl\\Thing",
        "probe.property::$reg:App\\Service\\Registration",
    ]


def test_an_import_bind_normalize_naming_no_value_refuses_the_rules_that_read_imports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant_imports(tmp_path, "^{nowhere}")

    status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)

    assert status == RULE_NOT_EXECUTABLE
    messages = [p["message"] for p in mapped["problems"]]
    assert messages and all("probe/rules/imports.yaml" in m and "nowhere" in m for m in messages)


def test_an_import_bind_normalize_naming_no_value_spares_rules_that_never_read_imports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no bound_first_segment step, no rule reads the imports, so none is refused."""
    _plant_imports(tmp_path, "^{nowhere}", bound=False)

    assert _ids(tmp_path, capsys) == [
        "probe.class::App\\Ctl\\Thing",
        "probe.property::$reg:App\\Ctl\\Reg",
    ]


@pytest.mark.parametrize(("bound", "rows"), [(True, ["find_class", "property"]), (False, [])])
def test_an_import_bind_normalize_that_does_not_compile_lists_rows_for_rules_that_read_imports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bound: bool, rows: list[str]
) -> None:
    _plant_imports(tmp_path, "^[{app_prefix}]", bound=bound, prefix="")

    _, skipped = _skipped(tmp_path, capsys)

    assert [(row["file"], row["rule"]) for row in skipped] == [("src/Thing.php", r) for r in rows]


ID_RULES = IMPORT_RULES.replace(
    "rules:\n",
    """\
- {name: probe.fn, id_namespace: probe.fn}
rules:
- rule: find_fn
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: 'PATTERN', template: '{hook}'}
  emits: [{node: {type: probe.fn}}]
  confidence: declared
""",
)

ID_SOURCE = IMPORT_SOURCE.replace(
    "class Thing", "function a_cron() {}\nfunction b_init() {}\n\nclass Thing"
)


@pytest.mark.parametrize(
    ("pattern", "prefix", "fns", "rows"),
    [
        ("^[{app_prefix}]_(?<hook>\\w+)$", "a", ["probe.fn::cron"], []),
        ("^[{app_prefix}]_(?<hook>\\w+)$", "", [], [("src/Thing.php", 7, "find_fn")]),
        # Whether a value makes a good range end is known only once it is filled in.
        ("^[z-{app_prefix}]_(?<hook>\\w+)$", "a", [], [("src/Thing.php", 7, "find_fn")]),
    ],
)
def test_a_settings_value_in_an_id_pattern_is_checked_when_the_value_is_filled_in(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pattern: str,
    prefix: str,
    fns: list[str],
    rows: list[tuple[str, int, str]],
) -> None:
    """At load, the pattern is not refused; filled with a value that makes it not compile, the
    rule makes no node there and lists one skipped row."""
    rules = ID_RULES.replace("PATTERN", pattern)
    _plant_imports(tmp_path, "^x", bound=False, prefix=prefix, rules=rules, source=ID_SOURCE)

    status, validated = _call(["validate", "probe"], capsys)
    ids, skipped = _skipped(tmp_path, capsys)

    assert (status, validated["problems"]) == (0, [])
    assert [i for i in ids if i.startswith("probe.fn::")] == fns
    assert [(row["file"], row["line"], row["rule"]) for row in skipped] == rows
    assert all("does not compile" in row["reason"] for row in skipped)


VALUE_RULES = """\
node_types:
- {name: site.thing, id_namespace: site.thing}
rules:
- rule: thing_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^use (?<name>\\S+)$'}
  values:
    v: {template: '{name}', normalize: [{replace: 'REPLACE', with: 'WITH'}]}
  id: {template: '{v}'}
  emits: [{node: {type: site.thing}}]
  confidence: declared
"""


def test_a_value_normalize_that_does_not_compile_lists_a_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^[{app_prefix}]", "", "s.x", rules=VALUE_RULES)

    ids, skipped = _skipped(tmp_path, capsys)

    assert ids == ["site.thing::s.x"]
    assert [(row["file"], row["rule"]) for row in skipped] == [("src/one.sx", "thing_line")]


def test_a_path_value_normalize_that_does_not_compile_lists_a_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_normalize = ", normalize: [{replace: '^[{app_prefix}]', with: ''}]"
    _plant(tmp_path, "^{area}\\.", "", "a.x", file="src/a/one.sx", path_normalize=path_normalize)

    ids, skipped = _skipped(tmp_path, capsys)

    assert ids == ["site.thing::x"]
    assert [(row["file"], row["rule"]) for row in skipped] == [("src/a/one.sx", "thing_line")]


def test_a_file_the_rule_matched_nothing_in_lists_no_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^[{app_prefix}]", "", "s.x", file="src/a/one.sx")
    plant(tmp_path, {"src/b/two.sx": "nothing here\n"})

    _, skipped = _skipped(tmp_path, capsys)

    assert [row["file"] for row in skipped] == ["src/a/one.sx"]


def test_a_step_whose_with_text_names_a_value_the_file_lacks_lists_no_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file's path gives no area, so the step does not run whether or not it compiles."""
    _plant(tmp_path, "^[{app_prefix}]", "", "s.x", with_="{area}")

    assert _skipped(tmp_path, capsys) == (["site.thing::s.x"], [])


@pytest.mark.parametrize(
    ("with_", "prefix", "expected"),
    [
        ("{app_prefix}\\1$0\\g<0>-", "s", "site.thing::s\\1$0\\g<0>-cart"),
        ("{app_prefix}-", "$1\\g<0>\\2", "site.thing::$1\\g<0>\\2-cart"),
        # A backslash in with text is literal, an odd one before a brace too: the value is not
        # filled in, and the backslash stays.
        ("\\{app_prefix}-", "s", "site.thing::\\{app_prefix}-cart"),
    ],
)
def test_with_text_is_literal_apart_from_the_values_it_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], with_: str, prefix: str, expected: str
) -> None:
    _plant(tmp_path, "^x\\.", prefix, "x.cart", with_=with_)

    assert _ids(tmp_path, capsys) == [expected]


def test_a_path_value_normalize_with_text_naming_no_settings_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_normalize = ", normalize: [{replace: '^a', with: '{nowhere}'}]"
    _plant(tmp_path, "x", "my", "shop.cart.Basket", path_normalize=path_normalize)

    status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)

    assert status == PACK_RULES_UNREADABLE
    assert [p["code"] for p in mapped["problems"]] == [PACK_RULES_UNREADABLE]
    assert "nowhere" in mapped["problems"][0]["message"]
