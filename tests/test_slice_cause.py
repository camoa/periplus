"""``slice`` is a macro: its starts, the members of a container start, then the walks by cause of
``neighbors`` and ``affected``, with each thing's content printed or written.

An invented app; `in_box` is a grouping kind, `links_to` only points, the other kinds set off
their to end:

    A, F -in_box-> Mod;  C -calls-> F -calls-> G -calls-> H -calls-> J
    F -uses-> Hub -calls-> K1, K2, K3;  F -links_to-> P;  X -calls-> C
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus import checkmap
from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import extract, members, walk
from periplus.navigate import slice as slicing

MOD = "t.module::app"
A, F, C, G, H, J, X = (f"t.function::app.{n}" for n in ("A", "F", "C", "G", "H", "J", "X"))
HUB = "t.service::app.hub"
KS = [f"t.function::app.K{n}" for n in (1, 2, 3)]
P = "t.route::app.page"

NODES = [
    _node(MOD, "t.module", line=1, file="app.info"),
    *(_node(n, "t.function", line=k, file="src/app.php") for k, n in enumerate((A, F, C, G), 1)),
    *(_node(n, "t.function", line=k, file="src/far.php") for k, n in enumerate((H, J, X), 1)),
    _node(HUB, "t.service", line=1, file="app.services"),
    *(_node(k, "t.function", line=n, file="src/k.php") for n, k in enumerate(KS, 1)),
    _node(P, "t.route", line=1, file="app.routing"),
]
EDGES = [
    _edge("in_box", A, MOD, 1, file="app.info"),
    _edge("in_box", F, MOD, 1, file="app.info"),
    _edge("calls", C, F, 3, file="src/app.php"),
    _edge("calls", F, G, 2, file="src/app.php"),
    _edge("calls", G, H, 4, file="src/app.php"),
    _edge("calls", H, J, 1, file="src/far.php"),
    _edge("calls", X, C, 3, file="src/far.php"),
    _edge("uses", F, HUB, 2, file="src/app.php"),
    *(_edge("calls", HUB, k, 1, file="app.services") for k in KS),
    _edge("links_to", F, P, 2, file="src/app.php"),
]
CAUSES = {
    "cause_from_kinds": ["calls", "uses"],
    "cause_none_kinds": ["in_box"],
    "cause_touch_kinds": ["links_to"],
}


def _site(root: Path, causes: bool = True) -> Path:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "type_hierarchy": [
            {"type": t, "parent": None} for t in ("t.module", "t.function", "t.service", "t.route")
        ],
        "grouping_kinds": ["in_box"],
        **(CAUSES if causes else {}),
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _slice(root: Path, *ids: str, **kw: Any) -> slicing.SliceReport:
    return slicing.run(root, {}, (), (), from_ids=ids, **kw)


@pytest.mark.parametrize(
    "options",
    [
        {"depth": 1},
        {"depth": 2},
        {"depth": None},
        {"depth": None, "hub": 2},
        {"depth": None, "hub": 2, "through": (HUB,)},
        {"depth": 2, "touch": True},
        {"depth": None, "kinds": ("calls",)},
    ],
)
def test_the_ids_are_the_members_and_the_two_walks_of_the_small_commands(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    site = _site(tmp_path)
    held = slicing.listed(_slice(site, MOD, **options))

    listed = members.listed(members.run(site, {}, [MOD], (), None))
    walked = {
        i
        for toward in ("off", "by")
        for i in walk.listed(
            walk.run_cause(
                site,
                {},
                [MOD, *listed],
                toward,
                options["depth"],
                options.get("kinds", ()),
                0,
                None,
                options.get("hub", walk.HUB),
                options.get("through", ()),
                options.get("touch", False),
            )
        )
    }
    assert set(listed) == {A, F}
    assert len(held) == len(set(held))
    assert set(held) == {MOD, *listed} | walked


def test_the_cli_ids_print_what_the_report_holds(tmp_path: Path) -> None:
    site = _site(tmp_path)
    printed = io.StringIO()
    with (
        contextlib.chdir(site),
        contextlib.redirect_stdout(printed),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        code = main(["slice", "--from", F, "--depth", "all", "--ids"])

    assert code == 0
    assert printed.getvalue().splitlines() == list(_slice(site, F, depth=None).held)


def test_a_repeated_from_adds_its_ids_to_the_earlier_ones(tmp_path: Path) -> None:
    site = _site(tmp_path)

    def printed(*args: str) -> list[str]:
        out = io.StringIO()
        with (
            contextlib.chdir(site),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            assert main(["slice", *args, "--depth", "1", "--ids"]) == 0
        return out.getvalue().splitlines()

    together = printed("--from", H, X)
    assert {H, J, X, C} <= set(together)
    assert printed("--from", H, "--from", X) == together


def test_a_hub_stops_the_walk_and_through_walks_it(tmp_path: Path) -> None:
    site = _site(tmp_path)
    stopped = _slice(site, F, depth=None, hub=2)
    lines = slicing.render_text(stopped).splitlines()

    assert HUB in stopped.held and not set(KS) & set(stopped.held)
    assert "  :1  hub  t.service  [hub: 3 links not walked]" in lines
    assert lines[2] == f"sets off:     3 hops, 4 things; 1 hub stopped ({HUB})"
    assert set(KS) <= set(_slice(site, F, depth=None, hub=2, through=(HUB,)).held)


def test_the_depth_holds_the_nearest_hops_and_names_the_whole_walk(tmp_path: Path) -> None:
    report = _slice(_site(tmp_path), F, depth=1)
    lines = slicing.render_text(report).splitlines()

    assert set(report.held) == {F, C, G, HUB}
    assert lines[2] == (
        "sets off:     3 hops, 7 things; 0 hubs stopped; this slice holds hop 1: 2;"
        " all: periplus neighbors F --depth all --limit 0"
    )


def test_one_direction_walks_one_way(tmp_path: Path) -> None:
    site = _site(tmp_path)

    assert set(_slice(site, F, direction="off", depth=None).held) == {F, G, H, J, HUB, *KS}
    assert set(_slice(site, F, direction="by", depth=None).held) == {F, C, X}


def test_touch_adds_what_a_thing_only_points_at(tmp_path: Path) -> None:
    site = _site(tmp_path)

    assert P not in _slice(site, F).held
    touched = _slice(site, F, touch=True)
    assert P in touched.held
    assert [r.touch for r in touched.rows.items if r.id == P] == [True]


def test_out_writes_exactly_the_ids_and_extract_of_them_gives_the_same_bytes(
    tmp_path: Path,
) -> None:
    site = _site(tmp_path)
    held = _slice(site, MOD).held
    written = _slice(site, MOD, out=Path("slice.json"))
    extract.run(site, {}, list(held), Path("extract.json"), None)
    document = json.loads((site / "slice.json").read_text(encoding="utf-8"))

    assert written.exit_code is ExitCode.OK
    assert {n["id"] for n in document["nodes"]} == set(held)
    assert all(e["from"] in held and e["to"] in held for e in document["edges"])
    assert (site / "slice.json").read_bytes() == (site / "extract.json").read_bytes()
    assert checkmap.run(site, {}, site / "slice.json").exit_code == 0


def test_out_over_its_limit_writes_nothing(tmp_path: Path) -> None:
    site = _site(tmp_path)
    report = _slice(site, MOD, out=Path("slice.json"), limit=3)

    assert report.exit_code is ExitCode.SLICE_TOO_LARGE
    assert not (site / "slice.json").exists()


def test_the_same_map_and_options_give_the_same_bytes(tmp_path: Path) -> None:
    one = _slice(_site(tmp_path / "a"), MOD, depth=None, touch=True)
    two = _slice(_site(tmp_path / "b"), MOD, depth=None, touch=True)

    assert slicing.render_text(one) == slicing.render_text(two)
    assert slicing.render_json(one) == slicing.render_json(two)


def test_a_map_without_causes_walks_raw_from_each_start_and_says_so(tmp_path: Path) -> None:
    site = _site(tmp_path, causes=False)
    report = _slice(site, F, C, depth=1)
    lines = slicing.render_text(report).splitlines()

    raw = {
        i
        for start in (F, C)
        for direction in ("out", "in")
        for i in walk.listed(walk.run(site, {}, start, direction, 1, (), 0, None))
    }
    assert set(report.held) == raw
    assert f"warning: {walk.NO_CAUSES}" in lines
    assert lines[3] == (
        "sets off:   4 things by the raw walk, as the map lists no cause;"
        " each: periplus neighbors ID --raw --depth 1 --limit 0 (for each of the 2 ids it walks"
        " from)"
    )


def test_ids_with_out_exits_2(tmp_path: Path) -> None:
    site = _site(tmp_path)
    with (
        contextlib.chdir(site),
        contextlib.redirect_stderr(io.StringIO()),
        pytest.raises(SystemExit) as stopped,
    ):
        main(["slice", "--from", F, "--ids", "--out", "s.json"])

    assert stopped.value.code == ExitCode.USAGE


def test_the_cli_default_depth_is_the_slice_default() -> None:
    from periplus import cli

    assert cli.SLICE_DEPTH == slicing.PRINT_DEPTH


def test_depth_0_lists_the_starts_and_their_members_alone(tmp_path: Path) -> None:
    site = _site(tmp_path)

    assert _slice(site, MOD, C, depth=0, touch=True).held == (MOD, C, A, F)
    assert _slice(site, MOD, depth=0).rows.items == (
        *(r for m in _slice(site, MOD, depth=0).members for r in m.rows),
    )


def _many(deep: Path) -> Path:
    """Twelve things named token in files of their own, each with a long description and
    calling five helpers, in a map at ``deep``."""
    tokens = [f"t.function::app.token{k:02}" for k in range(12)]
    files = {t: f"src/token{k:02}.php" for k, t in enumerate(tokens)}
    calls = [(t, f"t.function::app.help{k:02}_{n}") for k, t in enumerate(tokens) for n in range(5)]
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "cause_from_kinds": ["calls"],
        "nodes": sorted(
            [
                *(_node(t, "t.function", line=1, file=files[t]) for t in tokens),
                *(_node(h, "t.function", line=3, file=f"src/{h[-4:]}.php") for _, h in calls),
            ],
            key=lambda n: n["id"],
        ),
        "edges": [_edge("calls", t, h, 2, file=files[t]) for t, h in calls],
    }
    deep.parent.mkdir(parents=True)
    deep.write_text(json.dumps(document), encoding="utf-8")
    text = "Takes a token and checks it. " * 15
    entries = "".join(
        f"  {t}:\n    text: {text}\n    file: {files[t]}\n    line: 1\n" for t in tokens
    )
    (deep.parent / "descriptions.yaml").write_text(f"nodes:\n{entries}", encoding="utf-8")
    return deep


def test_a_slice_of_many_starts_and_a_long_map_path_still_prints_walk_rows(
    tmp_path: Path,
) -> None:
    deep = _many(tmp_path.joinpath(*["folder" * 40] * 5, "map.json"))
    report = slicing.run(tmp_path, {}, ["token"], (), map_path=deep)
    lines = slicing.render_text(report).splitlines()

    assert len(report.starts) == 12
    assert len(report.rows.items) >= slicing.ROW_FLOOR
    assert {r.walk for r in report.rows.items} == {"off"}
    assert sum(line.startswith("start ") for line in lines) == slicing.START_LINES
    (counted,) = [line for line in lines if line.startswith("+8 more starts;")]
    command = counted.split("members: ", 1)[1]
    assert command == f"periplus slice token --depth 0 --ids --map {deep}"

    printed = io.StringIO()
    with (
        contextlib.chdir(tmp_path),
        contextlib.redirect_stdout(printed),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        main(command.split()[1:])
    assert printed.getvalue().splitlines() == [s.row.id for s in report.starts]
