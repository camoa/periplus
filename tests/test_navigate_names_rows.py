"""Short names that resolve to one id, and the file, line and source line on every row."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node

from periplus.errors import ExitCode
from periplus.navigate import find, path, show, slice, walk

FORM = "php.type::Drupal\\my_module\\Form\\MyForm"
BUILD = "php.method::Drupal\\my_module\\Form\\MyForm::buildForm"
SUBMIT = "php.method::Drupal\\my_module\\Form\\MyForm::submitForm"
OTHER = "php.method::Drupal\\my_module\\Form\\OtherForm::submitForm"
LONG = "php.method::Drupal\\my_module\\Form\\MyForm::long"
HELPER = "php.function::helper"
FILE = "src/Form/MyForm.php"
GONE = "src/Form/OtherForm.php"

LONG_LINE = "    $x = '" + "a" * 200 + "';"
SOURCE = [
    "<?php",
    "",
    "namespace Drupal\\my_module\\Form;",
    "",
    "class MyForm extends FormBase {",
    "",
    "  public function buildForm() {",
    "    $this->submitForm();",
    "    helper();",
    "  }",
    "",
    "  public function submitForm() {",
    "  }",
    *[""] * 6,
    LONG_LINE,
]


def _project(root: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Path:
    """A project root holding ``.periplus/map.json`` and the source file the map points at."""
    (root / ".periplus").mkdir(parents=True)
    (root / "src" / "Form").mkdir(parents=True)
    (root / FILE).write_text("\n".join(SOURCE) + "\n", encoding="utf-8")
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": edges,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


NODES = [
    _node(FORM, "php.type", line=5, file=FILE),
    _node(BUILD, "php.method", line=7, file=FILE),
    _node(SUBMIT, "php.method", line=12, file=FILE),
    _node(OTHER, "php.method", line=3, file=GONE),
    _node(LONG, "php.method", line=20, file=FILE),
    _node(HELPER, "php.function"),
    _node("x::a", line=1, file=FILE),
    _node("y::x::a", line=1, file=FILE),
]
EDGES = [
    _edge("defines", FORM, BUILD, 7, file=FILE),
    _edge("defines", FORM, LONG, 20, file=FILE),
    _edge("defines", FORM, SUBMIT),
    _edge("calls", BUILD, SUBMIT, 8, file=FILE),
    _edge("calls", BUILD, HELPER),
    _edge("calls", OTHER, BUILD, 3, file=GONE),
    _edge("calls", SUBMIT, HELPER, 99, file=FILE),
]


def _site(tmp_path: Path) -> Path:
    return _project(tmp_path, NODES, EDGES)


# --- short names ---------------------------------------------------------------------------


def test_a_unique_short_name_resolves_and_says_so(tmp_path: Path) -> None:
    report = walk.run(_site(tmp_path), {}, "MyForm", "out", 1, [], 50, None)

    assert report.start == FORM
    assert report.problems == ()
    assert report.warnings == (f"resolved 'MyForm' to {FORM}",)
    assert f"warning: resolved 'MyForm' to {FORM}".replace("\\", "\\\\") in walk.render_text(report)
    assert json.loads(walk.render_json(report))["warnings"] == [f"resolved 'MyForm' to {FORM}"]


def test_a_class_and_method_tail_resolves_to_the_method(tmp_path: Path) -> None:
    report = show.run(_site(tmp_path), {}, "MyForm::buildForm", 50, None)

    assert report.id == BUILD
    assert report.warnings == (f"resolved 'MyForm::buildForm' to {BUILD}",)
    assert json.loads(show.render_json(report))["warnings"] == list(report.warnings)


def test_short_names_match_without_regard_to_case(tmp_path: Path) -> None:
    report = path.run(_site(tmp_path), {}, "myform", "HELPER", [], 50, None)

    assert (report.source, report.target) == (FORM, HELPER)
    assert report.problems == ()


def test_a_full_id_wins_over_a_short_name_it_also_is(tmp_path: Path) -> None:
    report = show.run(_site(tmp_path), {}, "x::a", 50, None)

    assert report.id == "x::a"
    assert report.warnings == ()


def test_a_tie_lists_the_candidates_and_walks_nothing(tmp_path: Path) -> None:
    report = walk.run(_site(tmp_path), {}, "submitForm", "in", 1, [], 50, None)

    assert report.exit_code == ExitCode.NODE_NOT_FOUND
    assert report.rows.items == ()
    text = walk.render_text(report)
    assert text.splitlines() == [
        "periplus affected",
        "31 'submitForm' matches 2 nodes; give one of these ids",
        f"  {SUBMIT}  php.method  {FILE}:12".replace("\\", "\\\\"),
        f"  {OTHER}  php.method  {GONE}:3".replace("\\", "\\\\"),
    ]


def test_a_tie_of_more_than_twenty_lists_twenty_and_counts_the_rest(tmp_path: Path) -> None:
    nodes = [_node(f"t::n{i:02}::run", line=1, file=FILE) for i in range(25)]
    report = show.run(_project(tmp_path, nodes, []), {}, "run", 50, None)

    lines = show.render_text(report).splitlines()
    assert lines[1] == "31 'run' matches 25 nodes; give one of these ids"
    assert lines[2:22] == [f"  t::n{i:02}::run  t.x  {FILE}:1" for i in range(20)]
    assert lines[22:] == ["  and 5 more"]


def test_a_tie_is_the_same_bytes_on_every_run(tmp_path: Path) -> None:
    site = _site(tmp_path)
    first = slice.render_json(
        slice.run(site, {}, ["submitForm"], [], "out", 1, [], 0, Path("s.json"), None)
    )
    second = slice.render_json(
        slice.run(site, {}, ["submitForm"], [], "out", 1, [], 0, Path("s.json"), None)
    )

    assert first == second
    assert json.loads(first)["problems"][0]["code"] == ExitCode.NODE_NOT_FOUND


def test_no_match_keeps_the_unknown_id_error_and_hints_at_find(tmp_path: Path) -> None:
    report = show.run(_site(tmp_path), {}, "MyFrom", 50, None)

    assert report.exit_code == ExitCode.NODE_NOT_FOUND
    lines = show.render_text(report).splitlines()
    assert lines[1].startswith("31 no node has the id 'MyFrom'")
    assert lines[2:] == ["  hint: run periplus find MyFrom"]


# --- locations and source lines --------------------------------------------------------------


def _walk_rows(tmp_path: Path, start: str, direction: str) -> dict[str, walk.WalkRow]:
    report = walk.run(_site(tmp_path), {}, start, direction, 1, [], 50, None)
    return {row.id: row for row in report.rows.items}


def test_a_row_takes_the_edge_location_first(tmp_path: Path) -> None:
    row = _walk_rows(tmp_path, BUILD, "out")[SUBMIT]

    assert (row.location, row.source) == (f"{FILE}:8", "$this->submitForm();")


def test_a_row_without_an_edge_location_takes_the_reached_node_location(tmp_path: Path) -> None:
    row = _walk_rows(tmp_path, FORM, "out")[SUBMIT]

    assert (row.location, row.source) == (f"{FILE}:12", "public function submitForm() {")


def test_a_row_with_no_location_at_all_says_so(tmp_path: Path) -> None:
    row = _walk_rows(tmp_path, BUILD, "out")[HELPER]

    assert (row.location, row.source) == (None, None)


def test_a_missing_file_or_a_line_past_the_end_leaves_the_source_out(tmp_path: Path) -> None:
    gone = _walk_rows(tmp_path / "in", BUILD, "in")[OTHER]
    past = _walk_rows(tmp_path / "out", SUBMIT, "out")[HELPER]

    assert (gone.location, gone.source) == (f"{GONE}:3", None)
    assert (past.location, past.source) == (f"{FILE}:99", None)


def test_a_long_source_line_is_cut_to_160_characters(tmp_path: Path) -> None:
    row = _walk_rows(tmp_path, FORM, "out")[LONG]

    assert row.source == LONG_LINE.strip()[:160]


def test_the_walk_row_text_and_json_carry_location_and_source(tmp_path: Path) -> None:
    report = walk.run(_site(tmp_path), {}, BUILD, "in", 1, [], 50, None)

    lines = walk.render_text(report).splitlines()
    escaped = OTHER.replace("\\", "\\\\")
    built = BUILD.replace("\\", "\\\\")
    assert lines[2:] == [
        f"  1  {escaped}  php.method  mapped  via calls to {built}  {GONE}:3",
        f"  1  {FORM.replace(chr(92), chr(92) * 2)}  php.type  mapped  via defines to {built}"
        f"  {FILE}:7",
        "      | public function buildForm() {",
    ]
    rows = json.loads(walk.render_json(report))["rows"]["items"]
    assert [(r["location"], r["source"]) for r in rows] == [
        (f"{GONE}:3", None),
        (f"{FILE}:7", "public function buildForm() {"),
    ]


def test_show_edge_rows_carry_the_source_line(tmp_path: Path) -> None:
    report = show.run(_site(tmp_path), {}, FORM, 50, None)

    lines = show.render_text(report).splitlines()
    at = lines.index(
        f"    {SUBMIT.replace(chr(92), chr(92) * 2)}  php.method  mapped  {FILE}:12"
        "  x2  inferred  php:r"
    )
    assert lines[at + 1] == "      | public function submitForm() {"
    outgoing = json.loads(show.render_json(report))["outgoing"]["items"]
    assert [(r["location"], r["source"]) for r in outgoing] == [
        (f"{FILE}:7", "public function buildForm() {"),
        (f"{FILE}:20", LONG_LINE.strip()[:160]),
        (f"{FILE}:12", "public function submitForm() {"),
    ]


def test_show_says_no_location_when_neither_end_has_one(tmp_path: Path) -> None:
    report = show.run(_site(tmp_path), {}, BUILD, 50, None)

    lines = show.render_text(report).splitlines()
    helper = next(line for line in lines if line.startswith(f"    {HELPER}"))
    assert helper.startswith(f"    {HELPER}  php.function  mapped  no location")


def test_path_steps_carry_location_and_source(tmp_path: Path) -> None:
    report = path.run(_site(tmp_path), {}, FORM, BUILD, [], 50, None)

    lines = path.render_text(report).splitlines()
    assert lines[-2].endswith(f"  {FILE}:7")
    assert lines[-1] == "      | public function buildForm() {"
    step = json.loads(path.render_json(report))["chains"]["items"][0][0]
    assert (step["location"], step["source"]) == (f"{FILE}:7", "public function buildForm() {")


def test_find_rows_carry_the_declaration_line(tmp_path: Path) -> None:
    report = find.run(_site(tmp_path), {}, "MyForm", (), 1, None)

    lines = find.render_text(report).splitlines()
    assert lines[2].endswith(f"  {FILE}:5")
    assert lines[3] == "      | class MyForm extends FormBase {"
    item = json.loads(find.render_json(report))["items"][0]
    assert item["source"] == "class MyForm extends FormBase {"


def test_a_map_given_by_path_reads_source_under_its_project(tmp_path: Path) -> None:
    site = _site(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    report = find.run(elsewhere, {}, "MyForm", (), 1, site / ".periplus" / "map.json")

    assert report.matches.items[0].source == "class MyForm extends FormBase {"


# --- the affected header ---------------------------------------------------------------------


def test_affected_on_an_unknown_id_prints_its_own_header(tmp_path: Path) -> None:
    report = walk.run(_site(tmp_path), {}, "nothing_like_it", "in", 1, [], 50, None)

    assert walk.render_text(report).splitlines()[0] == "periplus affected"
