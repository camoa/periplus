"""``periplus validate`` outside a project reports the collisions ``periplus map`` refuses.

A rutter that declares a settings value named like one of its own rule captures collides in every
project. ``validate`` from a folder with no settings holds no value, so it must read the collision
from the manifest's declared names. Every test calls ``periplus.cli.main`` in process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_validate import Project, project  # noqa: F401 - fixture
from test_validate_engine_checks import _call, _edit, _fixture, _pin, _problems


@pytest.mark.criterion(id="c1")
def test_a_declared_value_named_like_a_rule_capture_is_refused_outside_a_project_c1(
    project: Project,  # noqa: F811
) -> None:
    user_packs = project.config / "packs"
    user_packs.mkdir()
    pack = _fixture(user_packs, "collidefix")
    _edit(
        pack,
        Path("pack.yaml"),
        "depends:",
        "values:\n  name: A value named like the capture the command rule makes.\ndepends:",
    )
    _pin(project, "collidefix", 'values:\n  name: "x"\n')
    bare = project.root.parent / "bare"
    bare.mkdir()

    map_status, mapped = _call(["map"], cwd=project.root, config=project.config)
    status, validated = _call(["validate", "collidefix"], cwd=bare, config=project.config)

    assert map_status != 0, mapped
    assert status == map_status
    assert {code for code, _ in _problems(validated)} == {code for code, _ in _problems(mapped)}
