"""A map run that selects no file says so at the top; a whole run that selects none fails.

The fault: a project whose pack looked in folders that do not exist wrote a map of 0 nodes and
0 edges, printed its normal report and exited 0. A neutral pack stands in for any stack.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant, rutter

from periplus.errors import ExitCode
from periplus.map import MapReport, render_json, render_text, run
from periplus.preflight import check_runtime_dependencies


def _manifest(name: str, folders: str) -> str:
    return (
        f"pack: {name}\nversion: 0.0.1\ndepends: []\nfolders:\n{folders}"
        "files:\n  types:\n    note:\n      endings: [note]\n      reader: data\n"
        "      format: yaml\n"
    )


def _rules(name: str, folder: str) -> dict[str, str]:
    return {
        f"{name}.yaml": (
            f"node_types:\n- {{name: {name}.item, id_namespace: {name}.item}}\nrules:\n"
            f"- rule: item\n  reads: file\n  in: [{folder}]\n"
            "  match: {file: '*', filetype: note}\n  id: {template: '{file_stem}'}\n"
            f"  emits: [{{node: {{type: {name}.item}}}}]\n  confidence: declared\n"
        )
    }


def _two_packs(root: Path, notes: dict[str, str]) -> None:
    """`alpha` reads `lib`, `beta` reads `{base}/notes` with `base` at `./src`; both pinned."""
    rutter(root, "alpha", _manifest("alpha", "  lib: ./lib\n"), _rules("alpha", "lib"))
    rutter(
        root,
        "beta",
        _manifest("beta", "  base: ./src\n  deep: '{base}/notes'\n"),
        _rules("beta", "deep"),
    )
    plant(
        root,
        {
            ".periplus/settings.yml": (
                "periplus_version: 0\npacks: [alpha@0.0.1, beta@0.0.1]\n"
            ),
            **notes,
        },
    )


def _map(root: Path) -> MapReport:
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
    )


def test_a_run_that_selects_no_file_exits_nothing_selected(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"elsewhere/one.note": "a: 1\n"})

    report = _map(tmp_path)

    assert report.exit_code == ExitCode.NOTHING_SELECTED
    assert [p.code for p in report.problems] == [ExitCode.NOTHING_SELECTED]


def test_a_run_that_selects_no_file_writes_no_map_and_keeps_the_old_one(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"elsewhere/one.note": "a: 1\n"})
    old = tmp_path / ".periplus" / "map.json"
    old.write_text('{"kept": true}\n')

    report = _map(tmp_path)

    assert report.map_path is None
    assert old.read_text() == '{"kept": true}\n'


def test_a_pack_that_selects_no_file_names_the_base_folder_and_its_value(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.note": "a: 1\n"})

    report = _map(tmp_path)

    assert report.exit_code == ExitCode.OK
    assert report.empty_packs == (("beta", (("base", "./src", 0),)),)


def test_a_pack_that_selects_files_is_not_listed(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.note": "a: 1\n", "src/notes/two.note": "b: 2\n"})

    report = _map(tmp_path)

    assert report.empty_packs == ()
    assert report.nodes == 2


def test_the_empty_pack_warning_is_printed_above_the_map_section(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.note": "a: 1\n"})

    text = render_text(_map(tmp_path))

    assert text.index("Packs that selected no file:") < text.index("\nMap:")
    assert (
        "  beta: base = ./src, no such folder; if the code is elsewhere, declare the folder "
        "under folders in .periplus/settings.yml\n"
    ) in text


def test_a_found_folder_with_no_file_the_pack_reads_is_not_called_elsewhere(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.note": "a: 1\n", "src/readme.txt": "x\n"})

    text = render_text(_map(tmp_path))

    assert (
        "  beta: base = ./src, 1 folder found; it holds no file the rules of beta read\n"
    ) in text
    assert "elsewhere" not in text


def test_the_whole_run_message_says_nothing_was_selected_and_no_map_written(
    tmp_path: Path,
) -> None:
    _two_packs(tmp_path, {"elsewhere/one.note": "a: 1\n"})

    report = _map(tmp_path)

    assert report.problems[0].message == (
        "no file was selected, so no map was written and any existing map was left as it was: "
        "every pinned pack looked only in folders that hold none of its files; declare where the "
        "code is under folders in .periplus/settings.yml"
    )
    text = render_text(report)
    assert text.index("Packs that selected no file:") < text.index("\nMap:")
    assert "  alpha: lib = ./lib, no such folder;" in text


def test_the_json_report_lists_each_empty_pack_with_its_folders(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.note": "a: 1\n"})

    payload = json.loads(render_json(_map(tmp_path)))

    assert payload["empty_packs"] == [
        {"pack": "beta", "folders": [{"folder": "base", "value": "./src", "found": 0}]}
    ]


def test_a_run_that_selects_no_file_still_lists_the_files_no_rule_read(tmp_path: Path) -> None:
    _two_packs(tmp_path, {"lib/one.txt": "a\n"})

    report = _map(tmp_path)

    assert report.exit_code == ExitCode.NOTHING_SELECTED
    assert report.unread == ("lib/one.txt",)
