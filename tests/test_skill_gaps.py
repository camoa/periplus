"""The gaps skill: its runnable commands and its gap-read programs."""

from __future__ import annotations

import json
import re
import runpy
import shlex
from pathlib import Path
from typing import Any

import pytest
from _skills import ROOT, blocks, example_project, run_periplus

SKILL = ROOT / "src" / "periplus" / "skills" / "periplus-gaps" / "SKILL.md"
HEADINGS = ("Resolution gaps", "Detail gaps", "Site faults")


def _nav_commands() -> list[list[str]]:
    return [
        shlex.split(line[2:])
        for _, body in blocks(SKILL, "nav-run")
        for line in body.splitlines()
        if line.startswith("$ periplus")
    ]


def _run_gap_read(
    tmp_path: Path,
    map_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Run every gap-read block in-process on `map_file`; return what they printed."""
    printed = []
    for index, (_, body) in enumerate(blocks(SKILL, "gap-read")):
        script = tmp_path / f"gap_read_{index}.py"
        script.write_text(body)
        monkeypatch.setattr("sys.argv", [str(script), str(map_file)])
        capsys.readouterr()
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as stop:
            assert stop.code in (None, 0), f"block {index} exited {stop.code}"
        printed.append(capsys.readouterr().out)
    return "\n".join(printed)


def _section(out: str, heading: str) -> list[str]:
    """The lines printed under `heading`, up to the next report heading."""
    inside: list[str] = []
    active = False
    for line in out.splitlines():
        bare = line.strip().lstrip("#").strip().rstrip(":")
        if bare in HEADINGS:
            active = bare == heading
            continue
        if active and line.strip():
            inside.append(line)
    return inside


def _fields(line: str) -> list[str]:
    return re.split(r"\s{2,}", line.strip())


def _count(line: str) -> int | None:
    last = line.split()[-1:] or [""]
    return int(last[0]) if last[0].isdigit() else None


def _node(
    node_id: str,
    node_type: str,
    state: str = "mapped",
    rule: str = "function",
    pack: str = "python_text",
    file: str | None = "shop/a.py",
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": node_id,
        "locations": [{"file": file, "line": 1}] if file else [],
        "provenance": [{"confidence": "declared", "pack": pack, "rule": rule, "sets": ["id"]}],
        "state": state,
        "type": node_type,
    }
    if state == "unresolved":
        node["unresolved_detail"] = {
            "found": "no mapped node of this name",
            "rule": f"{pack}/{rule}",
            "searched_for": node_id.split("::")[1],
            "types_tried": [node_type],
        }
    return node


def _edge(
    src: str,
    dst: str,
    kind: str = "imports",
    confidence: str = "declared",
    file: str = "shop/a.py",
    line: int = 2,
) -> dict[str, Any]:
    return {
        "from": src,
        "to": dst,
        "kind": kind,
        "locations": [{"file": file, "line": line}],
        "occurrences": 1,
        "provenance": [{"confidence": confidence, "pack": "python_text", "rule": "call"}],
    }


def _write_map(
    path: Path,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    hierarchy: list[dict[str, Any]] | None = None,
    packs: list[str] | None = None,
) -> Path:
    edges = edges or []
    by_state: dict[str, int] = {}
    for n in nodes:
        by_state[n["state"]] = by_state.get(n["state"], 0) + 1
    document = {
        "counts": {"edges": len(edges), "nodes": len(nodes), "nodes_by_state": by_state},
        "edges": edges,
        "generated_by": "periplus 0.4.1",
        "nodes": nodes,
        "packs": [{"pack": p, "version": "0.1.0"} for p in packs or ["python_text"]],
        "periplus_map_version": 0,
        "roots": ["."],
        "settings": ".periplus/settings.yml",
        "type_hierarchy": hierarchy
        or [{"parent": None, "type": t} for t in sorted({n["type"] for n in nodes})],
    }
    path.write_text(json.dumps(document, indent=1, sort_keys=True))
    return path


def _state_lines(resolution: list[str]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for line in resolution:
        word = line.split()[0].lower() if line.split() else ""
        if word in ("referenced", "unresolved", "inferred") and _count(line) is not None:
            counted[word] = _count(line) or 0
    return counted


def _first_party_lines(resolution: list[str]) -> list[tuple[int, int]]:
    found = [re.search(r"first-party\s+(\d+)\s+outside\s+(\d+)", x) for x in resolution]
    return [(int(m.group(1)), int(m.group(2))) for m in found if m]


@pytest.mark.criterion(id="wo1")
def test_gaps_skill_nav_run_commands_exit_zero_with_rows_wo1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commands = _nav_commands()
    verbs = {c[1] for c in commands if len(c) > 1}
    assert {"check-map", "types", "find"} <= verbs, f"skill names only {sorted(verbs)}"
    assert ["periplus", "map", "--format", "json"] in commands, f"skill runs {commands}"
    project = example_project(tmp_path)
    mapped = run_periplus(["map"], project, monkeypatch, capsys)
    assert mapped.code == 0, mapped.out + mapped.err
    for argv in commands:
        run = run_periplus(argv[1:], project, monkeypatch, capsys)
        assert run.code == 0, f"{argv}: {run.out}{run.err}"
        assert run.out.strip(), f"{argv} printed no row"


@pytest.mark.criterion(id="wo1")
def test_gap_read_blocks_run_on_the_example_map_and_print_counted_lists_wo1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = example_project(tmp_path)
    mapped = run_periplus(["map"], project, monkeypatch, capsys)
    assert mapped.code == 0, mapped.out + mapped.err
    map_file = project / ".periplus" / "map.json"
    out = _run_gap_read(tmp_path, map_file, monkeypatch, capsys)
    assert [h for h in HEADINGS if h not in out] == [], f"printed {out!r}"
    real = json.loads(map_file.read_text())
    states = [n["state"] for n in real["nodes"]]
    inferred = sum(
        any(p["confidence"] == "inferred" for p in e["provenance"]) for e in real["edges"]
    )
    assert _state_lines(_section(out, "Resolution gaps")) == {
        "referenced": states.count("referenced"),
        "unresolved": states.count("unresolved"),
        "inferred": inferred,
    }, out


@pytest.mark.criterion(id="c2")
def test_resolution_gaps_count_each_state_with_a_first_party_split_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = [_node(f"python.module::m{i}", "python.module", rule="module") for i in range(2)]
    nodes.append(_node("python.module::m2", "python.module", rule="module", file=None))
    nodes += [
        _node(f"python.module::ref{i}", "python.module", "referenced", "import_first", file=None)
        for i in range(3)
    ]
    nodes += [
        _node(f"python.function::un{i}", "python.function", "unresolved", "call", file=None)
        for i in range(2)
    ]
    edges = [
        _edge("python.module::m0", "python.function::un0", "calls", "inferred"),
        _edge("python.module::m0", "python.function::un1", "calls", "inferred"),
        _edge("python.module::m1", "python.function::un0", "calls", "inferred"),
        _edge("python.module::m1", "python.module::ref0", "imports", "inferred"),
        _edge("python.module::m2", "python.function::un1", "calls", "inferred"),
        _edge("python.module::m0", "python.module::m1", "imports", "declared"),
    ]
    map_file = _write_map(tmp_path / "map.json", nodes, edges)
    out = _run_gap_read(tmp_path, map_file, monkeypatch, capsys)
    resolution = _section(out, "Resolution gaps")
    assert _state_lines(resolution) == {"referenced": 3, "unresolved": 2, "inferred": 5}, out
    splits = _first_party_lines(resolution)
    assert len(splits) == 3, resolution
    by_state = dict(zip(_state_lines(resolution), splits, strict=True))
    assert by_state["referenced"] == (0, 3), resolution
    assert by_state["unresolved"] == (0, 2), resolution
    assert by_state["inferred"] == (4, 1), resolution


@pytest.mark.criterion(id="c2")
def test_detail_gaps_group_nodes_by_rule_and_the_discriminator_for_that_rule_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = [
        _node(f"drupal.config::eca.model_{i}", "drupal.config", rule="any_config_file")
        for i in range(3)
    ]
    nodes.append(_node("drupal.config::system.site", "drupal.config", rule="any_config_file"))
    nodes += [
        _node("php.class::Drupal\\mymod\\One", "php.class", rule="class_decl"),
        _node("php.class::Drupal\\mymod\\Two", "php.class", rule="class_decl"),
        _node("php.class::Drupal\\other\\Three", "php.class", rule="class_decl"),
        _node("php.class::Loose", "php.class", rule="class_decl"),
    ]
    nodes += [_node(f"php.function::f{i}", "php.function", rule="function_decl") for i in range(2)]
    out = _run_gap_read(tmp_path, _write_map(tmp_path / "map.json", nodes), monkeypatch, capsys)
    rows = [_fields(x) for x in _section(out, "Detail gaps")]
    triples = {
        tuple(r)
        for r in rows
        if len(r) == 3 and r[0] in ("any_config_file", "class_decl", "function_decl")
    }
    assert triples == {
        ("any_config_file", "eca", "3"),
        ("any_config_file", "system", "1"),
        ("class_decl", "mymod", "2"),
        ("class_decl", "other", "1"),
        ("class_decl", "none", "1"),
        ("function_decl", "-", "2"),
    }, rows


@pytest.mark.criterion(id="c2")
def test_detail_gaps_list_each_parent_type_with_present_children_and_none_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = [_node(f"generic.a::item{i}", "generic.a", rule="a_rule") for i in range(2)]
    hierarchy: list[dict[str, Any]] = [
        {"parent": None, "type": "generic.thing"},
        {"parent": "generic.thing", "type": "generic.a"},
        {"parent": "generic.thing", "type": "generic.b"},
        {"parent": None, "type": "generic.lonely"},
    ]
    map_file = _write_map(tmp_path / "map.json", nodes, hierarchy=hierarchy)
    out = _run_gap_read(tmp_path, map_file, monkeypatch, capsys)
    rows = [_fields(x) for x in _section(out, "Detail gaps")]
    child_rows = {tuple(r) for r in rows if len(r) == 3 and r[0].startswith("generic.")}
    assert ("generic.thing", "generic.a", "2") in child_rows, rows
    assert ("generic.thing", "generic.b", "0") in child_rows, rows
    assert ("generic.lonely", "none", "0") in child_rows, rows


@pytest.mark.criterion(id="c2")
def test_detail_gaps_rank_referenced_modules_by_distinct_leaning_nodes_and_pack_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = [_node(f"php.class::m{i}", "php.class", rule="class_decl") for i in range(3)]
    nodes += [
        _node(f"drupal.module::{m}", "drupal.module", "referenced", "info", "drupal", None)
        for m in ("eca", "views", "alpha")
    ]
    nodes += [
        _node("php.type::Drupal\\token\\A", "php.type", "referenced", "use", "php", None),
        _node("php.type::Drupal\\token\\B", "php.type", "referenced", "use", "php", None),
    ]
    edges = [_edge(f"php.class::m{i}", "drupal.module::views") for i in range(3)]
    edges += [
        _edge("php.class::m0", "php.type::Drupal\\token\\A"),
        _edge("php.class::m0", "php.type::Drupal\\token\\B"),
        _edge("php.class::m1", "php.type::Drupal\\token\\A"),
        _edge("php.class::m0", "drupal.module::alpha"),
        _edge("php.class::m1", "drupal.module::alpha"),
        _edge("php.class::m0", "drupal.module::eca"),
    ]
    map_file = _write_map(
        tmp_path / "map.json",
        nodes,
        edges,
        packs=["python_text", "ecalike", "eca_first", "eca_second", "token", "views_ui"],
    )
    out = _run_gap_read(tmp_path, map_file, monkeypatch, capsys)
    modules = [_fields(x) for x in _section(out, "Detail gaps") if "rutter:" in x]
    assert modules == [
        ["views", "3", "rutter: views_ui"],
        ["alpha", "2", "rutter: none"],
        ["token", "2", "rutter: token"],
        ["eca", "1", "rutter: eca_first"],
    ], modules


@pytest.mark.criterion(id="c3")
def test_site_faults_print_apart_with_file_and_line_and_never_as_rule_gaps_c3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def call(src: str, dst: str, file: str, line: int) -> dict[str, Any]:
        return _edge(src, dst, "calls", file=file, line=line)

    nodes = [
        _node("php.type::Foo", "php.type", rule="class", pack="php", file="src/Foo.php"),
        _node("php.method::Foo::have", "php.method", rule="method", pack="php", file="src/Foo.php"),
        _node("php.method::Foo::missing", "php.method", "referenced", "call", "php", None),
        _node("php.type::Child", "php.type", rule="class", pack="php", file="src/Child.php"),
        _node("php.type::Base", "php.type", "referenced", "extends", "php", None),
        _node("php.method::Child::inherited", "php.method", "referenced", "call", "php", None),
        _node("php.type::Sub", "php.type", rule="class", pack="php", file="src/Sub.php"),
        _node("php.type::Mid", "php.type", rule="class", pack="php", file="src/Mid.php"),
        _node("php.method::Mid::up", "php.method", rule="method", pack="php", file="src/Mid.php"),
        _node("php.method::Sub::up", "php.method", "referenced", "call", "php", None),
        _node(
            "drupal.module::mymod", "drupal.module", rule="info", pack="drupal", file="m.info.yml"
        ),
        _node(
            "drupal.library::mymod/gone", "drupal.library", "referenced", "attach", "drupal", None
        ),
        _node("drupal.library::far/lib", "drupal.library", "referenced", "attach", "drupal", None),
        _node("php.type::Drupal\\mymod\\Gone", "php.type", "referenced", "use", "php", None),
        _node("php.type::Drupal\\far\\Thing", "php.type", "referenced", "use", "php", None),
        _node("php.method::a_caller", "php.method", rule="method", pack="php", file="src/c.php"),
    ]
    edges = [
        _edge("php.type::Foo", "php.method::Foo::have", "contains"),
        _edge("php.type::Child", "php.type::Base", "inherits"),
        _edge("php.type::Sub", "php.type::Mid", "inherits"),
        _edge("php.type::Mid", "php.method::Mid::up", "contains"),
        call("php.method::a_caller", "php.method::Foo::missing", "src/c.php", 12),
        call("php.method::a_caller", "php.method::Foo::missing", "src/z.php", 40),
        call("php.method::a_caller", "php.method::Child::inherited", "src/c.php", 13),
        call("php.method::a_caller", "php.method::Sub::up", "src/c.php", 14),
        call("php.method::a_caller", "drupal.library::mymod/gone", "src/lib.php", 21),
        call("php.method::a_caller", "drupal.library::far/lib", "src/lib.php", 22),
        call("php.method::a_caller", "php.type::Drupal\\mymod\\Gone", "src/use.php", 31),
        call("php.method::a_caller", "php.type::Drupal\\far\\Thing", "src/use.php", 32),
    ]
    map_file = _write_map(tmp_path / "map.json", nodes, edges)
    out = _run_gap_read(tmp_path, map_file, monkeypatch, capsys)
    faults = [_fields(x) for x in _section(out, "Site faults")]
    assert sorted(faults) == sorted(
        [
            ["php.method::Foo::missing", "src/c.php:12", "method no class defines"],
            ["drupal.library::mymod/gone", "src/lib.php:21", "library no libraries file defines"],
            ["php.type::Drupal\\mymod\\Gone", "src/use.php:31", "class no file holds"],
        ]
    ), faults
    detail = _section(out, "Detail gaps")
    modules = [_fields(x) for x in detail if "rutter:" in x]
    assert [m[:2] for m in modules] == [["far", "1"]], f"fault nodes counted as gaps: {detail}"
    for fault in faults:
        assert fault[0] not in "\n".join(detail), f"{fault[0]} listed as a missing rule: {detail}"
