"""The suite runs on every core and prints its durations and header."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _pytest(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
    )


@pytest.mark.criterion(id="c4")
def test_pyproject_lists_xdist_in_dev_extra_and_runs_n_auto_with_durations_c4() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = data["project"]["optional-dependencies"]["dev"]
    assert any(d.lower().startswith("pytest-xdist") for d in dev), dev
    addopts = data["tool"]["pytest"]["ini_options"]["addopts"].split()
    assert "-n" in addopts and addopts[addopts.index("-n") + 1] == "auto", addopts
    assert any(a.startswith("--durations") for a in addopts), addopts
    assert "-q" not in addopts, addopts


@pytest.mark.criterion(id="c1")
def test_collect_only_counts_at_least_584_tests_c1() -> None:
    run = _pytest(["-o", "addopts=", "--collect-only", "-q", str(ROOT / "tests")], ROOT)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-1000:]
    total = sum(1 for line in run.stdout.splitlines() if "::" in line)
    assert total >= 584, f"collected {total}"


RUNTIME_DEPENDENCIES = [
    "ruamel.yaml==0.19.1",
    "platformdirs==4.11.5",
    "jsonschema==4.26.0",
    "tree-sitter==0.26.0",
    "tree-sitter-php==0.24.1",
]


def test_runtime_dependencies_unchanged_and_xdist_only_in_dev_extra_wo1() -> None:
    now = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert now["dependencies"] == RUNTIME_DEPENDENCIES, (
        RUNTIME_DEPENDENCIES,
        now["dependencies"],
    )
    runner = ("pytest-xdist", "execnet")
    held = {"dependencies": now["dependencies"]}
    for name, deps in now.get("optional-dependencies", {}).items():
        if name != "dev":
            held[name] = deps
    for where, deps in held.items():
        found = [d for d in deps if d.lower().startswith(runner)]
        assert not found, (where, found)
