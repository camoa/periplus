"""periplus show reads the project's descriptions file when --map names a slice elsewhere."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_show_descriptions import DESCRIPTIONS, EDGE_LINE, NODE_LINE, A, _run, _write_map


@pytest.mark.criterion(id="c7")
def test_show_on_a_slice_outside_the_map_folder_prints_the_project_entries_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = _write_map(tmp_path)
    (tmp_path / ".periplus" / "descriptions.yaml").write_text(DESCRIPTIONS)
    piece = tmp_path / "feature.map.json"
    shutil.copyfile(path, piece)

    code, text = _run(capsys, A, piece, "text")
    lines = [ln.strip() for ln in text.splitlines()]
    assert code == 0, text
    assert NODE_LINE in lines, text
    assert EDGE_LINE in lines, text
    assert "description: none" not in lines, text
