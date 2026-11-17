"""Packaging requirements, as tests.

These assert the things a person would otherwise have to check by hand after every change to
``pyproject.toml``: that the version is written in one place, that the dependency posture
intended is the posture the manifest declares.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# The contract, which is data the way the packs are data: four JSON Schemas that define what a
# pack is and two prose specs an author builds against. `tests/test_contract.py` imports this set.
EXPECTED_CONTRACT_FILES = {
    "periplus/contract/schema/map.schema.json",
    "periplus/contract/schema/navigation.schema.json",
    "periplus/contract/schema/pack-file.schema.json",
    "periplus/contract/schema/pack-manifest.schema.json",
    "periplus/contract/schema/project-settings.schema.json",
    "periplus/contract/spec/engine.md",
    "periplus/contract/spec/rules.md",
}


@pytest.fixture(scope="session")
def manifest() -> dict[str, object]:
    """The parsed ``pyproject.toml``, which is the authority every test here compares against."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_distribution_name_is_declared_once(manifest: dict[str, object]) -> None:
    """``periplus.DISTRIBUTION`` names the distribution ``pyproject.toml`` declares.

    The two are written in different files and nothing but this test makes them agree. A rename
    that updates one and not the other makes ``importlib.metadata.version`` raise at runtime for
    a package that installed perfectly.
    """
    import periplus

    project = manifest["project"]
    assert isinstance(project, dict)
    assert project["name"] == periplus.DISTRIBUTION


def test_version_comes_from_the_manifest_and_is_not_written_twice(
    manifest: dict[str, object],
) -> None:
    """``periplus.__version__`` resolves to the version ``pyproject.toml`` declares."""
    import periplus

    project = manifest["project"]
    assert isinstance(project, dict)
    assert periplus.__version__ == project["version"]


def _normalised(name: str) -> str:
    """One distribution name, in the single form both sides of the comparison below are put into.

    Lowercased with ``-`` mapped to ``.``, which is what makes ``ruamel.yaml`` and ``ruamel-yaml``
    compare equal — PEP 503 treats ``-``, ``_`` and ``.`` as the same character in a distribution
    name, and the two files spell this one differently.
    """
    return name.strip().lower().replace("-", ".").replace("_", ".")


def test_runtime_dependencies_are_exactly_the_three_the_design_decided(
    manifest: dict[str, object],
) -> None:
    """The list the package hardcodes and the list the manifest declares are the same three names.

    **The number changed from two to three, and the name of this test changed with it**, because
    the name is part of the record: patching the literal would have left the file claiming a
    posture the project no longer holds. ``jsonschema`` is the third, decided by the user before
    design — ``periplus validate`` and the CI step both need a validator, and a fail-closed subset
    validator of our own would produce a verdict that agrees with a reference implementation only
    as far as our implementation is correct.

    ``preflight.REQUIRED`` is the half that matters most. It is the list the startup check reads,
    and a distribution missing from it kills the process with an ``ImportError`` instead of exiting
    9 naming it — the one failure ``preflight.py`` exists to prevent.
    """
    project = manifest["project"]
    assert isinstance(project, dict)
    declared = project["dependencies"]
    assert isinstance(declared, list)

    from ruamel.yaml import YAML

    from periplus.preflight import REQUIRED

    # The grammar a bundled rutter pins is declared by the package and is not a start-up
    # requirement.
    pinned: set[str] = set()
    for path in sorted((PROJECT_ROOT / "src" / "periplus" / "packs").glob("*@*/pack.yaml")):
        document = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
        grammar = document.get("grammar")
        if grammar:
            pinned.add(f"{grammar['provider']}-{grammar['language']}")

    manifest_names = sorted(
        _normalised(dep.split("==")[0].split(">=")[0].split("[")[0]) for dep in declared
    )
    assert pinned
    assert manifest_names == sorted(_normalised(name) for name in {*REQUIRED, *pinned})
    assert _normalised("jsonschema") in manifest_names
    assert len(REQUIRED) == 4, (
        f"the design decided four start-up distributions, not {len(REQUIRED)}"
    )


def test_main_returns_rather_than_exiting() -> None:
    """``main`` returns an integer for a normal invocation and never calls ``sys.exit``.

    The entrypoint contract turns exception classes into exit codes in one place; a ``main`` that
    exits from inside would make every one of those paths untestable except through SystemExit.
    """
    from periplus.cli import main

    assert main(["--version"]) == 0


#: Everything ``jsonschema`` pulls behind it, measured with ``uv pip install jsonschema==4.26.0``
#: on 2026-09-02: six distributions resolved, of which these five are the new transitive closure.
#: ``rpds-py`` is a compiled Rust extension, which is why the lock grows per-platform wheel entries
#: rather than one line.
EXPECTED_JSONSCHEMA_CLOSURE = {
    "attrs",
    "jsonschema-specifications",
    "referencing",
    "rpds-py",
    "typing-extensions",
}


def test_lockfile_confirms_the_runtime_closure_the_validator_decision_grew() -> None:
    """The seven runtime distributions, and exactly the transitive closure the decision bought.

    **This test used to be called ``..._is_two_packages`` and asserted that every runtime
    dependency had zero transitive dependencies.** Its own failure message said that posture was
    "a recorded decision, so this is a design question rather than a lockfile update", and a design
    question is exactly what it became: ``jsonschema`` brings five distributions, one of them a
    compiled extension. The name and the assertion are rewritten to the decision now in force
    rather than patched to keep the old one passing.

    What survives is the guard, narrowed rather than dropped. ``platformdirs`` and ``ruamel-yaml``
    still pull nothing, and ``jsonschema``'s closure is pinned to the five that were measured — so
    a version bump that adds a sixth fails here rather than on somebody's unlucky install.

    The install on one machine only shows what that machine resolved. ``uv.lock`` resolves for
    every platform the project supports, so it is where a closure is actually checkable.
    """
    with (PROJECT_ROOT / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)

    # Grouped, not keyed. uv.lock declares resolution-markers, so one name can legitimately
    # appear more than once with different markers; a dict comprehension keeps only the last
    # entry and would silently check one resolution while reporting green on the other.
    packages: dict[str, list[dict[str, object]]] = {}
    for entry in lock["package"]:
        packages.setdefault(str(entry["name"]), []).append(entry)

    roots = packages["periplus-map"]
    for root in roots:
        deps = root.get("dependencies", [])
        assert isinstance(deps, list)
        assert {dep["name"] for dep in deps} == {
            "jsonschema",
            "platformdirs",
            "ruamel-yaml",
            "tree-sitter",
            "tree-sitter-php",
            "tree-sitter-go",
            "tree-sitter-javascript",
        }

    for name in ("platformdirs", "ruamel-yaml"):
        for entry in packages[name]:
            transitive = entry.get("dependencies", [])
            assert transitive == [], (
                f"{name} {entry['version']} now depends on "
                f"{[d['name'] for d in transitive]}; these two were taken on as zero-transitive "
                f"and only jsonschema's closure was accepted, so this is a design question "
                f"rather than a lockfile update"
            )

    reached: set[str] = set()
    frontier = ["jsonschema"]
    while frontier:
        name = frontier.pop()
        for entry in packages.get(name, []):
            deps = entry.get("dependencies", [])
            assert isinstance(deps, list)
            for dep in deps:
                if dep["name"] not in reached:
                    reached.add(str(dep["name"]))
                    frontier.append(str(dep["name"]))

    assert reached == EXPECTED_JSONSCHEMA_CLOSURE, (
        f"jsonschema's closure is now {sorted(reached)}; it was accepted as "
        f"{sorted(EXPECTED_JSONSCHEMA_CLOSURE)}, so a change here is a design question"
    )


CHECKS_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "checks.yml"


@pytest.mark.criterion(id="wo1")
def test_lockfile_names_periplus_map_at_the_pyproject_version_wo1(manifest: dict) -> None:
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8"))
    ours = [p for p in lock["package"] if p["name"] == "periplus-map"]
    assert [p["version"] for p in ours] == [manifest["project"]["version"]], ours
