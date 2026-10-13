"""``periplus show``: grouping by kind, the other end, the cut, the unknown id and the CLI tie."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import show


def _prov(confidence: str, rule: str = "r") -> dict[str, Any]:
    return {"pack": "php", "rule": rule, "confidence": confidence, "sets": []}


def _node(id: str, type: str, state: str = "mapped", **extra: Any) -> dict[str, Any]:
    where = [{"file": "src/a.php", "line": 3}] if state == "mapped" else []
    return {
        "id": id,
        "type": type,
        "state": state,
        "locations": where,
        "provenance": [_prov("declared")],
        **extra,
    }


def _edge(kind: str, source: str, target: str, line: int, *prov: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": [{"file": "src/a.php", "line": line}],
        "provenance": list(prov) or [_prov("inferred")],
        "occurrences": 2,
    }


DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "nodes": [
        _node(
            "php.method::A::go", "php.method", roles=["entry"], attributes={"visibility": "public"}
        ),
        _node("php.method::B::run", "php.method"),
        _node("php.method::C::run", "php.method", "referenced"),
        _node("php.type::A", "php.type"),
    ],
    "edges": [
        _edge("calls", "php.method::A::go", "php.method::C::run", 9, _prov("inferred", "x")),
        _edge(
            "calls",
            "php.method::A::go",
            "php.method::B::run",
            7,
            _prov("declared", "y"),
            _prov("inferred", "x"),
        ),
        _edge("defines", "php.type::A", "php.method::A::go", 1),
        _edge("calls", "php.method::B::run", "php.method::A::go", 4),
    ],
}


def _map(root: Path) -> Path:
    path = root / "map.json"
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    return path


def test_the_node_is_shown_with_its_roles_attributes_and_provenance(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 50, _map(tmp_path))

    assert (report.id, report.type, report.state) == ("php.method::A::go", "php.method", "mapped")
    assert report.roles == ("entry",)
    assert report.attributes == {"visibility": "public"}
    assert report.locations == ({"file": "src/a.php", "line": 3},)
    assert report.provenance[0]["rule"] == "r"
    assert report.exit_code is ExitCode.OK


def test_outgoing_edges_are_grouped_by_kind_then_other_end(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 50, _map(tmp_path))

    assert [(r["kind"], r["other"]) for r in report.outgoing.items] == [
        ("calls", "php.method::B::run"),
        ("calls", "php.method::C::run"),
    ]
    first = report.outgoing.items[0]
    assert first["other_type"] == "php.method"
    assert first["other_state"] == "mapped"
    assert first["locations"] == [{"file": "src/a.php", "line": 7}]
    assert first["occurrences"] == 2
    assert first["confidences"] == ["declared", "inferred"]
    assert first["rules"] == ["php:x", "php:y"]


def test_the_other_end_state_shows_a_call_that_leaves_the_mapped_code(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 50, _map(tmp_path))

    assert report.outgoing.items[1]["other_state"] == "referenced"


def test_incoming_edges_name_the_other_end_that_arrives(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 50, _map(tmp_path))

    assert [(r["kind"], r["other"]) for r in report.incoming.items] == [
        ("calls", "php.method::B::run"),
        ("defines", "php.type::A"),
    ]


def test_limit_applies_to_each_side_with_its_own_total(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 1, _map(tmp_path))

    assert (report.outgoing.shown, report.outgoing.total) == (1, 2)
    assert (report.incoming.shown, report.incoming.total) == (1, 2)
    assert "showing 1 of 2" in show.render_text(report)


def test_an_unknown_id_exits_node_not_found_naming_the_id_and_find(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::gone", 50, _map(tmp_path))

    assert report.exit_code is ExitCode.NODE_NOT_FOUND
    message = report.problems[0].message
    assert "php.method::A::gone" in message
    assert "periplus find" in message


def test_text_and_json_carry_the_same_edges(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, "php.method::A::go", 50, _map(tmp_path))
    text = show.render_text(report)
    document = json.loads(show.render_json(report))

    assert "calls:" in text
    assert "php.method::C::run  php.method  referenced  src/a.php:9" in text
    assert [r["other"] for r in document["outgoing"]["items"]] == [
        "php.method::B::run",
        "php.method::C::run",
    ]
    assert document["incoming"]["total"] == 2


def test_the_format_choices_are_exactly_the_show_renderers() -> None:
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["show"]._actions if a.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(show.RENDERERS)
    assert fmt.default == next(iter(show.RENDERERS))


def test_main_exits_node_not_found_and_prints_the_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _map(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["show", "php.type::A", "--map", str(path)]) == 0
    assert "defines:" in capsys.readouterr().out
    assert main(["show", "nope::x", "--map", str(path)]) == int(ExitCode.NODE_NOT_FOUND)
    assert "nope::x" in capsys.readouterr().out


def test_a_map_state_with_a_newline_cannot_forge_a_line_in_the_text_report(tmp_path: Path) -> None:
    document = json.loads(json.dumps(DOCUMENT))
    document["nodes"][0]["state"] = "mapped\nFAKE LINE"
    (tmp_path / "map.json").write_text(json.dumps(document), encoding="utf-8")

    report = show.run(tmp_path, {}, "php.method::A::go", 50, tmp_path / "map.json")
    text = show.render_text(report)

    assert "FAKE LINE" not in text.splitlines()
    assert "state: mapped\\nFAKE LINE" in text
