"""A pack names the path patterns of its stack's supporting code, as tests; the settings add to
them or clear them. The map carries the resulting list, so a command that reads only the map
knows them, and a third-party pack names them exactly as a bundled pack does.
"""

from __future__ import annotations

import json
from pathlib import Path

import _own_pack
from _own_pack import plant

from periplus.checkmap import run as check_map
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

RULES = """
node_types:
  - {name: own.box, id_namespace: box}
rules:
  - rule: box
    reads: file
    in: [source]
    match: {declaration: class_declaration, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.box}}]
    confidence: declared
"""


def _map(root: Path, pack: str = "", settings: str = "") -> tuple[dict[str, object], bytes]:
    plant(root, RULES)
    if pack:
        manifest = root / _own_pack.PACK / "pack.yaml"
        manifest.write_text(manifest.read_text().replace("files:\n", f"files:\n{pack}"))
    (root / ".periplus/settings.yml").write_text(_own_pack.SETTINGS + settings)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert check_map(root, {}, root / "map.json").exit_code == 0
    written = (root / "map.json").read_bytes()
    document: dict[str, object] = json.loads(written)
    return document, written


def test_the_map_carries_the_packs_patterns_sorted(tmp_path: Path) -> None:
    document, _ = _map(tmp_path, '  supporting: ["tests/**", "**/fixtures/**"]\n')

    assert document["supporting_paths"] == ["**/fixtures/**", "tests/**"]


def test_the_settings_add_patterns(tmp_path: Path) -> None:
    document, _ = _map(tmp_path, '  supporting: ["tests/**"]\n', 'supporting: ["demo/**"]\n')

    assert document["supporting_paths"] == ["demo/**", "tests/**"]


def test_the_settings_clear_the_packs_patterns(tmp_path: Path) -> None:
    document, _ = _map(
        tmp_path,
        '  supporting: ["tests/**"]\n',
        'supporting_from_packs: false\nsupporting: ["demo/**"]\n',
    )

    assert document["supporting_paths"] == ["demo/**"]


def test_a_map_without_patterns_is_unchanged(tmp_path: Path) -> None:
    document, written = _map(tmp_path / "a")
    _, cleared = _map(
        tmp_path / "b", '  supporting: ["tests/**"]\n', "supporting_from_packs: false\n"
    )

    assert "supporting_paths" not in document
    assert written == cleared
