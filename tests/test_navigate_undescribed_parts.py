"""``periplus undescribed`` says which part types it decided on, with each one's share, and
``--parts-too`` counts their things as main things.

A tiny map: function ``a`` holds parameters ``x`` and ``y``; ``y`` holds ``z``. Two of the three
parameters nest and hold nothing, so the parameter type is a part type at 66%.
"""

from __future__ import annotations

import json
from pathlib import Path

from _navigate import _document, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import undescribed

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"


def _write(root: Path) -> Path:
    nodes = [
        _node("t.f::a", "t.f", line=1),
        _node("t.p::a::x", "t.p", line=1),
        _node("t.p::a::y", "t.p", line=1),
        _node("t.p::a::y::z", "t.p", line=1),
    ]
    path = root / "map.json"
    path.write_text(json.dumps(_document(nodes, [])), encoding="utf-8")
    return path


def test_the_reply_names_each_part_type_with_its_share(tmp_path: Path) -> None:
    lines = undescribed.render_text(undescribed.run(tmp_path, {}, [], "file", _write(tmp_path)))

    assert lines.splitlines()[1:4] == [
        "described 0 of 1 main thing; 1 undescribed",
        "left out: 3 parts (t.p 3)",
        "part types: t.p 66%; count them too with --parts-too",
    ]


def test_parts_too_counts_the_things_of_part_types_as_main(tmp_path: Path) -> None:
    report = undescribed.run(tmp_path, {}, [], "type", _write(tmp_path), parts_too=True)

    assert undescribed.render_text(report).splitlines()[1:] == [
        "described 0 of 4 main things; 4 undescribed",
        "part types: t.p 66%; counted as main things (--parts-too)",
        "by type:",
        "  3  t.p",
        "  1  t.f",
    ]
    assert len(undescribed.listed(report)) == 4


def test_json_carries_the_shares_and_the_option_and_fits_the_schema(tmp_path: Path) -> None:
    path = _write(tmp_path)
    plain = json.loads(undescribed.render_json(undescribed.run(tmp_path, {}, [], "file", path)))
    too = json.loads(
        undescribed.render_json(undescribed.run(tmp_path, {}, [], "file", path, parts_too=True))
    )
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))

    assert (plain["part_types"], plain["parts_too"]) == ([{"type": "t.p", "share": 66}], False)
    assert (too["parts_too"], too["left_out"]["parts"], too["main"]) == (True, {}, 4)
    assert list(validator.iter_errors(plain)) == list(validator.iter_errors(too)) == []


def test_the_command_takes_parts_too(tmp_path: Path) -> None:
    assert main(["undescribed", "--parts-too", "--map", str(_write(tmp_path))]) == 0
