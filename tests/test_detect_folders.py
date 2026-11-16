"""A detector signal may name a folder in braces and end in a file-name pattern.

The folder resolves as `init` places it: the pack's default, or the first of its
`folder_candidates` that exists. Detections come back with each pack after the packs it depends
on. The fixture packs name no real stack.
"""

from __future__ import annotations

from pathlib import Path

from periplus.detect import detect_packs
from periplus.packs import PackCandidate, PackRoot, discover_candidates

BASE = """\
pack: base
version: 0.1.0
depends: []
folders:
  conf: ./etc/conf
  code: ./lib
  code_root: "{code}/**"
folder_candidates:
  conf: [settings/conf]
"""

LISTED = """\
pack: listed
version: 0.1.0
depends: [base]
detect:
  any_of:
    - path: "{conf}/list.txt"
      contains: "\\n  listed: "
"""

SCRIPTED = """\
pack: scripted
version: 0.1.0
depends: [base]
detect:
  any_of:
    - path: "{code_root}/*.script"
"""


def _candidates(tmp_path: Path, manifests: dict[str, str]) -> tuple[PackCandidate, ...]:
    packs = tmp_path / "packs"
    for entry, text in manifests.items():
        (packs / entry).mkdir(parents=True)
        (packs / entry / "pack.yaml").write_text(text)
    root = PackRoot(kind="project", display=str(packs), traversable=packs, exists=True, source=None)
    return discover_candidates((root,))


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    return repo


def test_a_signal_naming_a_folder_reads_it_where_the_candidate_placed_it(tmp_path: Path) -> None:
    candidates = _candidates(tmp_path, {"base@0.1.0": BASE, "listed@0.1.0": LISTED})
    repo = _repo(tmp_path, {"settings/conf/list.txt": "things:\n  other: 0\n  listed: 0\n"})

    found = detect_packs(repo, candidates)

    assert [(one.pin, one.path) for one in found] == [("listed@0.1.0", "settings/conf/list.txt")]


def test_a_signal_naming_a_folder_still_checks_what_the_file_contains(tmp_path: Path) -> None:
    candidates = _candidates(tmp_path, {"base@0.1.0": BASE, "listed@0.1.0": LISTED})
    repo = _repo(tmp_path, {"settings/conf/list.txt": "things:\n  other: 0\n  listed_ui: 0\n"})

    assert detect_packs(repo, candidates) == ()


def test_a_file_name_pattern_finds_a_file_at_any_depth_and_names_it(tmp_path: Path) -> None:
    candidates = _candidates(tmp_path, {"base@0.1.0": BASE, "scripted@0.1.0": SCRIPTED})
    repo = _repo(tmp_path, {"lib/one/two/run.script": "", "lib/one/notes.txt": ""})

    found = detect_packs(repo, candidates)

    assert [(one.pin, one.path) for one in found] == [("scripted@0.1.0", "lib/one/two/run.script")]


def test_a_file_name_pattern_that_matches_no_file_detects_nothing(tmp_path: Path) -> None:
    candidates = _candidates(tmp_path, {"base@0.1.0": BASE, "scripted@0.1.0": SCRIPTED})
    repo = _repo(tmp_path, {"lib/one/run.scripts": "", "elsewhere/run.script": ""})

    assert detect_packs(repo, candidates) == ()


def test_a_pack_comes_after_a_detected_pack_it_depends_on(tmp_path: Path) -> None:
    under = "pack: zeta\nversion: 0.1.0\ndepends: []\ndetect:\n  any_of:\n    - path: m.txt\n"
    over = "pack: alpha\nversion: 0.1.0\ndepends: [zeta]\ndetect:\n  any_of:\n    - path: m.txt\n"
    candidates = _candidates(tmp_path, {"zeta@0.1.0": under, "alpha@0.1.0": over})
    repo = _repo(tmp_path, {"m.txt": ""})

    assert [one.pin for one in detect_packs(repo, candidates)] == ["zeta@0.1.0", "alpha@0.1.0"]


def test_the_bundled_packs_detect_a_docroot_site_and_place_its_folders(tmp_path: Path) -> None:
    """The first-run fault: code under docroot, configuration under config/default."""
    import importlib.resources

    from periplus.detect import place_folders
    from periplus.packs import PACKS_DIRECTORY

    shipped = importlib.resources.files("periplus") / PACKS_DIRECTORY
    root = PackRoot(
        kind="bundled", display=str(shipped), traversable=shipped, exists=True, source=None
    )
    candidates = discover_candidates((root,))
    extension = "module:\n  eca: 0\n  paragraphs: 0\n  salesforce: 0\n  salesforce_eca: 0\n"
    repo = _repo(
        tmp_path,
        {
            "composer.json": '{"require": {"drupal/core-recommended": "^11"}}\n',
            "config/default/core.extension.yml": extension + "  webform: 0\nprofile: minimal\n",
            "docroot/modules/custom/mod/mod.info.yml": "name: mod\n",
            "docroot/modules/custom/mod/drush.services.yml": "services: {}\n",
            "docroot/modules/custom/mod/js/mod.js": "",
            "docroot/themes/custom/look/look.info.yml": "name: look\n",
        },
    )

    found = detect_packs(repo, candidates)
    placed = place_folders(repo, candidates, [one.pin for one in found])

    assert [(one.pack, one.path) for one in found] == [
        ("drupal_basic", "composer.json"),
        ("drupal_js_basic", "docroot/modules/custom/mod/js/mod.js"),
        ("drush_basic", "docroot/modules/custom/mod/drush.services.yml"),
        ("eca_basic", "config/default/core.extension.yml"),
        ("paragraphs_basic", "config/default/core.extension.yml"),
        ("webform_basic", "config/default/core.extension.yml"),
        ("salesforce_basic", "config/default/core.extension.yml"),
        ("salesforce_eca_basic", "config/default/core.extension.yml"),
    ]
    assert [(one.folder, one.path) for one in placed] == [
        ("config", "config/default"),
        ("custom_module", "docroot/modules/custom"),
        ("custom_theme", "docroot/themes/custom"),
    ]
