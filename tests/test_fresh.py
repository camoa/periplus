"""``periplus map`` writes an inputs record beside the map, and ``periplus fresh`` compares it with
the project as it is now: the files the rules read, the settings, the rutters and the tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant
from test_select_walks_once import SETTINGS, _project

import periplus
import periplus.map as map_module
from periplus.cli import main
from periplus.errors import ExitCode
from periplus.fresh import FreshReport, render_json, render_text
from periplus.fresh import run as fresh
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  src: ./src/**
files:
  types:
    t:
      endings: [t]
      reader: text
"""

RULES = r"""node_types:
- {name: own.word, id_namespace: own.word}
rules:
- rule: word
  reads: file
  in: [src]
  match: {file: '*', filetype: t, text: '(?m)^(?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.word}}]
  confidence: declared
"""

RUTTER = ".periplus/packs/own@0.0.1"


def _env(root: Path) -> dict[str, str]:
    return {"PERIPLUS_CONFIG_DIR": str(root / "config-dir")}


def _built(root: Path) -> Path:
    plant(
        root,
        {
            f"{RUTTER}/pack.yaml": MANIFEST,
            f"{RUTTER}/rules/own.yaml": RULES,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "src/a.t": "alpha\n",
            "src/b.t": "beta\n",
            "src/deep/c.t": "gamma\n",
            "src/notes.txt": "not a rule's file\n",
        },
    )
    _map(root)
    return root


def _map(root: Path, output: Path | None = None) -> None:
    report = run(
        start=root, env=_env(root), dependencies=check_runtime_dependencies(), output=output
    )
    assert report.problems == (), report.problems


def _fresh(root: Path, map_path: Path | None = None) -> FreshReport:
    return fresh(
        start=root, env=_env(root), dependencies=check_runtime_dependencies(), map_path=map_path
    )


def test_an_untouched_project_is_fresh_and_exits_0(tmp_path: Path) -> None:
    report = _fresh(_built(tmp_path))
    assert (report.state, report.exit_code) == ("fresh", ExitCode.OK)
    assert render_text(report).splitlines()[2] == (
        "fresh: 3 files, the settings, 1 rutter and the tool match the map"
    )


@pytest.mark.parametrize("settings", sorted(SETTINGS))
def test_a_project_of_nested_linked_and_excluded_folders_is_fresh_after_its_map(
    tmp_path: Path, settings: str
) -> None:
    _project(tmp_path, 6, SETTINGS[settings])
    _map(tmp_path)
    report = _fresh(tmp_path)
    assert (report.state, report.files, report.exit_code) == ("fresh", ((), (), ()), ExitCode.OK)


def test_an_edited_file_is_named_as_changed(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / "src/a.t").write_text("alpha\nomega\n")
    report = _fresh(root)
    assert (report.state, report.files) == ("stale", (("src/a.t",), (), ()))
    assert report.exit_code == ExitCode.MAP_STALE
    lines = render_text(report).splitlines()
    assert lines[2] == "stale: 1 file changed; settings same; rutters same; tool same"
    assert lines[3:] == ["files changed:", "  src/a.t", "run periplus map to rebuild"]


def test_a_file_whose_line_ends_alone_changed_is_changed(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / "src/a.t").write_bytes(b"alpha\r\n")
    assert (_fresh(root).state, _fresh(root).files) == ("stale", (("src/a.t",), (), ()))


DOCBLOCK = """<?php

namespace App;

/**
 * Sends the reminders.
 */
class Reminder
{
}
"""


def test_line_ends_that_change_a_tree_rule_s_map_make_it_stale(tmp_path: Path) -> None:
    """A tree rule reads the raw bytes: the class's summary is lost when its file turns CRLF."""
    plant(
        tmp_path,
        {
            ".periplus/settings.yml": "periplus_version: 0\npacks: [php_basic@0.3.0]\n",
            "src/Reminder.php": DOCBLOCK,
        },
    )
    _map(tmp_path)
    before = (tmp_path / ".periplus/map.json").read_bytes()
    (tmp_path / "src/Reminder.php").write_bytes(DOCBLOCK.replace("\n", "\r\n").encode())
    report = _fresh(tmp_path)
    _map(tmp_path, Path("rebuilt.json"))
    assert (tmp_path / "rebuilt.json").read_bytes() != before
    assert (report.state, report.files) == ("stale", (("src/Reminder.php",), (), ()))


def test_an_added_file_a_rule_s_folder_covers_is_named_as_added(tmp_path: Path) -> None:
    root = _built(tmp_path)
    plant(root, {"src/new.t": "delta\n", "src/new.txt": "no rule reads this\n", "out/x.t": "x\n"})
    report = _fresh(root)
    assert (report.state, report.files) == ("stale", ((), ("src/new.t",), ()))


def test_a_deleted_file_is_named_as_removed(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / "src/b.t").unlink()
    report = _fresh(root)
    assert (report.state, report.files) == ("stale", ((), (), ("src/b.t",)))


def test_a_changed_settings_value_makes_it_stale_and_says_settings(tmp_path: Path) -> None:
    root = _built(tmp_path)
    settings = root / ".periplus/settings.yml"
    settings.write_text(settings.read_text() + "exclude: ['src/none/**']\n")
    report = _fresh(root)
    assert (report.state, report.settings_changed, report.files) == ("stale", True, ((), (), ()))
    assert "; settings changed;" in render_text(report)


def test_a_comment_in_the_settings_file_changes_nothing(tmp_path: Path) -> None:
    root = _built(tmp_path)
    settings = root / ".periplus/settings.yml"
    settings.write_text("# a note\n" + settings.read_text())
    assert _fresh(root).state == "fresh"


def test_a_changed_rule_file_in_a_project_rutter_makes_it_stale_and_names_it(
    tmp_path: Path,
) -> None:
    root = _built(tmp_path)
    rules = root / RUTTER / "rules/own.yaml"
    rules.write_text(rules.read_text().replace("confidence: declared", "confidence: inferred"))
    report = _fresh(root)
    assert (report.state, report.packs, report.settings_changed) == (
        "stale",
        (("own@0.0.1",), (), ()),
        False,
    )
    assert "rutters changed:\n  own@0.0.1\n" in render_text(report)


def test_a_different_tool_version_alone_makes_it_stale_and_says_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _built(tmp_path)
    then = periplus.__version__
    monkeypatch.setattr(periplus, "__version__", "99.0.0")
    report = _fresh(root)
    assert (report.state, report.files, report.packs, report.settings_changed) == (
        "stale",
        ((), (), ()),
        ((), (), ()),
        False,
    )
    assert render_text(report).splitlines()[2] == (
        "stale: files same; settings same; rutters same; "
        f"tool changed: periplus {then} then, periplus 99.0.0 now"
    )


def test_the_record_is_the_same_bytes_from_two_runs_in_two_places_and_holds_no_path(
    tmp_path: Path,
) -> None:
    one = _built(tmp_path / "one")
    first = (one / ".periplus/map.inputs.json").read_bytes()
    _map(one)
    other = _built(tmp_path / "elsewhere" / "two")
    assert (one / ".periplus/map.inputs.json").read_bytes() == first
    assert (other / ".periplus/map.inputs.json").read_bytes() == first
    record = json.loads(first)
    assert sorted(record["files"]) == ["src/a.t", "src/b.t", "src/deep/c.t"]
    assert str(tmp_path) not in first.decode()


def test_the_record_leaves_the_map_bytes_as_they_were(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _built(tmp_path)
    with_record = (root / ".periplus/map.json").read_bytes()
    monkeypatch.setattr(map_module, "write_inputs", lambda *_: ())
    _map(root, Path("plain.json"))
    assert (root / "plain.json").read_bytes() == with_record
    assert not (root / "plain.inputs.json").exists()


def test_a_map_with_no_record_was_built_before_and_exits_34(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / ".periplus/map.inputs.json").unlink()
    report = _fresh(root)
    assert (report.state, report.exit_code, int(report.exit_code)) == (
        "unknown",
        ExitCode.MAP_STALE,
        34,
    )
    text = render_text(report)
    assert "unknown: no inputs record at " in text
    assert "built by a Periplus older than this command" in text
    assert "for the project's map, run periplus map to build it with its record" in text


def test_a_record_of_another_map_is_unknown(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / ".periplus/map.json").write_text("{}\n")
    report = _fresh(root)
    assert (report.state, report.exit_code) == ("unknown", ExitCode.MAP_STALE)
    assert "is of another map" in report.reason


def test_a_map_written_elsewhere_has_its_record_beside_it(tmp_path: Path) -> None:
    root = _built(tmp_path)
    _map(root, Path("out/built.json"))
    assert (root / "out/built.inputs.json").is_file()
    assert _fresh(root, Path(root / "out/built.json")).state == "fresh"


def test_a_slice_file_carries_no_record_and_points_at_the_map_it_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _built(tmp_path)
    monkeypatch.chdir(root)
    assert main(["extract", "own.word::alpha", "--out", "piece.json"]) == 0
    capsys.readouterr()
    assert not (root / "piece.inputs.json").exists()
    report = _fresh(root, Path("piece.json"))
    assert (report.state, report.exit_code) == ("unknown", ExitCode.MAP_STALE)
    assert "a map file that slice --out, extract, join, common or minus wrote" in report.reason
    assert main(["fresh", "--map", "piece.json"]) == 34
    text = capsys.readouterr().out
    assert "unknown: no inputs record at piece.inputs.json" in text
    assert "run periplus fresh on the map it came from" in text


def test_the_json_report_names_the_state_and_each_change(tmp_path: Path) -> None:
    root = _built(tmp_path)
    (root / "src/a.t").write_text("changed\n")
    (root / "src/b.t").unlink()
    document = json.loads(render_json(_fresh(root)))
    assert {key: document[key] for key in ("command", "state", "settings", "files", "packs")} == {
        "command": "fresh",
        "state": "stale",
        "settings": "same",
        "files": {"changed": ["src/a.t"], "added": [], "removed": ["src/b.t"]},
        "packs": {"changed": [], "added": [], "removed": []},
    }
    assert document["tool"] == {"then": document["made_by"], "now": document["made_by"]}


def test_a_map_built_with_a_named_settings_file_is_fresh_against_the_same_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _built(tmp_path)
    plant(root, {"alt.yml": "periplus_version: 0\npacks: [own@0.0.1]\nexclude: ['src/deep/**']\n"})
    env, dependencies = _env(root), check_runtime_dependencies()
    built = run(start=root, env=env, dependencies=dependencies, settings_path=root / "alt.yml")
    assert built.problems == (), built.problems
    record = json.loads((root / ".periplus/map.inputs.json").read_text())
    assert record["settings_file"] == "alt.yml"
    named = fresh(
        start=root,
        env=env,
        dependencies=dependencies,
        map_path=None,
        settings_path=root / "alt.yml",
    )
    assert (named.state, named.exit_code) == ("fresh", ExitCode.OK)
    monkeypatch.chdir(root)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", env["PERIPLUS_CONFIG_DIR"])
    assert main(["fresh", "--settings", "alt.yml"]) == 0
    capsys.readouterr()
    assert main(["fresh"]) == 34
    assert capsys.readouterr().out.splitlines()[2:] == [
        "unknown: the map was built with the settings file alt.yml, and this run read "
        ".periplus/settings.yml",
        "run periplus fresh --settings alt.yml",
    ]


def test_the_record_names_the_default_settings_file_by_its_path_in_the_project(
    tmp_path: Path,
) -> None:
    record = json.loads((_built(tmp_path) / ".periplus/map.inputs.json").read_text())
    assert record["settings_file"] == ".periplus/settings.yml"


SETTINGS_CHANGES = {
    "values": "values: {module: example.com/app}\n",
    "folders": "folders: {src: './src/**'}\n",
    "re_include": "re_include: ['src/none/**']\n",
    "first_party": "first_party: {include: ['src/**']}\n",
    "extensions": "extensions: {.zz: t}\n",
}


@pytest.mark.parametrize("key", sorted(SETTINGS_CHANGES))
def test_a_change_to_each_settings_key_makes_the_map_stale(tmp_path: Path, key: str) -> None:
    root = _built(tmp_path)
    settings = root / ".periplus/settings.yml"
    settings.write_text(settings.read_text() + SETTINGS_CHANGES[key])
    report = _fresh(root)
    assert (report.state, report.settings_changed, report.files) == ("stale", True, ((), (), ()))


def test_pack_paths_give_the_same_record_from_two_places(tmp_path: Path) -> None:
    records = []
    for place in ("one", "elsewhere/two"):
        root = tmp_path / place
        plant(
            root,
            {
                "vendor/packs/own@0.0.1/pack.yaml": MANIFEST,
                "vendor/packs/own@0.0.1/rules/own.yaml": RULES,
                ".periplus/settings.yml": (
                    "periplus_version: 0\npacks: [own@0.0.1]\npack_paths: [vendor/packs]\n"
                ),
                "src/a.t": "alpha\n",
            },
        )
        _map(root)
        records.append((root / ".periplus/map.inputs.json").read_bytes())
    assert records[0] == records[1]
    assert json.loads(records[0])["packs"] == {
        "own@0.0.1": json.loads(records[0])["packs"]["own@0.0.1"]
    }
