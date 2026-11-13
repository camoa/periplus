"""How printed slice picks its start nodes from words, and ranks the rows under each start.

An invented app. Node types by count in the map: t.class 1, t.service 1, t.route 3, t.method 99, of
which 90 are fillers that make "app" a word most nodes match.

    A::run [src/a.php] and B::go [src/b.php] call ClaimService::makeClaim [src/ClaimService.php]
    B::go calls Other::claimAll [src/Other.php]
    ClaimTest::claimHelper [tests/ClaimTest.php] calls ClaimTest::setUp, same file
    X::boot [src/x.php] -uses-> the service claim_service [app.services.yml]
    routes claim.page (mapped), claim.x (unresolved), claim.wishlist (mapped)
    Store::run [src/Store.php] -calls-> lib.Thing::save, -uses-> claim_service
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node

from periplus.navigate import slice as slicing

CLASS = "t.class::app.ClaimService"
SERVICE = "t.service::claim_service"
PAGE = "t.route::claim.page"
MISSING = "t.route::claim.x"
WISH = "t.route::claim.wishlist"
CLAIM = "t.method::app.ClaimService::makeClaim"
ALL = "t.method::app.Other::claimAll"
HELPER = "t.method::app.Tests.ClaimTest::claimHelper"
SETUP = "t.method::app.Tests.ClaimTest::setUp"
RUN = "t.method::app.A::run"
GO = "t.method::app.B::go"
BOOT = "t.method::app.X::boot"
STORE = "t.method::app.Store::run"
SAVE = "t.method::lib.Thing::save"

NODES = [
    _node(CLASS, "t.class", line=3, file="src/ClaimService.php"),
    _node(SERVICE, "t.service", line=1, file="app.services.yml"),
    _node(PAGE, "t.route", line=1, file="app.routing.yml"),
    _node(MISSING, "t.route", state="unresolved"),
    _node(WISH, "t.route", line=5, file="app.routing.yml"),
    _node(CLAIM, "t.method", line=5, file="src/ClaimService.php"),
    _node(ALL, "t.method", line=2, file="src/Other.php"),
    _node(HELPER, "t.method", line=4, file="tests/ClaimTest.php"),
    _node(SETUP, "t.method", line=9, file="tests/ClaimTest.php"),
    _node(RUN, "t.method", line=2, file="src/a.php"),
    _node(GO, "t.method", line=2, file="src/b.php"),
    _node(BOOT, "t.method", line=2, file="src/x.php"),
    _node(STORE, "t.method", line=2, file="src/Store.php"),
    _node(SAVE, "t.method", state="referenced"),
    *[
        _node(f"t.method::app.Filler::f{n:02}", "t.method", line=n, file="src/f.php")
        for n in range(1, 91)
    ],
]
EDGES = [
    _edge("calls", RUN, CLAIM, 3, file="src/a.php"),
    _edge("calls", GO, CLAIM, 3, file="src/b.php"),
    _edge("calls", GO, ALL, 4, file="src/b.php"),
    _edge("calls", HELPER, SETUP, 5, file="tests/ClaimTest.php"),
    _edge("uses", BOOT, SERVICE, 3, file="src/x.php"),
    _edge("calls", STORE, SAVE, 3, file="src/Store.php"),
    _edge("uses", STORE, SERVICE, 4, file="src/Store.php"),
]


def _site(root: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Path:
    (root / ".periplus").mkdir(parents=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": edges,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _piece(
    root: Path, *words: str, nodes: Any = None, edges: Any = None, **kw: Any
) -> slicing.SliceReport:
    args: dict[str, Any] = {
        "prefixes": (),
        "direction": "both",
        "depth": None,
        "kinds": (),
        "limit": None,
        "out": None,
        "map_path": None,
    }
    args.update(kw)
    site = _site(root, NODES if nodes is None else nodes, EDGES if edges is None else edges)
    return slicing.run(site, {}, words, **args)


def _ids(report: slicing.SliceReport) -> list[str]:
    return [start.row.id for start in report.starts]


def test_rarer_types_start_first(tmp_path: Path) -> None:
    assert _ids(_piece(tmp_path, "claim", starts=3)) == [CLASS, SERVICE, PAGE]


def test_one_type_gives_at_most_its_share_of_starts(tmp_path: Path) -> None:
    report = _piece(tmp_path, "claim", starts=6)

    assert [i for i in _ids(report) if i.startswith("t.method::")] == [CLAIM, ALL]


def test_inside_a_type_the_node_more_other_files_depend_on_comes_first(tmp_path: Path) -> None:
    methods = [i for i in _ids(_piece(tmp_path, "claim", starts=6)) if i.startswith("t.method")]

    assert methods[0] == CLAIM
    assert HELPER not in methods


def test_a_node_not_mapped_never_beats_a_mapped_one_of_its_type(tmp_path: Path) -> None:
    routes = [i for i in _ids(_piece(tmp_path, "claim", starts=20)) if i.startswith("t.route")]

    assert routes[0] != MISSING


def test_more_words_then_a_larger_share_of_the_id_win(tmp_path: Path) -> None:
    far = "t.route::claim.some.long.path.to.wishes"
    nodes = [*NODES, _node(far, "t.route", line=7, file="app.routing.yml")]
    routes = _ids(_piece(tmp_path / "a", "claim", "wish", starts=20, nodes=nodes))
    assert [i for i in routes if "route" in i][:3] == [WISH, far, PAGE]

    long = "t.route::claim.aaaa.longer"
    nodes = [*NODES, _node(long, "t.route", line=9, file="app.routing.yml")]
    one = [i for i in _ids(_piece(tmp_path / "b", "claim", starts=20, nodes=nodes)) if "route" in i]
    assert one[0] == PAGE


def test_a_common_word_never_puts_its_starts_before_a_rare_words(tmp_path: Path) -> None:
    report = _piece(tmp_path, "app", "wish", starts=1)

    assert _ids(report) == [WISH]


def test_a_node_that_matches_a_rare_and_a_common_word_beats_one_with_the_rare_alone(
    tmp_path: Path,
) -> None:
    tools = "t.method::app.claim_tools"
    nodes = [
        *(n for n in NODES if n["id"] != CLASS),
        _node(tools, "t.method", line=1, file="t.php"),
    ]

    assert _ids(_piece(tmp_path, "claim", "app", starts=1, nodes=nodes)) == [tools]


def test_a_word_only_in_the_type_or_owner_part_of_an_id_scores_nothing(tmp_path: Path) -> None:
    arg = "t.arg::app.ClaimService::makeClaim::$x"
    nodes = [*NODES, _node(arg, "t.arg", line=5, file="src/ClaimService.php")]

    assert _ids(_piece(tmp_path, "claim", starts=1, nodes=nodes)) == [CLASS]


def test_a_unique_name_among_several_words_is_also_searched_as_a_word(tmp_path: Path) -> None:
    later = "t.method::app.Other::makeClaimLater"
    nodes = [*NODES, _node(later, "t.method", line=8, file="src/Other.php")]

    assert _ids(_piece(tmp_path / "a", "makeClaim", nodes=nodes)) == [CLAIM]
    assert later in _ids(_piece(tmp_path / "b", "makeClaim", "wishlist", nodes=nodes))


def test_rows_are_budgeted_per_start(tmp_path: Path) -> None:
    report = _piece(tmp_path, "claim_service", "ClaimService::makeClaim", limit=2)

    assert [row.start for row in report.rows.items] == [SERVICE, CLAIM]


def test_inside_a_start_a_rarer_type_ranks_before_a_common_one(tmp_path: Path) -> None:
    callers = [
        _edge("calls", c, SAVE, 9, file=f) for c, f in ((RUN, "src/a.php"), (GO, "src/b.php"))
    ]
    report = _piece(tmp_path, "Store::run", limit=1, edges=[*EDGES, *callers])

    assert [row.id for row in report.rows.items] == [SERVICE]
