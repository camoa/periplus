"""A path value's ``root_name`` names a settings value: when the settings give it, the pattern
searches the path with that value and a slash before it, wherever the path it searches starts at
the project folder. So a project that is one unit at its root maps from its own root with the ids
it gets as a folder of a larger project. A root_name naming no settings value, and a given value
that is no folder name, are refused when the pack loads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant, rutter

from periplus.cli import main

PACK_RULES_UNREADABLE = 19

MANIFEST = """\
pack: acme
version: 0.0.1
depends: []
values:
  unit_name: The name of the unit the project folder is, when it is one.
folders:
  units: ./units
  unit_files: "{units}/**"
files:
  types:
    code:
      endings: [sx]
      reader: text
      path_values:
        # The innermost folder before src, from the project folder.
        unit:
          pattern: '^(?:.*?/)??(?<unit>[^/]+)/src/[^/]+\\.sx$'
          template: '{unit}'
          root_name: ROOT_NAME
        # The first folder below units.
        top:
          pattern: '^(?<top>[^/]+)/'
          template: '{top}'
          relative_to: units
          root_name: unit_name
        # The folder that holds the file, as it is on disk.
        dir:
          pattern: '^(?<dir>.+)/[^/]+$'
          template: '{dir}'
"""

RULES = """\
node_types:
- {name: acme.thing, id_namespace: acme.thing}
rules:
- rule: thing_line
  reads: file
  in: [unit_files]
  match: {file: '*', filetype: code, text: '(?m)^thing (?<name>\\S+)$'}
  id: {template: 'ID'}
  emits: [{node: {type: acme.thing}}]
  confidence: declared
"""


def _plant(
    root: Path,
    files: dict[str, str],
    settings: str = "",
    *,
    root_name: str = "unit_name",
    id_template: str = "{top}|{unit}.{name}",
) -> None:
    manifest = MANIFEST.replace("ROOT_NAME", root_name)
    rutter(root, "acme", manifest, {"acme.yaml": RULES.replace("ID", id_template)})
    plant(
        root,
        {
            ".periplus/settings.yml": f"periplus_version: 0\npacks:\n  - acme@0.0.1\n{settings}",
            **files,
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
def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _project(tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / name
    root.mkdir()
    monkeypatch.chdir(root)
    return root


ROOT_UNIT = """\
folders:
  units: .
values:
  unit_name: inv
"""


def test_a_project_that_is_one_unit_gets_the_ids_it_gets_as_a_folder_of_a_larger_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    larger = _project(tmp_path, "larger", monkeypatch)
    _plant(
        larger,
        {"units/inv/src/one.sx": "thing basket\n", "units/inv/sub/src/two.sx": "thing cart\n"},
    )
    as_folder = _ids(larger, capsys)

    alone = _project(tmp_path, "checkout-anywhere", monkeypatch)
    _plant(alone, {"src/one.sx": "thing basket\n", "sub/src/two.sx": "thing cart\n"}, ROOT_UNIT)

    assert as_folder == ["acme.thing::inv|inv.basket", "acme.thing::inv|sub.cart"]
    assert _ids(alone, capsys) == as_folder


def test_without_the_value_the_path_is_searched_as_it_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, "folders:\n  units: .\n")

    # The first folder is src, and no folder before src names the unit: no id.
    assert _ids(root, capsys) == []


def test_a_value_relative_to_a_folder_below_the_root_is_not_given_the_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"units/zed/src/one.sx": "thing basket\n"}, "values:\n  unit_name: inv\n")

    assert _ids(root, capsys) == ["acme.thing::zed|zed.basket"]


def test_a_path_value_without_root_name_sees_the_path_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"sub/src/two.sx": "thing cart\n"}, ROOT_UNIT, id_template="{dir}|{name}")

    assert _ids(root, capsys) == ["acme.thing::sub/src|cart"]


def _problems(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[tuple[int, str]]]:
    """The status and problems of map, asserted equal to those of validate."""
    map_status, mapped = _call(["map", "--output", str(root / "out.json")], capsys)
    status, validated = _call(["validate", "acme"], capsys)
    problems = [(p["code"], p["message"]) for p in mapped["problems"]]
    assert (status, [(p["code"], p["message"]) for p in validated["problems"]]) == (
        map_status,
        problems,
    )
    return map_status, problems


def test_a_root_name_naming_no_settings_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, root_name="nowhere")

    status, problems = _problems(root, capsys)

    assert status == PACK_RULES_UNREADABLE
    assert problems == [
        (
            PACK_RULES_UNREADABLE,
            "acme/pack.yaml: the path value unit of the file type code has the root_name "
            "nowhere, no settings value",
        )
    ]


@pytest.mark.parametrize("given", ["''", "'.'", "'..'", "inv/sub", "'inv\\sub'"])
def test_a_root_name_value_that_is_no_folder_name_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    given: str,
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, f"values:\n  unit_name: {given}\n")

    status, problems = _problems(root, capsys)

    assert status == PACK_RULES_UNREADABLE
    assert [code for code, _ in problems] == [PACK_RULES_UNREADABLE]
    settings = root / ".periplus" / "settings.yml"
    assert problems[0][1].startswith(
        f"the settings value unit_name of {settings}, which acme/pack.yaml reads as the name of "
        "the project folder, is "
    ), problems[0][1]
    assert problems[0][1].endswith(", which is no folder name"), problems[0][1]


def test_a_capture_that_is_also_a_settings_value_stays_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, "values:\n  unit: inv\n", root_name="unit")

    status, problems = _problems(root, capsys)

    assert status == PACK_RULES_UNREADABLE
    assert (
        PACK_RULES_UNREADABLE,
        "acme/pack.yaml: the path value unit of the file type code has the template {unit}, "
        "which names unit, both a capture of its pattern and a settings value",
    ) in problems


RULE_NOT_EXECUTABLE = 26


def test_a_root_name_value_that_a_template_also_reads_is_still_asked_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(
        root, {"src/one.sx": "thing basket\n"}, "folders:\n  units: .\n",
        id_template="{unit_name}.{name}",
    )

    status, problems = _problems(root, capsys)

    assert status == RULE_NOT_EXECUTABLE
    assert problems == [
        (
            RULE_NOT_EXECUTABLE,
            "acme/pack.yaml: the rutter acme reads the settings value unit_name, which the "
            "project settings do not give",
        )
    ]


def test_a_settings_value_with_an_empty_name_puts_nothing_before_a_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(
        root,
        {"sub/src/two.sx": "thing cart\n"},
        "folders:\n  units: .\nvalues:\n  '': inv\n",
        id_template="{dir}|{name}",
    )

    assert _ids(root, capsys) == ["acme.thing::sub/src|cart"]


def test_a_root_name_may_name_a_value_the_settings_give_as_a_template_may(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    settings = ROOT_UNIT + "  given_name: inv\n"
    _plant(root, {"src/one.sx": "thing basket\n"}, settings, root_name="given_name")

    assert _ids(root, capsys) == ["acme.thing::inv|inv.basket"]


@pytest.mark.parametrize("given", ["' inv '", "'in v'", '"a\\nb"', '"a\\tb"', '"a\\x07b"'])
def test_a_root_name_value_with_a_space_or_a_control_character_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    given: str,
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, f"values:\n  unit_name: {given}\n")

    status, problems = _problems(root, capsys)

    assert status == PACK_RULES_UNREADABLE
    assert [code for code, _ in problems] == [PACK_RULES_UNREADABLE]
    assert problems[0][1].endswith(", which is no folder name"), problems[0][1]


UNREADABLE_SETTINGS = 4


@pytest.mark.parametrize("given", ["123", "[inv]"])
def test_a_settings_value_that_is_not_text_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    given: str,
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    settings = f"folders:\n  units: .\nvalues:\n  unit_name: {given}\n"
    _plant(root, {"src/one.sx": "thing basket\n"}, settings)

    status, report = _call(["map", "--output", str(root / "out.json")], capsys)

    path = root / ".periplus" / "settings.yml"
    assert status == UNREADABLE_SETTINGS
    assert [(p["code"], p["message"]) for p in report["problems"]] == [
        (
            UNREADABLE_SETTINGS,
            f"{path}: the value unit_name under values is not text, so no value of this "
            "file is used; write a number, true or false in quotes, as unit_name: '8'",
        )
    ]


def test_a_settings_value_whose_name_is_not_text_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, "values:\n  8: inv\n  unit_name: inv\n")

    status, report = _call(["map", "--output", str(root / "out.json")], capsys)

    path = root / ".periplus" / "settings.yml"
    assert (status, [(p["code"], p["message"]) for p in report["problems"]]) == (
        UNREADABLE_SETTINGS,
        [
            (
                UNREADABLE_SETTINGS,
                f"{path}: the name 8 under values is not text, so no value of this file is "
                "used; write the name in quotes, as '8'",
            )
        ],
    )


def test_a_user_settings_value_that_is_not_text_is_refused_naming_that_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, "folders:\n  units: .\n")
    plant(tmp_path, {"_config/settings.yml": "values:\n  unit_name: true\n"})

    status, report = _call(["map", "--output", str(root / "out.json")], capsys)

    path = tmp_path / "_config" / "settings.yml"
    assert status == UNREADABLE_SETTINGS
    assert [p["message"] for p in report["problems"]] == [
        f"{path}: the value unit_name under values is not text, so no value of this file is "
        "used; write a number, true or false in quotes, as unit_name: '8'"
    ]


def test_an_empty_root_name_is_refused_by_the_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n"}, root_name="''")

    status, report = _call(["validate", "acme"], capsys)

    assert status == 16
    assert [(e["pointer"], e["keyword"]) for e in report["errors"]] == [
        ("$.files.types.code.path_values.unit.root_name", "pattern")
    ]


def test_the_map_is_byte_identical_in_two_differently_named_folders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    written = []
    for name in ("first-checkout", "a/second/inv-copy"):
        root = _project(tmp_path, name.replace("/", "_"), monkeypatch)
        _plant(root, {"src/one.sx": "thing basket\n", "sub/src/two.sx": "thing cart\n"}, ROOT_UNIT)
        _ids(root, capsys)
        written.append((root / "out.json").read_bytes())

    assert written[0] == written[1]
    assert b"inv|inv.basket" in written[0]


BASE = """\
pack: base
version: 0.0.1
depends: []
values:
  unit_name: The name of the unit the project folder is, when it is one.
"""


def test_a_root_name_may_name_a_value_a_dependency_declares(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    manifest = MANIFEST.replace("ROOT_NAME", "unit_name").replace(
        "depends: []\nvalues:\n  unit_name: The name of the unit the project folder is, when it "
        "is one.\n",
        "depends: [base]\n",
    )
    assert "depends: [base]" in manifest
    rutter(root, "base", BASE)
    rutter(root, "acme", manifest, {"acme.yaml": RULES.replace("ID", "{top}|{unit}.{name}")})
    pins = "periplus_version: 0\npacks:\n  - base@0.0.1\n  - acme@0.0.1\n"
    plant(root, {".periplus/settings.yml": pins + ROOT_UNIT, "src/one.sx": "thing basket\n"})

    assert _ids(root, capsys) == ["acme.thing::inv|inv.basket"]

    plant(root, {".periplus/settings.yml": pins + "folders:\n  units: .\n"})
    status, report = _call(["map", "--output", str(root / "out.json")], capsys)
    assert (status, report["problems"]) == (0, [])


OTHER = """\
pack: other
version: 0.0.1
depends: []
values:
  other_name: The name of the other unit the project folder is.
folders:
  other_files: ./**
files:
  types:
    code2:
      endings: [sy]
      reader: text
      path_values:
        part:
          pattern: '^(?<part>[^/]+)/'
          template: '{part}'
          root_name: other_name
"""

OTHER_RULES = """\
node_types:
- {name: other.thing, id_namespace: other.thing}
rules:
- rule: other_line
  reads: file
  in: [other_files]
  match: {file: '*', filetype: code2, text: '(?m)^thing (?<name>\\S+)$'}
  id: {template: '{part}.{name}'}
  emits: [{node: {type: other.thing}}]
  confidence: declared
"""


def test_two_packs_naming_different_values_each_put_their_own_name_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    _plant(root, {"src/one.sx": "thing basket\n", "src/one.sy": "thing pear\n"})
    rutter(root, "other", OTHER, {"other.yaml": OTHER_RULES})
    pins = "periplus_version: 0\npacks:\n  - acme@0.0.1\n  - other@0.0.1\n"
    plant(root, {".periplus/settings.yml": pins + ROOT_UNIT + "  other_name: fruit\n"})

    assert _ids(root, capsys) == ["acme.thing::inv|inv.basket", "other.thing::fruit.pear"]


DETECTED = MANIFEST.replace("ROOT_NAME", "unit_name").replace(
    "depends: []\n", "depends: []\ndetect:\n  any_of:\n    - path: unit.marker\n"
)


def test_init_prints_the_root_name_values_of_the_packs_it_detects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "p", monkeypatch)
    plant(tmp_path, {"_config/packs/acme@0.0.1/pack.yaml": DETECTED})
    plant(root, {"unit.marker": ""})
    capsys.readouterr()

    status = main(["init"])

    assert status == 0
    assert (
        "  value     unit_name: The name of the unit the project folder is, when it is one. "
        "Set it under values in .periplus/settings.yml when this folder is that one unit."
    ) in capsys.readouterr().out.splitlines()
