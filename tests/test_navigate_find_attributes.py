"""``periplus find`` over node attributes: string values and list items match, ranked after ids
and before descriptions inside each group, marked with the attribute's name, and the matched
value printed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _node

from periplus.navigate import find

LONG = "  Profile\tx" + "y" * 200 + "\nsecond line"

DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "t.route", "parent": None},
        {"type": "t.perm", "parent": None},
        {"type": "t.plugin", "parent": None},
    ],
    "nodes": [
        _node(
            "t.route::r1",
            "t.route",
            line=1,
            file="routes.yml",
            attributes={"title": "Edit Profile", "path": "/user/{id}/edit", "weight": 3},
        ),
        _node("t.route::profile", "t.route", line=5, file="routes.yml"),
        _node("t.perm::p1", "t.perm", attributes={"roles": [7, "Profile editor"]}),
        _node(
            "t.plugin::p2",
            "t.plugin",
            attributes={"count": 5, "flag": True, "nested": {"label": "profile"}},
        ),
        _node("t.perm::p3", "t.perm"),
        _node("t.plugin::p4", "t.plugin", attributes={"label": LONG}),
    ],
    "edges": [],
}

DESCRIPTIONS = """\
nodes:
  t.perm::p3:
    text: Shows the profile.
    file: perms.yml
    line: 1
  t.plugin::p4:
    text: A plugin.
    file: plugins.yml
    line: 1
"""


def _find(root: Path, text: str, *types: str) -> find.FindReport:
    map_path = root / "map.json"
    map_path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    (root / "descriptions.yaml").write_text(DESCRIPTIONS, encoding="utf-8")
    return find.run(root, {}, text, types, 0, map_path)


def _matched(report: find.FindReport) -> list[tuple[str, str, str | None]]:
    return [(r.id, r.matched, r.matched_attribute) for r in report.matches.items]


def test_ids_rank_first_then_attributes_then_descriptions(tmp_path: Path) -> None:
    # The two located routes are main things; the three with no location come after them.
    assert _matched(_find(tmp_path, "PROFILE")) == [
        ("t.route::profile", "id", None),
        ("t.route::r1", "attribute", "title"),
        ("t.perm::p1", "attribute", "roles"),
        ("t.plugin::p4", "attribute", "label"),
        ("t.perm::p3", "description", None),
    ]


def test_several_matching_attributes_name_the_first_in_sorted_order(tmp_path: Path) -> None:
    assert _matched(_find(tmp_path, "edit")) == [
        ("t.route::r1", "attribute", "path"),
        ("t.perm::p1", "attribute", "roles"),
    ]


def test_numbers_booleans_and_nested_objects_do_not_match(tmp_path: Path) -> None:
    assert _matched(_find(tmp_path, "5")) == []
    assert _matched(_find(tmp_path, "true")) == []
    assert _matched(_find(tmp_path, "7")) == []
    assert "t.plugin::p2" not in [r.id for r in _find(tmp_path, "profile").matches.items]


def test_type_filter_and_by_type_cover_attribute_matches(tmp_path: Path) -> None:
    report = _find(tmp_path, "profile", "t.plugin")

    assert _matched(report) == [("t.plugin::p4", "attribute", "label")]
    assert report.by_type == {"t.plugin": 1}
    assert _find(tmp_path, "profile").by_type == {"t.perm": 2, "t.plugin": 1, "t.route": 2}


def test_text_marks_the_row_and_prints_the_value_cut_and_escaped(tmp_path: Path) -> None:
    lines = find.render_text(_find(tmp_path, "profile")).splitlines()

    assert "t.route::r1  t.route  mapped  routes.yml:1  [attribute title]" in lines
    at = lines.index("t.route::r1  t.route  mapped  routes.yml:1  [attribute title]")
    assert lines[at + 1] == "      @ title: Edit Profile"
    plugin = lines.index("t.plugin::p4  t.plugin  mapped  no location  [attribute label]")
    value = ("Profile\tx" + "y" * 200)[:160].replace("\t", "\\t")
    assert lines[plugin + 1 : plugin + 3] == [f"      @ label: {value}", "      # A plugin."]
    assert lines[lines.index("t.perm::p1  t.perm  mapped  no location  [attribute roles]") + 1] == (
        "      @ roles: Profile editor"
    )
    assert "t.route::profile  t.route  mapped  routes.yml:5" in lines
    assert "t.perm::p3  t.perm  mapped  no location  [description]" in lines
    assert sum(line.startswith("      @") for line in lines) == 3


def test_json_rows_carry_matched_and_matched_attribute(tmp_path: Path) -> None:
    rows = json.loads(find.render_json(_find(tmp_path, "profile")))["items"]

    assert [(r["matched"], r["matched_attribute"]) for r in rows] == [
        ("id", None),
        ("attribute", "title"),
        ("attribute", "roles"),
        ("attribute", "label"),
        ("description", None),
    ]
