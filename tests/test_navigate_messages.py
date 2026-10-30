"""The walk's `via` line and the two navigation exit cases (29 unreadable, 30 damaged)."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import pytest

from periplus.cli import main

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "navigation.md"
_FENCE = r"```[^\n]*\n(?P<body>.*?)^```$"


class _Ran:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code, self.out, self.err = code, out, err

    @property
    def both(self) -> str:
        return self.out + self.err


def _run(
    args: list[str],
    cwd: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _Ran:
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(config))
    capsys.readouterr()
    try:
        code = main(args)
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else 0
    seen = capsys.readouterr()
    return _Ran(code or 0, seen.out, seen.err)


def _guide_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Path:
    """The guide's worked example, written out and mapped, as the guide's demo script does."""
    site = tmp_path / "project"
    (site / ".periplus").mkdir(parents=True)
    shipped = ROOT / "examples" / "second-stack"
    shutil.copytree(shipped / "packs", site / ".periplus" / "packs")
    shutil.copy(shipped / "settings.yml", site / ".periplus" / "settings.yml")
    text = GUIDE.read_text(encoding="utf-8")
    pattern = r"^<!-- nav-file: (?P<path>\S+) -->\n" + _FENCE
    for m in re.finditer(pattern, text, re.M | re.S):
        target = site / m["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(m["body"], encoding="utf-8")
    config = tmp_path / "userconf"
    config.mkdir()
    done = _run(["map"], site, config, monkeypatch, capsys)
    assert done.code == 0, done.both
    return site


def _chain_map(site: Path, out: Path) -> list[str]:
    """A map holding A -K1-> B -K2-> C, with two different real edge kinds, from the real map."""
    whole = json.loads((site / ".periplus" / "map.json").read_text(encoding="utf-8"))
    a, b, c = (n["id"] for n in whole["nodes"][:3])
    kinds = sorted({e["kind"] for e in whole["edges"]})
    assert len(kinds) >= 2, kinds
    k1, k2 = kinds[:2]
    template = whole["edges"][0]
    whole["nodes"] = whole["nodes"][:3]
    whole["edges"] = [
        {**template, "from": a, "kind": k1, "to": b},
        {**template, "from": b, "kind": k2, "to": c},
    ]
    whole["counts"] = {
        "edges": 2,
        "edges_by_kind": {k1: 1, k2: 1},
        "nodes": 3,
        "nodes_by_state": {n["state"]: 1 for n in whole["nodes"]}
        if len({n["state"] for n in whole["nodes"]}) == 3
        else whole["counts"]["nodes_by_state"],
        "nodes_by_type": whole["counts"]["nodes_by_type"],
    }
    out.write_text(json.dumps(whole), encoding="utf-8")
    return [a, b, c, k1, k2]


def _problem_line(out: str, code: int) -> str:
    lines = [line for line in out.splitlines() if line.startswith(f"{code} ")]
    return lines[0] if lines else ""


@pytest.mark.criterion(id="c3")
def test_via_line_names_the_item_reached_from_in_the_walk_direction_c3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _guide_project(tmp_path, monkeypatch, capsys)
    config = tmp_path / "userconf"
    planted = tmp_path / "chain.json"
    a, b, c, k1, k2 = _chain_map(site, planted)
    out = _run(
        ["neighbors", a, "--depth", "2", "--map", str(planted)], site, config, monkeypatch, capsys
    )
    assert out.code == 0, out.both
    rows = {line.split()[1]: line for line in out.out.splitlines() if re.match(r"^\s+\d+\s", line)}
    assert rows[b].endswith(f"via {k1} from {a}"), rows[b]
    assert rows[c].endswith(f"via {k2} from {b}"), rows[c]
    back = _run(
        ["affected", c, "--depth", "2", "--map", str(planted)], site, config, monkeypatch, capsys
    )
    assert back.code == 0, back.both
    rows = {line.split()[1]: line for line in back.out.splitlines() if re.match(r"^\s+\d+\s", line)}
    assert rows[b].endswith(f"via {k2} to {c}"), rows[b]
    assert rows[a].endswith(f"via {k1} to {b}"), rows[a]


@pytest.mark.criterion(id="c4")
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_find_on_an_unreadable_map_exits_29_saying_it_cannot_read_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _guide_project(tmp_path, monkeypatch, capsys)
    config = tmp_path / "userconf"
    unreadable = tmp_path / "unreadable.json"
    shutil.copy(site / ".periplus" / "map.json", unreadable)
    unreadable.chmod(0)
    try:
        done = _run(["find", "shop", "--map", str(unreadable)], site, config, monkeypatch, capsys)
    finally:
        unreadable.chmod(0o600)
    assert done.code == 29, done.both
    assert "cannot read" in _problem_line(done.out, 29), done.out


@pytest.mark.criterion(id="c4")
def test_find_on_a_map_with_a_malformed_row_exits_30_saying_damaged_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _guide_project(tmp_path, monkeypatch, capsys)
    config = tmp_path / "userconf"
    whole = json.loads((site / ".periplus" / "map.json").read_text(encoding="utf-8"))
    whole["nodes"][0] = "junk"
    broken = tmp_path / "row-fault.json"
    broken.write_text(json.dumps(whole), encoding="utf-8")
    done = _run(["find", "shop", "--map", str(broken)], site, config, monkeypatch, capsys)
    assert done.code == 30, done.both
    assert "damaged" in _problem_line(done.out, 30), done.out
