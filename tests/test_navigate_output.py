"""The six navigation commands share one output contract: byte-identical runs, cut lists, a schema.

Proved once here, across all six, because each command's own module cannot see what the others do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

SRC = Path(__file__).resolve().parent.parent / "src"
SCHEMA = SRC / "periplus" / "contract" / "schema" / "navigation.schema.json"

HUB = "x::hub"
SINK = "x::sink"
LEAVES = [f"x::leaf{n}" for n in range(1, 7)]
MIDDLES = [f"x::mid{n}" for n in range(1, 4)]
ACCENTED = "x::café"

# Six edges leave the hub; three equal-length chains reach the sink, so every list has more than
# two entries. The accented id is the one an ASCII-only or locale-sensitive path would change.
EDGES = (
    [("calls", HUB, leaf) for leaf in LEAVES]
    + [("calls", HUB, m) for m in MIDDLES]
    + [("calls", m, SINK) for m in MIDDLES]
    + [("uses", HUB, ACCENTED)]
)

#: Each command as argv, and how many items its list holds before any cut.
COMMANDS: dict[str, list[str]] = {
    "types": ["types"],
    "find": ["find", "x::"],
    "show": ["show", HUB],
    "neighbors": ["neighbors", HUB],
    "affected": ["affected", SINK],
    "path": ["path", HUB, SINK],
}

_CHILD = "import sys; from periplus.cli import main; sys.exit(main())"


# Several types, most with a parent, so the types listing has rows a set would reorder by seed.
TYPE_OF = {HUB: "t.hub", SINK: "t.sink", ACCENTED: "t.café"}
TYPE_OF |= {leaf: "t.leaf" for leaf in LEAVES} | {m: "t.mid" for m in MIDDLES}
HIERARCHY = {"t.x": None, "t.hub": "t.x", "t.café": "t.x", "t.leaf": "t.x"}
HIERARCHY |= {"t.mid": "t.leaf", "t.sink": "t.mid"}


def _node(id: str) -> dict[str, Any]:
    return {
        "id": id,
        "type": TYPE_OF[id],
        "state": "mapped",
        "locations": [{"file": "a.php", "line": 1}],
        "provenance": [{"pack": "p", "rule": "r", "confidence": "declared", "sets": []}],
    }


def _edge(kind: str, source: str, target: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": [{"file": "a.php", "line": 2}],
        "provenance": [{"pack": "p", "rule": "r", "confidence": "declared", "sets": []}],
    }


def _write_map(path: Path) -> None:
    names = sorted({HUB, SINK, ACCENTED, *LEAVES, *MIDDLES})
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "p", "version": "0.1.0"}],
        "roots": ["."],
        "type_hierarchy": [{"type": t, "parent": p} for t, p in sorted(HIERARCHY.items())],
        "nodes": [_node(n) for n in names],
        "edges": [_edge(*e) for e in sorted(EDGES)],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A project whose default map exists, a directory outside it, and the map's own path."""
    project = tmp_path / "project"
    (project / ".periplus").mkdir(parents=True)
    (project / "web" / "deep").mkdir(parents=True)
    map_path = project / ".periplus" / "map.json"
    _write_map(map_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    return project / "web" / "deep", elsewhere, map_path


def _run(cwd: Path, argv: list[str], **overrides: str) -> str:
    """Run one command in a fresh interpreter, so seed, locale and directory are this call's."""
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PERIPLUS_CONFIG_DIR": str(cwd / "no-user-config"),
        **overrides,
    }
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _CHILD, *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )
    assert result.returncode == 0, f"{argv}: {result.stdout}{result.stderr}"
    return result.stdout


@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_command_prints_the_same_bytes_across_seeds_locales_and_working_directories(
    tree: tuple[Path, Path, Path], name: str, fmt: str
) -> None:
    """Seeds 0 and 2 (0 and 1 hid a set-order defect before), a second locale, a second directory.

    The first three runs sit inside the project and find its default map from there. The fourth
    runs from outside it and is handed the map, so a path leaking into the output differs.
    """
    inside, outside, map_path = tree
    argv = [*COMMANDS[name], "--format", fmt]
    first = _run(inside, argv, PYTHONHASHSEED="0", LC_ALL="C")
    second = _run(inside, argv, PYTHONHASHSEED="2", LC_ALL="C")
    third = _run(inside, argv, PYTHONHASHSEED="0", LC_ALL="es_ES.utf8")
    fourth = _run(outside, [*argv, "--map", str(map_path)], PYTHONHASHSEED="0", LC_ALL="C")

    assert first
    assert first == second
    assert first == third
    assert first == fourth


# Command, the total it reports before any cut.
LISTS = [
    ("find", 12),
    ("show", 10),
    ("neighbors", 10),
    ("affected", 3),
    ("path", 3),
]


def _cut(name: str, document: dict[str, Any]) -> dict[str, Any]:
    if name == "show":
        return document["outgoing"]  # type: ignore[no-any-return]
    if name == "find":
        return document
    return document["chains" if name == "path" else "rows"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("name,total", LISTS)
def test_a_limit_below_the_count_reports_total_shown_and_the_cut_in_json_and_text(
    tree: tuple[Path, Path, Path], name: str, total: int
) -> None:
    inside, _, _ = tree
    argv = [*COMMANDS[name], "--limit", "2"]

    listing = _cut(name, json.loads(_run(inside, [*argv, "--format", "json"])))
    assert (listing["total"], listing["shown"], listing["truncated"]) == (total, 2, True)
    assert len(listing["items"]) == 2

    text = _run(inside, [*argv, "--format", "text"])
    assert f"showing 2 of {total}" in text

    whole = _cut(name, json.loads(_run(inside, [*COMMANDS[name], "--format", "json"])))
    assert (whole["total"], whole["shown"], whole["truncated"]) == (total, total, False)
    assert f"showing {total} of" not in _run(inside, [*COMMANDS[name], "--format", "text"])


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_commands_json_validates_against_the_shipped_navigation_schema(
    tree: tuple[Path, Path, Path], name: str
) -> None:
    inside, _, _ = tree
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": f"#/$defs/{name}"}]})
    argv = [*COMMANDS[name], "--format", "json"]

    for variant in ([], [] if name == "types" else ["--limit", "2"]):
        document = json.loads(_run(inside, [*argv, *variant]))
        assert list(validator.iter_errors(document)) == [], document


def test_the_schema_rejects_a_listing_that_lacks_its_cut_marker(
    tree: tuple[Path, Path, Path],
) -> None:
    """The schema is not vacuous: a find result without ``truncated`` fails it."""
    inside, _, _ = tree
    document = json.loads(_run(inside, ["find", "x::", "--format", "json"]))
    del document["truncated"]

    assert list(Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(document))
