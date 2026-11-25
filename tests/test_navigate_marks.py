"""A node that holds an attribute the map's ``marks`` header names prints that mark on its rows.

An invented shop: a module left out of the install, a function in it, a caller outside it, and a
test in supporting code. The module and everything in it hold ``installed``.

    GO -calls-> RUN -in_module-> SHOP;  CHECK -calls-> RUN
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import build_parser
from periplus.map import run
from periplus.navigate import find, path, show, walk
from periplus.navigate import slice as slicing
from periplus.navigate.mapfile import MapIndex
from periplus.preflight import check_runtime_dependencies

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

SHOP = "t.module::shop"
RUN = "t.function::shop_run"
GO = "t.function::core_go"
CHECK = "t.function::shop_check"
OFF = {"installed": "no"}

NODES = [
    _node(SHOP, "t.module", line=1, file="mods/shop/shop.info", attributes=OFF),
    _node(RUN, "t.function", line=3, file="mods/shop/shop.php", attributes=OFF),
    _node(GO, "t.function", line=2, file="core/go.php"),
    _node(
        CHECK,
        "t.function",
        line=4,
        file="tests/ShopTest.php",
        attributes={**OFF, "title": "stock checker"},
    ),
]
EDGES = [
    _edge("calls", GO, RUN, 3, file="core/go.php"),
    _edge("in_module", RUN, SHOP, 3, file="mods/shop/shop.php"),
    _edge("calls", CHECK, RUN, 5, file="tests/ShopTest.php"),
]
MARK = "  [not installed]"


def _document(marks: bool = True) -> dict[str, Any]:
    document: dict[str, Any] = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
        "supporting_paths": ["tests/**"],
    }
    if marks:
        document["marks"] = {"installed": "not installed"}
    return document


def _map(root: Path, marks: bool = True) -> Path:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    target = root / ".periplus" / "map.json"
    target.write_text(json.dumps(_document(marks)), encoding="utf-8")
    return target


def _valid(document: Any, name: str) -> list[Any]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": f"#/$defs/{name}"}]})
    return list(validator.iter_errors(document))


def _line(text: str, start: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(start))


def _piece(root: Path, *ids: str) -> slicing.SliceReport:
    return slicing.run(root, {}, ids, (), "both", None, (), None, None, _map(root))


def test_marks_are_the_mark_of_each_held_attribute_in_attribute_name_order() -> None:
    document = _document()
    document["marks"] = {"zeta": "z mark", "alpha": "a mark"}
    document["nodes"] = [_node(RUN, attributes={"zeta": 1, "alpha": "x", "other": "y"})]
    document["edges"] = []

    assert MapIndex(document).marks(RUN) == ("a mark", "z mark")


def test_a_map_without_marks_gives_none_and_loads_unchanged(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "shop_run", (), 0, _map(tmp_path, marks=False))

    assert report.problems == ()
    assert [row.marks for row in report.matches.items] == [()]
    assert MARK not in find.render_text(report)


def test_find_prints_the_mark_after_the_match_and_before_supporting_code(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "checker", (), 0, _map(tmp_path))

    assert _line(find.render_text(report), CHECK).endswith(
        "[attribute title]  [not installed]  [supporting code]"
    )


def test_find_json_rows_carry_marks_always(tmp_path: Path) -> None:
    document = json.loads(find.render_json(find.run(tmp_path, {}, "shop", (), 0, _map(tmp_path))))

    assert {row["id"]: row["marks"] for row in document["items"]} == {
        SHOP: ["not installed"],
        RUN: ["not installed"],
        CHECK: ["not installed"],
    }
    assert _valid(document, "find") == []


def test_find_mark_keeps_only_nodes_that_carry_the_mark(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "", (), 0, _map(tmp_path), marks=["not installed"])

    assert {row.id for row in report.matches.items} == {SHOP, RUN, CHECK}


def test_find_mark_no_node_carries_warns_with_the_marks_the_map_holds(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "", (), 0, _map(tmp_path), marks=["uninstalled"])

    assert report.matches.items == ()
    assert report.warnings == (
        "no node carries the mark 'uninstalled'; the map's marks: not installed",
    )


def test_find_takes_mark_without_a_text() -> None:
    args = build_parser().parse_args(["find", "--mark", "not installed", "--mark", "other"])

    assert (args.text, args.mark) == ([], ["not installed", "other"])


def test_show_prints_the_mark_on_the_node_header(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, SHOP, 50, _map(tmp_path))

    assert show.render_text(report).splitlines()[0] == f"periplus show {SHOP}{MARK}"
    assert json.loads(show.render_json(report))["marks"] == ["not installed"]


def test_show_prints_the_other_end_mark_on_an_edge_row(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, GO, 50, _map(tmp_path))
    document = json.loads(show.render_json(report))

    assert _line(show.render_text(report), f"    {RUN}  ").endswith(MARK)
    assert [row["other_marks"] for row in document["outgoing"]["items"]] == [["not installed"]]
    assert _valid(document, "show") == []


def test_neighbors_prints_the_mark_on_a_reached_row(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, GO, "out", 2, (), 0, _map(tmp_path))
    document = json.loads(walk.render_json(report))

    assert _line(walk.render_text(report), f"  1  {RUN}  ").endswith(MARK)
    assert {row["id"]: row["marks"] for row in document["rows"]["items"]} == {
        RUN: ["not installed"],
        SHOP: ["not installed"],
    }
    assert _valid(document, "neighbors") == []


def test_affected_prints_the_mark_on_a_reached_row(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, SHOP, "in", 1, (), 0, _map(tmp_path))

    assert _line(walk.render_text(report), f"  1  {RUN}  ").endswith(MARK)


def test_path_prints_the_mark_at_both_ends_of_a_step(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, GO, SHOP, (), 0, _map(tmp_path))
    text = path.render_text(report)
    document = json.loads(path.render_json(report))

    assert _line(text, f"    {GO} --calls--> {RUN}{MARK}  ")
    assert _line(text, f"    {RUN}{MARK} --in_module--> {SHOP}{MARK}  ")
    steps = document["chains"]["items"][0]
    assert [(s["from_marks"], s["to_marks"]) for s in steps] == [
        ([], ["not installed"]),
        (["not installed"], ["not installed"]),
    ]
    assert _valid(document, "path") == []


def test_slice_prints_the_mark_on_the_node_line(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, GO))

    assert _line(text, "  :3  shop_run  t.function").endswith(MARK)


def test_slice_json_rows_and_starts_carry_marks(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, RUN)))

    assert [s["marks"] for s in document["starts"]] == [["not installed"]]
    assert {r["id"]: r["marks"] for r in document["rows"]["items"]} == {
        GO: [],
        SHOP: ["not installed"],
    }
    assert _valid(document, "slice_piece") == []


def test_slice_prints_the_mark_on_a_start_line(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, RUN))

    assert _line(text, "start shop_run  t.function").endswith(MARK)


def test_a_function_in_a_drupal_module_core_extension_does_not_list_carries_the_mark(
    tmp_path: Path,
) -> None:
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    for name in ("shop", "stock"):
        module = tmp_path / "web" / "modules" / "custom" / name
        module.mkdir(parents=True)
        (module / f"{name}.info.yml").write_text(f"name: {name}\ntype: module\n")
        (module / f"{name}.module").write_text(f"<?php\n\nfunction {name}_run() {{\n}}\n")
        (module / "src").mkdir()
        (module / "src" / "Crate.php").write_text(
            f"<?php\n\nnamespace Drupal\\{name};\n\n"
            "class Crate {\n  public function open() {\n  }\n}\n"
        )
    (tmp_path / "config" / "sync").mkdir(parents=True)
    (tmp_path / "config" / "sync" / "core.extension.yml").write_text("module:\n  shop: 0\n")
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "_config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.map_path is not None, report.problems
    index = MapIndex(json.loads(Path(report.map_path).read_text(encoding="utf-8")))

    # run is no hook any source names, so both helpers also carry hook_known's mark.
    assert index.marks("php.function::stock_run") == ("hook by name only", "not installed")
    assert index.marks("php.function::shop_run") == ("hook by name only",)
    assert index.marks("php.method::Drupal\\stock\\Crate::open") == ("not installed",)
