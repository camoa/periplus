"""The commands a printed slice suggests carry ``--map PATH`` when the run was given one, and a
start named by an id shows that id escaped once.

A tiny map at ``other/m.json``, not the default place: box ``b`` groups class ``C``; ``C``
contains ``go`` and ``stop``; ``go`` calls ``stop``, ``far`` and ``farther``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _navigate import _edge, _node

from periplus.navigate import slice as slicing

BOX = "t.box::b"
C = "t.class::C"
GO = "t.method::C::go"
STOP = "t.method::C::stop"
FAR = "t.method::D::far"
FARTHER = "t.method::D::farther"
SLASHED = "t.method::A\\B::run"
SUGGESTS = re.compile(r"periplus (show|members|find|legend|path|slice --from)\b")


def _site(root: Path) -> Path:
    nodes = [
        _node(BOX, "t.box", line=1, file="b.info"),
        _node(C, "t.class", line=1, file="src/C.php"),
        _node(GO, "t.method", line=2, file="src/C.php"),
        _node(STOP, "t.method", line=3, file="src/C.php"),
        _node(FAR, "t.method", line=1, file="src/D.php"),
        _node(FARTHER, "t.method", line=2, file="src/D.php"),
        _node(SLASHED, "t.method", line=1, file="src/A.php"),
    ]
    edges = [
        _edge("in_box", C, BOX, 1, file="b.info"),
        _edge("contains", C, GO, 2, file="src/C.php"),
        _edge("contains", C, STOP, 3, file="src/C.php"),
        *(_edge("calls", GO, end, 2, file="src/C.php") for end in (STOP, FAR, FARTHER)),
    ]
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "grouping_kinds": ["in_box"],
        "legend": {"edge_kinds": {"calls": "x" * 400, "contains": "y" * 400}},
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": edges,
    }
    (root / "other").mkdir()
    (root / "other" / "m.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _lines(root: Path, *given: str, limit: int | None) -> list[str]:
    report = slicing.run(
        _site(root), {}, given, (), "both", None, (), limit, None, root / "other/m.json", starts=1
    )
    assert not report.problems
    return slicing.render_text(report).splitlines()


def test_every_suggested_command_carries_the_map_given(tmp_path: Path) -> None:
    lines = _lines(tmp_path, "b", "far", limit=1)
    suggesting = [line for line in lines if SUGGESTS.search(line)]
    commands = sum(len(SUGGESTS.findall(line)) for line in suggesting)

    assert {"members", "find", "slice --from", "show", "path"} <= {
        m for line in suggesting for m in SUGGESTS.findall(line)
    }
    assert commands == sum(line.count(f"--map {tmp_path}/other/m.json") for line in suggesting)


def test_a_cut_legend_and_its_command_carry_the_map(tmp_path: Path) -> None:
    kept = slicing.LEGEND_BYTES
    slicing.LEGEND_BYTES = 10
    try:
        lines = _lines(tmp_path, GO, limit=0)
    finally:
        slicing.LEGEND_BYTES = kept

    assert f"  +2 more: periplus legend --kind K --map {tmp_path}/other/m.json" in lines


def test_a_start_given_by_id_shows_the_id_escaped_once(tmp_path: Path) -> None:
    lines = _lines(tmp_path, SLASHED, limit=None)

    # One backslash in the id prints as two, as every row prints it; repr then escape made four.
    assert "start run  t.method  (given as 't.method::A\\\\B::run')" in lines


def test_the_cut_note_commands_carry_the_map(tmp_path: Path) -> None:
    kept = slicing.BYTE_LIMIT
    slicing.BYTE_LIMIT = 100
    try:
        lines = _lines(tmp_path, GO, limit=None)
    finally:
        slicing.BYTE_LIMIT = kept
    cut = next(line for line in lines if line.startswith("cut to fit"))

    assert f"periplus legend --kind K --map {tmp_path}/other/m.json;" in cut
    assert cut.endswith(f"periplus show NAME --limit 0 --map {tmp_path}/other/m.json")
