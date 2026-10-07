"""Packaging requirements, as tests.

These assert the things a person would otherwise have to check by hand after every change to
``pyproject.toml``: that the version is written in one place, that the dependency posture
intended is the posture the manifest declares, and that the wheel actually carries the
pack data. The last one is settled here by listing a
built wheel rather than by trusting a build backend's documented behaviour.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Resolved once, to an absolute path, rather than passed as the bare name "uv".
#
# This does NOT remove trust in PATH, and an earlier comment here claimed it did — shutil.which
# performs the same PATH lookup execvp would, and returns the same program. What it actually buys
# is worth less but is real: every call in a run uses one resolved binary rather than re-resolving
# per call, a missing uv becomes an explicit failure with a message instead of a FileNotFoundError
# out of exec, and ruff's S607 is answered by fact rather than by a suppression.
UV = shutil.which("uv")

# The five packs the wheel must carry, with the versions their own manifests declare, mapped to
# the number of files each one holds. Written out rather than derived from the directory listing:
# a test that reads the same directory it is checking would pass against an empty one.
#
# Per pack rather than one total. A single total of 69 is held constant by any swap anywhere:
# add `credentials.yaml` under a pack, delete one real pack file, and the credential ships with
# a single total still green. Counting per pack narrows that — the deletion now has to come out
# of the same pack as the addition, which pairs the two lines in the diff a reviewer reads.
#
# It does not close it, and counting cannot. A balanced swap holds any count at any granularity:
# inside one pack, or across two category directories of one pack. Nor does an addition at least
# force a `git rm` a reviewer cannot read past. A `git mv` to `credentials.yaml` with a token
# appended renders as `{cache_backend.yaml => credentials.yaml} | 1 +` with no deletion line at
# all, and appending a token to an existing pack file changes no path whatsoever.
#
# So state the limit plainly: these assertions bound the SET of pack files that ship. They do not
# bound the CONTENT of any of them, at all. A payload inside a file whose path is expected is
# invisible here and cannot be made visible by any further path or count assertion — the append
# case changes nothing about the paths. Catching that is pack-schema validation in the loader,
# where a file whose top-level keys are not pack vocabulary fails to load; it is deferred there
# deliberately rather than approximated here.
BUNDLED_PACKS = {
    "advancedqueue_basic@0.0.1": 4,
    "ai_basic@0.0.1": 5,
    "config_pages_basic@0.0.1": 2,
    "crop_basic@0.0.1": 2,
    "drupal@0.1.0": 48,
    "drupal_basic@0.3.0": 78,
    "drupal_js_basic@0.0.1": 10,
    "drush_basic@0.0.1": 4,
    "eck_basic@0.0.1": 3,
    "go@0.0.2": 4,
    "go_basic@0.0.3": 5,
    "js_basic@0.0.1": 2,
    "laravel_basic@0.0.5": 6,
    "paragraphs_basic@0.0.1": 2,
    "php@0.1.0": 12,
    "php_basic@0.2.0": 6,
    "profile_basic@0.0.1": 2,
    "salesforce_basic@0.0.1": 6,
    "twig@0.0.1": 2,
    "twig_basic@0.1.0": 1,
    "twig_tweak_basic@0.0.1": 5,
    "webform_basic@0.0.1": 4,
    "yaml@0.0.1": 3,
    "yaml_basic@0.1.0": 1,
}

# Everything the wheel may carry under periplus/ that is not pack data: the modules, and the two
# data files that sit beside them -- the PEP 561 marker and the settings stub `init` writes.
# Declared, so that a file which is neither a module nor a pack cannot ride along unnoticed —
# a fake PyPI token as src/periplus/deploy_notes.txt reaches the wheel, and a check that only
# looks inside packs/ passes. Adding a module means adding it here,
# which is the review moment this exists to create.
EXPECTED_MODULE_FILES = {
    "periplus/__init__.py",
    "periplus/cli.py",
    "periplus/detect.py",
    "periplus/errors.py",
    "periplus/manifest.py",
    "periplus/packs.py",
    "periplus/preflight.py",
    "periplus/report.py",
    "periplus/resolution.py",
    "periplus/settings.py",
    "periplus/spec.py",
    "periplus/py.typed",
    "periplus/settings.stub.yml",
    "periplus/init.py",
    "periplus/layout.py",
    "periplus/map.py",
    "periplus/engine/__init__.py",
    "periplus/engine/emit.py",
    "periplus/engine/packload.py",
    "periplus/engine/rules.py",
    "periplus/engine/pattern.py",
    "periplus/engine/check.py",
    "periplus/engine/select.py",
    "periplus/engine/source.py",
    "periplus/engine/tree.py",
    "periplus/validate.py",
    "periplus/update.py",
}

# The contract, which is data the way the packs are data: four JSON Schemas that define what a
# pack is and two prose specs an author builds against. Declared for the same reason the modules
# are — a seventh file under contract/ has to be admitted here before it can reach a user — and
# kept as its own set rather than folded into EXPECTED_MODULE_FILES, because a set holding both
# would stop naming either. `tests/test_contract.py` imports this set and asserts an install
# exposes exactly it, so the archive bound and the installed bound cannot drift apart.
EXPECTED_CONTRACT_FILES = {
    "periplus/contract/schema/map.schema.json",
    "periplus/contract/schema/pack-file.schema.json",
    "periplus/contract/schema/pack-manifest.schema.json",
    "periplus/contract/schema/project-settings.schema.json",
    "periplus/contract/spec/engine.md",
    "periplus/contract/spec/rules.md",
}

# Everything the wheel may carry in its .dist-info directory. Declared for the same reason the
# module files are: a `license-files` glob in pyproject.toml can land a token file at
# periplus_map-0.1.0.dist-info/licenses/, and a wheel-contents check that filters members to
# those under periplus/ never looks at the rest of the archive. The names here are the backend's own
# metadata plus the two license files the manifest's `license-files` names; a third license file, or
# any new metadata entry, has to be admitted here first.
EXPECTED_DIST_INFO_FILES = {
    "METADATA",
    "RECORD",
    "WHEEL",
    "entry_points.txt",
    "licenses/LICENSE",
    "licenses/NOTICE",
}

# Everything the sdist may carry at the root of its extraction directory, alongside src/periplus.
# `.gitignore` and `PKG-INFO` are hatchling's, not the manifest's: the sdist target's `include`
# list names neither, and both arrive anyway, so they are declared as observed rather than as
# expected from reading the manifest.
EXPECTED_SDIST_ROOT_FILES = {
    ".gitignore",
    "LICENSE",
    "NOTICE",
    "PKG-INFO",
    "README.md",
    "pyproject.toml",
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
    # requirement. The only exceptions are the reference packs go and yaml, whose grammars the
    # package does not declare, go_basic, whose grammar is installed with the extra go, and
    # js_basic, whose grammar is installed with the extra js; each must still pin one, so the list
    # cannot outlive its reason.
    undeclared = {"go", "go_basic", "js_basic", "yaml"}
    pinned, excepted = set(), {}
    for path in sorted((PROJECT_ROOT / "src" / "periplus" / "packs").glob("*@*/pack.yaml")):
        document = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
        grammar = document.get("grammar")
        if grammar:
            name = f"{grammar['provider']}-{grammar['language']}"
            if document["pack"] in undeclared:
                excepted[document["pack"]] = name
            else:
                pinned.add(name)

    manifest_names = sorted(
        _normalised(dep.split("==")[0].split(">=")[0].split("[")[0]) for dep in declared
    )
    assert pinned
    assert set(excepted) == undeclared, excepted
    assert not {_normalised(name) for name in excepted.values()} & set(manifest_names), excepted
    assert manifest_names == sorted(_normalised(name) for name in {*REQUIRED, *pinned})
    assert _normalised("jsonschema") in manifest_names
    assert len(REQUIRED) == 4, (
        f"the design decided four start-up distributions, not {len(REQUIRED)}"
    )


def _scripts_dir(venv: Path) -> Path:
    """The directory an installer puts console scripts in, for this platform.

    POSIX puts them in ``bin`` and Windows in ``Scripts``. Hardcoding ``bin`` makes a test that
    cannot run on a platform this project declares support for — and the design justifies the
    platformdirs dependency by exactly that concern, so a test that assumes POSIX contradicts
    its own component's reasoning.
    """
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a fixed argv with no shell. Every caller builds its own list; nothing is interpolated
    into a string, and no value reaches a shell."""
    return subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        argv, capture_output=True, text=True, **kwargs
    )


def _run_or_fail(argv: list[str], what: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command and fail with its stderr rather than with a bare CalledProcessError.

    ``check=True`` alongside ``capture_output=True`` discards the output on failure, so a run
    with no network reported three install tests failing and said nothing about why. The cause
    belongs in the failure message.
    """
    result = _run(argv, check=False, **kwargs)
    if result.returncode != 0:
        pytest.fail(f"{what} failed with status {result.returncode}\n{result.stderr}")
    return result


def _assert_periplus_on_path(venv: Path, expected_version: str, how: str) -> None:
    """Assert an install put ``periplus`` on the PATH of ``venv`` and that it prints the version.

    ``shutil.which`` against that venv's script directory is the part that makes this an
    assertion about PATH rather than about a file existing at a path we constructed. A test that
    builds the script's absolute path and runs it proves the file is there; it never shows that
    installing put it somewhere a shell would find.
    """
    scripts = _scripts_dir(venv)
    found = shutil.which("periplus", path=str(scripts))
    assert found is not None, (
        f"{how}: periplus is not on the PATH of {scripts}; "
        f"that directory holds {sorted(p.name for p in scripts.iterdir())[:12]}"
    )

    result = _run([found, "--version"], check=False)
    assert result.returncode == 0, f"{how}: {result.stderr}"
    # Exact, not a substring. `expected in stdout` passes for any output that merely contains
    # the number, including a future banner that prints a different version alongside it.
    assert result.stdout.strip() == expected_version, f"{how}: printed {result.stdout!r}"


@pytest.mark.slow
def test_pip_install_puts_the_command_on_the_path(
    manifest: dict[str, object], tmp_path: Path
) -> None:
    """``pip install -e .`` into a fresh venv puts ``periplus`` on that venv's PATH.

    One of the three supported install paths. Each gets its own venv under ``tmp_path``
    so the run leaves nothing behind and cannot pass because of an earlier install.
    """
    project = manifest["project"]
    assert isinstance(project, dict)

    venv = tmp_path / "pipenv"
    _run_or_fail([sys.executable, "-m", "venv", str(venv)], "python -m venv")
    python = _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")
    _run_or_fail(
        [str(python), "-m", "pip", "install", "-q", "-e", str(PROJECT_ROOT)], "pip install -e ."
    )

    _assert_periplus_on_path(venv, str(project["version"]), "pip install -e .")


@pytest.mark.slow
def test_uv_pip_install_puts_the_command_on_the_path(
    manifest: dict[str, object], tmp_path: Path
) -> None:
    """``uv pip install -e .`` into a fresh venv puts ``periplus`` on that venv's PATH."""
    if UV is None:
        pytest.fail("uv is not on PATH, so this install path cannot be exercised")
    project = manifest["project"]
    assert isinstance(project, dict)

    venv = tmp_path / "uvenv"
    _run_or_fail([UV, "venv", str(venv)], "uv venv")
    python = _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")
    _run_or_fail(
        [UV, "pip", "install", "--python", str(python), "-e", str(PROJECT_ROOT)],
        "uv pip install -e .",
    )

    _assert_periplus_on_path(venv, str(project["version"]), "uv pip install -e .")


@pytest.mark.slow
def test_uv_tool_install_puts_the_command_on_the_path(
    manifest: dict[str, object], tmp_path: Path
) -> None:
    """``uv tool install .`` puts ``periplus`` on the tool bin directory's PATH.

    Redirected into ``tmp_path`` through ``UV_TOOL_DIR`` and ``UV_TOOL_BIN_DIR`` rather than
    installing into the developer's real ``~/.local/bin``. A test that writes into the machine
    running it is one people learn to skip.
    """
    if UV is None:
        pytest.fail("uv is not on PATH, so this install path cannot be exercised")
    project = manifest["project"]
    assert isinstance(project, dict)

    bin_dir = tmp_path / "toolbin"
    env = {
        **os.environ,
        "UV_TOOL_DIR": str(tmp_path / "tools"),
        "UV_TOOL_BIN_DIR": str(bin_dir),
    }
    _run_or_fail([UV, "tool", "install", str(PROJECT_ROOT)], "uv tool install .", env=env)

    found = shutil.which("periplus", path=str(bin_dir))
    assert found is not None, (
        f"uv tool install: periplus is not on the PATH of {bin_dir}; "
        f"it holds {sorted(p.name for p in bin_dir.iterdir()) if bin_dir.exists() else 'nothing'}"
    )
    result = _run([found, "--version"], check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(project["version"])


def test_main_returns_rather_than_exiting() -> None:
    """``main`` returns an integer for a normal invocation and never calls ``sys.exit``.

    The entrypoint contract turns exception classes into exit codes in one place; a ``main`` that
    exits from inside would make every one of those paths untestable except through SystemExit.
    """
    from periplus.cli import main

    assert main(["--version"]) == 0


def _pack_file_counts(paths: set[str], prefix: str) -> dict[str, int]:
    """Group archive member names under ``prefix`` into a pack name -> file count map.

    Comparing this against ``BUNDLED_PACKS`` asserts three things at once, which is why the
    callers use it instead of a length: that no undeclared pack directory appears, that no
    declared one vanished, and that each pack holds exactly the number of files it was declared
    to hold.
    """
    return dict(Counter(path.removeprefix(prefix).split("/", 1)[0] for path in paths))


def _assert_pack_data_is_bounded(paths: set[str], prefix: str, artifact: str) -> None:
    """Assert the pack files an artifact ships are how many, where and what they were declared
    to be.

    Shared by the wheel and the sdist, because they are two artifacts built from two ``include``
    lists and a file that reaches only one of them still reaches users. Three assertions, each
    bounding a different thing, because no one of them is sufficient alone.

    All three bound the set of paths that ship and none of them reads a byte of any file. Content
    is out of scope here and is the pack loader's schema validation to catch — see the note on
    BUNDLED_PACKS for the bypasses that follow from that, none of which these assertions can see.
    """
    # How many, per pack. An addition with no matching deletion fails here, and a deletion with
    # no matching addition fails here. A balanced swap inside one pack does not — see the note on
    # BUNDLED_PACKS — so what this buys is that the swap must `git rm` a real file out of the same
    # pack, which is a deletion a reviewer sees beside the addition.
    counts = _pack_file_counts(paths, prefix)
    assert counts == BUNDLED_PACKS, (
        f"the {artifact}'s pack files are {counts}, expected {BUNDLED_PACKS}. If a pack "
        "legitimately gained or lost a file, update that pack's count deliberately."
    )

    # Where. A pack's root directory holds its manifest and nothing else; every rule file lives in
    # a category directory below it. That is how all five packs are actually built, and it is the
    # assertion that catches the obvious plant — `credentials.yaml` dropped beside
    # `pack.yaml`, one real file deleted to hold the count — which the counts alone let through.
    # No depth is fixed below the category, so a pack that grows a nested directory still passes.
    at_pack_root = sorted(
        path
        for path in paths
        if path.removeprefix(prefix).count("/") == 1 and not path.endswith("/pack.yaml")
    )
    assert at_pack_root == [], (
        f"{at_pack_root} sit at a pack's root in the {artifact}, where only pack.yaml belongs; "
        "rule files live in a category directory below it"
    )

    # What. Pack data is YAML, so a shipped file that is not YAML is not pack data whatever
    # directory it sits in. A payload has to be renamed to `.yaml` before it can ride along.
    not_yaml = sorted(path for path in paths if not path.endswith(".yaml"))
    assert not_yaml == [], f"the {artifact} ships non-YAML files inside the packs: {not_yaml}"


def _build_wheel(destination: Path) -> Path:
    """Build a wheel into ``destination`` and return its path."""
    if UV is None:
        # Failing rather than skipping is deliberate. Its caller is what settles whether the
        # wheel carries the pack data, which the design recorded as its one unverified
        # assumption. A silent skip would leave it unverified while the suite reported green.
        pytest.fail("uv is not on PATH, so the wheel-contents assumption cannot be settled")
    _run_or_fail(
        [UV, "build", "--wheel", "--out-dir", str(destination)],
        "uv build --wheel",
        cwd=PROJECT_ROOT,
    )
    wheels = sorted(destination.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {[w.name for w in wheels]}"
    return wheels[0]


def _build_sdist(destination: Path) -> Path:
    """Build a source distribution into ``destination`` and return its path."""
    if UV is None:
        # Fails rather than skips, for the same reason the wheel builder does: the sdist is the
        # artifact PyPI serves to anyone whose platform has no wheel, so leaving its contents
        # unchecked while reporting green is the failure mode this whole file exists to avoid.
        pytest.fail("uv is not on PATH, so the sdist contents cannot be checked")
    _run_or_fail(
        [UV, "build", "--sdist", "--out-dir", str(destination)],
        "uv build --sdist",
        cwd=PROJECT_ROOT,
    )
    sdists = sorted(destination.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, found {[s.name for s in sdists]}"
    return sdists[0]


def _artifact_stem(manifest: dict[str, object]) -> str:
    """The escaped ``name-version`` stem both artifacts build their internal paths from.

    Derived from the declared name and version rather than written out, so a version bump does
    not turn these into tests that have to be edited before they can pass. The escaping rule is
    the packaging formats' own: runs of ``-``, ``_`` and ``.`` collapse to a single ``_``.
    """
    project = manifest["project"]
    assert isinstance(project, dict)
    escaped = re.sub(r"[-_.]+", "_", str(project["name"]))
    return f"{escaped}-{project['version']}"


def test_the_wheel_carries_exactly_the_declared_modules_packs_and_metadata(
    manifest: dict[str, object], tmp_path: Path
) -> None:
    """Every member of the built wheel is a declared module, declared pack data, the declared
    contract, or declared ``.dist-info`` metadata — and every bundled pack arrives whole.

    One build, five things asserted off it, because ``uv build --wheel`` is the expensive part and
    each family of assertions bounds a different way a file reaches users.

    *Nothing outside the package or the metadata.* Filtering the archive to members under
    ``periplus/`` bounds the package and says nothing about the rest of the file. A
    ``license-files`` glob in ``pyproject.toml`` can place a token file at
    ``periplus_map-0.1.0.dist-info/licenses/``, outside such a filter. So the partition starts from
    the whole namelist, there are two categories and no third, and the second is enumerated — which
    is what makes a new metadata file, or a second file swept in by a widened license glob, a
    failure rather than a silent inclusion.

    *The packs and the typing marker are there at all.* This is the design's one unverified
    assumption, and it has two halves. Whether hatchling ships a directory under the package as
    data at all, and whether an ``@`` in that directory's name survives the wheel's own path
    handling. Both are settled by listing the archive.

    *The pack data is complete, not just the manifests.* A build backend that ships one file per
    directory and drops the rest would satisfy the manifest check above and leave the packs
    unusable, so what is on disk is counted against what is in the archive.

    *The contract ships, and only the contract.* The four schemas and two specs are data with no
    Python beside it, so nothing imports them and no import error would announce their absence.
    Enumerating them here is what makes a dropped schema a failed build rather than a wheel that
    installs fine and cannot tell a pack author what a pack is.

    *Nothing rides along beside the modules.* That is where a stray file next to ``__init__.py``
    lands — and where a fake PyPI token is invisible to a check that looks only at packs.

    ``tmp_path`` keeps the build output out of the tree and is torn down for us, so a failed run
    leaves no wheel behind to be picked up by the next one.
    """
    wheel = _build_wheel(tmp_path)
    dist_info = f"{_artifact_stem(manifest)}.dist-info"

    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]

    outside = sorted(
        name
        for name in names
        if not name.startswith("periplus/") and not name.startswith(f"{dist_info}/")
    )
    assert outside == [], (
        f"the wheel carries {outside}, which is neither package content nor {dist_info} metadata"
    )

    shipped_metadata = {
        name.removeprefix(f"{dist_info}/") for name in names if name.startswith(f"{dist_info}/")
    }
    assert shipped_metadata == EXPECTED_DIST_INFO_FILES, (
        f"{dist_info} carries {sorted(shipped_metadata - EXPECTED_DIST_INFO_FILES)} beyond the "
        f"declared metadata, and is missing {sorted(EXPECTED_DIST_INFO_FILES - shipped_metadata)}"
    )

    assert "periplus/py.typed" in names

    for pack in sorted(BUNDLED_PACKS):
        manifest_path = f"periplus/packs/{pack}/pack.yaml"
        assert manifest_path in names, (
            f"{manifest_path} is missing from the wheel; "
            f"the archive holds {sorted(n for n in names if n.startswith('periplus/packs/'))[:5]}"
        )

    in_wheel = {name for name in names if name.startswith("periplus/packs/")}
    packs_dir = PROJECT_ROOT / "src" / "periplus" / "packs"
    on_disk = {
        f"periplus/packs/{path.relative_to(packs_dir).as_posix()}"
        for path in packs_dir.rglob("*")
        if path.is_file()
    }

    assert on_disk, "no pack files found on disk; the fixture itself is wrong"
    assert on_disk == in_wheel

    # Set equality above catches a build that DROPS pack files. It cannot catch one that ADDS a
    # file, because both sides are built from the same directory — a stray secrets file dropped
    # under packs/ ships in the wheel while this test passes. The helper is what bounds an addition,
    # in three ways at once.
    _assert_pack_data_is_bounded(in_wheel, "periplus/packs/", "wheel")

    in_contract = {name for name in names if name.startswith("periplus/contract/")}
    assert in_contract == EXPECTED_CONTRACT_FILES, (
        f"the wheel carries {sorted(in_contract - EXPECTED_CONTRACT_FILES)} beyond the declared "
        f"contract, and is missing {sorted(EXPECTED_CONTRACT_FILES - in_contract)}"
    )

    beyond_packs = {name for name in names if name.startswith("periplus/")} - in_wheel - in_contract
    assert beyond_packs == EXPECTED_MODULE_FILES, (
        f"the wheel carries {sorted(beyond_packs - EXPECTED_MODULE_FILES)} beyond the declared "
        f"modules, and is missing {sorted(EXPECTED_MODULE_FILES - beyond_packs)}"
    )


def test_the_sdist_carries_exactly_the_source_tree_and_the_root_files(
    manifest: dict[str, object], tmp_path: Path
) -> None:
    """Every member of the sdist is a declared root file, a module, pack data, or the contract.

    The sdist was covered by nothing. It is a second artifact built from a second ``include``
    list, PyPI serves it to anyone installing from source, and until this test every assertion in
    this file was about the wheel — so a file that reached only the sdist reached users without
    ever being looked at. Same shape as the wheel checks on purpose: a declared expectation, so a
    new file has to be admitted here before it can ship.

    ``isfile`` is asserted per member rather than assumed. A tar can carry symlinks, hardlinks and
    device nodes, and a name-only check reads a symlink as an ordinary file; the prefix check
    below is likewise the guard against a member whose path escapes the extraction directory.
    """
    sdist = _build_sdist(tmp_path)
    prefix = _artifact_stem(manifest)

    with tarfile.open(sdist) as archive:
        members = archive.getmembers()

    irregular = sorted(m.name for m in members if not m.isfile())
    assert irregular == [], f"the sdist carries non-regular members: {irregular}"

    escaping = sorted(m.name for m in members if not m.name.startswith(f"{prefix}/"))
    assert escaping == [], f"the sdist carries members outside {prefix}/: {escaping}"

    inside = {m.name.removeprefix(f"{prefix}/") for m in members}
    packs = {name for name in inside if name.startswith("src/periplus/packs/")}
    contract = {name for name in inside if name.startswith("src/periplus/contract/")}
    modules = {name for name in inside if name.startswith("src/periplus/")} - packs - contract
    root = inside - packs - modules - contract

    assert root == EXPECTED_SDIST_ROOT_FILES, (
        f"the sdist carries {sorted(root - EXPECTED_SDIST_ROOT_FILES)} beyond the declared root "
        f"files, and is missing {sorted(EXPECTED_SDIST_ROOT_FILES - root)}"
    )
    expected_contract = {f"src/{name}" for name in EXPECTED_CONTRACT_FILES}
    assert contract == expected_contract, (
        f"the sdist carries {sorted(contract - expected_contract)} beyond the declared contract, "
        f"and is missing {sorted(expected_contract - contract)}"
    )
    expected_modules = {f"src/{name}" for name in EXPECTED_MODULE_FILES}
    assert modules == expected_modules, (
        f"the sdist carries {sorted(modules - expected_modules)} beyond the declared modules, "
        f"and is missing {sorted(expected_modules - modules)}"
    )
    _assert_pack_data_is_bounded(packs, "src/periplus/packs/", "sdist")


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
    """The three runtime distributions, and exactly the transitive closure the decision bought.

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
