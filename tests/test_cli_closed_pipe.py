"""A command whose standard output is closed early, as ``| head`` does, ends quietly with 141."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node

from periplus.cli import main
from periplus.errors import ExitCode


def test_a_closed_pipe_ends_with_141_and_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes = [_node(f"x::n{i}", line=1) for i in range(200)]
    edges = [_edge("calls", f"x::n{i}", f"x::n{i + 1}", 1) for i in range(199)]
    path = tmp_path / "map.json"
    path.write_text(json.dumps(_document(nodes, edges)), encoding="utf-8")
    read, write = os.pipe()
    os.close(read)
    stream = io.TextIOWrapper(os.fdopen(write, "wb"), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", stream)

    assert main(["find", "x::", "--limit", "0", "--map", str(path)]) == ExitCode.OUTPUT_CLOSED
    # What is left in the buffer goes nowhere, so the flush at the interpreter's exit is quiet.
    stream.write("more\n")
    stream.flush()
    stream.close()
