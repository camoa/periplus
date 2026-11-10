"""periplus show prints the description entries the descriptions file holds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _navigate import PROV, _edge, _node

from periplus.cli import main

A = "php::A"
B = "php::B"
NODE_LINE = "description: Loads the thing. (src/a.php:3)"
EDGE_LINE = "description: Calls B to save. (src/a.php:5)"
NOT_A_MAP = 30


def _write_map(folder: Path) -> Path:
    doc = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "1"}],
        "roots": ["."],
        "nodes": [_node(A, line=3), _node(B, line=9)],
        "edges": [_edge("calls", A, B, 5, PROV)],
    }
    (folder / ".periplus").mkdir(exist_ok=True)
    path = folder / ".periplus" / "map.json"
    path.write_text(json.dumps(doc))
    return path


def _run(capsys: pytest.CaptureFixture[str], node: str, path: Path, fmt: str) -> tuple[int, str]:
    code = main(["show", node, "--map", str(path), "--format", fmt])
    return code, capsys.readouterr().out


DESCRIPTIONS = """\
nodes:
  php::A:
    text: Loads the thing.
    file: src/a.php
    line: 3
edges:
  - from: php::A
    kind: calls
    to: php::B
    text: Calls B to save.
    file: src/a.php
    line: 5
"""


@pytest.mark.criterion(id="c7")
def test_show_prints_node_and_edge_entries_in_text_and_json_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_map(tmp_path)
    (tmp_path / ".periplus" / "descriptions.yaml").write_text(DESCRIPTIONS)

    code, text = _run(capsys, A, path, "text")
    assert code == 0
    lines = [ln.strip() for ln in text.splitlines()]
    assert NODE_LINE in lines
    assert EDGE_LINE in lines
    edge_row = next(i for i, ln in enumerate(lines) if ln.startswith(B))
    assert lines[edge_row + 1] == EDGE_LINE
    assert "description: none" not in lines

    code, out = _run(capsys, A, path, "json")
    doc = json.loads(out)
    assert code == 0
    assert doc["description"] == {"text": "Loads the thing.", "file": "src/a.php", "line": 3}
    row = doc["outgoing"]["items"][0]
    assert row["description"] == {"text": "Calls B to save.", "file": "src/a.php", "line": 5}


@pytest.mark.criterion(id="c7")
def test_show_says_none_for_a_node_without_an_entry_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_map(tmp_path)
    (tmp_path / ".periplus" / "descriptions.yaml").write_text(DESCRIPTIONS)

    code, text = _run(capsys, B, path, "text")
    assert code == 0
    assert "description: none" in [ln.strip() for ln in text.splitlines()]

    code, out = _run(capsys, B, path, "json")
    assert json.loads(out)["description"] is None


@pytest.mark.criterion(id="c7")
def test_show_without_a_descriptions_file_adds_only_the_none_line_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_map(tmp_path)

    code, text = _run(capsys, A, path, "text")
    assert code == 0
    lines = text.splitlines()
    assert "Outgoing (1):" in text
    assert [ln for ln in lines if "description:" in ln] == ["description: none"]

    code, out = _run(capsys, A, path, "json")
    doc = json.loads(out)
    assert code == 0
    assert doc["description"] is None
    assert doc["problems"] == []
    assert doc["outgoing"]["items"][0]["description"] is None


@pytest.mark.criterion(id="c7")
@pytest.mark.parametrize(
    "content",
    [
        "nodes: [unclosed\n",
        "nodes:\n  php::A:\n    text: Loads.\n    file: src/a.php\n    line: zero\n",
    ],
)
def test_show_reports_a_bad_descriptions_file_as_a_problem_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    path = _write_map(tmp_path)
    (tmp_path / ".periplus" / "descriptions.yaml").write_text(content)

    code, out = _run(capsys, A, path, "json")
    doc = json.loads(out)
    assert code == NOT_A_MAP
    assert len(doc["problems"]) == 1
    assert "descriptions.yaml" in json.dumps(doc["problems"][0])
    assert doc["id"] == A
    assert doc["description"] is None
    assert [r["other"] for r in doc["outgoing"]["items"]] == [B]

    code, text = _run(capsys, A, path, "text")
    assert code == NOT_A_MAP
    assert "php::A" in text
    assert "description: none" in text
