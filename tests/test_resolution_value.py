"""A pack may not give the resolution mark a value the map schema rejects (c4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from _own_pack import plant

from periplus.cli import main

RULES = """\
node_types:
- name: own.call_site
  id_namespace: own.call_site
rules:
- rule: call_site_from_call
  reads: file
  in:
  - source
  match:
    declaration: member_call_expression
    name_child: name
    filetype: php
  id:
    from: declared_name
  emits:
  - node:
      type: own.call_site
  - attribute:
      name: resolution
      template: static
  confidence: declared
"""


@pytest.mark.criterion(id="c4")
def test_validate_refuses_a_resolution_value_other_than_runtime_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plant(tmp_path, RULES)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-home"))
    assert main(["validate", "own@0.0.1"]) != 0


TEXT_RULES = """\
node_types:
- name: own.note
  id_namespace: own.note
rules:
- rule: note_from_text
  reads: file
  in:
  - source
  match:
    file: '*.txt'
    filetype: note
    text: 'go (?<name>\\\\w+)'
  id:
    from:
      capture: name
  emits:
  - node:
      type: own.note
  - attribute:
      name: resolution
      template: '{name}'
  confidence: declared
"""


@pytest.mark.criterion(id="c4")
def test_a_text_rule_may_not_fill_the_resolution_mark_from_a_capture_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plant(tmp_path, TEXT_RULES)
    (tmp_path / "src/note.txt").write_text("go static\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-home"))
    assert main(["validate", "own@0.0.1"]) != 0
    code = main(["map", "--output", "bad.json"])
    seen = capsys.readouterr()
    assert code != 0
    assert "'runtime' was expected" in seen.out + seen.err
    assert not (tmp_path / "bad.json").exists()
