"""Creating a project: the three paths, the record, and the refusal.

Every test here runs `initialise_project` against a temporary tree and never through the console
script. The entry point is what a second consumer imports and what these assertions exercise; the
one place the wiring is tested end to end is `test_console_script.py`.

The module under test is the first thing in this package that writes. One of its properties is
therefore not shared with anything already shipped and is asserted here rather than assumed: that
a refused run leaves the existing file untouched byte for byte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.errors import ExitCode
from periplus.init import InitReport, TargetExists, initialise_project, render_text
from periplus.preflight import DependencyStatus
from periplus.resolution import resolve
from periplus.settings import (
    PROJECT_MARKER,
    SETTINGS_FILENAME,
    load_settings_document,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"

# A fixed, complete dependency tuple, supplied the way `main` supplies it. Spelled here rather than
# imported from `test_resolution` so the two files stay independently runnable, and read off no
# installed metadata so no assertion here depends on what this machine has.
DEPENDENCIES = (
    DependencyStatus(distribution="platformdirs", installed="4.11.5", present=True),
    DependencyStatus(distribution="ruamel.yaml", installed="0.19.1", present=True),
)


def _settings(root: Path) -> Path:
    """The one path the command is about, spelled once."""
    return root / PROJECT_MARKER / SETTINGS_FILENAME


def test_it_creates_the_marker_the_packs_directory_and_the_settings_file(tmp_path: Path) -> None:
    """Init creates all three, against a tree that had none of them.

    The packs directory is asserted alongside the settings file because it is the project's own
    pack root: `status` reports it `present` afterwards, and a run that wrote the settings file
    and skipped the directory would satisfy a narrower reading of the requirement while leaving the
    search path a directory short.
    """
    report = initialise_project(tmp_path)

    assert (tmp_path / PROJECT_MARKER).is_dir()
    assert (tmp_path / PROJECT_MARKER / "packs").is_dir()
    assert _settings(tmp_path).is_file()

    assert report.created is True
    assert report.root == tmp_path
    assert report.settings == _settings(tmp_path)
    assert report.problems == ()
    assert report.exit_code is ExitCode.OK


def test_the_bytes_it_wrote_are_the_bytes_it_ships(tmp_path: Path) -> None:
    """Written unchanged, byte for byte, with LF endings and no re-encoding on the way through.

    The written file is also loaded back, which is the whole justification for
    shipping bytes rather than emitting them: a template can be edited into something that no
    longer parses, and nothing about writing it would say so.
    """
    initialise_project(tmp_path)

    shipped = (SRC / "periplus" / "settings.stub.yml").read_bytes()

    assert _settings(tmp_path).read_bytes() == shipped
    assert b"\r\n" not in _settings(tmp_path).read_bytes()
    assert dict(load_settings_document(_settings(tmp_path))) == {"periplus_version": 0}


def test_a_second_run_refuses_and_leaves_the_first_run_byte_identical(tmp_path: Path) -> None:
    """The refusal names the file, exits non-zero, and overwrites nothing.

    The file is edited between the runs on purpose. Comparing the second run against the stub
    would pass for a run that rewrote the file with identical content, which is exactly the
    behaviour to forbid; comparing it against a version only this test could have
    produced is what makes the assertion about not writing rather than about writing the same
    thing.
    """
    initialise_project(tmp_path)
    edited = "periplus_version: 0\npacks:\n  - drupal@0.1.0\n"
    _settings(tmp_path).write_text(edited, encoding="utf-8", newline="\n")

    report = initialise_project(tmp_path)

    assert _settings(tmp_path).read_text(encoding="utf-8") == edited
    assert report.created is False
    assert report.exit_code is ExitCode.TARGET_EXISTS
    assert [problem.code for problem in report.problems] == [ExitCode.TARGET_EXISTS]
    assert str(_settings(tmp_path)) in report.problems[0].detail["path"]
    assert report.problems[0].detail["cause"] == "settings_file"


@pytest.mark.parametrize(
    ("level", "cause"),
    [("marker", "marker_not_a_directory"), ("packs", "packs_not_a_directory")],
)
def test_a_file_where_a_directory_belongs_is_refused_not_raised(
    tmp_path: Path, level: str, cause: str
) -> None:
    """Two causes behind one exit code, distinguished by `detail`, not by a second code.

    `mkdir(exist_ok=True)` still refuses when the path exists and is not a directory, which is
    correct: a file where a created directory belongs is a mistake to resolve, not something to
    route around. It is one thing to do about it -- look at the named path -- so it is one code
    with several causes, the way `SettingsUnreadable` is one class for four.

    The `packs` row is the branch that used to break the invariant: a regular file there made the
    second `mkdir` propagate `FileExistsError`, so a caller got a traceback instead of the designed
    refusal. `initialise_project` does not claim to never raise -- `FileNotFoundError` for a missing
    parent and `PermissionError` for an unwritable directory both propagate -- but it does claim
    that a path in the way becomes a report.
    """
    target = tmp_path / PROJECT_MARKER
    if level == "packs":
        target.mkdir()
        target = target / "packs"
    target.write_text("not a directory\n", encoding="utf-8")

    report = initialise_project(tmp_path)

    assert report.created is False
    assert report.exit_code is ExitCode.TARGET_EXISTS
    assert report.problems[0].detail["cause"] == cause
    assert target.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize(
    ("level", "cause"),
    [("marker", "marker_is_a_symlink"), ("packs", "packs_is_a_symlink")],
)
def test_a_symlinked_directory_is_refused_rather_than_followed(
    tmp_path: Path, level: str, cause: str
) -> None:
    """A `.periplus` symlink would make `init` write outside the tree and misreport where.

    `mkdir(exist_ok=True)` swallows the error whenever `is_dir()` is true, and `is_dir()` follows
    the link -- measured, not assumed. So without this check a repository carrying a `.periplus`
    symlink turns one `periplus init` into a create-a-file-and-a-directory primitive anywhere the
    user can write, and the report names the in-repo path while the bytes land elsewhere. It also
    relocates the project's own pack search root outside the reviewed tree, which is the thing the
    committed-and-diffable property exists to prevent. The `packs` row is the same hole one level
    down: `.periplus/` can be real and `.periplus/packs` a link out.

    The settings file itself was never exposed: `open(..., "x")` is `O_EXCL | O_CREAT`, which
    refuses an existing symlink outright. The directories are what needed the check.
    """
    victim = tmp_path / "victim"
    victim.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    link = repo / PROJECT_MARKER
    if level == "packs":
        link.mkdir()
        link = link / "packs"
    link.symlink_to(victim)

    report = initialise_project(repo)

    assert report.created is False
    assert report.exit_code is ExitCode.TARGET_EXISTS
    assert report.problems[0].detail["cause"] == cause
    assert sorted(p.name for p in victim.iterdir()) == []


def test_it_completes_from_a_half_initialised_project(tmp_path: Path) -> None:
    """A `.periplus/` with no settings file inside it is a state, not an error.

    The same directory holds the project's own packs, so a person may have made it to drop a pack
    in, and a crashed earlier run leaves exactly this. `exist_ok=True` on the directories and `"x"`
    on the file is what lets this run write only what is missing; reversing either half turns a
    recoverable tree into a refusal.
    """
    (tmp_path / PROJECT_MARKER).mkdir()

    report = initialise_project(tmp_path)

    assert report.created is True
    assert report.problems == ()
    assert _settings(tmp_path).is_file()
    assert (tmp_path / PROJECT_MARKER / "packs").is_dir()


def test_it_creates_no_parent_directory_it_was_not_given(tmp_path: Path) -> None:
    """`parents=False`, so a run in a place that does not exist says so rather than inventing it.

    `pathlib` creates ancestors permissively whatever `exist_ok` says, so the guard has to be
    `parents=False` and not a value of `exist_ok`. A run against a missing directory should raise
    rather than manufacture the whole path, because the path it would manufacture is not one
    anybody asked for.
    """
    missing = tmp_path / "no" / "such" / "tree"

    try:
        initialise_project(missing)
    except FileNotFoundError:
        pass
    else:  # pragma: no cover - the failure branch is the assertion
        raise AssertionError("initialise_project invented a parent directory")

    assert not (tmp_path / "no").exists()


def test_the_render_names_the_file_on_both_paths(tmp_path: Path) -> None:
    """The report is the data, so the refusal is part of it and goes to stdout like the rest."""
    created = render_text(initialise_project(tmp_path))
    refused = render_text(initialise_project(tmp_path))

    assert str(_settings(tmp_path)) in created
    assert str(tmp_path / PROJECT_MARKER / "packs") in created
    assert str(_settings(tmp_path)) in refused
    assert created.endswith("\n")
    assert refused.endswith("\n")


def test_the_escape_turns_every_line_forging_character_into_its_ordinal() -> None:
    """The stated property, asserted directly: exact output, over the whole range.

    There is one copy now. `init.py` held a second whose body was byte-identical, and this test
    parametrized over both -- agreement was never the assertion, because two copies of one function
    share every hole they have: neither escaped the C1 range, so U+009B, CSI in a UTF-8 xterm,
    reached a rendered report as a raw control sequence. The copy is deleted and `init` imports
    this function; the case table it was checked against is carried over unchanged, over the whole
    Unicode `Cc` category, 0x00-0x1F and 0x7F-0x9F.

    U+2028 and U+2029 are in the table because they are not control characters and `splitlines()`
    splits on them anyway: a name holding one produced output with no newline in it at all that
    `splitlines()` still read as three lines.

    The expectations are spelled out rather than derived from the implementation -- derived from it,
    this assertion could not disagree -- which is also why the three named forms are listed by hand
    and the whole range is generated rather than a list of interesting inputs chosen by hand. An
    earlier version named eight cases and had no carriage return among them, so deleting the `\\r`
    rule from one of the two copies left them divergent and the whole suite still passing.
    """
    from periplus.report import _escape as escape

    # Three of the C0 characters have a named form, applied before the ordinal pass, so the
    # expectation is not uniformly `\xNN`.
    named = {0x09: "\\t", 0x0A: "\\n", 0x0D: "\\r"}
    cases: list[tuple[str, str]] = []
    for code in [*range(0x20), *range(0x7F, 0xA0)]:
        # Built outside the f-string: a backslash inside a nested one is 3.12+ syntax and this
        # project's floor is 3.11, so the shorter form would have been a portability bug the
        # suite could not see while it runs on 3.14.
        marker = named.get(code, f"\\x{code:02x}")
        cases.append((f"name{chr(code)}tail", f"name{marker}tail"))
    for code in (0x2028, 0x2029):
        # Spelled out rather than imported from `_LINE_BOUNDARIES`: derived from the
        # implementation, this guard would skip whatever the implementation stopped escaping.
        marker = f"\\u{code:04x}"
        cases.append((f"name{chr(code)}tail", f"name{marker}tail"))
    cases += [
        ("plain", "plain"),
        ("back\\slash", "back\\\\slash"),
        ("surrogate\udcff", "surrogate\\udcff"),
        ("Émile", "Émile"),
        ("", ""),
    ]

    for case, expected in cases:
        rendered = escape(case)
        # Exact output, and not "the raw character is gone": that is satisfied by deleting it, and
        # a mutant that deleted C1 rather than escaping it would pass the whole suite.
        # What separates escaping from dropping is that the ordinal turns up in the output.
        assert rendered == expected, f"_escape on {case!r} rendered {rendered!r}"
        # One line, whatever went in. `str.splitlines()` splits on more than `\n`, and counting
        # newlines would have missed the two boundaries above.
        assert len(rendered.splitlines()) <= 1, f"_escape forged a line on {case!r}"


def test_the_render_escapes_a_control_character_in_every_value_it_prints() -> None:
    """`_escape` being correct is one property; `render_text` calling it is another.

    The test above asserts the function over a case table. It says nothing about the three values
    this renderer passes through it, and a cleanup that merged the two away left all three call
    sites unasserted -- removing every one of them kept the suite green.

    ESC is the character rather than a newline because it is the one the escape exists to stop: a
    directory named `evil\\x1b[2Ktree` writes a raw erase-line sequence into a report a person
    reads, and no line count would notice. The problem message carries the same path because a
    refusal quotes it, which is how the third value is reachable.

    Both assertions compare the whole rendered string, not "the raw ESC is absent". Absence is
    satisfied by dropping the character, and a mutant that drops rather than escapes is an
    easy one to miss. What separates the two is that `\\x1b`
    turns up where the character was.
    """
    root = Path("/nowhere/evil\x1b[2Ktree")
    settings = root / PROJECT_MARKER / SETTINGS_FILENAME
    # The same tree with the escape applied, spelled by hand: derived from `_escape`, this
    # expectation could not disagree with it.
    escaped_root = Path("/nowhere/evil\\x1b[2Ktree")

    created = render_text(InitReport(root=root, settings=settings, created=True, problems=()))

    assert created == (
        "periplus init created\n"
        f"  settings  {escaped_root / PROJECT_MARKER / SETTINGS_FILENAME}\n"
        f"  packs     {escaped_root / PROJECT_MARKER / 'packs'}\n"
    )

    refusal = TargetExists(
        f"the settings file already exists and was not changed: {settings}",
        {"path": str(settings), "cause": "settings_file"},
    )
    refused = render_text(
        InitReport(root=root, settings=settings, created=False, problems=(refusal.problem(),))
    )

    assert refused == (
        "periplus init refused\n"
        "  10  the settings file already exists and was not changed: "
        f"{escaped_root / PROJECT_MARKER / SETTINGS_FILENAME}\n"
    )


def test_it_prefills_the_packs_it_was_given_into_the_settings_it_writes(tmp_path: Path) -> None:
    """Init in a matching fixture writes the pack name.

    Loaded back rather than searched for as a substring. `packs:` appears in the shipped stub as a
    commented reference block naming `drupal@0.1.0`, so a test asserting the text is in the file
    passes against a run that wrote nothing at all -- and against one that wrote a pin inside a
    comment, which is the failure that looks most like success. What
    "writes the pack name" means is that the settings loader reads it back as a declared value, and
    that is the only form of the assertion that can tell the two apart.

    `periplus_version` is asserted alongside because a prefill that replaced the stub rather than
    adding to it would satisfy everything above while throwing away the file's other declared key
    and all of its reference prose.
    """
    report = initialise_project(tmp_path, packs=("drupal@0.1.0", "acme@1.0.0"))

    assert report.created is True
    assert report.problems == ()
    assert report.exit_code is ExitCode.OK

    document = load_settings_document(_settings(tmp_path))
    packs = document.get("packs")
    assert packs is not None, "the settings file declares no `packs:`, so nothing was prefilled"
    assert list(packs) == ["drupal@0.1.0", "acme@1.0.0"]
    assert document.get("periplus_version") == 0
    assert b"\r\n" not in _settings(tmp_path).read_bytes()


def test_it_declares_no_packs_when_it_detected_none(tmp_path: Path) -> None:
    """At the unit tier, an empty prefill declares nothing.

    A commented-out key is "not declared", which the stub says in as many words and `periplus
    status` prints rather than guessing a value for. So the assertion is the absence of the key,
    not the absence of the text.

    Green when this was written, and kept anyway: it is the guard against a prefill that runs
    unconditionally and writes `packs: []` into every project, which would turn "not declared" into
    "declared empty" for every repository that matches nothing.
    """
    report = initialise_project(tmp_path, packs=())

    assert report.created is True
    assert report.problems == ()
    assert report.exit_code is ExitCode.OK
    assert "packs" not in load_settings_document(_settings(tmp_path))


def test_what_resolves_is_what_the_settings_file_says_and_not_what_was_detected(
    tmp_path: Path,
) -> None:
    """Init "leaves the value editable", tested as the one thing that can falsify it.

    Editable is not a property of the bytes. The failure it rules out is a tool that detects at
    resolution time and applies the answer regardless of the file -- which writes the same settings
    file, passes every assertion above, and cannot be edited at all, because deleting the line
    changes nothing.

    So this asserts twice against `resolve`, which is the reader every later command goes through.
    First that the prefilled pin arrives carrying the project settings file as its source, and then
    that replacing the pin replaces what resolves. A runtime detector fails the second assertion by
    handing back drupal again.

    The pins are deliberately not installed. `resolve` reports them unmatched, and this test says
    nothing about that: what it is about is which value was read, not whether a directory answers
    it.

    **The `composer.json` below is the fixture condition the whole test rests on.** Against an
    empty directory a resolution-time detector detects nothing -- so it would have nothing to
    override the edit with, the second assertion would hold, and the test would pass against
    exactly the defect its docstring names. A root the
    shipped drupal detector matches is what gives a runtime detector a competing answer to hand
    back, and it is the only condition under which the failure this test names can occur.
    """
    config = tmp_path / "userconf"
    config.mkdir()
    env = {"PERIPLUS_CONFIG_DIR": str(config)}
    root = tmp_path / "project"
    root.mkdir()
    (root / "composer.json").write_text(
        '{"require": {"drupal/core-recommended": "^11.1"}}\n', encoding="utf-8"
    )

    initialise_project(root, packs=("drupal@0.1.0",))
    resolved = resolve(root, env, DEPENDENCIES).settings

    assert resolved is not None
    assert resolved.packs is not None, "the initialised project resolves no `packs:` at all"
    assert resolved.packs.value == ("drupal@0.1.0",)
    assert [ref.kind for ref in resolved.packs.sources] == ["project"], (
        "the pin must come from the project settings file, which is the file a person edits"
    )

    _settings(root).write_text(
        "periplus_version: 0\npacks:\n  - edited@9.9.9\n", encoding="utf-8", newline="\n"
    )
    edited = resolve(root, env, DEPENDENCIES).settings

    assert edited is not None
    assert edited.packs is not None
    assert edited.packs.value == ("edited@9.9.9",), (
        "editing the file did not change what resolves, so the value was never the file's"
    )
