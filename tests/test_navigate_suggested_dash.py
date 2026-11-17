"""A suggested command reads its starts with ``-`` when they came from standard input or are more
than three; ``hubs`` takes ``--through`` and ``only`` takes ``--hub`` and ``--through``."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node

from periplus.cli import main
from periplus.navigate import depth, walk

CAUSES = {"from": ["calls"], "touch": ["links_to"]}
# Four starts s0 .. s3, each setting off a chain of three; each is pointed at by a link.
EDGES = [("calls", f"x::s{s}", f"x::s{s}c0", 1) for s in range(4)]
EDGES += [("calls", f"x::s{s}c{i}", f"x::s{s}c{i + 1}", i + 2) for s in range(4) for i in range(2)]
EDGES += [("links_to", f"x::l{s}", f"x::s{s}", 9) for s in range(4)]
FOUR = [f"x::s{s}" for s in range(4)]


def _write(root: Path, edges: list[tuple[Any, ...]] = EDGES) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], CAUSES)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _cut_line(root: Path, ids: list[str], piped: bool = False) -> str:
    report = walk.run_cause(root, {}, ids, "off", 1, (), 0, _write(root), piped=piped)
    return walk.render_text(report).splitlines()[0]


def test_more_than_three_starts_print_a_dash_and_the_note(tmp_path: Path) -> None:
    path = tmp_path / "map.json"

    assert _cut_line(tmp_path, FOUR).endswith(
        f"all: periplus neighbors - --depth all --limit 0 --map {path} (with the same ids piped in)"
    )


def test_three_starts_are_named(tmp_path: Path) -> None:
    assert "all: periplus neighbors x::s0 x::s1 x::s2 --depth" in _cut_line(tmp_path, FOUR[:3])


def test_starts_read_from_standard_input_print_a_dash_however_few(tmp_path: Path) -> None:
    assert "all: periplus neighbors - --depth all" in _cut_line(tmp_path, FOUR[:1], piped=True)


def test_depth_touching_lines_follow_the_same_rule(tmp_path: Path) -> None:
    lines = depth.render_text(depth.run(tmp_path, {}, FOUR, _write(tmp_path))).splitlines()
    touching = next(line for line in lines if line.startswith("touching:"))
    on = f"--map {tmp_path / 'map.json'}"
    piped = f"see periplus affected - --touch {on} (with the same ids piped in)"

    assert touching.endswith(piped)
    one = depth.render_text(depth.run(tmp_path, {}, FOUR[:1], _write(tmp_path), piped=True))
    assert piped in one


def test_the_command_line_says_piped_for_dash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = str(_write(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO("x::s0\n"))

    assert main(["neighbors", "-", "--map", path]) == 0
    assert "periplus neighbors - --depth all" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO("x::s0\n"))
    main(["depth", "-", "--map", path])
    assert "see periplus affected - --touch" in capsys.readouterr().out


# a -> h -> k0, k1, k2: with --hub 2, h is a hub unless --through walks it.
HUB_EDGES = [("calls", "x::a", "x::h", 1)] + [("calls", "x::h", f"x::k{m}", 2) for m in range(3)]


def test_hubs_through_walks_a_hub_and_lists_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path, HUB_EDGES))

    main(["hubs", "x::a", "--hub", "2", "--ids", "--map", path])
    assert capsys.readouterr().out == "x::h\n"
    main(["hubs", "x::a", "--hub", "2", "--through", "x::h", "--ids", "--map", path])
    assert capsys.readouterr().out == ""


def test_only_takes_the_hub_limit_and_through(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path, HUB_EDGES))

    main(["only", "x::a", "--hub", "2", "--ids", "--map", path])
    assert capsys.readouterr().out == "x::h\n"
    main(["only", "x::a", "--hub", "2", "--through", "x::h", "--ids", "--map", path])
    assert capsys.readouterr().out.splitlines() == ["x::h", "x::k0", "x::k1", "x::k2"]
