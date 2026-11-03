"""The navigation commands' result rows: frozen dataclasses, and the same output as before."""

from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node, _prov

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import find, path, show, types, walk

GO = "php.method::A::go"
RUN_B = "php.method::B::run"

DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "php.symbol", "parent": None},
        {"type": "php.method", "parent": "php.symbol"},
        {"type": "php.type", "parent": "php.symbol"},
    ],
    "nodes": [
        _node(GO, "php.method", line=3, roles=["entry"], attributes={"visibility": "public"}),
        _node(RUN_B, "php.method", line=3),
        _node("php.method::C::run", "php.method", "referenced"),
        _node("php.type::A", "php.type", line=3),
    ],
    "edges": [
        _edge("calls", GO, "php.method::C::run", 9, _prov("inferred", "x")),
        _edge("calls", GO, RUN_B, 7, _prov("declared", "y"), _prov("inferred", "x")),
        _edge("defines", "php.type::A", GO, 1),
        _edge("calls", RUN_B, GO, 4),
    ],
}

# What each command printed with --format json on DOCUMENT before rows were dataclasses.
PINNED: dict[str, str] = {
    "types": """\
{
  "edge_kinds": [
    {
      "count": 3,
      "kind": "calls"
    },
    {
      "count": 1,
      "kind": "defines"
    }
  ],
  "node_types": [
    {
      "count": 3,
      "parent": "php.symbol",
      "type": "php.method"
    },
    {
      "count": 1,
      "parent": "php.symbol",
      "type": "php.type"
    }
  ],
  "problems": []
}
""",
    "find": """\
{
  "items": [
    {
      "id": "php.method::B::run",
      "location": "src/a.php:3",
      "state": "mapped",
      "type": "php.method"
    },
    {
      "id": "php.method::C::run",
      "location": null,
      "state": "referenced",
      "type": "php.method"
    }
  ],
  "problems": [],
  "shown": 2,
  "total": 2,
  "truncated": false,
  "warnings": []
}
""",
    "neighbors": """\
{
  "direction": "out",
  "problems": [],
  "rows": {
    "items": [
      {
        "depth": 1,
        "id": "php.method::B::run",
        "kind": "calls",
        "state": "mapped",
        "type": "php.method",
        "via": "php.method::A::go"
      },
      {
        "depth": 1,
        "id": "php.method::C::run",
        "kind": "calls",
        "state": "referenced",
        "type": "php.method",
        "via": "php.method::A::go"
      }
    ],
    "shown": 2,
    "total": 2,
    "truncated": false
  },
  "start": "php.method::A::go",
  "warnings": []
}
""",
    "affected": """\
{
  "direction": "in",
  "problems": [],
  "rows": {
    "items": [
      {
        "depth": 1,
        "id": "php.method::B::run",
        "kind": "calls",
        "state": "mapped",
        "type": "php.method",
        "via": "php.method::A::go"
      },
      {
        "depth": 1,
        "id": "php.type::A",
        "kind": "defines",
        "state": "mapped",
        "type": "php.type",
        "via": "php.method::A::go"
      }
    ],
    "shown": 2,
    "total": 2,
    "truncated": false
  },
  "start": "php.method::A::go",
  "warnings": []
}
""",
    "show": """\
{
  "attributes": {
    "visibility": "public"
  },
  "id": "php.method::A::go",
  "incoming": {
    "items": [
      {
        "confidences": [
          "inferred"
        ],
        "kind": "calls",
        "locations": [
          {
            "file": "src/a.php",
            "line": 4
          }
        ],
        "occurrences": 2,
        "other": "php.method::B::run",
        "other_state": "mapped",
        "other_type": "php.method",
        "rules": [
          "php:r"
        ]
      },
      {
        "confidences": [
          "inferred"
        ],
        "kind": "defines",
        "locations": [
          {
            "file": "src/a.php",
            "line": 1
          }
        ],
        "occurrences": 2,
        "other": "php.type::A",
        "other_state": "mapped",
        "other_type": "php.type",
        "rules": [
          "php:r"
        ]
      }
    ],
    "shown": 2,
    "total": 2,
    "truncated": false
  },
  "locations": [
    {
      "file": "src/a.php",
      "line": 3
    }
  ],
  "outgoing": {
    "items": [
      {
        "confidences": [
          "declared",
          "inferred"
        ],
        "kind": "calls",
        "locations": [
          {
            "file": "src/a.php",
            "line": 7
          }
        ],
        "occurrences": 2,
        "other": "php.method::B::run",
        "other_state": "mapped",
        "other_type": "php.method",
        "rules": [
          "php:x",
          "php:y"
        ]
      },
      {
        "confidences": [
          "inferred"
        ],
        "kind": "calls",
        "locations": [
          {
            "file": "src/a.php",
            "line": 9
          }
        ],
        "occurrences": 2,
        "other": "php.method::C::run",
        "other_state": "referenced",
        "other_type": "php.method",
        "rules": [
          "php:x"
        ]
      }
    ],
    "shown": 2,
    "total": 2,
    "truncated": false
  },
  "problems": [],
  "provenance": [
    {
      "confidence": "declared",
      "pack": "php",
      "rule": "r",
      "sets": []
    }
  ],
  "roles": [
    "entry"
  ],
  "state": "mapped",
  "type": "php.method"
}
""",
    "path": """\
{
  "chains": {
    "items": [
      [
        {
          "from": "php.method::A::go",
          "kind": "calls",
          "to": "php.method::B::run"
        }
      ]
    ],
    "shown": 1,
    "total": 1,
    "truncated": false
  },
  "from": "php.method::A::go",
  "problems": [],
  "to": "php.method::B::run",
  "warnings": []
}
""",
}


def _map(root: Path, document: dict[str, Any] = DOCUMENT) -> Path:
    target = root / "map.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


ARGV: dict[str, list[str]] = {
    "types": ["types"],
    "find": ["find", "run"],
    "neighbors": ["neighbors", GO],
    "affected": ["affected", GO],
    "show": ["show", GO],
    "path": ["path", GO, RUN_B],
}


@pytest.mark.parametrize("name", sorted(ARGV))
def test_each_command_prints_the_json_it_printed_before_rows_were_dataclasses_c2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    where = _map(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main([*ARGV[name], "--format", "json", "--map", str(where)]) == 0
    assert capsys.readouterr().out == PINNED[name]


def _type_row(root: Path) -> Any:
    return types.run(root, {}, _map(root)).node_types[0]


def _kind_row(root: Path) -> Any:
    return types.run(root, {}, _map(root)).edge_kinds[0]


def _find_row(root: Path) -> Any:
    return find.run(root, {}, "run", None, 50, _map(root)).matches.items[0]


def _walk_row(root: Path) -> Any:
    return walk.run(root, {}, GO, "out", 1, [], 50, _map(root)).rows.items[0]


def _edge_row(root: Path) -> Any:
    return show.run(root, {}, GO, 50, _map(root)).outgoing.items[0]


def _step(root: Path) -> Any:
    return path.run(root, {}, GO, RUN_B, [], 10, _map(root)).chains.items[0][0]


ROWS: list[tuple[Callable[[Path], Any], dict[str, Any]]] = [
    (_type_row, {"type": "php.method", "count": 3, "parent": "php.symbol"}),
    (_kind_row, {"kind": "calls", "count": 3}),
    (
        _find_row,
        {"id": RUN_B, "type": "php.method", "state": "mapped", "location": "src/a.php:3"},
    ),
    (_walk_row, {"id": RUN_B, "depth": 1, "kind": "calls", "via": GO}),
    (
        _edge_row,
        {"kind": "calls", "other": RUN_B, "other_type": "php.method", "occurrences": 2},
    ),
    (_step, {"start": GO, "kind": "calls", "end": RUN_B}),
]


@pytest.mark.parametrize(("make", "expected"), ROWS, ids=[make.__name__ for make, _ in ROWS])
def test_every_navigation_row_is_a_frozen_dataclass_with_named_attributes_c2(
    tmp_path: Path, make: Callable[[Path], Any], expected: dict[str, Any]
) -> None:
    row = make(tmp_path)

    assert dataclasses.is_dataclass(type(row))
    assert {name: getattr(row, name) for name in expected} == expected
    first = next(iter(expected))
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(row, first, "changed")


def test_an_outgoing_edge_row_holds_the_file_and_line_the_map_holds_c2(tmp_path: Path) -> None:
    row = show.run(tmp_path, {}, GO, 50, _map(tmp_path)).outgoing.items[0]

    assert [(loc.file, loc.line) for loc in row.locations] == [("src/a.php", 7)]


def test_an_edge_row_is_frozen_all_the_way_down_wo2(tmp_path: Path) -> None:
    row = show.run(tmp_path, {}, GO, 50, _map(tmp_path)).outgoing.items[0]

    assert dataclasses.is_dataclass(type(row))
    assert isinstance(row.locations, tuple)
    assert isinstance(row.confidences, tuple)
    assert isinstance(row.rules, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.locations[0].line = 99


@pytest.mark.parametrize(
    "damage",
    [
        lambda edge: edge["locations"][0].update(file=3, line="x"),
        lambda edge: edge.__setitem__("occurrences", "two"),
    ],
    ids=["locations", "occurrences"],
)
def test_a_damaged_edge_field_still_exits_not_a_map_wo2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: Callable[[dict[str, Any]], None],
) -> None:
    document = copy.deepcopy(DOCUMENT)
    damage(document["edges"][1])
    where = _map(tmp_path, document)
    monkeypatch.chdir(tmp_path)

    assert main(["show", GO, "--map", str(where)]) == int(ExitCode.NOT_A_MAP)
