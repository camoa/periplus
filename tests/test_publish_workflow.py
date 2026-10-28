"""The tag-triggered publish workflow."""

import re
from collections.abc import Iterator
from typing import Any

import pytest
from ruamel.yaml import YAML
from test_packaging import PROJECT_ROOT

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
PUBLISH = WORKFLOWS / "publish.yml"
CHECKS = WORKFLOWS / "checks.yml"
UV_PIN = re.compile(r"uv==([\w.]+)")


def _load(path: Any) -> dict[str, Any]:
    loaded: dict[str, Any] = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    return loaded


def _strings(node: Any) -> Iterator[str]:
    """Every key and scalar value in a parsed YAML tree, as text."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item)
    elif node is not None:
        yield str(node)


def _uv_pins(steps: list[dict[str, Any]]) -> set[str]:
    return {pin for s in steps for pin in UV_PIN.findall(str(s.get("run", "")))}


@pytest.mark.criterion(id="c2")
def test_publish_runs_only_on_a_version_tag_with_no_stored_credential_c2() -> None:
    workflow = _load(PUBLISH)
    assert workflow["on"] == {"push": {"tags": ["v*"]}}, workflow["on"]

    jobs = workflow["jobs"]
    build, publish = jobs["build"], jobs["publish"]
    assert publish["environment"] == "pypi"
    assert publish["permissions"].get("id-token") == "write"
    assert "id-token" not in build.get("permissions", {}), "build job can mint a token"

    for text in _strings(workflow):
        lowered = text.lower().replace("id-token", "")
        for word in ("secret", "password", "token"):
            assert word not in lowered, f"{word!r} in {text!r}"

    build_runs = [str(s.get("run", "")) for s in build["steps"]]
    assert any("uv build --no-sources" in run for run in build_runs), build_runs
    checks = [s for s in build["steps"] if s.get("id") == "check-version"]
    assert len(checks) == 1, "no single check-version step in the build job"
    assert "GITHUB_REF_NAME" in checks[0]["run"]
    assert "tomllib" in checks[0]["run"]

    checks_pins = _uv_pins(_load(CHECKS)["jobs"]["tests"]["steps"])
    assert len(checks_pins) == 1, f"checks.yml uv pins: {checks_pins}"
    for name, job in jobs.items():
        assert _uv_pins(job["steps"]) == checks_pins, f"{name} job uv pin differs"

    uses = [s["uses"] for job in jobs.values() for s in job["steps"] if "uses" in s]
    assert uses, "no action is used"
    for value in uses:
        assert value.startswith("actions/"), f"not a GitHub-owned action: {value}"
        assert re.fullmatch(r"actions/[\w.-]+@\S+", value), f"not pinned: {value}"
