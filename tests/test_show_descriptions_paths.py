"""periplus show finds the descriptions of the project the --map file sits in."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_show_descriptions import DESCRIPTIONS, NODE_LINE, A, _run, _write_map


@pytest.mark.criterion(id="c7")
def test_show_finds_the_project_of_a_relative_slice_and_of_another_projects_map_c7(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    here, other = tmp_path / "here", tmp_path / "other"
    for root in (here, other):
        root.mkdir()
        _write_map(root)
    (here / ".periplus" / "descriptions.yaml").write_text(DESCRIPTIONS)
    (here / "web").mkdir()
    shutil.copyfile(here / ".periplus" / "map.json", here / "web" / "slice.json")
    monkeypatch.chdir(here / "web")

    code, text = _run(capsys, A, Path("slice.json"), "text")
    assert code == 0, text
    assert NODE_LINE in [ln.strip() for ln in text.splitlines()], text

    monkeypatch.chdir(other)
    code, text = _run(capsys, A, here / ".periplus" / "map.json", "text")
    assert code == 0, text
    assert NODE_LINE in [ln.strip() for ln in text.splitlines()], text
