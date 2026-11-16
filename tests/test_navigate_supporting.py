"""Nodes in supporting code, by the map's supporting_paths, are folded or printed after the rest.

An invented app; `tests/**` is supporting code.

    RUN -calls-> SEND;  RUN_TEST -calls-> RUN;  SEND_TEST, FAKE -calls-> SEND
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import build_parser
from periplus.navigate import find, show, walk
from periplus.navigate import slice as slicing

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

RUN = "t.method::app.Runner::run"
SEND = "t.method::app.Sender::send"
RUN_TEST = "t.method::app.RunnerTest::testRun"
SEND_TEST = "t.method::app.SenderTest::testSend"
FAKE = "t.method::app.FakeSender::send"

NODES = [
    _node(RUN, "t.method", line=3, file="src/Runner.php"),
    _node(SEND, "t.method", line=5, file="src/Sender.php"),
    _node(RUN_TEST, "t.method", line=4, file="tests/RunnerTest.php"),
    _node(SEND_TEST, "t.method", line=4, file="tests/SenderTest.php"),
    _node(FAKE, "t.method", line=4, file="tests/fixtures/FakeSender.php"),
]
EDGES = [
    _edge("calls", RUN, SEND, 4, file="src/Runner.php"),
    _edge("calls", RUN_TEST, RUN, 5, file="tests/RunnerTest.php"),
    _edge("calls", SEND_TEST, SEND, 5, file="tests/SenderTest.php"),
    _edge("calls", FAKE, SEND, 5, file="tests/fixtures/FakeSender.php"),
]


def _map(root: Path, patterns: bool = True) -> Path:
    document: dict[str, Any] = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    if patterns:
        document["supporting_paths"] = ["tests/**"]
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    path = root / ".periplus" / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _piece(root: Path, *words: str, **kw: Any) -> slicing.SliceReport:
    _map(root, kw.pop("patterns", True))
    args: dict[str, Any] = {
        "prefixes": (),
        "direction": "both",
        "depth": None,
        "kinds": (),
        "limit": None,
        "out": None,
        "map_path": None,
    }
    args.update(kw)
    return slicing.run(root, {}, words, **args)


def _valid(document: Any, name: str) -> list[Any]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": f"#/$defs/{name}"}]})
    return list(validator.iter_errors(document))


def test_a_printed_slice_folds_supporting_code_into_one_count_line(tmp_path: Path) -> None:
    report = _piece(tmp_path, RUN)
    text = slicing.render_text(report)

    assert {row.id for row in report.rows.items} == {SEND}
    assert (
        "+3 in supporting code (tests/**): show with --support, or with the in-full commands at"
        " the end"
    ) in text.splitlines()
    assert "SenderTest" not in text and "FakeSender" not in text


def test_support_prints_supporting_code(tmp_path: Path) -> None:
    report = _piece(tmp_path, RUN, support=True)
    text = slicing.render_text(report)

    assert {RUN_TEST, SEND_TEST, FAKE} <= {row.id for row in report.rows.items}
    assert "in supporting code" not in text


def test_a_map_without_patterns_prints_as_before(tmp_path: Path) -> None:
    report = _piece(tmp_path, RUN, patterns=False)

    assert {RUN_TEST, SEND_TEST, FAKE} <= {row.id for row in report.rows.items}


def test_a_start_is_not_picked_from_supporting_code(tmp_path: Path) -> None:
    starts = [s.row.id for s in _piece(tmp_path, "sender").starts]

    assert starts == [SEND]


def test_a_start_is_picked_from_supporting_code_when_every_match_is_there(tmp_path: Path) -> None:
    assert [s.row.id for s in _piece(tmp_path, "fakesender").starts] == [FAKE]


def test_support_lets_a_start_come_from_supporting_code(tmp_path: Path) -> None:
    starts = [s.row.id for s in _piece(tmp_path, "sender", support=True).starts]

    assert SEND_TEST in starts or FAKE in starts


def test_the_piece_json_counts_supporting_code_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, RUN)))

    assert _valid(document, "slice_piece") == []
    assert document["pieces"][0]["supporting"] == 3


def test_find_marks_supporting_rows_and_sorts_them_last(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "send", (), 0, _map(tmp_path))
    lines = find.render_text(report).splitlines()

    assert [row.id for row in report.matches.items] == [SEND, FAKE, SEND_TEST]
    assert [row.supporting for row in report.matches.items] == [False, True, True]
    assert any(line.startswith(FAKE) and line.endswith("[supporting code]") for line in lines)
    assert _valid(json.loads(find.render_json(report)), "find") == []


def test_show_prints_supporting_edges_last_under_a_heading(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, SEND, 50, _map(tmp_path))
    lines = show.render_text(report).splitlines()

    def at(start: str) -> int:
        return next(n for n, line in enumerate(lines) if line.startswith(start))

    incoming = lines.index("Incoming (3):")
    heading = lines.index("  in supporting code:")
    assert incoming < at(f"    {RUN}  ") < heading < at(f"    {FAKE}  ") < at(f"    {SEND_TEST}  ")
    assert lines[heading + 1] == "  calls:"
    assert _valid(json.loads(show.render_json(report)), "show") == []


def test_affected_prints_supporting_rows_last_under_a_heading(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, SEND, "in", 2, [], 50, _map(tmp_path))
    lines = walk.render_text(report).splitlines()

    assert [row.id for row in report.rows.items] == [RUN, FAKE, SEND_TEST, RUN_TEST]
    assert lines[3] == "  in supporting code:"
    assert _valid(json.loads(walk.render_json(report)), "affected") == []


def test_the_cli_takes_support() -> None:
    assert build_parser().parse_args(["slice", "x", "--support"]).support is True


def test_a_piece_of_one_thing_says_thing(tmp_path: Path) -> None:
    lines = slicing.render_text(_piece(tmp_path, SEND, kinds=("none",))).splitlines()

    assert "piece 1 of 1: 1 thing, starts: Sender::send" in lines
