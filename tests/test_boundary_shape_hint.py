"""A boundary block the manifest schema refuses names the shape to write, at the refusal."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_boundary import BOUNDARY, SHAPE, _run

from periplus.errors import ExitCode

OLD_KEYS = (
    "boundary:\n  applies_to_paths: [vendor/**]\n  emit_boundary_nodes: on_reference\n"
    "  type_hierarchy: [{type: Fw}]\n"
)


@pytest.mark.parametrize(
    "boundary",
    [
        OLD_KEYS,
        BOUNDARY.replace("    ancestry: [inherits]\n", ""),
        BOUNDARY.split("    names:\n")[0],
    ],
    ids=["old-keys", "no-ancestry", "no-names"],
)
def test_a_schema_refused_boundary_names_the_working_shape(tmp_path: Path, boundary: str) -> None:
    report = _run(tmp_path, boundary=boundary)
    assert report.exit_code == ExitCode.SCHEMA_INVALID, report.problems
    assert report.map_path is None
    refused = [p for p in report.problems if p.detail.get("pointer", "").startswith("$.boundary")]
    assert refused, report.problems
    for problem in refused:
        assert problem.message.endswith(f"; write {SHAPE}"), problem.message
