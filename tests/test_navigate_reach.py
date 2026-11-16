"""``periplus reach``: ``depth``, then ``neighbors`` and ``affected`` fitted to a text budget,
with what ``only`` returns tagged and the hubs as ``hubs`` prints them."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import depth, hubs, only, reach, walk
from periplus.navigate.mapfile import load_map

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"
CAUSES = {"from": ["calls"], "none": ["contains"]}

# x::n0 sets off n1 .. n6 along a chain; x::q also sets off n3, so n3 .. n6 are not reached only
# through n0, and n1, n2 are. x::p sets off n0.
CHAIN = [("calls", f"x::n{i}", f"x::n{i + 1}", i + 1) for i in range(6)]
CHAIN += [("calls", "x::q", "x::n3", 20), ("calls", "x::p", "x::n0", 9)]


def _write(root: Path, edges: list[tuple[Any, ...]] = CHAIN) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], CAUSES)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _reach(root: Path, *ids: str, edges: Any = CHAIN, **opt: Any) -> reach.ReachReport:
    return reach.run(root, {}, list(ids), _write(root, edges), **opt)


def _text(root: Path, *ids: str, **opt: Any) -> str:
    return reach.render_text(_reach(root, *ids, **opt))


def test_the_reply_starts_with_the_depth_report_as_depth_prints_it(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0")
    path = tmp_path / "map.json"
    measured = depth.render_text(depth.run(tmp_path, {}, ["x::n0"], path))

    assert text.startswith("periplus reach x::n0\n\n" + measured)


def test_unbudgeted_walks_are_the_small_commands_output(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", limit=0)
    path = tmp_path / "map.json"
    for toward in ("off", "by"):
        part = walk.render_text(
            walk.run_cause(tmp_path, {}, ["x::n0"], toward, None, (), 0, path)  # type: ignore[arg-type]
        )
        # The only tags are the one thing reach adds to a walk's rows.
        assert part.replace("  [only]", "") in text.replace("  [only]", "")


def test_what_only_returns_is_tagged_and_nothing_else(tmp_path: Path) -> None:
    lines = _text(tmp_path, "x::n0", limit=0).splitlines()
    tagged = sorted(line.split()[0] for line in lines if line.endswith("[only]"))
    returned = only.listed(only.run(tmp_path, {}, ["x::n0"], tmp_path / "map.json"))

    assert tagged == ["n1", "n2"]
    assert sorted(i.split("::")[1] for i in returned) == tagged


def test_the_only_line_names_the_only_command(tmp_path: Path) -> None:
    lines = _text(tmp_path, "x::n0").splitlines()
    path = tmp_path / "map.json"

    assert (
        f"only through the starts: 2 of 6 things set off, tagged [only]; all: periplus only "
        f"x::n0 --map {path}"
    ) in lines


def test_direction_off_leaves_out_what_sets_it_off(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", direction="off")

    assert "periplus neighbors x::n0" in text
    assert "periplus affected" not in text


def test_direction_by_leaves_out_the_walk_off_and_the_only_line(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", direction="by")

    assert "periplus affected x::n0" in text
    assert "periplus neighbors" not in text
    assert "only through" not in text


# Thirty hops set off from x::n0, one hop sets it off: a walk long enough that cutting it pays.
LONG = [("calls", f"x::n{i}", f"x::n{i + 1}", i + 1) for i in range(30)]
LONG += [("calls", "x::p", "x::n0", 99)]


def test_a_small_budget_turns_far_hops_into_counts_and_names_the_full_command(
    tmp_path: Path,
) -> None:
    path = tmp_path / "map.json"
    lines = _text(tmp_path, "x::n0", edges=LONG, limit=1500).splitlines()

    cut = [line for line in lines if line.startswith("showing ")]
    assert cut == [
        f"showing {cut[0].split()[1]} of 30 (hops 1-{cut[0].split()[1]} of 30); "
        f"all: periplus neighbors x::n0 --depth all --limit 0 --map {path}"
    ]
    assert "hop 30: 1 thing (t.x 1)" in lines


def test_a_walk_that_fits_in_less_than_half_gives_the_rest_to_the_other(tmp_path: Path) -> None:
    whole = _reach(tmp_path, "x::n0", edges=LONG, limit=0)
    off, by = (walk.render_text(w) for w in whole.walks)
    fixed = len(reach.render_text(whole)) - len(off) - len(by)
    budget = 2000

    text = _text(tmp_path, "x::n0", edges=LONG, limit=budget)
    halved = walk.render_text(replace(whole.walks[0], limit=(budget - fixed) // 2))

    assert by in text
    assert len(text) <= budget
    assert text.count("  calls  ") > halved.count("  calls  ")


def test_the_hubs_print_as_hubs_prints_them(tmp_path: Path) -> None:
    edges = [("calls", "x::a", "x::h", 1)] + [("calls", "x::h", f"x::k{m}", 2) for m in range(3)]
    path = _write(tmp_path, edges)
    text = reach.render_text(reach.run(tmp_path, {}, ["x::a"], path, hub=2))
    listed = hubs.render_text(hubs.run(tmp_path, {}, ["x::a"], "off", None, 2, path))

    assert listed in text
    assert "periplus hubs x::a\nset off by:" not in text


def test_through_reaches_every_part(tmp_path: Path) -> None:
    edges = [("calls", "x::a", "x::h", 1)] + [("calls", "x::h", f"x::k{m}", 2) for m in range(3)]
    path = _write(tmp_path, edges)
    report = reach.run(tmp_path, {}, ["x::a"], path, hub=2, through=["x::h"])
    text = reach.render_text(report)

    assert "sets off:     2 hops, 4 things;" in text
    assert "only through the starts: 4 of 4 things set off" in text
    assert report.walks[0].again.endswith(f"--hub 2 --through x::h --map {path}")
    assert f"all: periplus only x::a --hub 2 --through x::h --map {path}" in text
    assert "periplus hubs" not in text


def test_ids_print_the_union_starts_first(tmp_path: Path) -> None:
    ids = reach.listed(_reach(tmp_path, "x::n3"))

    assert ids[0] == "x::n3"
    assert len(ids) == len(set(ids))
    assert set(ids) == {f"x::n{i}" for i in range(7)} | {"x::p", "x::q"}


def test_more_than_three_starts_name_dash_in_the_full_commands(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", "x::n1", "x::n2", "x::q", limit=600)

    assert "all: periplus neighbors - --depth all --limit 0" in text
    assert "(with the same ids piped in)" in text
    assert "periplus only - " in text


def test_the_json_matches_the_schema(tmp_path: Path) -> None:
    document = json.loads(reach.render_json(_reach(tmp_path, "x::n0")))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/reach"}]})

    assert list(validator.iter_errors(document)) == []
    assert document["only"] == ["x::n1", "x::n2"]
    assert [w["command"] for w in document["walks"]] == ["neighbors", "affected"]


def test_the_same_map_prints_the_same_bytes(tmp_path: Path) -> None:
    assert _text(tmp_path, "x::n0", limit=700) == _text(tmp_path, "x::n0", limit=700)


def test_the_map_is_read_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path)
    calls = []

    def counted(*args: Any) -> Any:
        calls.append(args)
        return load_map(*args)

    monkeypatch.setattr(reach, "load_map", counted)
    reach.run(tmp_path, {}, ["x::n0"], path)

    assert len(calls) == 1


def test_the_command_line_runs_it_and_reads_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = str(_write(tmp_path))

    assert main(["reach", "x::n0", "--map", path]) == 0
    assert capsys.readouterr().out.startswith("periplus reach x::n0\n")
    assert main(["reach", "nope", "--map", path]) == 31
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO("x::n0\n"))
    assert main(["reach", "-", "--ids", "--map", path]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "x::n0"
    monkeypatch.setattr("sys.stdin", io.StringIO("x::n0\n"))
    assert main(["reach", "-", "--limit", "500", "--map", path]) == 0
    assert "(with the same ids piped in)" in capsys.readouterr().out
