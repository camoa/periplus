"""``periplus validate`` runs the pack checks ``periplus map`` runs, and a rutter declares the
settings values its rules read.

Every test calls ``periplus.cli.main`` in process. The broken packs are copies of the bundled
``drush_basic`` rutter, renamed, with one edit each; a test that needs a text rule first adds
one to the copy, since the rutter reads its commands from the tree. The oracle for the first
group is ``map`` itself: the problems ``validate`` gives equal the problems ``map`` gives
for the same pack.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from test_validate import (
    BUNDLED_PACKS,
    Project,
    _run,
    elsewhere,  # noqa: F401 - fixture
    project,  # noqa: F401 - fixture
)

from periplus.errors import ExitCode

SOURCE = "drush_basic@0.1.0"
RULE_FILE = Path("command") / "command_docblock.yaml"
TEXT_RULE_FILE = Path("command") / "command_text.yaml"
TEXT_RULE = r"""$schema: "https://periplus.dev/schema/0/pack-file.schema.json"
rules:
- rule: command_from_text
  reads: file
  in: [source]
  match:
    file: '**'
    filetype: drupal_php_text
    reads_sections: [block_comment]
    text: '@command[ \t]+(?<name>[\w:.-]+)'
  id: {template: '{name}'}
  emits: [{node: {type: drush.command}}]
  confidence: declared
- rule: command_method_from_text
  reads: file
  in: [source]
  match:
    file: '**'
    filetype: drupal_php_text
    reads_sections: [block_comment]
    text: '@command[ \t]+(?<name>[\w:.-]+)[\s\S]*?function\s+(?<method>\w+)'
  id: {template: '{name}'}
  emits:
  - edge:
      kind: command_method
      from: this_node
      to: {template: '{psr4_class}::{method}', types: [php.method], on_miss: unresolved}
  confidence: inferred
"""
RULE_NOT_EXECUTABLE = 26


def _call(args: Sequence[str], *, cwd: Path, config: Path) -> tuple[int, dict[str, object]]:
    """Run the entry function in process and return its status and its JSON report."""
    result = _run([*args, "--format", "json"], cwd=cwd, config=config)
    return result.returncode, json.loads(result.stdout)


def _fixture(packs: Path, name: str, *, depends: str | None = None) -> Path:
    """A renamed copy of the bundled drush_basic rutter under ``packs``."""
    target = packs / f"{name}@0.0.1"
    shutil.copytree(BUNDLED_PACKS / SOURCE, target)
    manifest = target / "pack.yaml"
    text = manifest.read_text(encoding="utf-8").replace(
        "\npack: drush_basic\n", f"\npack: {name}\n"
    )
    if depends is not None:
        text = text.replace("depends: [drupal_basic, php_basic]", f"depends: [{depends}]")
    manifest.write_text(text, encoding="utf-8")
    return target


def _edit(pack: Path, relative: Path, old: str, new: str) -> None:
    path = pack / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{relative} no longer holds {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _pin(where: Project, name: str, values: str = "") -> None:
    (where.root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks:\n  - {name}@0.0.1\n{values}", encoding="utf-8"
    )


def _problems(payload: dict[str, object]) -> list[tuple[object, object]]:
    problems = payload["problems"]
    assert isinstance(problems, list)
    return [(p["code"], p["message"]) for p in problems]


def _both(
    where: Project, name: str
) -> tuple[int, list[tuple[object, object]], int, list[tuple[object, object]]]:
    """The status and problems ``map`` gives for the pinned pack, then ``validate``'s."""
    map_status, mapped = _call(["map"], cwd=where.root, config=where.config)
    status, validated = _call(["validate", name], cwd=where.root, config=where.config)
    return map_status, _problems(mapped), status, _problems(validated)


@pytest.mark.criterion(id="c1")
def test_a_reads_sections_name_the_file_type_lacks_gives_the_map_problem_c1(
    project: Project,  # noqa: F811
) -> None:
    pack = _fixture(project.packs, "sectionfix")
    (pack / TEXT_RULE_FILE).write_text(TEXT_RULE, encoding="utf-8")
    _edit(
        pack, TEXT_RULE_FILE, "reads_sections: [block_comment]", "reads_sections: [no_such_section]"
    )
    _pin(project, "sectionfix")

    map_status, expected, status, actual = _both(project, "sectionfix")

    assert map_status == RULE_NOT_EXECUTABLE
    assert actual == expected
    assert status == map_status


@pytest.mark.criterion(id="c1")
def test_a_node_state_key_is_reported_as_accepted_and_not_executed_c1(
    project: Project,  # noqa: F811
) -> None:
    pack = _fixture(project.packs, "statefix")
    _edit(
        pack,
        RULE_FILE,
        "      type: drush.command\n",
        "      type: drush.command\n      state: declared\n",
    )
    _pin(project, "statefix")

    map_status, expected, status, actual = _both(project, "statefix")

    assert map_status == RULE_NOT_EXECUTABLE
    assert actual == expected
    assert status == map_status


@pytest.mark.criterion(id="c1")
def test_edge_kind_from_types_in_two_id_namespaces_give_the_map_problem_c1(
    project: Project,  # noqa: F811
) -> None:
    pack = _fixture(project.packs, "endfix")
    (pack / TEXT_RULE_FILE).write_text(TEXT_RULE, encoding="utf-8")
    _edit(
        pack,
        Path("command") / "command.yaml",
        '- kind: command_method\n  description: "The Drush command runs that method"\n'
        "  from: drush.command",
        '- kind: command_method\n  description: "The Drush command runs that method"\n'
        "  from: [drush.command, php.class]",
    )
    _pin(project, "endfix")

    map_status, expected, status, actual = _both(project, "endfix")

    assert map_status == RULE_NOT_EXECUTABLE
    assert actual == expected
    assert status == map_status


@pytest.mark.criterion(id="c1")
def test_a_problem_in_a_pack_the_named_pack_depends_on_is_reported_c1(
    project: Project,  # noqa: F811
) -> None:
    base = _fixture(project.packs, "basefix")
    (base / TEXT_RULE_FILE).write_text(TEXT_RULE, encoding="utf-8")
    _edit(
        base, TEXT_RULE_FILE, "reads_sections: [block_comment]", "reads_sections: [no_such_section]"
    )
    top = project.packs / "topfix@0.0.1"
    top.mkdir()
    (top / "pack.yaml").write_text(
        '$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"\n'
        "pack: topfix\nversion: 0.0.1\ndepends: [basefix]\n",
        encoding="utf-8",
    )
    _pin(project, "topfix")

    map_status, expected, status, actual = _both(project, "topfix")

    assert map_status == RULE_NOT_EXECUTABLE
    assert actual == expected
    assert status == map_status


def _valued_pack(packs: Path, name: str, *, declared: bool) -> None:
    pack = _fixture(packs, name)
    (pack / TEXT_RULE_FILE).write_text(TEXT_RULE, encoding="utf-8")
    _edit(pack, TEXT_RULE_FILE, "template: '{name}'", "template: '{drush_prefix}{name}'")
    if declared:
        _edit(
            pack,
            Path("pack.yaml"),
            "depends:",
            "values:\n  drush_prefix: A prefix put before every command id.\ndepends:",
        )


@pytest.mark.criterion(id="c2")
def test_validate_accepts_a_declared_value_and_refuses_an_undeclared_one_c2(
    elsewhere: Project,  # noqa: F811
) -> None:
    user_packs = elsewhere.config / "packs"
    user_packs.mkdir()
    _valued_pack(user_packs, "declaredfix", declared=True)
    _valued_pack(user_packs, "undeclaredfix", declared=False)

    declared_status, declared = _call(
        ["validate", "declaredfix"], cwd=elsewhere.root, config=elsewhere.config
    )
    undeclared_status, undeclared = _call(
        ["validate", "undeclaredfix"], cwd=elsewhere.root, config=elsewhere.config
    )

    assert (declared_status, declared["problems"], declared["errors"]) == (0, [], [])
    assert undeclared_status == RULE_NOT_EXECUTABLE
    assert _problems(undeclared)


@pytest.mark.criterion(id="c2")
def test_map_refuses_an_omitted_declared_value_and_maps_when_it_is_given_c2(
    project: Project,  # noqa: F811
) -> None:
    _valued_pack(project.packs, "declaredfix", declared=True)

    _pin(project, "declaredfix")
    omitted_status, omitted = _call(["map"], cwd=project.root, config=project.config)
    _pin(project, "declaredfix", 'values:\n  drush_prefix: "x:"\n')
    given_status, given = _call(["map"], cwd=project.root, config=project.config)

    assert _problems(omitted) == [
        (
            RULE_NOT_EXECUTABLE,
            "declaredfix/pack.yaml: the rutter declaredfix reads the settings value "
            "drush_prefix, which the project settings do not give",
        )
    ]
    assert omitted_status == RULE_NOT_EXECUTABLE
    # The project holds no source file, so the run that loads ends at nothing selected.
    assert given_status == ExitCode.NOTHING_SELECTED
    assert [p["code"] for p in given["problems"]] == [ExitCode.NOTHING_SELECTED]


@pytest.mark.criterion(id="c2")
def test_validate_in_a_project_refuses_an_omitted_declared_value_as_map_does_c2(
    project: Project,  # noqa: F811
) -> None:
    (project.root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks:\n  - go_basic@{_pinned_version('go_basic')}\n",
        encoding="utf-8",
    )

    map_status, expected, status, actual = _both(project, "go_basic")

    assert expected == [
        (
            RULE_NOT_EXECUTABLE,
            "go_basic/pack.yaml: the rutter go_basic reads the settings value module, which the "
            "project settings do not give",
        )
    ]
    assert map_status == RULE_NOT_EXECUTABLE
    assert (status, actual) == (map_status, expected)


@pytest.mark.criterion(id="c2")
def test_a_value_only_an_unrelated_pack_declares_does_not_satisfy_a_rule_c2(
    elsewhere: Project,  # noqa: F811
) -> None:
    user_packs = elsewhere.config / "packs"
    user_packs.mkdir()
    _valued_pack(user_packs, "undeclaredfix", declared=False)
    for name, body in (
        ("valuesfix", "depends: []\nvalues:\n  drush_prefix: A prefix.\n"),
        ("bothfix", "depends: [undeclaredfix, valuesfix]\n"),
    ):
        (user_packs / f"{name}@0.0.1").mkdir()
        (user_packs / f"{name}@0.0.1" / "pack.yaml").write_text(
            '$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"\n'
            f"pack: {name}\nversion: 0.0.1\n{body}",
            encoding="utf-8",
        )

    alone_status, alone = _call(
        ["validate", "undeclaredfix"], cwd=elsewhere.root, config=elsewhere.config
    )
    status, combined = _call(["validate", "bothfix"], cwd=elsewhere.root, config=elsewhere.config)

    assert alone_status == RULE_NOT_EXECUTABLE
    assert (status, _problems(combined)) == (alone_status, _problems(alone))


@pytest.mark.criterion(id="c2")
@pytest.mark.parametrize("pack", ["typescript", "go_basic"])
def test_validate_in_a_project_asks_no_value_of_a_rutter_the_project_does_not_pin_c2(
    project: Project,  # noqa: F811
    pack: str,
) -> None:
    """The project pins js_basic only, so it gives no value the named rutter declares, and the
    named rutter's folders resolve against its own dependency order, not the pinned one."""
    (project.root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks:\n  - js_basic@{_pinned_version('js_basic')}\n",
        encoding="utf-8",
    )

    status, payload = _call(["validate", pack], cwd=project.root, config=project.config)

    assert (status, payload["errors"], payload["problems"]) == (0, [], [])


@pytest.mark.criterion(id="c2")
def test_validate_resolves_folders_by_its_own_order_when_a_pinned_dependency_is_missing_c2(
    project: Project,  # noqa: F811
) -> None:
    """A pinned neighbour gives typescript_source a second value and depends on a rutter nothing
    carries; the pinned order has a problem, so folders resolve against typescript's own order."""
    neighbour = project.packs / "neighbourfix@0.0.1"
    neighbour.mkdir()
    (neighbour / "pack.yaml").write_text(
        '$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"\n'
        "pack: neighbourfix\nversion: 0.0.1\ndepends: [nosuchfix]\n"
        "folders:\n  typescript_source: ./other/**\n",
        encoding="utf-8",
    )
    (project.root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks:\n  - typescript@{_pinned_version('typescript')}\n"
        "  - neighbourfix@0.0.1\nvalues:\n  typescript_alias_root: src\n",
        encoding="utf-8",
    )

    status, payload = _call(["validate", "typescript"], cwd=project.root, config=project.config)

    assert (status, payload["errors"], payload["problems"]) == (0, [], [])


def _pinned_version(name: str) -> str:
    """The version half of the bundled directory ``<name>@<version>``."""
    (directory,) = [e for e in BUNDLED_PACKS.iterdir() if e.name.startswith(f"{name}@")]
    return directory.name.split("@")[1]


ACME_MANIFEST = """$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"
pack: {name}
version: 0.0.1
depends: [{depends}]
folders:
  {folder}: ./**
"""
ACME_RULES = """$schema: "https://periplus.dev/schema/0/pack-file.schema.json"
node_types:
- name: {name}.item
  id_namespace: {name}.item
rules:
- rule: {name}_items
  reads: file
  in: [{folder}]
  match:
    file: '*.inv'
    filetype: yaml
    each: 'items.*'
    where: [{{id_matches: '^a'}}]
  id: {{from: key}}
  emits: [{{node: {{type: {name}.item}}}}]
  confidence: declared
"""


def _acme(packs: Path, name: str, *, depends: str = "yaml_basic") -> Path:
    """A neutral rutter with one data rule that ``map`` executes, under ``packs``."""
    target = packs / f"{name}@0.0.1"
    target.mkdir()
    folder = f"{name}_root"
    (target / "pack.yaml").write_text(
        ACME_MANIFEST.format(name=name, depends=depends, folder=folder), encoding="utf-8"
    )
    (target / "inv.yaml").write_text(ACME_RULES.format(name=name, folder=folder), encoding="utf-8")
    return target


@pytest.mark.parametrize(
    ("key", "old", "new"),
    [
        ("match.where.*.matches", "{id_matches: '^a'}", "{matches: '^a'}"),
        ("id.from.key", "id: {from: key}", "id: {from: {key: name}}"),
        (
            "values.*.from.key",
            "id: {from: key}",
            "id: {from: key}\n  values: {label: {from: {key: name}}}",
        ),
    ],
)
def test_validate_reports_a_data_rule_key_map_does_not_execute_as_map_does(
    project: Project,  # noqa: F811
    key: str,
    old: str,
    new: str,
) -> None:
    _edit(_acme(project.packs, "acme"), Path("inv.yaml"), old, new)
    _pin(project, "acme")

    map_status, expected, status, actual = _both(project, "acme")

    assert map_status == RULE_NOT_EXECUTABLE
    assert [m for _, m in expected] == [
        f"acme/inv.yaml: the rule acme_items cannot be executed: the key {key} is accepted and "
        "not executed"
    ]
    assert (status, actual) == (map_status, expected)


def test_validate_of_a_pack_that_fails_its_schema_gives_the_other_problems_map_gives(
    project: Project,  # noqa: F811
) -> None:
    """The named pack fails its schema and the pack it depends on holds a rule map refuses. Map
    gives both; validate lists the first under its schema errors and the second as a problem."""
    _edit(_acme(project.packs, "basefix"), Path("inv.yaml"), "{id_matches: '^a'}", "{matches: 'a'}")
    _edit(
        _acme(project.packs, "topfix", depends="basefix"),
        Path("pack.yaml"),
        "topfix_root: ./**",
        "topfix_root: {template: '.'}",
    )
    _pin(project, "topfix")

    map_status, expected, status, payload = (
        *_call(["map"], cwd=project.root, config=project.config),
        *_call(["validate", "topfix"], cwd=project.root, config=project.config),
    )
    mapped = _problems(expected)
    errors = payload["errors"]
    assert isinstance(errors, list)

    assert {code for code, _ in mapped} == {ExitCode.SCHEMA_INVALID, RULE_NOT_EXECUTABLE}
    assert _problems(payload) == [p for p in mapped if p[0] != ExitCode.SCHEMA_INVALID]
    schema = [m for code, m in mapped if code == ExitCode.SCHEMA_INVALID]
    assert len(schema) == len(errors)
    assert all(
        m.startswith(f"topfix/{e['file']} {e['pointer']}: {e['message']}")
        for m, e in zip(schema, errors, strict=True)
    )
    assert status == ExitCode.SCHEMA_INVALID != 0
    assert map_status == ExitCode.SCHEMA_INVALID


def test_the_text_form_never_says_no_problems_beneath_a_schema_error(
    project: Project,  # noqa: F811
) -> None:
    _edit(_acme(project.packs, "acme"), Path("pack.yaml"), "acme_root: ./**", "acme_root: 7")
    _pin(project, "acme")

    result = _run(["validate", "acme"], cwd=project.root, config=project.config)
    problems = result.stdout.split("\nProblems:\n", 1)[1]

    assert "\nSchema errors:\n  pack.yaml  $.folders.acme_root" in result.stdout
    assert problems.splitlines()[0].strip() != "none"
    assert "periplus map refuses" in problems
    assert result.returncode == ExitCode.SCHEMA_INVALID


def _manifest(packs: Path, name: str, body: str) -> None:
    """A pack of one manifest, ``body`` written after its name and version."""
    (packs / f"{name}@0.0.1").mkdir()
    (packs / f"{name}@0.0.1" / "pack.yaml").write_text(
        '$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"\n'
        f"pack: {name}\nversion: 0.0.1\n{body}",
        encoding="utf-8",
    )


def _pin_all(where: Project, *names: str) -> None:
    (where.root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n" + "".join(f"  - {n}@0.0.1\n" for n in names),
        encoding="utf-8",
    )


def test_validate_gives_the_schema_problem_of_a_dependency_as_map_does(
    project: Project,  # noqa: F811
) -> None:
    """The named pack is sound and the pack it depends on fails its schema in its folders."""
    _manifest(project.packs, "basefix", "depends: []\nfolders:\n  basefix_root: 7\n")
    _manifest(project.packs, "topfix", "depends: [basefix]\n")
    _pin(project, "topfix")

    map_status, expected, status, actual = _both(project, "topfix")

    assert [code for code, _ in expected] == [ExitCode.SCHEMA_INVALID]
    assert (status, actual) == (map_status, expected)


def test_validate_of_a_pack_that_fails_its_schema_gives_the_pinned_conflicts_map_gives(
    project: Project,  # noqa: F811
) -> None:
    """Two pinned packs add one table row and one folder with different values; the named pack,
    which depends on one of them, fails its schema."""
    _manifest(project.packs, "ownfix", "depends: []\ntables:\n  t:\n    k1: v\n")
    for name, row, folder in (("midfix", "x", "a/**"), ("otherfix", "y", "b/**")):
        _manifest(
            project.packs,
            name,
            f"depends: [ownfix]\nadd_table_rows:\n  ownfix:\n    t:\n      k2: {row}\n"
            f"folders:\n  shared: {folder}\n",
        )
    _manifest(project.packs, "topfix", "depends: [midfix]\nfolders:\n  topfix_root: 7\n")
    _pin_all(project, "topfix", "otherfix")

    map_status, expected, status, actual = _both(project, "topfix")

    assert {code for code, _ in expected} > {ExitCode.SCHEMA_INVALID}
    assert actual == [p for p in expected if not p[1].startswith("topfix/")]
    assert status == map_status == ExitCode.SCHEMA_INVALID


def test_validate_gives_the_fix_map_names_for_a_boundary_schema_error(
    project: Project,  # noqa: F811
) -> None:
    _edit(_acme(project.packs, "acme"), Path("pack.yaml"), "folders:", "boundary: 7\nfolders:")
    _pin(project, "acme")

    _, mapped = _call(["map"], cwd=project.root, config=project.config)
    (message,) = [m for _, m in _problems(mapped)]
    hint = message.rsplit("; ", 1)[1]
    text = _run(["validate", "acme"], cwd=project.root, config=project.config).stdout
    _, payload = _call(["validate", "acme"], cwd=project.root, config=project.config)
    errors = payload["errors"]
    assert isinstance(errors, list)

    assert hint.startswith("write boundary: {<group>")
    assert hint in text.split("\nSchema errors:\n", 1)[1].split("\nProblems:\n", 1)[0]
    assert [e["hint"] for e in errors] == [hint]


def test_the_text_form_names_no_schema_refusal_when_the_pack_passes_its_schema(
    project: Project,  # noqa: F811
) -> None:
    _edit(_acme(project.packs, "acme"), Path("inv.yaml"), "{id_matches: '^a'}", "{matches: 'a'}")
    _pin(project, "acme")

    result = _run(["validate", "acme"], cwd=project.root, config=project.config)

    assert result.returncode == RULE_NOT_EXECUTABLE
    assert "match.where.*.matches is accepted and not executed" in result.stdout
    assert "periplus map refuses" not in result.stdout


REFERENCE_MANIFEST = """$schema: "https://periplus.dev/schema/0/pack-manifest.schema.json"
pack: acmeref
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  acmeref_root: ./**
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""
REFERENCE_RULES = """$schema: "https://periplus.dev/schema/0/pack-file.schema.json"
node_types:
- {name: acmeref.unit, id_namespace: acmeref.unit}
edge_kinds:
- {kind: acmeref_makes, from: [acmeref.unit], to: [acmeref.unit]}
rules:
- rule: acmeref_makes
  reads: file
  in: [acmeref_root]
  match:
    reference: object_creation_expression
    name_child: [name]
    filetype: php
    where: [{has_child: arguments}]
  emits: [{edge: {kind: acmeref_makes, from: enclosing_declaration, to: {types: [acmeref.unit]}}}]
  confidence: declared
"""


def test_validate_refuses_a_reference_rule_condition_as_map_does(
    project: Project,  # noqa: F811
) -> None:
    """A condition a reference rule's where does not take is refused with the one message that
    names the conditions it takes, within and not_within among them."""
    target = project.packs / "acmeref@0.0.1"
    target.mkdir()
    (target / "pack.yaml").write_text(REFERENCE_MANIFEST, encoding="utf-8")
    (target / "rules.yaml").write_text(REFERENCE_RULES, encoding="utf-8")
    _pin(project, "acmeref")

    map_status, expected, status, actual = _both(project, "acmeref")

    assert map_status == RULE_NOT_EXECUTABLE
    assert [m for _, m in expected] == [
        "acmeref/rules.yaml: the rule acmeref_makes cannot be executed: the match.where of a "
        "reference rule holds only name_matches, within, not_within, in_table and not_in_table "
        "conditions, within and not_within each a list of tree node types"
    ]
    assert (status, actual) == (map_status, expected)
