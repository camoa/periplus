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

SOURCE = "drush_basic@0.0.1"
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
    _pin(project, "js_basic")

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
