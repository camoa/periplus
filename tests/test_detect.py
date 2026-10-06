"""Framework detection: what the manifest schema declares, and what a repository is recognised as.

`pack-manifest.schema.json` declares a `detect:` key and at least one bundled pack uses it; the
field exists in the schema, and a fixture repo matching that pack's detector is recognised.

What `init` does with a detection is tested in `test_init.py` and `test_console_script.py` beside
the rest of what `init` does.

**The property every test here is arranged around.** A detector is
declared in a pack manifest, never in engine code, so a third-party pack must be detected exactly
as a bundled one is. Two tests exist only to make that falsifiable: one detects a fixture pack this
package has never heard of, and one plants a repository full of PHP, YAML and Twig and asserts that
the packs owning those languages -- which declare no detector -- fire nothing. An implementation
that hardcoded a framework table would pass every other test in this file.

Fixture packs are written under `tmp_path`, never edits to the five that ship, for the reason
`test_manifest.py` gives: a detector introduced into a bundled pack to suit a test is a change to
the product, and four other suites read those five packs.

`_bundled_pin` reads the shipped directory name off disk rather than spelling `drupal@0.1.0` here.
The version in a directory name is package data, not the code under test, and a test that pins it
by hand breaks on a version bump for a reason that has nothing to do with detection.
"""

from __future__ import annotations

import importlib.resources
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from periplus.detect import DETECT_KEY, Detection, detect_packs
from periplus.manifest import load_manifest
from periplus.packs import PACKS_DIRECTORY, PackCandidate, PackRoot, discover_candidates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
MANIFEST_SCHEMA = SRC / "periplus" / "contract" / "schema" / "pack-manifest.schema.json"

#: A `composer.json` that requires Drupal, and one that requires something else. The first is what
#: a Drupal repository has and the second is what every other PHP repository has, so the pair is
#: the whole difference between a detector and a guess.
DRUPAL_COMPOSER = '{"require": {"drupal/core-recommended": "^11.1", "drush/drush": "^13"}}\n'
SYMFONY_COMPOSER = '{"require": {"symfony/console": "^7.2", "twig/twig": "^3.14"}}\n'


def _bundled_root() -> PackRoot:
    """The pack directory inside the installed package, as a root the discovery stage can list."""
    directory = importlib.resources.files("periplus") / PACKS_DIRECTORY
    return PackRoot(
        kind="bundled",
        display=str(directory),
        traversable=directory,
        exists=directory.is_dir(),
        source=None,
    )


def _fixture_root(directory: Path) -> PackRoot:
    """A root record for a pack directory a test built.

    Constructed rather than produced by `resolve_pack_roots`, which would put the bundled root on
    the search path beside the fixture and let the five shipped packs answer for a fixture. The
    same reason `test_manifest.py` constructs its own.
    """
    return PackRoot(
        kind="project",
        display=str(directory),
        traversable=directory,
        exists=directory.is_dir(),
        source=None,
    )


def _candidates(root: PackRoot) -> tuple[PackCandidate, ...]:
    """Everything under one root, classified the way an installed root is classified."""
    return discover_candidates((root,))


def _write_pack(root: Path, entry: str, manifest: str) -> Path:
    """One pack directory under `root`, holding the given `pack.yaml`.

    `pack.yaml` is spelled out rather than taken from `MANIFEST_FILENAME`, for the reason
    `test_manifest.py` gives: a fixture that names the file the way the module names it agrees with
    the module whatever either is renamed to.
    """
    directory = root / entry
    directory.mkdir(parents=True)
    (directory / "pack.yaml").write_text(manifest, encoding="utf-8")
    return directory


def _packs_dir(tmp_path: Path) -> Path:
    """A directory to write fixture packs into."""
    directory = tmp_path / "packs"
    directory.mkdir()
    return directory


def _repo(tmp_path: Path, files: Mapping[str, str]) -> Path:
    """A repository to detect against, holding the named files with the given contents.

    Keys are repository-relative paths with `/` separators, so a fixture reads the way the tree it
    builds looks.
    """
    root = tmp_path / "repo"
    root.mkdir()
    for name, text in files.items():
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _bundled_pin(pack: str) -> str:
    """The `<pack>@<version>` directory the install actually ships for one pack name."""
    entries = sorted(
        candidate.entry
        for candidate in _candidates(_bundled_root())
        if candidate.status == "named"
        and candidate.name is not None
        and candidate.name.pack == pack
    )
    assert len(entries) == 1, f"the install ships {entries} for the pack named {pack!r}"
    return entries[0]


def _schema() -> dict[str, object]:
    """The shipped pack-manifest schema, parsed."""
    document = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _subschema(node: object, *path: str) -> dict[str, object]:
    """One position inside a schema document, or a failure naming the position that was missing."""
    where = "#"
    for step in path:
        assert isinstance(node, dict), f"{where} is {type(node).__name__}, not an object"
        assert step in node, f"{where} declares no {step!r}"
        node = node[step]
        where = f"{where}/{step}"
    assert isinstance(node, dict), f"{where} is {type(node).__name__}, not an object"
    return node


# -------------------------------------------------------------------------------------------
# The field exists in the schema
# -------------------------------------------------------------------------------------------


def test_the_pack_manifest_schema_declares_a_detect_key() -> None:
    """The field exists in the schema, and it is a hard requirement rather than a tidiness one.

    `pack-manifest.schema.json` sets `additionalProperties: false` at its root. So until `detect`
    is a declared property, a pack shipping a detector is a manifest the validator will refuse --
    the feature would be unusable by the packs it exists for, and nothing else in the suite would
    say so. The second assertion is what makes the first one load-bearing rather than cosmetic.
    """
    schema = _schema()

    assert schema.get("additionalProperties") is False, (
        "this test's whole reason is that an undeclared key is refused; if the schema stopped "
        "closing its root, the first assertion below would no longer be about anything"
    )
    assert DETECT_KEY in _subschema(schema, "properties"), (
        f"the manifest schema declares no {DETECT_KEY!r}, so a pack that ships one is invalid"
    )


def test_the_detect_schema_requires_a_path_and_refuses_a_key_it_did_not_declare() -> None:
    """The shape, written down here because a test is what settles it and prose is not.

    A detector is a set of alternatives -- a repository is Drupal if its composer.json requires
    Drupal *or* it has a docroot -- so the block names the combining rule instead of leaving a bare
    list for a reader to guess at:

        detect:
          any_of:
            - path: composer.json      # repository-relative, and it must exist
              contains: "drupal/core"  # optional: a literal substring of that file's text
            - path: web/core/lib/Drupal.php

    `additionalProperties: false` at both levels is the assertion that matters. A pack author who
    writes `contain:` for `contains:` must get a refusal, not a detector that silently tests
    existence alone and fires on every PHP repository in the world.

    `contains` is a literal substring and not a regular expression. Detection reads third-party
    pack data with no time limit around it, and this project's engine language was chosen partly on
    what a backtracking regex engine costs; a substring has no such cost and no such failure mode.
    """
    detect = _subschema(_schema(), "properties", DETECT_KEY)

    assert detect.get("additionalProperties") is False, (
        "a misspelled key inside `detect:` must be refused, not ignored"
    )
    assert detect.get("required") == ["any_of"], (
        f"`detect:` declares required {detect.get('required')!r}; the block names its combining "
        "rule, so `any_of` is not optional"
    )

    signal = _subschema(detect, "properties", "any_of", "items")

    assert signal.get("additionalProperties") is False, (
        "a misspelled key inside a signal must be refused, not ignored"
    )
    assert signal.get("required") == ["path"], (
        f"a signal declares required {signal.get('required')!r}; a signal with no path names no "
        "file and can only ever match everything or nothing"
    )
    assert "contains" in _subschema(signal, "properties"), (
        "a signal must be able to require text inside the file it names; existence alone cannot "
        "tell a Drupal composer.json from any other one"
    )


# -------------------------------------------------------------------------------------------
# A bundled pack uses it, and a matching fixture repo is recognised
# -------------------------------------------------------------------------------------------


def test_a_bundled_pack_ships_a_detector_the_schema_admits() -> None:
    """At least one bundled pack uses it, and the tie between the two halves.

    The schema edit and the pack edit are two files, and either landing without the other is a
    broken state no other test sees: a schema declaring a key nothing uses is dead weight, and a
    pack declaring a key the schema does not is an invalid manifest. So this reads the detector out
    of every shipped `pack.yaml` and checks each key against the schema position that governs it.

    It asserts nothing about *which* pack, deliberately. The requirement is "at least one", and
    naming drupal here would make a decision about product content into a test that fails when
    somebody adds a second detector.
    """
    schema = _schema()
    detect_schema = _subschema(schema, "properties", DETECT_KEY)
    signal_schema = _subschema(detect_schema, "properties", "any_of", "items")
    declared_signal_keys = set(_subschema(signal_schema, "properties"))

    detectors: dict[str, object] = {}
    for candidate in _candidates(_bundled_root()):
        if candidate.status != "named" or candidate.name is None:
            continue
        document = load_manifest(_bundled_root().traversable / candidate.entry).document
        if DETECT_KEY in document:
            detectors[candidate.entry] = document[DETECT_KEY]

    assert detectors, "no bundled pack declares a detector, so nothing exercises the key at all"

    declared_detect_keys = set(_subschema(detect_schema, "properties"))
    for entry, block in sorted(detectors.items()):
        assert isinstance(block, dict), f"{entry}: `detect:` is {type(block).__name__}, not a block"
        assert set(block) <= declared_detect_keys, (
            f"{entry}: `detect:` uses {sorted(set(block) - declared_detect_keys)}, "
            "which the schema does not declare"
        )
        alternatives = block.get("any_of")
        assert isinstance(alternatives, list) and alternatives, (
            f"{entry}: `any_of` is {alternatives!r}, and a detector with no alternatives detects "
            "nothing"
        )
        for index, signal in enumerate(alternatives):
            assert isinstance(signal, dict), f"{entry}: any_of[{index}] is not a signal"
            assert "path" in signal, f"{entry}: any_of[{index}] names no path"
            assert set(signal) <= declared_signal_keys, (
                f"{entry}: any_of[{index}] uses {sorted(set(signal) - declared_signal_keys)}, "
                "which the schema does not declare"
            )


def test_a_repository_matching_a_bundled_detector_is_recognised(tmp_path: Path) -> None:
    """Recognition, against the pack that ships and a repository built to match it.

    A Drupal repository is one whose `composer.json` requires Drupal core. That sentence is the
    requirement this assertion comes from, and it is what the bundled drupal detector has to
    express -- the string below was not read off an implementation, because there is none.

    The pin is read off the shipped directory rather than typed, so a version bump does not fail a
    test about detection.
    """
    repo = _repo(tmp_path, {"composer.json": DRUPAL_COMPOSER})

    detected = detect_packs(repo, _candidates(_bundled_root()))

    assert [found.pin for found in detected] == [_bundled_pin("drupal_basic")]
    assert detected[0].path == "composer.json", (
        "a detection carries the evidence that produced it, so a person can be told why"
    )


def test_a_php_repository_that_is_not_drupal_is_recognised_as_nothing(tmp_path: Path) -> None:
    """The near miss, and the languages that declare no detector.

    This repository is PHP, YAML and Twig throughout, and the install ships a pack for each of the
    three. None of them declares a detector, because "there is PHP here" is not a stack anybody
    pins -- drupal already reaches php and yaml through `depends`, and pinning a language pack
    because a file with that extension exists would prefill noise into every settings file.

    So the empty result is the assertion, and it is the one an engine with a built-in framework
    table fails. The `composer.json` requires Symfony rather than nothing, which is the case a
    detector that tested existence alone gets wrong.
    """
    repo = _repo(
        tmp_path,
        {
            "composer.json": SYMFONY_COMPOSER,
            "src/Kernel.php": "<?php\nnamespace App;\nclass Kernel {}\n",
            "config/services.yaml": "services:\n  _defaults:\n    autowire: true\n",
            "templates/base.html.twig": "{% block body %}{% endblock %}\n",
        },
    )

    assert detect_packs(repo, _candidates(_bundled_root())) == ()


# -------------------------------------------------------------------------------------------
# A detector is pack data, never engine code
# -------------------------------------------------------------------------------------------


def test_a_third_party_pack_is_recognised_exactly_as_a_bundled_one_is(tmp_path: Path) -> None:
    """The extensibility property, as the only test that can falsify it.

    `acme` is not a stack this package has ever heard of, and `acme.toml` is not a filename anything
    in `src/` mentions. If recognising it needs an engine change, the design is wrong -- and every
    other test in this file would still pass, because every other one detects something the
    codebase already knows the name of.

    The signal carries no `contains`, so this also settles the path-only form: a file being there is
    enough when the filename itself is the evidence.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "acme@1.0.0",
        "pack: acme\nversion: 1.0.0\ndepends: []\ndetect:\n  any_of:\n    - path: acme.toml\n",
    )
    repo = _repo(tmp_path, {"acme.toml": "[acme]\n"})

    detected = detect_packs(repo, _candidates(_fixture_root(packs)))

    assert detected == (Detection(pack="acme", pin="acme@1.0.0", path="acme.toml"),)


def test_a_pack_that_declares_no_detector_is_never_recognised(tmp_path: Path) -> None:
    """A pack with no `detect:` block contributes nothing, however much of it is in the tree.

    The repository below is full of the files this pack claims. A detector inferred from `files:`
    or from `folders:` would fire here, and that is the shortcut this test exists to close: a pack
    saying which extensions are its own is not a pack saying a repository is its stack.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "quiet@0.1.0",
        "pack: quiet\nversion: 0.1.0\ndepends: []\nfiles:\n  extensions: [quiet]\n",
    )
    repo = _repo(tmp_path, {"one.quiet": "", "two.quiet": ""})

    assert detect_packs(repo, _candidates(_fixture_root(packs))) == ()


# -------------------------------------------------------------------------------------------
# Determinism, and the ways a detector can be wrong
# -------------------------------------------------------------------------------------------


def test_detection_carries_no_state_from_one_call_to_the_next(tmp_path: Path) -> None:
    """A second call with the same arguments returns what the first did, and nothing accumulates.

    **This is not the sorting test, and under its old name it claimed to be.** It was called
    `..._sorted_by_pin_and_identical_across_runs` and asserted the sorted list against three packs
    under a single root -- where `discover_candidates` already returns candidates sorted by entry,
    so pin order and candidate order are the same list and an implementation that never sorts
    produces the expectation anyway. Proven by planting `return tuple(found.values())` in place of
    the sort: this test passed. A name claiming coverage it does not have is worse than a
    duplicate, because a reader grepping for sort coverage finds it and stops looking.

    Sorting is owned by `test_detection_guards.py`, whose
    `test_detections_are_sorted_by_pin_and_not_by_the_root_a_pack_was_found_under` puts the packs
    under two roots so that candidate order crosses pin order. That one caught the same plant, so
    the assertion is dropped here rather than duplicated there.

    What is left is the half nothing else asserts: two calls agree. The failure it catches is state
    carried between them -- an accumulator or a mutable default never reset, which returns six
    detections the second time. Three packs rather than one, so that growth is visible.

    Its limit, stated because a determinism test that overstates its reach is worse than none. Two
    calls inside one process cannot see cross-process variation: a set of strings iterates in one
    order for the life of an interpreter, so an implementation whose order depends on
    `PYTHONHASHSEED` passes this and still writes a different settings file on another machine. The
    stated property is byte-identical output across machines; this is the within-process half.
    """
    packs = _packs_dir(tmp_path)
    for entry, pack in (("zeta@0.1.0", "zeta"), ("alpha@2.0.0", "alpha"), ("mid@1.5.0", "mid")):
        _write_pack(
            packs,
            entry,
            f"pack: {pack}\nversion: {entry.split('@')[1]}\ndepends: []\n"
            "detect:\n  any_of:\n    - path: marker.txt\n",
        )
    repo = _repo(tmp_path, {"marker.txt": ""})
    candidates = _candidates(_fixture_root(packs))

    first = detect_packs(repo, candidates)
    second = detect_packs(repo, candidates)

    # No assertion on the order. See the docstring: this fixture cannot see it, and
    # `test_detection_guards.py` owns it.
    assert first == second


@pytest.mark.parametrize(
    ("case", "block"),
    [
        ("not a mapping", "detect: composer.json\n"),
        ("no alternatives", "detect:\n  any_of: []\n"),
        ("alternatives are not a list", "detect:\n  any_of: composer.json\n"),
        ("a signal with no path", "detect:\n  any_of:\n    - contains: anything\n"),
        ("a signal that is not a mapping", "detect:\n  any_of:\n    - composer.json\n"),
        ("a path that is not a string", "detect:\n  any_of:\n    - path: 12\n"),
    ],
    ids=[
        "not-a-mapping",
        "no-alternatives",
        "alternatives-not-a-list",
        "signal-with-no-path",
        "signal-not-a-mapping",
        "path-not-a-string",
    ],
)
def test_a_detector_that_cannot_be_read_recognises_nothing(
    tmp_path: Path, case: str, block: str
) -> None:
    """Every unreadable detector fails towards detecting nothing, never towards matching everything.

    The direction is the whole point. A detection becomes a pin in a settings file that is
    committed and reviewed, so a spurious one costs a wrong line in an artifact and a missed one
    costs a line somebody types. `- contains: anything` with no path is the case that separates the
    two: an implementation that treats a missing path as "no constraint" fires on every repository
    there is.

    The repository holds files on purpose. Against an empty tree these would all pass whatever the
    implementation did, which is the fixture mistake that makes a test look like a specification
    without being one.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(packs, "broken@0.1.0", f"pack: broken\nversion: 0.1.0\ndepends: []\n{block}")
    repo = _repo(tmp_path, {"composer.json": DRUPAL_COMPOSER, "anything": "text\n"})

    assert detect_packs(repo, _candidates(_fixture_root(packs))) == (), f"fired on {case}"


def test_a_manifest_that_cannot_be_read_is_skipped_and_the_rest_still_detect(
    tmp_path: Path,
) -> None:
    """One broken pack on the search path does not stop the run or take the others down with it.

    `periplus init` is the caller, and a directory matching no pack still
    exits 0 there. A third-party pack with a truncated `pack.yaml` sitting in `.periplus/packs/`
    must not turn creating a project into a traceback.

    Skipped and not reported: `manifest.py` raises `ManifestUnreadable` for exactly this file and
    this function swallows it, because the command that reports on the pack search path is
    `periplus status`, not the one that creates a directory.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(packs, "broken@0.1.0", "pack: [unclosed\n")
    _write_pack(
        packs,
        "acme@1.0.0",
        "pack: acme\nversion: 1.0.0\ndepends: []\ndetect:\n  any_of:\n    - path: acme.toml\n",
    )
    repo = _repo(tmp_path, {"acme.toml": "[acme]\n"})

    assert [found.pin for found in detect_packs(repo, _candidates(_fixture_root(packs)))] == [
        "acme@1.0.0"
    ]


def test_a_detector_path_that_leaves_the_repository_never_fires(tmp_path: Path) -> None:
    """A pack is third-party code, and a signal path is third-party data. It stays under the root.

    Both spellings below reach a real file outside the repository, and `pathlib` obliges: `root /
    "../outside.txt"` resolves upwards, and joining an absolute path discards the root entirely. So
    an implementation that writes `(root / signal["path"]).is_file()` and stops fires on both.

    What that buys an attacker is a probe. A detector alternative per candidate path turns a
    committed settings file into a readout of which files exist on the machine that ran `init`, and
    the person reviewing that diff has no way to see where the answer came from. It is the same
    class of hole `init`'s own symlink refusal closes one level up, and it is cheap to close here:
    a signal path is repository-relative, and anything that does not stay under the root is not a
    signal.
    """
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "nosy@0.1.0",
        "pack: nosy\nversion: 0.1.0\ndepends: []\n"
        "detect:\n"
        "  any_of:\n"
        "    - path: ../outside.txt\n"
        f"    - path: {tmp_path / 'outside.txt'}\n",
    )
    repo = _repo(tmp_path, {"kept": "in the repository\n"})

    assert detect_packs(repo, _candidates(_fixture_root(packs))) == ()
