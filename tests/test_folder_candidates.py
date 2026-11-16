"""`folder_candidates`: a pack's other conventional places for a folder, and what `init` writes.

A pack's `folders` value is its default. When that does not exist in a repository and one of the
pack's candidates does, `init` writes the candidate under `folders` in the settings it creates.
The knowledge of the places is the pack's; the fixture packs here name no real stack.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from periplus.detect import Placement, place_folders
from periplus.init import initialise_project, render_text
from periplus.packs import PackCandidate, PackRoot, discover_candidates
from periplus.preflight import check_runtime_dependencies
from periplus.resolution import folder_overrides, resolve

SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "periplus"
    / "contract"
    / "schema"
    / "pack-manifest.schema.json"
)

MANIFEST = """\
pack: thing
version: 0.1.0
depends: []
folders:
  code: ./lib/code
  deep: "{code}/inner"
folder_candidates:
  code: [src/code, app/code]
"""


def _candidates(tmp_path: Path, manifest: str = MANIFEST) -> tuple[PackCandidate, ...]:
    packs = tmp_path / "packs"
    (packs / "thing@0.1.0").mkdir(parents=True)
    (packs / "thing@0.1.0" / "pack.yaml").write_text(manifest)
    root = PackRoot(kind="project", display=str(packs), traversable=packs, exists=True, source=None)
    return discover_candidates((root,))


def _folders(root: Path) -> dict[str, str | tuple[str, ...]]:
    """The folders the settings file `init` wrote under `root` declares, as `map` reads them."""
    env = {"PERIPLUS_CONFIG_DIR": str(root / "config-dir")}
    resolution = resolve(start=root, env=env, dependencies=check_runtime_dependencies())
    return folder_overrides(resolution.settings)


def _repo(tmp_path: Path, *folders: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for folder in folders:
        (repo / folder).mkdir(parents=True)
    return repo


def test_the_schema_admits_a_list_of_paths_per_folder() -> None:
    schema = json.loads(SCHEMA.read_text())
    valid = {"pack": "thing", "version": "0.1.0", "folder_candidates": {"code": ["src"]}}
    invalid = {"pack": "thing", "version": "0.1.0", "folder_candidates": {"code": "src"}}

    assert list(Draft202012Validator(schema).iter_errors(valid)) == []
    assert list(Draft202012Validator(schema).iter_errors(invalid)) != []


def test_a_missing_default_is_placed_at_the_candidate_that_exists(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "app/code")

    placed = place_folders(repo, _candidates(tmp_path), ["thing@0.1.0"])

    assert placed == (
        Placement("code", "app/code", False, ("./lib/code",), ("src/code", "app/code")),
    )


def test_the_first_candidate_that_exists_wins(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "app/code", "src/code")

    placed = place_folders(repo, _candidates(tmp_path), ["thing@0.1.0"])

    assert [one.path for one in placed] == ["src/code"]


def test_a_default_that_exists_is_kept(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "lib/code", "app/code")

    placed = place_folders(repo, _candidates(tmp_path), ["thing@0.1.0"])

    assert placed == (
        Placement("code", "./lib/code", True, ("./lib/code",), ("src/code", "app/code")),
    )


def test_a_folder_found_nowhere_has_no_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "elsewhere")

    placed = place_folders(repo, _candidates(tmp_path), ["thing@0.1.0"])

    assert placed == (Placement("code", None, False, ("./lib/code",), ("src/code", "app/code")),)


def test_a_candidate_outside_the_repository_is_never_chosen(tmp_path: Path) -> None:
    manifest = MANIFEST.replace("[src/code, app/code]", "[../outside, app/code]")
    (tmp_path / "outside").mkdir()
    repo = _repo(tmp_path, "app/code")

    placed = place_folders(repo, _candidates(tmp_path, manifest), ["thing@0.1.0"])

    assert [one.path for one in placed] == ["app/code"]


def test_init_writes_an_active_folders_block_that_the_settings_read(tmp_path: Path) -> None:
    placed = (Placement("code", "app/code", False, ("./lib/code",), ("src/code", "app/code")),)

    initialise_project(tmp_path, packs=["thing@0.1.0"], placed=placed)

    assert _folders(tmp_path) == {"code": "app/code"}


def test_init_writes_no_folders_block_for_a_kept_default_or_an_unplaced_folder(
    tmp_path: Path,
) -> None:
    placed = (
        Placement("code", "./lib/code", True, ("./lib/code",), ()),
        Placement("other", None, False, ("./x",), ("y",)),
    )

    initialise_project(tmp_path, packs=["thing@0.1.0"], placed=placed)

    assert _folders(tmp_path) == {}


def test_init_prints_each_folder_it_placed_kept_or_could_not_place(tmp_path: Path) -> None:
    placed = (
        Placement("code", "app/code", False, ("./lib/code",), ("src/code", "app/code")),
        Placement("kept", "./lib/kept", True, ("./lib/kept",), ()),
        Placement("other", None, False, ("./x",), ("y",)),
    )

    rendered = render_text(initialise_project(tmp_path, packs=["thing@0.1.0"], placed=placed))

    assert rendered.endswith(
        "  folder    code = app/code, written to the settings; the default ./lib/code does not "
        "exist\n"
        "  folder    kept = ./lib/kept, the pack's default\n"
        "  unplaced  other: none of ./x, y exists; declare it under folders in "
        ".periplus/settings.yml\n"
    )


def test_the_command_places_the_folders_of_the_packs_it_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from periplus.cli import main

    repo = _repo(tmp_path, "app/code", ".periplus/packs/thing@0.1.0")
    manifest = MANIFEST + "detect:\n  any_of:\n    - path: thing.txt\n"
    (repo / ".periplus/packs/thing@0.1.0/pack.yaml").write_text(manifest)
    (repo / "thing.txt").write_text("")
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-dir"))
    monkeypatch.chdir(repo)
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        status = main(["init"])

    assert status == 0
    assert "  folder    code = app/code, written to the settings;" in printed.getvalue()
    assert _folders(repo) == {"code": "app/code"}
