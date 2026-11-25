"""A folder value that names a loop of links, and a file no one may read, end ``periplus map`` and
``periplus fresh`` alike with one plain line and exit 20, never a traceback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_demo_a_support import plant

from periplus.cli import main

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  src: ./src
  more: ./loop/**
files:
  types:
    t:
      endings: [t]
      reader: text
"""

RULES = r"""node_types:
- {name: own.word, id_namespace: own.word}
rules:
- rule: word
  reads: file
  in: [src, more]
  match: {file: '*', filetype: t, text: '(?m)^(?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.word}}]
  confidence: declared
"""


@pytest.fixture
def project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Path:
    plant(
        tmp_path,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "src/a.t": "alpha\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-dir"))
    assert main(["map"]) == 0
    capsys.readouterr()
    return tmp_path


def _both(capsys: pytest.CaptureFixture[str]) -> list[tuple[int, str]]:
    """Each command's exit code and the last line it printed."""
    found = []
    for command in ("map", "fresh"):
        code = main([command])
        found.append((code, capsys.readouterr().out.splitlines()[-1]))
    return found


def test_a_folder_value_that_names_a_loop_of_links_is_a_plain_error(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "loop").symlink_to("loop")
    assert _both(capsys) == [
        (20, "  20 folder loop cannot be read: its links lead in a loop"),
        (20, "folder loop cannot be read: its links lead in a loop"),
    ]


@pytest.mark.skipif(os.geteuid() == 0, reason="file permissions do not bind for root")
def test_a_file_no_one_may_read_is_a_plain_error(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "src/a.t").chmod(0)
    try:
        assert _both(capsys) == [
            (20, "  20 src/a.t cannot be read: Permission denied"),
            (20, "src/a.t cannot be read: Permission denied"),
        ]
    finally:
        (project / "src/a.t").chmod(0o644)
