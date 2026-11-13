"""``periplus find`` narrowing: several types, type hints, path prefixes, the cut footer, and
matches and rows from the descriptions file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import find, path, walk
from periplus.navigate.listing import cut
from periplus.navigate.source import description_line

DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "php.symbol", "parent": None},
        {"type": "php.class", "parent": "php.symbol"},
        {"type": "php.method", "parent": "php.symbol"},
        {"type": "yaml.key", "parent": None},
    ],
    "nodes": [
        _node("php.type::my_module.MyForm", "php.class", line=1, file="src/Form/MyForm.php"),
        _node("php.method::MyForm::build", "php.method", line=3, file="src/Form/MyForm.php"),
        _node("php.method::MyForm::submit", "php.method", line=7, file="src/Form/MyForm.php"),
        _node("php.method::Helper::run", "php.method", line=2, file="lib/Helper.php"),
        _node("yaml.key::my_module.form", "yaml.key", line=1, file="./config/routes.yml"),
        _node("yaml.key::my_module.claim", "yaml.key", line=4, file="config/routes.yml"),
    ],
    "edges": [
        _edge(
            "calls",
            "php.method::Helper::run",
            "php.method::MyForm::submit",
            2,
            file="lib/Helper.php",
        ),
    ],
}

DESCRIPTIONS = """\
nodes:
  php.method::Helper::run:
    text: |
      Files the Claim for the user.
      Second line is not shown.
    file: lib/Helper.php
    line: 2
  php.method::MyForm::submit:
    text: Saves the form values.
    file: src/Form/MyForm.php
    line: 7
"""


def _map(root: Path, descriptions: str | None = DESCRIPTIONS) -> Path:
    map_path = root / "map.json"
    map_path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    if descriptions is not None:
        (root / "descriptions.yaml").write_text(descriptions, encoding="utf-8")
    return map_path


def _ids(report: find.FindReport) -> list[str]:
    return [row.id for row in report.matches.items]


def _find(
    root: Path,
    text: str,
    *types: str,
    limit: int = 50,
    paths: tuple[str, ...] = (),
    descriptions: str | None = DESCRIPTIONS,
) -> find.FindReport:
    return find.run(root, {}, text, types, limit, _map(root, descriptions), paths)


# 1. --type repeatable


def test_two_types_keep_nodes_of_either(tmp_path: Path) -> None:
    report = _find(tmp_path, "my", "php.class", "yaml.key")

    assert _ids(report) == [
        "php.type::my_module.MyForm",
        "yaml.key::my_module.claim",
        "yaml.key::my_module.form",
    ]
    assert report.warnings == ()


def test_each_unknown_type_gets_one_warning(tmp_path: Path) -> None:
    report = _find(tmp_path, "my", "php.class", "nope.a", "nope.b")

    assert _ids(report) == ["php.type::my_module.MyForm"]
    assert [w.split(";")[0] for w in report.warnings] == [
        "no type named 'nope.a' is in the map",
        "no type named 'nope.b' is in the map",
    ]


# 2. hint for a wrong type name


def test_an_id_prefix_used_as_a_type_suggests_the_types_under_it(tmp_path: Path) -> None:
    report = _find(tmp_path, "my", "php.type")

    assert report.matches.total == 0
    (warning,) = report.warnings
    assert warning.startswith("no type named 'php.type' is in the map")
    assert warning.endswith("did you mean: php.class")


def test_a_part_of_a_type_name_suggests_the_types_holding_it(tmp_path: Path) -> None:
    (warning,) = _find(tmp_path, "my", "PHP").warnings

    assert warning.endswith("did you mean: php.class, php.method")


def test_a_type_name_holding_a_held_type_suggests_it(tmp_path: Path) -> None:
    (warning,) = _find(tmp_path, "my", "php.classes").warnings

    assert warning.endswith("did you mean: php.class")


def test_a_type_name_with_nothing_near_gives_no_suggestion(tmp_path: Path) -> None:
    (warning,) = _find(tmp_path, "my", "zzz").warnings

    assert "did you mean" not in warning


# 3. --path


def test_path_keeps_nodes_whose_file_starts_with_the_prefix(tmp_path: Path) -> None:
    assert _ids(_find(tmp_path, "my", paths=("src/Form",))) == [
        "php.type::my_module.MyForm",
        "php.method::MyForm::build",
        "php.method::MyForm::submit",
    ]
    assert _ids(_find(tmp_path, "my_module", paths=("./config/",))) == [
        "yaml.key::my_module.claim",
        "yaml.key::my_module.form",
    ]


def test_several_paths_keep_a_node_matching_any(tmp_path: Path) -> None:
    report = _find(tmp_path, "run", paths=("lib", "src"))

    assert _ids(report) == ["php.method::Helper::run"]
    assert report.warnings == ()


def test_a_path_matching_no_file_warns(tmp_path: Path) -> None:
    report = _find(tmp_path, "my", paths=("src/Form", "web/"))

    assert len(_ids(report)) == 3
    assert report.warnings == ("no file in the map starts with 'web/'",)


# 4. the cut footer


def test_a_cut_list_counts_matches_by_type_and_says_how_to_narrow(tmp_path: Path) -> None:
    report = _find(tmp_path, "my", limit=2)
    text = find.render_text(report)

    assert report.by_type == {"php.class": 1, "php.method": 2, "yaml.key": 2}
    assert text.splitlines()[-3:] == [
        "showing 2 of 5",
        "by type: php.method 2, yaml.key 2, php.class 1",
        "narrow with --type T or --path P",
    ]
    assert json.loads(find.render_json(report))["by_type"] == report.by_type


def test_the_footer_names_at_most_eight_types() -> None:
    report = find.FindReport(
        cut([find.FindRow("a", "t", "mapped", None)] * 3, 1),
        by_type={f"t{n}": 1 for n in range(10)},
    )

    assert "by type: t0 1, t1 1, t2 1, t3 1, t4 1, t5 1, t6 1, t7 1, and 2 more types" in (
        find.render_text(report)
    )


def test_an_uncut_list_has_no_footer_but_json_has_by_type(tmp_path: Path) -> None:
    report = _find(tmp_path, "my")
    text = find.render_text(report)

    assert "by type" not in text
    assert "narrow with" not in text
    assert json.loads(find.render_json(report))["by_type"] == {
        "php.class": 1,
        "php.method": 2,
        "yaml.key": 2,
    }


# 5. descriptions


def test_a_description_only_match_ranks_after_every_id_match(tmp_path: Path) -> None:
    report = _find(tmp_path, "CLAIM")

    assert _ids(report) == ["yaml.key::my_module.claim", "php.method::Helper::run"]
    assert [row.matched for row in report.matches.items] == ["id", "description"]
    text = find.render_text(report)
    assert "php.method::Helper::run  php.method  mapped  lib/Helper.php:2  [description]" in text
    assert "yaml.key::my_module.claim  yaml.key  mapped  config/routes.yml:4\n" in text
    rows = json.loads(find.render_json(report))["items"]
    assert [row["matched"] for row in rows] == ["id", "description"]


def test_a_description_matches_as_one_phrase(tmp_path: Path) -> None:
    assert _ids(_find(tmp_path, "the claim")) == ["php.method::Helper::run"]
    assert _ids(_find(tmp_path, "claim the")) == []


def test_a_find_row_prints_its_description_first_line(tmp_path: Path) -> None:
    report = _find(tmp_path, "submit")
    text = find.render_text(report)

    assert report.matches.items[0].description == "Saves the form values."
    assert "      # Saves the form values.\n" in text
    rows = json.loads(find.render_json(report))["items"]
    assert rows[0]["description"] == "Saves the form values."
    assert rows[0]["matched"] == "id"


def test_no_descriptions_file_matches_ids_only(tmp_path: Path) -> None:
    report = _find(tmp_path, "claim", descriptions=None)

    assert _ids(report) == ["yaml.key::my_module.claim"]
    assert report.problems == ()
    assert json.loads(find.render_json(report))["items"][0]["description"] is None


def test_a_damaged_descriptions_file_is_a_problem_as_in_show(tmp_path: Path) -> None:
    report = _find(tmp_path, "claim", descriptions="nodes: [")

    assert _ids(report) == ["yaml.key::my_module.claim"]
    assert report.exit_code is ExitCode.NOT_A_MAP


def test_a_walk_row_prints_the_description_after_the_source_line(tmp_path: Path) -> None:
    map_path = _map(tmp_path)
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "Helper.php").write_text("<?php\n  $form->submit();\n", encoding="utf-8")
    report = walk.run(tmp_path, {}, "php.method::MyForm::submit", "in", 1, (), 50, map_path)
    lines = walk.render_text(report).splitlines()

    at = lines.index("      | $form->submit();")
    assert lines[at + 1] == "      # Files the Claim for the user."
    full = "Files the Claim for the user.\nSecond line is not shown.\n"
    assert report.rows.items[0].description == full
    assert json.loads(walk.render_json(report))["rows"]["items"][0]["description"] == full


def test_a_path_step_prints_the_reached_node_description(tmp_path: Path) -> None:
    map_path = _map(tmp_path)
    report = path.run(
        tmp_path, {}, "php.method::Helper::run", "php.method::MyForm::submit", (), 50, map_path
    )

    assert "      # Saves the form values." in path.render_text(report).splitlines()
    chain = json.loads(path.render_json(report))["chains"]["items"][0]
    assert chain[0]["description"] == "Saves the form values."


def test_a_description_line_is_cut_and_escaped() -> None:
    assert description_line(None) == []
    assert description_line("  " + "x" * 200 + "\nmore") == ["      # " + "x" * 160]
    assert description_line("a\tb") == ["      # a\\tb"]


def test_main_takes_repeated_type_and_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    map_path = _map(tmp_path)
    monkeypatch.chdir(tmp_path)
    argv = [
        "find",
        "my",
        "--type",
        "php.class",
        "--type",
        "yaml.key",
        "--path",
        "config",
        "--path",
        "src",
        "--map",
        str(map_path),
        "--format",
        "json",
    ]

    assert main(argv) == 0
    first = capsys.readouterr().out
    assert main(argv) == 0
    assert capsys.readouterr().out == first
    assert [row["id"] for row in json.loads(first)["items"]] == [
        "php.type::my_module.MyForm",
        "yaml.key::my_module.claim",
        "yaml.key::my_module.form",
    ]
