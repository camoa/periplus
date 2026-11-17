"""An edge that holds attributes prints them on its row, and find matches an edge by one.

An invented form: a builder registers two callables under keys, one under two keys at two places.

    BUILD -registers-> SHAPE  [key: #shape]
    BUILD -registers-> CHECK  [key: #check, #fix]
    BUILD -calls-> PLAIN
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.navigate import diff, find, path, sets, show, walk
from periplus.navigate import slice as slicing

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

BUILD = "t.method::Form::build"
SHAPE = "t.method::Form::shape"
CHECK = "t.method::Form::check"
PLAIN = "t.method::Form::plain"
FILE = "src/Form.php"
DIFFERS = {
    "differs": [
        {"file": FILE, "line": 4, "value": "#check"},
        {"file": FILE, "line": 6, "value": "#fix"},
    ]
}


def _registers(target: str, line: int, attributes: Any) -> dict[str, Any]:
    return {**_edge("registers", BUILD, target, line, file=FILE), "attributes": attributes}


def _doc(causes: bool = True, key: str = "#shape") -> dict[str, Any]:
    ids = sorted({BUILD, SHAPE, CHECK, PLAIN})
    nodes = [_node(n, "t.method", line=i + 1, file=FILE) for i, n in enumerate(ids)]
    edges = [
        _registers(SHAPE, 3, {"key": key}),
        _registers(CHECK, 4, {"key": DIFFERS}),
        _edge("calls", BUILD, PLAIN, 5, file=FILE),
    ]
    flow = {"from": ["calls", "registers"]} if causes else None
    return _document(nodes, edges, flow)


def _map(root: Path, name: str = "map.json", **given: Any) -> Path:
    target = root / name
    target.write_text(json.dumps(_doc(**given)), encoding="utf-8")
    return target


def _line(text: str, part: str) -> str:
    return next(line for line in text.splitlines() if part in line)


def _valid(document: Any, name: str) -> list[Any]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": f"#/$defs/{name}"}]})
    return list(validator.iter_errors(document))


def test_show_prints_the_attributes_on_the_edge_row(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, BUILD, 50, _map(tmp_path))
    text = show.render_text(report)
    document = json.loads(show.render_json(report))

    assert _line(text, f"    {SHAPE}  ").endswith(" [key: #shape]")
    assert _line(text, f"    {CHECK}  ").endswith(" [key: #check, #fix]")
    assert "[" not in _line(text, f"    {PLAIN}  ")
    rows = {row["other"]: row["attributes"] for row in document["outgoing"]["items"]}
    assert rows == {SHAPE: {"key": "#shape"}, CHECK: {"key": DIFFERS}, PLAIN: {}}
    assert _valid(document, "show") == []


def test_find_matches_an_edge_by_an_attribute_value(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "#fix", (), 0, _map(tmp_path))
    document = json.loads(find.render_json(report))

    assert [(e.target, e.matched, e.matched_attribute) for e in report.edges] == [
        (CHECK, "attribute", "key")
    ]
    assert _line(find.render_text(report), "  registers") == (
        f"  registers [key: #check, #fix]  build -> check  {FILE}:4  [attribute key]"
    )
    (edge,) = document["edges"]
    assert (edge["matched"], edge["matched_attribute"], edge["attributes"]) == (
        "attribute",
        "key",
        {"key": DIFFERS},
    )
    assert _valid(document, "find") == []


def test_find_matches_no_edge_whose_attributes_lack_the_words(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "#nothing", (), 0, _map(tmp_path))

    assert report.edges == ()


def test_neighbors_prints_the_attributes_after_the_kind(tmp_path: Path) -> None:
    report = walk.run_cause(tmp_path, {}, [BUILD], "off", 1, (), 0, _map(tmp_path), full=True)
    document = json.loads(walk.render_json(report))

    assert f"{SHAPE}  t.method  mapped  registers [key: #shape]  " in walk.render_text(report)
    rows = {row["id"]: row["via_attributes"] for row in document["rows"]}
    assert rows == {SHAPE: {"key": "#shape"}, CHECK: {"key": DIFFERS}, PLAIN: {}}
    assert _valid(document, "neighbors") == []


def test_affected_prints_the_attributes_after_the_kind_and_rev(tmp_path: Path) -> None:
    report = walk.run_cause(tmp_path, {}, [CHECK], "by", 1, (), 0, _map(tmp_path), full=True)

    assert "registers (rev) [key: #check, #fix]  " in walk.render_text(report)


def test_the_raw_walk_prints_the_attributes_after_the_kind(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, BUILD, "out", 1, (), 0, _map(tmp_path, causes=False))
    document = json.loads(walk.render_json(report))

    assert f"via registers [key: #shape] from {BUILD}" in walk.render_text(report)
    rows = {row["id"]: row["attributes"] for row in document["rows"]["items"]}
    assert rows[SHAPE] == {"key": "#shape"} and rows[PLAIN] == {}
    assert _valid(document, "neighbors") == []


def test_slice_tags_each_linked_name_and_carries_the_attributes(tmp_path: Path) -> None:
    report = slicing.run(tmp_path, {}, [BUILD], (), "both", None, (), None, None, _map(tmp_path))
    document = json.loads(slicing.render_json(report))

    assert _line(slicing.render_text(report), "registers ->").strip() == (
        "registers -> check [key: #check, #fix], shape [key: #shape]"
    )
    rows = {row["id"]: row["attributes"] for row in document["rows"]["items"]}
    assert rows == {SHAPE: {"key": "#shape"}, CHECK: {"key": DIFFERS}, PLAIN: {}}
    assert _valid(document, "slice_piece") == []


def test_diff_names_a_changed_attribute_and_join_counts_the_copies(tmp_path: Path) -> None:
    old, new = _map(tmp_path, "old.json"), _map(tmp_path, "new.json", key="#round")

    changed = diff.run(tmp_path, {}, old, new).edges
    assert changed is not None
    assert [(r.target, r.fields) for r in changed["changed"].items] == [(SHAPE, ("attributes",))]
    joined = sets.run(tmp_path, {}, "join", [old, new], None)
    assert joined.warnings and "0 things and 1 edge differ" in joined.warnings[0]
    assert sets.run(tmp_path, {}, "common", [old, old], None).warnings == ()


def test_path_prints_the_attributes_inside_the_step_arrow(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, BUILD, CHECK, (), 0, _map(tmp_path))
    document = json.loads(path.render_json(report))

    assert _line(path.render_text(report), "-->").startswith(
        f"    {BUILD} --registers [key: #check, #fix]--> {CHECK}  "
    )
    (step,) = document["chains"]["items"][0]
    assert step["attributes"] == {"key": DIFFERS}
    assert json.loads(path.render_json(path.run(tmp_path, {}, BUILD, PLAIN, (), 0, _map(tmp_path))))[
        "chains"
    ]["items"][0][0]["attributes"] == {}
    assert _valid(document, "path") == []
