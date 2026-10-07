"""Guards in the detection path, each with a fixture that reaches it.

**These are mutation-verification tests and not TDD reds.** Every one was written *after* the
implementation it exercises, from mutation runs over `detect.py`, `init.py` and the shipped drupal
manifest: the branch was broken, the whole suite stayed green, and the test below is what makes
that branch's absence visible. So none of these assertions is evidence that a requirement was
written down before the code -- `tests/test_detect.py`, `tests/test_init.py` and
`tests/test_console_script.py` are where that evidence lives, and they are untouched. What these
prove is narrower and still worth having: that guards which currently protect nothing observable
are sensitive.

They live in their own file for the same reason. Adding them to the specification files would mix
assertions written against a design with assertions written against an implementation, and a later
reader has no way to tell which is which once they sit in one list.

Each was verified the same way it was found: break the thing, watch the test below fail, restore
it, watch it pass. A guard test that passes with its guard removed is not a test of that guard.

What is covered here, and why each earned a test rather than a note:

* A misspelled key in a detector -- `contain:` for `contains:`, or `all_of:` beside `any_of:` --
  is a false positive across a whole language, so both levels are closed and both are asserted.
* Detections are sorted by pin, on two roots, because a one-root fixture cannot tell a sort from
  the order discovery already produced.
* The evidence reported is the first matching signal, which is the ordinary case for the shipped
  drupal detector rather than a contrived one.
* A pack directory name cannot forge a line into the settings file it is written to.
* A repository-carried symlink cannot point a signal outside the checkout, which is the one
  containment case a lexical check passes.
* The shipped docroot signal matches, so a typo in `drupal_basic@0.3.0/pack.yaml` fails something.
* The report names its evidence, escaped, and says nothing at all when nothing was detected.

Four gaps the same runs turned up are deliberately left open: a non-string `path:` or `contains:`,
an unreadable signal file, and a pin found under two roots. Each reaches a guard that fails towards
detecting nothing, which costs a line somebody types rather than a line nobody wrote.
"""

from __future__ import annotations

import contextlib
import importlib.resources
import io
import os
from collections.abc import Mapping
from pathlib import Path

from periplus.detect import Detection, detect_packs
from periplus.init import InitReport, initialise_project, render_text
from periplus.packs import PACKS_DIRECTORY, PackCandidate, PackRoot, discover_candidates
from periplus.settings import PROJECT_MARKER, SETTINGS_FILENAME, load_settings_document

#: A `composer.json` that requires Symfony and not Drupal. The near miss, which is the only fixture
#: a signal-shape test can use: against a repository that genuinely is Drupal, a detector that
#: ignored its own `contains` would fire and be right, and the test would say nothing.
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


def _bundled_pin(pack: str) -> str:
    """The `<pack>@<version>` directory the install actually ships for one pack name.

    Read off disk rather than spelled, for the reason `test_detect.py` gives: the version in a
    directory name is package data, and a test that types it breaks on a version bump for a reason
    that has nothing to do with detection.
    """
    entries = sorted(
        candidate.entry
        for candidate in discover_candidates((_bundled_root(),))
        if candidate.status == "named"
        and candidate.name is not None
        and candidate.name.pack == pack
    )
    assert len(entries) == 1, f"the install ships {entries} for the pack named {pack!r}"
    return entries[0]


def _root(directory: Path) -> PackRoot:
    """A root record for a pack directory a test built, with no bundled root beside it."""
    return PackRoot(
        kind="project",
        display=str(directory),
        traversable=directory,
        exists=directory.is_dir(),
        source=None,
    )


def _candidates(*directories: Path) -> tuple[PackCandidate, ...]:
    """Everything under the given roots, classified and ordered the way an install's roots are."""
    return discover_candidates(tuple(_root(directory) for directory in directories))


def _write_pack(root: Path, entry: str, manifest: str) -> Path:
    """One pack directory under `root`, holding the given `pack.yaml`."""
    directory = root / entry
    directory.mkdir(parents=True)
    (directory / "pack.yaml").write_text(manifest, encoding="utf-8")
    return directory


def _packs_dir(tmp_path: Path, name: str = "packs") -> Path:
    """A directory to write fixture packs into. Named, because two roots is one of the cases."""
    directory = tmp_path / name
    directory.mkdir()
    return directory


def _repo(tmp_path: Path, files: Mapping[str, str]) -> Path:
    """A repository to detect against, holding the named files with the given contents."""
    root = tmp_path / "repo"
    root.mkdir()
    for name, text in files.items():
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_a_misspelled_key_inside_a_signal_detects_nothing_rather_than_existence(
    tmp_path: Path,
) -> None:
    """`contain:` for `contains:` must refuse, not degrade into a test of the filename alone.

    This is the failure that costs the most and shows the least. The pack below meant to require
    `drupal/core` inside `composer.json` and misspelled the key by one character. Ignore the
    unknown key and what is left is `path: composer.json`, which every PHP repository on earth
    satisfies -- so one typo turns a Drupal detector into a detector for Composer, and the pin it
    writes lands in a file somebody commits.

    Measured with the guard removed, against this exact fixture: it returns a `Detection` for a
    Symfony repository.

    `pack-manifest.schema.json` closes both levels with `additionalProperties: false`, and that is
    not what makes this pass. Nothing validates a manifest against that schema before a detector
    runs -- `load_manifest` deliberately enforces no line of it -- so the refusal has to exist in
    the evaluator too, and this is the assertion that says it does.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "typo@0.1.0",
        "pack: typo\nversion: 0.1.0\ndepends: []\n"
        "detect:\n"
        "  any_of:\n"
        "    - path: composer.json\n"
        '      contain: "drupal/core"\n',
    )
    repo = _repo(tmp_path, {"composer.json": SYMFONY_COMPOSER})

    assert detect_packs(repo, _candidates(packs)) == ()


def test_a_misspelled_key_beside_any_of_detects_nothing(tmp_path: Path) -> None:
    """The same refusal one level up, where the combining rule is named.

    `all_of:` is the plausible mistake here rather than a typo: an author who wants every signal to
    match writes the word the schema does not declare. Read as "an unknown block I will ignore",
    the detector collapses to whatever `any_of` alone says, which is the opposite of what was
    written -- a pack asking for two conditions gets a detector satisfied by one.

    The repository holds the file the surviving alternative names, so the empty result is the
    assertion. Against a tree without it these would pass whatever the implementation did.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "both@0.1.0",
        "pack: both\nversion: 0.1.0\ndepends: []\n"
        "detect:\n"
        "  any_of:\n"
        "    - path: composer.json\n"
        "  all_of:\n"
        "    - path: never-here\n",
    )
    repo = _repo(tmp_path, {"composer.json": SYMFONY_COMPOSER})

    assert detect_packs(repo, _candidates(packs)) == ()


def test_detections_are_sorted_by_pin_and_not_by_the_root_a_pack_was_found_under(
    tmp_path: Path,
) -> None:
    """Sorted by pin, where sorted order and discovery order genuinely disagree.

    `discover_candidates` returns roots in order and entries within a root sorted by name, so a
    fixture whose packs all sit under one root has a discovery order that is already pin order --
    and an implementation that returned what it found, unsorted, passes. Two roots separate them:
    `zeta` is under the first root and `alpha` under the second, so discovery yields zeta then
    alpha and only a sort puts alpha first.

    What the sort buys is determinism. A `packs:` list written by `init` must not depend
    on which root a pack happened to be installed under, or two machines holding the same tree
    write two different committed files.
    """
    first = _packs_dir(tmp_path, "first-root")
    second = _packs_dir(tmp_path, "second-root")
    _write_pack(
        first,
        "zeta@0.1.0",
        "pack: zeta\nversion: 0.1.0\ndepends: []\ndetect:\n  any_of:\n    - path: marker.txt\n",
    )
    _write_pack(
        second,
        "alpha@0.1.0",
        "pack: alpha\nversion: 0.1.0\ndepends: []\ndetect:\n  any_of:\n    - path: marker.txt\n",
    )
    repo = _repo(tmp_path, {"marker.txt": ""})
    candidates = _candidates(first, second)

    assert [candidate.entry for candidate in candidates] == ["zeta@0.1.0", "alpha@0.1.0"], (
        "the fixture must present the packs in an order a sort would change, or the assertion "
        "below holds for an implementation that never sorts"
    )
    assert [found.pin for found in detect_packs(repo, candidates)] == ["alpha@0.1.0", "zeta@0.1.0"]


def test_the_evidence_is_the_first_matching_signal_and_not_the_last(tmp_path: Path) -> None:
    """Which signal is reported when more than one matches, which is the ordinary Drupal case.

    A Drupal checkout built with Composer has both: a `composer.json` requiring core, and a
    docroot. So the detector that ships has two matching alternatives on a normal repository, and
    nothing until now said which one a person is shown.

    First, because the order the alternatives are written in is the author's statement of what
    counts as evidence -- the strongest claim first, the fallback after it. Reporting the last
    match instead hands somebody reviewing a settings file the weaker reason and no way to tell
    that a better one existed.
    """
    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "acme@1.0.0",
        "pack: acme\nversion: 1.0.0\ndepends: []\n"
        "detect:\n"
        "  any_of:\n"
        "    - path: acme.toml\n"
        "    - path: vendor/acme/marker\n",
    )
    repo = _repo(tmp_path, {"acme.toml": "[acme]\n", "vendor/acme/marker": ""})

    detected = detect_packs(repo, _candidates(packs))

    assert [found.path for found in detected] == ["acme.toml"]


def test_a_pack_directory_name_cannot_forge_a_second_pin_into_the_settings_file(
    tmp_path: Path,
) -> None:
    """A pin is a directory name, and a directory name is not a safe YAML scalar.

    On Linux a directory name is any byte sequence without `/` or NUL, newlines included. A pin
    written plainly into the file therefore lets whoever chose that name write the *next* line as
    well -- and the name below closes the quoted scalar and opens a list item, so a repository that
    detected one pack declares two. The forged pin is loaded by every later command, and the person
    reviewing the diff sees a settings file that looks hand-written.

    That makes this the one guard in this file whose failure is content forged into a committed,
    reviewed artifact rather than a wrong answer. `init` writes each pin through `json.dumps`, a
    subset of YAML 1.2's double-quoted form, so the newline survives as an escape inside one scalar
    instead of as a line break between two.

    The assertion is the loaded list and never the file's text: the planted name appears in the
    bytes either way, and only the loader can say whether it arrived as one value or two.
    """
    forged = 'evil@0.1.0"\n  - injected@9.9.9'

    initialise_project(tmp_path, packs=(forged,))

    document = load_settings_document(tmp_path / PROJECT_MARKER / SETTINGS_FILENAME)
    packs = document.get("packs")
    assert packs is not None
    assert list(packs) == [forged], (
        "the pin was written as YAML rather than as a value, so a directory name wrote a line of "
        "the settings file"
    )


def test_a_symlink_in_the_repository_cannot_point_a_signal_out_of_it(tmp_path: Path) -> None:
    """The containment check resolves both sides, and that is what a lexical one cannot do.

    `test_detect.py`'s escape test covers `../outside.txt` and an absolute path. Both are defeated
    lexically, so an implementation normalising the string instead of resolving the path passes it
    -- measured, by replacing `.resolve()` with `os.path.normpath` and watching the whole suite stay
    green. This is the case that separates them: `vendor/hosts` has no `..` in it and is not
    absolute, so it survives every lexical test there is and still names a file outside the
    checkout.

    What that buys an attacker is the probe again, one layer down. A repository can carry a symlink
    -- vendored trees are full of them -- so a pack declaring `path: vendor/hosts` plus a `contains`
    reads a file on the machine that ran `init` and reports the answer as a pin in a committed file.

    The target is a file this test wrote rather than `/etc/hosts`. A test whose result depends on
    what the machine running it happens to have is the thing this project forbids, and the
    guard does not care which file is on the far end of the link.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hosts").write_text("127.0.0.1 localhost\n", encoding="utf-8")

    repo = _repo(tmp_path, {"kept": "in the repository\n"})
    (repo / "vendor").mkdir()
    (repo / "vendor" / "hosts").symlink_to(outside / "hosts")

    packs = _packs_dir(tmp_path)
    _write_pack(
        packs,
        "nosy@0.1.0",
        "pack: nosy\nversion: 0.1.0\ndepends: []\n"
        "detect:\n"
        "  any_of:\n"
        "    - path: vendor/hosts\n"
        '      contains: "localhost"\n',
    )

    assert (repo / "vendor" / "hosts").is_file(), (
        "the fixture must plant a link that resolves to a real file, or the assertion below holds "
        "for a detector that simply found nothing there"
    )
    assert detect_packs(repo, _candidates(packs)) == ()


def test_the_shipped_docroot_signal_matches_a_checkout_with_no_composer_json(
    tmp_path: Path,
) -> None:
    """The drupal pack's second alternative, which until now was shipped data nothing exercised.

    `test_detect.py` builds a repository holding a `composer.json` that requires Drupal core, which
    the first alternative answers. The second -- `web/core/lib/Drupal.php` -- is what recognises a
    checkout that has core in the tree and no `composer.json` at the root, and a typo in that path
    inside `drupal_basic@0.3.0/pack.yaml` failed nothing.

    So the repository below has the docroot and no `composer.json` at all, which is the only fixture
    that can reach the second alternative: with both present the first one answers first and this
    test would pass against a pack that had lost the docroot signal entirely.

    The evidence is asserted alongside the pin, because the point of the alternative is that a
    person is told which of the two matched.
    """
    repo = _repo(
        tmp_path,
        {"web/core/lib/Drupal.php": "<?php\nclass Drupal {\n  const VERSION = '11.1.0';\n}\n"},
    )

    detected = detect_packs(repo, discover_candidates((_bundled_root(),)))

    assert [(found.pin, found.path) for found in detected] == [
        (_bundled_pin("drupal_basic"), "web/core/lib/Drupal.php")
    ]


def test_the_report_names_the_evidence_for_every_pack_it_detected() -> None:
    """The `detected` line, and both of the values it escapes.

    A pin is a pack directory name and an evidence path is a string out of a third-party
    `pack.yaml`. Both are chosen by whoever wrote the pack, both reach a terminal, and an ESC in
    either forges a line of a report a person reads -- the same hole `test_init.py` closes for the
    three values that were already printed, one line further down the same function.

    Both halves carry ESC on purpose, so deleting either `_escape` call fails this: with one
    deleted the other still escapes and the whole-string comparison still disagrees. And it is a
    whole-string comparison rather than "the raw ESC is absent", because absence is also satisfied
    by dropping the character.
    """
    root = Path("/nowhere/tree")
    settings = root / PROJECT_MARKER / SETTINGS_FILENAME
    report = InitReport(
        root=root,
        settings=settings,
        created=True,
        problems=(),
        detected=(
            Detection(pack="drupal", pin="drupal@0.1.0", path="composer.json"),
            Detection(pack="evil", pin="evil\x1b[2K@1.0.0", path="a\x1b[2Kb.json"),
        ),
    )

    assert render_text(report) == (
        "periplus init created\n"
        f"  settings  {settings}\n"
        f"  packs     {root / PROJECT_MARKER / 'packs'}\n"
        "  detected  drupal@0.1.0 via composer.json\n"
        "  detected  evil\\x1b[2K@1.0.0 via a\\x1b[2Kb.json\n"
    )


def test_a_run_that_detected_nothing_prints_no_detected_line(tmp_path: Path) -> None:
    """Detecting nothing is a state, and a report says nothing about it rather than saying "none".

    The ordinary outcome for most repositories. A renderer that printed a header with no rows under
    it, or a `detected  (none)` line, would turn the ordinary case into something that looks like a
    finding -- and `init`'s two existing render assertions compare whole strings, so this is also
    what keeps the new line from leaking into every run's output.
    """
    rendered = render_text(initialise_project(tmp_path))

    # Line by line, not `"detected" not in rendered`. `tmp_path` is named after the test that asked
    # for it, so the word is already in the two paths this report prints and a substring search
    # answers about the fixture rather than about the renderer.
    assert [line for line in rendered.splitlines() if line.startswith("  detected")] == []
    assert rendered.endswith(f"  packs     {tmp_path / PROJECT_MARKER / 'packs'}\n")


def test_the_command_prints_the_evidence_for_the_pack_it_detected(tmp_path: Path) -> None:
    """The wiring, at the surface a person types, which is the half a render test cannot reach.

    `Detection.path` existed and nothing in `src/` read it: `cli` passed the pins alone, so the
    evidence was carried, asserted by two tests, and thrown away before anything printed it. A
    render test says the renderer can print evidence it is handed; only this says the command hands
    it any.
    """
    from periplus.cli import main

    config = tmp_path / "userconf"
    config.mkdir()
    project = tmp_path / "drupal-site"
    project.mkdir()
    (project / "composer.json").write_text(
        '{"require": {"drupal/core-recommended": "^11.1"}}\n', encoding="utf-8"
    )

    previous = os.environ.get("PERIPLUS_CONFIG_DIR")
    os.environ["PERIPLUS_CONFIG_DIR"] = str(config)
    here = Path.cwd()
    os.chdir(project)
    try:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            status = main(["init"])
    finally:
        os.chdir(here)
        if previous is None:
            del os.environ["PERIPLUS_CONFIG_DIR"]
        else:
            os.environ["PERIPLUS_CONFIG_DIR"] = previous

    assert status == 0
    assert f"  detected  {_bundled_pin('drupal_basic')} via composer.json\n" in printed.getvalue()
