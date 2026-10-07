"""The pack search path: which roots are searched, what is under them, and what a pin matches.

Every test runs against a real temporary tree or against the real bundled root, because the two
functions that reach the filesystem are filesystem functions by nature — a root's `exists`, an
entry's type and the order `iterdir` happens to return things in are only true of a directory that
is there. `match_pins` touches nothing and is tested against constructed candidates.

The one property the whole component exists to hold is that no file inside a pack directory is
opened. It is asserted with an interpreter audit hook rather than by patching the readers or by
making the files unreadable. Both of those enumerate a mechanism and both were defeated by one they
did not name — `chmod 000` by a suite running as root, and a monkeypatch over `builtins.open` by
`io.open`, which holds its own reference to the same object. The hook is raised from inside the
interpreter and nothing can rebind past it.
"""

from __future__ import annotations

import importlib.resources
import os
import sys
from pathlib import Path

import pytest

from periplus.errors import ExitCode
from periplus.packs import (
    PACKS_DIRECTORY,
    PackName,
    discover_candidates,
    match_pins,
    resolve_pack_roots,
)
from periplus.settings import (
    PROJECT_MARKER,
    ResolvedSetting,
    SourceRef,
    load_settings_document,
    locate_settings,
    resolve_settings,
)

# The packs that ship inside the wheel, in the code-point order discovery has to return them
# in. Written out rather than read off the directory, for the reason the packaging suite gives
# about its own copy: a list derived from the thing under test agrees with any edit to it.
BUNDLED_PACK_NAMES = [
    "advancedqueue_basic@0.0.1",
    "ai_basic@0.0.1",
    "config_pages_basic@0.0.1",
    "crop_basic@0.0.1",
    "drupal@0.1.0",
    "drupal_basic@0.3.0",
    "drupal_js_basic@0.0.1",
    "drush_basic@0.0.1",
    "eck_basic@0.0.1",
    "go@0.0.2",
    "go_basic@0.0.3",
    "js_basic@0.0.1",
    "laravel_basic@0.0.5",
    "paragraphs_basic@0.0.1",
    "php@0.1.0",
    "php_basic@0.2.0",
    "profile_basic@0.0.1",
    "salesforce_basic@0.0.1",
    "twig@0.0.1",
    "twig_basic@0.1.0",
    "twig_tweak_basic@0.0.1",
    "webform_basic@0.0.1",
    "yaml@0.0.1",
    "yaml_basic@0.1.0",
]


# The opens-nothing guard. An audit hook cannot be removed once installed, so it is installed once
# here and does nothing at all until `_AUDIT_ROOTS` is armed — one list check per `open` event for
# the rest of the process. Armed, it records the path of every open under any pack root, whatever
# mechanism opened it: CPython raises this event from inside the interpreter, so `builtins.open`,
# `io.open`, `os.open`, `Path.open` and `Path.read_text` all reach it and none can rebind past it.
_AUDIT_ROOTS: list[str] = []
_AUDIT_OPENS: list[str] = []


def _record_opens(event: str, args: tuple[object, ...]) -> None:
    if event != "open" or not _AUDIT_ROOTS:
        return
    try:
        opened = os.fsdecode(args[0])
    except TypeError:
        return  # an open by file descriptor names no path
    if any(opened.startswith(root) for root in _AUDIT_ROOTS):
        _AUDIT_OPENS.append(opened)


sys.addaudithook(_record_opens)


def _configured(*entries: tuple[Path, str]) -> ResolvedSetting[tuple[Path, ...]]:
    """A `pack_paths` value built by hand, each entry paired with the file that declared it.

    Constructed rather than resolved, for the tests where the settings cascade is not what is under
    test. The one test that *is* about attribution builds its value from two real settings files
    instead, because a hand-built `entry_sources` would agree with whatever this module does with
    it.
    """
    return ResolvedSetting(
        value=tuple(path for path, _ in entries),
        sources=tuple(dict.fromkeys(SourceRef(kind="project", name=name) for _, name in entries)),
        entry_sources=tuple(SourceRef(kind="project", name=name) for _, name in entries),
    )


def test_a_root_that_does_not_exist_is_reported_absent_rather_than_omitted(
    tmp_path: Path,
) -> None:
    """A root with no directory behind it comes back with `exists` false, still in the tuple.

    This is the reason the record carries `exists` at all: a person whose
    pin did not resolve needs to read the list of places that were looked in, and a place that was
    looked in and found empty is one of them. Omitting it would print a shorter list that says
    nothing about why.

    Both absent roots are real absent directories under `tmp_path` rather than constructed values,
    because `exists` is a claim about the filesystem.
    """
    roots = resolve_pack_roots(tmp_path / "norepo", tmp_path / "nouserconf", None)

    absent = [root for root in roots if root.kind in {"project", "user"}]
    assert [root.kind for root in absent] == ["project", "user"]
    assert [root.exists for root in absent] == [False, False]
    assert [root.display for root in absent] == [
        str(tmp_path / "norepo" / PROJECT_MARKER / PACKS_DIRECTORY),
        str(tmp_path / "nouserconf" / PACKS_DIRECTORY),
    ]


def test_the_three_fixed_roots_come_back_in_order_with_the_configured_ones_after(
    tmp_path: Path,
) -> None:
    """Project, user, bundled, then `pack_paths` — with all four existing, so order is order.

    A fixture where only one root exists cannot tell an ordering from a coincidence, so all three
    fixed roots and one configured root are real directories here. The bundled root is the
    installed one; nothing constructs it.
    """
    root = tmp_path / "repo"
    (root / PROJECT_MARKER / PACKS_DIRECTORY).mkdir(parents=True)
    user_dir = tmp_path / "userconf"
    (user_dir / PACKS_DIRECTORY).mkdir(parents=True)
    extra = tmp_path / "extra"
    extra.mkdir()

    roots = resolve_pack_roots(root, user_dir, _configured((extra, "/repo/.periplus/settings.yml")))

    assert [r.kind for r in roots] == ["project", "user", "bundled", "configured"]
    assert [r.exists for r in roots] == [True, True, True, True]
    assert [r.source for r in roots] == [
        None,
        None,
        None,
        SourceRef(kind="project", name="/repo/.periplus/settings.yml"),
    ]


def test_a_project_root_of_none_produces_no_project_record(tmp_path: Path) -> None:
    """Run outside any repository and the project root is not reported absent — it is not reported.

    `absent` is for a directory that has a path and is not there. A root with no path has no name
    to print, and printing one would name a directory nothing ever intended to search. This is
    `locate_settings`' own rule for a layer whose file location is not knowable.
    """
    roots = resolve_pack_roots(None, tmp_path / "nouserconf", None)

    assert [root.kind for root in roots] == ["user", "bundled"]


def test_each_configured_root_names_the_settings_file_that_declared_that_entry(
    tmp_path: Path,
) -> None:
    """A configured root's `source` is the file that declared *that path*, not the last file.

    One fixture, built so that both available wrong answers are distinguishable. Each file declares
    `/opt/shared` and one path of its own, so the union drops the project file's copy of the shared
    directory: the effective value has three entries, `sources` has two references — user then
    project, because both files declared the key — and `entry_sources` has three, two of them the
    user file and the last the project file.

    An implementation that zips the value against `sources` runs out of references before it runs
    out of roots, and one that attributes *every* entry to `sources[0]` reports the user file
    against a directory only the project file named. Both were planted. No fixture where each file
    contributes one surviving path can tell the first apart, and none where every surviving entry
    came from one file can tell the second apart.
    """
    user_dir = tmp_path / "userconf"
    user_dir.mkdir()
    root = tmp_path / "repo"
    (root / PROJECT_MARKER).mkdir(parents=True)
    (user_dir / "settings.yml").write_text(
        'pack_paths: ["/opt/shared", "./extra"]\n', encoding="utf-8"
    )
    (root / PROJECT_MARKER / "settings.yml").write_text(
        'pack_paths: ["/opt/shared", "./proj"]\n', encoding="utf-8"
    )

    sources = locate_settings(root, user_dir)
    documents = {source.kind: load_settings_document(source.path) for source in sources}
    settings = resolve_settings(documents["user"], documents["project"], sources)
    pack_paths = settings.pack_paths
    assert pack_paths is not None

    # The fixture's discriminating property, asserted rather than assumed: three entries, two
    # `sources`, and per-entry attribution that disagrees with both wrong answers.
    assert pack_paths.value == (Path("/opt/shared"), user_dir / "extra", root / "proj")
    assert [ref.kind for ref in pack_paths.sources] == ["user", "project"]

    roots = resolve_pack_roots(root, user_dir, pack_paths)

    user_ref = SourceRef(kind="user", name=str(user_dir / "settings.yml"))
    project_ref = SourceRef(kind="project", name=str(root / PROJECT_MARKER / "settings.yml"))
    configured = [r for r in roots if r.kind == "configured"]
    assert [r.display for r in configured] == [
        str(Path("/opt/shared")),
        str(user_dir / "extra"),
        str(root / "proj"),
    ]
    assert [r.source for r in configured] == [user_ref, user_ref, project_ref]


def test_root_order_beats_name_order_across_roots(tmp_path: Path) -> None:
    """Candidates sort by root first and by name only within a root.

    Every name in the second and third roots sorts before every name in the first, so a single
    global sort by name would put them first. A fixture whose roots happen to be in name order
    cannot tell the two rules apart.

    The first root here is the real bundled one, which is also the assertion that the fixed roots
    keep their position ahead of the configured ones once discovery has run.

    Within a root the order is code point order, and the directories are created in reverse of the
    order they must be reported in: on ext4 with hashed directories `iterdir`'s own order is
    arbitrary, so a test that asserted against `iterdir` would agree with whatever it returned and
    prove nothing, and one that created them in sorted order would pass with the sort deleted.
    """
    first = tmp_path / "first"
    first.mkdir()
    for name in ("o@1.0.0", "n@1.0.0", "m@1.0.0"):
        (first / name).mkdir()
    second = tmp_path / "second"
    second.mkdir()
    for name in ("b@1.0.0", "a@1.0.0"):
        (second / name).mkdir()

    roots = resolve_pack_roots(
        None, tmp_path / "nouserconf", _configured((first, "s.yml"), (second, "s.yml"))
    )
    candidates = discover_candidates(roots)

    assert [c.entry for c in candidates] == [
        *BUNDLED_PACK_NAMES,
        "m@1.0.0",
        "n@1.0.0",
        "o@1.0.0",
        "a@1.0.0",
        "b@1.0.0",
    ]


def test_every_entry_under_a_root_is_reported_with_what_its_name_makes_of_it(
    tmp_path: Path,
) -> None:
    """A directory that no pin can ever match is reported, and so is an entry that is not one.

    Five ways a name fails to be `<pack>@<version>` and one way an entry fails to be a directory,
    all under one root. Reporting them is the difference between "there is nothing there" and
    "there is something there that no pin can ever match"; dropping them would hide a `pack.yaml`
    a person left loose beside their packs.
    """
    extra = tmp_path / "extra"
    extra.mkdir()
    for name in ("drupal@0.1.0", "drupal", "a@b@c", "@1.0.0", "drupal@"):
        (extra / name).mkdir()
    (extra / "README.md").write_text("not a pack\n", encoding="utf-8")

    roots = resolve_pack_roots(None, tmp_path / "nouserconf", _configured((extra, "s.yml")))
    candidates = [c for c in discover_candidates(roots) if c.root.kind == "configured"]

    assert [(c.entry, c.status, c.name) for c in candidates] == [
        ("@1.0.0", "unnamed", None),
        ("README.md", "not_a_directory", None),
        ("a@b@c", "unnamed", None),
        ("drupal", "unnamed", None),
        ("drupal@", "unnamed", None),
        ("drupal@0.1.0", "named", PackName(pack="drupal", version="0.1.0")),
    ]


@pytest.mark.skipif(os.geteuid() == 0, reason="permissions do not apply to root")
def test_a_root_that_exists_and_cannot_be_listed_contributes_nothing_and_does_not_raise(
    tmp_path: Path,
) -> None:
    """An unreadable directory on the search path is not a failure of its own.

    There is no exit code for it, and inventing one is deliberately avoided. The root stays in the
    report with `exists` true, so a person reading the list of places that were looked in still sees
    it; a pin that needed one of its directories fails when it is matched.

    Skipped under root, where a mode of 0 does not stop a read and the test would pass for the wrong
    reason.
    """
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "php@0.1.0").mkdir()
    after = tmp_path / "after"
    after.mkdir()
    (after / "ok@1.0.0").mkdir()
    closed.chmod(0o000)
    try:
        roots = resolve_pack_roots(
            None, tmp_path / "nouserconf", _configured((closed, "s.yml"), (after, "s.yml"))
        )
        candidates = discover_candidates(roots)
    finally:
        closed.chmod(0o755)

    assert [r.exists for r in roots if r.kind == "configured"] == [True, True]
    # The root that could not be listed contributes nothing, and the root *after* it is still
    # searched: a catch around the whole loop rather than around the one `iterdir` would lose
    # every later root, and a fixture with nothing after the closed root could not tell.
    assert [c.entry for c in candidates] == [*BUNDLED_PACK_NAMES, "ok@1.0.0"]


def test_a_configured_path_that_is_already_a_fixed_root_is_not_searched_twice(
    tmp_path: Path,
) -> None:
    """A `pack_paths` entry naming a fixed root changes nothing: it was already to be searched.

    Without this, every directory under that path is discovered twice and every pin matching one of
    them reports a duplicate that does not exist. `settings.py` records the same hazard as the
    reason `pack_paths` merges by union rather than accumulation, and the reasoning has to reach
    across the fixed roots or it is only half applied.

    The survivor is the fixed root: it keeps its `project` kind and its `source` stays `None`,
    because the settings file did not add it and naming that file beside it would be a report that
    lies about where the directory came from.
    """
    root = tmp_path / "repo"
    project_packs = root / PROJECT_MARKER / PACKS_DIRECTORY
    project_packs.mkdir(parents=True)
    user_dir = tmp_path / "userconf"

    roots = resolve_pack_roots(
        root, user_dir, _configured((project_packs, "/repo/.periplus/settings.yml"))
    )

    assert len(roots) == 3
    assert [r.kind for r in roots] == ["project", "user", "bundled"]
    assert roots[0].display == str(project_packs)
    assert roots[0].source is None


def _tree(parent: Path, name: str, *entries: str) -> Path:
    """A pack root holding `entries` as directories, each with a real `pack.yaml` inside it."""
    root = parent / name
    root.mkdir()
    for entry in entries:
        (root / entry).mkdir()
        manifest = root / entry / "pack.yaml"
        manifest.write_text(f"pack: {entry}\nversion: 9.9.9\n", encoding="utf-8")
    return root


def test_three_unmatched_pins_produce_three_problems_in_one_run(tmp_path: Path) -> None:
    """One call reports every unmatched pin, which is why nothing here raises.

    An exception carries the first pin and the person fixes it, re-runs, and is told about the
    second. That is the tool doing half its work per run, and it is the reason this module ships no
    `HarnessError` subclass at all.

    The fourth pin does not parse as `<pack>@<version>` at all, and it is the same failure on the
    same path: there is no directory whose name is `drupal`, so it is reported as matched nowhere
    and needs no new code and no new exit code.

    Every problem also names the roots that were searched, which is what a person reads to see where
    the tool looked.
    """
    roots = resolve_pack_roots(None, tmp_path / "nouserconf", None)

    matches, problems = match_pins(
        ["one@1.0.0", "two@1.0.0", "three@1.0.0", "drupal"], discover_candidates(roots)
    )

    assert matches == ()
    assert [p.detail["pin"] for p in problems] == [
        "one@1.0.0",
        "two@1.0.0",
        "three@1.0.0",
        "drupal",
    ]
    assert {p.code for p in problems} == {ExitCode.PIN_UNMATCHED}
    assert problems[0].detail["searched"] == ", ".join(
        root.display for root in roots if root.kind in {"bundled", "configured"}
    )


def test_a_pin_matches_its_directory_name_byte_for_byte(tmp_path: Path) -> None:
    """No case folding and no version comparison. `drupal@0.1.0` matches `drupal@0.1.0` and nothing.

    The two ways a lookup gets quietly loosened are a case-insensitive compare and a version
    compare that treats `0.1` and `0.1.0` as one. Both are asserted against here, because either
    would make the harness decide something about pack identity, which is the validator's job.

    The four bundled packs no pin names are not a problem either: a directory under a person's pack
    folder is an error only when a pin needs it.
    """
    roots = resolve_pack_roots(None, tmp_path / "nouserconf", None)
    candidates = discover_candidates(roots)

    matched, problems = match_pins(["drupal@0.1.0"], candidates)
    folded, _ = match_pins(["DRUPAL@0.1.0"], candidates)
    shortened, _ = match_pins(["drupal@0.1"], candidates)

    assert len(matched) == 1
    assert matched[0].name == PackName(pack="drupal", version="0.1.0")
    assert matched[0].root.kind == "bundled"
    assert matched[0].path.endswith("/periplus/packs/drupal@0.1.0")
    assert folded == ()
    assert shortened == ()
    assert problems == ()


def test_one_name_under_two_roots_is_reported_twice_rather_than_resolved(tmp_path: Path) -> None:
    """Two roots holding one directory name give two matches and one problem, not a first-wins pick.

    The fixture is two roots holding one name, because that is what the rule is about: one root
    holding two names, or two roots holding two names, tests the code around the rule and not the
    rule. A deterministic tool cannot pick one of the two, and the order they were searched in must
    not become the answer.

    Both matches are returned alongside the problem. Dropping either would report the name once and
    resolve it by omission, which is the outcome to rule out.
    """
    first = _tree(tmp_path, "first", "dup@1.0.0")
    second = _tree(tmp_path, "second", "dup@1.0.0")
    roots = resolve_pack_roots(
        None, tmp_path / "nouserconf", _configured((first, "s.yml"), (second, "s.yml"))
    )

    matches, problems = match_pins(["dup@1.0.0"], discover_candidates(roots))

    assert len(matches) == 2
    assert [m.root.display for m in matches] == [str(first), str(second)]
    assert [m.path for m in matches] == [str(first / "dup@1.0.0"), str(second / "dup@1.0.0")]
    assert len(problems) == 1
    assert problems[0].code == ExitCode.PIN_DUPLICATED
    assert problems[0].detail["roots"] == f"{first}, {second}"


def test_no_file_inside_a_pack_directory_is_opened(tmp_path: Path) -> None:
    """The scope narrowing, asserted directly: every open is observed, and none is under a root.

    The guard is an interpreter audit hook, and the formulation matters more than the fixture does.
    Two weaker guards were tried and each was defeated by a mechanism it did not enumerate:

    * `chmod 000` on the `pack.yaml` files — what this component's design first proposed.
      Permissions do not apply to root, so on a suite running as root the files stay readable and
      the test passes whether or not the code opens them.
    * A monkeypatch over `Path.open`, `Path.read_text`, `Path.read_bytes` and `builtins.open`. That
      rebinds four names. `io.open` holds its own reference to the same object — `io.open is open`
      is `True`, so rebinding one name does not touch the other — and `os.open` is a separate entry
      point below both. A read through either passed the whole suite.

    An audit hook enumerates nothing. CPython raises the `open` event from inside the interpreter,
    so `builtins.open`, `io.open`, `os.open`, `Path.open` and `Path.read_text` all reach it, and
    `iterdir` — which this module must be free to do — raises none of it. Verified for all five;
    the three the monkeypatch missed are planted in the plant log.

    The pipeline runs twice with the hook armed for both, and nothing under test runs before it is
    armed. An earlier arrangement took the first result unwatched and compared the second against
    it; a read that happened only on the first call passed that, because the only unwatched call was
    the one that did the reading. The prefixes are therefore computed here rather than by calling
    `resolve_pack_roots` first, and they are wider than the roots: the whole temporary tree, and the
    installed pack directory reached the same way `packs.py` reaches it.

    Two assertions. The recorded opens are the property itself. Equality between the two runs is the
    determinism property in miniature, and it is the assertion that survives if a future guard
    stops recording — an audit hook only observes, so unlike the monkeypatch it changes nothing
    about the run it watches.
    """
    extra = _tree(tmp_path, "extra", "php@0.1.0", "drupal@0.2.0", "loose")
    (extra / "README.md").write_text("not a pack\n", encoding="utf-8")
    pins = ["php@0.1.0", "drupal@0.2.0", "missing@1.0.0"]

    def resolve() -> object:
        roots = resolve_pack_roots(None, tmp_path / "nouserconf", _configured((extra, "s.yml")))
        candidates = discover_candidates(roots)
        return roots, candidates, match_pins(pins, candidates)

    bundled = importlib.resources.files("periplus") / PACKS_DIRECTORY
    _AUDIT_OPENS.clear()
    _AUDIT_ROOTS.extend([f"{tmp_path}{os.sep}", f"{bundled}{os.sep}"])
    try:
        first = resolve()
        second = resolve()
    finally:
        _AUDIT_ROOTS.clear()

    assert _AUDIT_OPENS == []
    assert first == second
