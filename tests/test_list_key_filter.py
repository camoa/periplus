"""A list-form edge end keeps the keys its where globs select; absolute addresses make no node."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from test_library_scripts import MODULE, _map, _plant

import periplus
from periplus.engine.packload import _read_forward, _Unsupported

NOT_MATCHES = re.compile(
    r"( +)- not_matches: /?/\*\n +- not_matches: http:\*\n +- not_matches: https:\*\n"
)


def test_a_library_address_makes_no_node_and_no_edge(tmp_path: Path) -> None:
    _plant(tmp_path)
    libraries = tmp_path / MODULE / "mymodule.libraries.yml"
    libraries.write_text(
        "form:\n  js:\n    js/form.js: {}\n    js/extra.js: {}\n"
        "    https://cdn.example.com/lib.js: {type: external}\n"
        "    //cdn.example.com/other.js: {type: external}\n"
        "  dependencies:\n    - core/drupal\n"
    )
    document = _map(tmp_path)
    edges = [e for e in document["edges"] if e["kind"] == "library_includes_script"]
    assert len(edges) == 2
    assert not [n for n in document["nodes"] if "cdn.example.com" in str(n["id"])]


def test_a_matches_glob_keeps_exactly_the_keys_it_selects(tmp_path: Path) -> None:
    _plant(tmp_path)
    packs = tmp_path / ".periplus" / "packs"
    copy = packs / "js_copy@0.0.1"
    shutil.copytree(Path(periplus.__file__).parent / "packs" / "drupal_js_basic@0.0.1", copy)
    manifest = copy / "pack.yaml"
    manifest.write_text(manifest.read_text().replace("pack: drupal_js_basic", "pack: js_copy"))
    settings = tmp_path / ".periplus" / "settings.yml"
    settings.write_text(settings.read_text().replace("drupal_js_basic@0.0.1", "js_copy@0.0.1"))
    rule = copy / "behavior" / "behavior.yaml"
    rule.write_text(NOT_MATCHES.sub(r"\1- matches: js/f*\n", rule.read_text()))
    edges = [e for e in _map(tmp_path)["edges"] if e["kind"] == "library_includes_script"]
    assert [e["to"] for e in edges] == [f"js.file::{MODULE}/js/form.js"]


LIST_END = {"from": [{"each": "js.*"}], "template": "{key}"}


def _end(*where: object) -> dict[str, object]:
    return {"kind": "k", "from": "this_node", "to": {**LIST_END, "where": list(where)}}


@pytest.mark.parametrize(
    "where",
    [
        [{"foo": "x"}, {"listed_at": "dependencies.config"}],
        [{"matches": "a*"}, {"matches": "b*"}],
        [{"listed_at": "a"}, {"listed_at": "b"}],
        [{"listed_at": None}, {"listed_at": "b"}],
        [{"matches": 3}],
        [{"not_matches": ["a"]}],
        [{"matches": "a*", "not_matches": "b*"}],
    ],
)
def test_a_where_the_engine_cannot_run_is_refused_naming_the_accepted_forms(
    where: list[object],
) -> None:
    with pytest.raises(_Unsupported, match="listed_at, matches .* and not_matches"):
        _read_forward(_end(*where))


def test_a_glob_without_an_each_part_is_refused() -> None:
    edge = _end({"matches": "a*"})
    edge["to"]["from"] = ["key"]  # type: ignore[index]
    with pytest.raises(_Unsupported, match="not_matches"):
        _read_forward(edge)
