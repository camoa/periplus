"""The console script's error vocabulary, its dependency check, and the wiring between them."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.preflight import REQUIRED, DependencyStatus, check_runtime_dependencies


class _PinUnmatched(HarnessError):
    """A stand-in for the subclass ``packs.py`` will ship, defined here on purpose.

    Testing against a shipped subclass would test one instance of the mechanism. Two subclasses
    defined in the test file test the mechanism itself, and the second one is what makes a
    hardcoded code in ``problem()`` fail instead of pass.
    """

    code = ExitCode.PIN_UNMATCHED


class _SettingsNotFound(HarnessError):
    """The second subclass, carrying a different code. See ``_PinUnmatched``."""

    code = ExitCode.NO_SETTINGS


def test_a_harness_error_renders_a_problem_carrying_its_own_subclass_code() -> None:
    """``problem()`` reads the code off the raising class, not off a literal, and the facts it
    carries are a snapshot the caller cannot reach.

    Both subclasses are exercised in one test. With only one, a ``problem()`` that returned a
    hardcoded ``ExitCode.PIN_UNMATCHED`` would pass, and the design's claim that adding a failure
    class needs no edit to existing code would be untested while looking tested.

    ``frozen=True`` stops the ``detail`` field being rebound and does nothing about the mapping
    inside it, so without a copy a caller that reused its dictionary would edit a record a report
    had already collected. That is a determinism failure with no visible cause.
    """
    facts = {"pin": "drupal", "root": "bundled"}
    unmatched = _PinUnmatched("no directory matched the pin", facts)
    absent = _SettingsNotFound("no settings file at either level")

    assert unmatched.problem() == Problem(
        code=ExitCode.PIN_UNMATCHED,
        message="no directory matched the pin",
        detail={"pin": "drupal", "root": "bundled"},
    )
    assert absent.problem().code is ExitCode.NO_SETTINGS
    assert absent.problem().detail == {}

    facts["pin"] = "tampered"

    assert unmatched.problem().detail == {"pin": "drupal", "root": "bundled"}

    with pytest.raises(TypeError):
        unmatched.problem().detail["pin"] = "tampered"  # type: ignore[index]


def test_the_statuses_come_back_sorted_by_distribution_name() -> None:
    """Every required distribution is reported present with the version that is installed, in an
    order that comes from a sort rather than from the order the constant happens to be written in.

    Two runs on the same input must be byte-identical and these statuses reach the report, so the
    order has to come from somewhere other than a literal somebody typed.

    The last assertion is what keeps the ordering one honest. ``REQUIRED`` is deliberately not
    written in sorted order, so deleting the ``sorted()`` call changes the result and this test
    fails. Sort ``REQUIRED`` itself and this assertion fails on purpose — not because anything
    broke, but to say that the sort has become a no-op and the determinism above is no longer being
    tested.
    """
    from importlib.metadata import version

    statuses = check_runtime_dependencies()

    assert statuses == tuple(
        DependencyStatus(distribution=name, installed=version(name), present=True)
        for name in sorted(REQUIRED)
    )
    assert [status.distribution for status in statuses] == sorted(REQUIRED)
    assert sorted(REQUIRED) != list(REQUIRED), (
        "REQUIRED is now in sorted order, so check_runtime_dependencies()'s sort is unobservable "
        "and the assertion above passes whether or not it is still there"
    )


def test_the_format_choices_are_exactly_the_renderers_the_report_module_offers() -> None:
    """``--format``'s choices and ``report.RENDERERS`` name the same two formats, in the same order.

    They are two constants on purpose. ``cli`` may not import ``report``: ``report`` imports
    ``resolution``, which imports ``settings``, which imports ``ruamel.yaml``, so
    ``choices=tuple(RENDERERS)`` in ``build_parser`` would put a runtime distribution on the
    console script's module-level import path and a missing one would raise ``ImportError`` before
    the check that exists to name it.

    ``RENDERERS`` is imported inside this function rather than at module level, which is where it
    is harmless: this file is a test, not the console script.

    Asserted through the parser's behaviour as well as through its declaration. The declaration
    alone reads a private argparse attribute; the behaviour alone cannot show that the accepted set
    is only these two. Together they say both.
    """
    from periplus.cli import build_parser
    from periplus.report import RENDERERS

    parser = build_parser()
    # `_subparsers_action` and `_actions` are argparse internals. There is no public way to read a
    # subparser's declared choices back, and this is the tie that stops the duplicated constant
    # drifting, so the private access is the price of having the tie at all.
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    status_parser = subcommands.choices["status"]
    fmt = next(action for action in status_parser._actions if action.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(RENDERERS) == ("text", "json")
    assert fmt.default == next(iter(RENDERERS))

    for name in RENDERERS:
        assert parser.parse_args(["status", "--format", name]).format == name
    with pytest.raises(SystemExit) as refused:
        parser.parse_args(["status", "--format", "yaml"])
    assert refused.value.code == 2


def test_the_map_format_choices_and_default_are_exactly_the_map_renderers() -> None:
    """``map --format``'s choices and default name the same formats as ``map.RENDERERS``.

    The same tie as the one above, for the subcommand whose module imports ``jsonschema``, which
    is why ``cli`` writes the names as a literal and this test holds the literal to the table.
    """
    from periplus.cli import build_parser
    from periplus.map import RENDERERS

    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(action for action in subcommands.choices["map"]._actions if action.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(RENDERERS)
    assert fmt.default == next(iter(RENDERERS))


def test_the_export_format_choices_are_exactly_the_export_writers_wo2() -> None:
    """``export --format``'s choices name the formats ``export.WRITERS`` holds, in its order."""
    from periplus.cli import build_parser
    from periplus.navigate.export import WRITERS

    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(
        action for action in subcommands.choices["export"]._actions if action.dest == "format"
    )

    assert tuple(fmt.choices or ()) == tuple(WRITERS) == ("graphml", "dot", "mermaid")


def test_the_check_map_format_choices_and_default_are_exactly_the_check_map_renderers() -> None:
    """``check-map --format`` names the formats ``checkmap.RENDERERS`` holds, as ``map``'s does."""
    from periplus.checkmap import RENDERERS
    from periplus.cli import build_parser

    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    check = subcommands.choices["check-map"]
    fmt = next(action for action in check._actions if action.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(RENDERERS)
    assert fmt.default == next(iter(RENDERERS))


def test_main_returns_the_reports_exit_code_for_a_run_it_completed(tmp_path: Path) -> None:
    """``main(["status", ...])`` returns an integer, and it is the report's own code.

    Called directly rather than through the binary. The install checks and the two determinism
    demonstrations are the only places the script itself runs.
    """
    from periplus.cli import main

    config = tmp_path / "userconf"
    config.mkdir()
    cwd = Path.cwd()
    os.chdir(tmp_path)
    previous = os.environ.get("PERIPLUS_CONFIG_DIR")
    os.environ["PERIPLUS_CONFIG_DIR"] = str(config)
    try:
        status = main(["status", "--format", "json"])
    finally:
        os.chdir(cwd)
        if previous is None:
            del os.environ["PERIPLUS_CONFIG_DIR"]
        else:
            os.environ["PERIPLUS_CONFIG_DIR"] = previous

    # 0, because a temporary directory holding no settings file at either level is a state and not
    # a failure -- the run resolved everything it could and found nothing wrong. An integer and not
    # an ExitCode is what `[project.scripts]` hands the interpreter.
    assert status == 0, "an unconfigured run resolves; it does not fail"
    assert isinstance(status, int)


def test_the_settings_flag_reaches_the_resolution_and_anchors_the_project_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--settings PATH`` names the file to read, and the root it implies wins over the walk.

    The run starts inside a real project tree whose settings file says something different, so a
    wiring that dropped the flag would resolve that project and pass every assertion about a
    successful run. What it would not do is name the file the person asked for.
    """
    from periplus.cli import main

    walked = tmp_path / "walked"
    (walked / ".periplus").mkdir(parents=True)
    (walked / ".periplus" / "settings.yml").write_text("packs: []\n", encoding="utf-8")
    named = tmp_path / "named"
    named.mkdir()
    (named / "elsewhere.yml").write_text("periplus_version: 7\n", encoding="utf-8")
    config = tmp_path / "userconf"
    config.mkdir()

    cwd = Path.cwd()
    previous = os.environ.get("PERIPLUS_CONFIG_DIR")
    os.chdir(walked)
    os.environ["PERIPLUS_CONFIG_DIR"] = str(config)
    try:
        status = main(["status", "--format", "json", "--settings", str(named / "elsewhere.yml")])
    finally:
        os.chdir(cwd)
        if previous is None:
            del os.environ["PERIPLUS_CONFIG_DIR"]
        else:
            os.environ["PERIPLUS_CONFIG_DIR"] = previous

    document = json.loads(capsys.readouterr().out)
    assert status == 0
    assert document["project_root"] == str(named)
    assert document["settings"]["periplus_version"]["value"] == 7


def test_the_subcommands_are_exactly_the_set_listed_below() -> None:
    """The surface, asserted as a set rather than by trying names one at a time.

    ``resolve`` named a function rather than what a person is asking for, and it is gone rather
    than aliased: the tool is unpublished and installed on one machine, so there is no caller to
    break, and an alias would be a compatibility promise made to nobody and tested forever.

    ``validate`` is the fourth, and **this test's name changed with the set** rather than the
    literal alone. The name is the record of what the tool offers, and one reading
    ``..._are_exactly_init_spec_and_status`` while asserting four names would claim a surface the
    tool no longer has. A set and not a superset, so a fifth subcommand added without a decision
    fails here.
    """
    from periplus.cli import build_parser

    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )

    assert set(subcommands.choices) == {
        "init",
        "spec",
        "status",
        "validate",
        "map",
        "update",
        "types",
        "legend",
        "check-map",
        "find",
        "show",
        "neighbors",
        "affected",
        "depth",
        "path",
        "skills",
        "slice",
        "export",
    }


def test_the_old_subcommand_name_is_a_usage_error() -> None:
    """``periplus resolve`` exits 2, which is what makes "gone" different from "renamed"."""
    from periplus.cli import main

    with pytest.raises(SystemExit) as refused:
        main(["resolve"])

    assert refused.value.code == 2


def test_init_runs_to_completion_with_stdin_closed_and_refuses_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Init needs no terminal, and a second run's refusal status, at the surface a person types.

    ``init`` asks nothing, so it needs no terminal. ``sys.stdin`` is a closed stream, so a read
    from it raises instead of returning whatever pytest's capture left in its place.

    The same command run a second time refuses, and leaves the first run's file byte-identical.
    """
    from periplus.cli import main

    config = tmp_path / "userconf"
    config.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stdin", closed)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(config))
    monkeypatch.chdir(project)
    settings = project / ".periplus" / "settings.yml"

    first_status = main(["init"])
    first = capsys.readouterr()
    before = settings.read_bytes()
    second_status = main(["init"])
    second = capsys.readouterr()

    assert first_status == 0, f"{first.out}{first.err}"
    assert settings.is_file()
    assert (project / ".periplus" / "packs").is_dir()
    assert ".periplus" in first.out

    assert second_status == 10
    assert settings.read_bytes() == before
    assert str(project) in second.out, "the refusal names the file that stopped it"
    assert second.err == "", "a refusal is part of the report, so it goes to stdout"


def test_status_reports_the_project_pack_root_only_once_init_has_made_one(tmp_path: Path) -> None:
    """The project pack root appears in ``status`` only once ``init`` has made one.

    Before ``init`` there is **no project pack root row at all** — not one reading ``absent``.
    ``resolve_pack_roots`` emits no project record without a project root, on the stated grounds
    that a root with no path names a directory nothing ever intended to search. The assertion
    below would fail against a reading that expects an ``absent`` row.
    """
    from periplus.cli import main

    config = tmp_path / "userconf"
    config.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    def run(argv: list[str]) -> tuple[int, dict[str, object]]:
        previous = os.environ.get("PERIPLUS_CONFIG_DIR")
        os.environ["PERIPLUS_CONFIG_DIR"] = str(config)
        here = Path.cwd()
        os.chdir(project)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = main(argv)
        finally:
            os.chdir(here)
            if previous is None:
                del os.environ["PERIPLUS_CONFIG_DIR"]
            else:
                os.environ["PERIPLUS_CONFIG_DIR"] = previous
        return code, json.loads(buffer.getvalue()) if argv[-1] == "json" else {}

    _, before = run(["status", "--format", "json"])
    kinds_before = [root["kind"] for root in before["pack_roots"]]  # type: ignore[index,union-attr]

    assert "project" not in kinds_before, before

    run(["init"])

    _, after = run(["status", "--format", "json"])
    project_roots = [
        root
        for root in after["pack_roots"]  # type: ignore[index,union-attr]
        if root["kind"] == "project"
    ]

    assert len(project_roots) == 1, after
    assert project_roots[0]["exists"] is True
    assert str(project / ".periplus" / "packs") in str(project_roots[0]["display"])


def test_a_non_ascii_working_directory_survives_an_ascii_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_pin_the_output_stream()` leads, and this is the run that would fail if it did not.

    Both subcommands print paths taken from the working directory. Under a console whose encoding
    cannot represent them an unpinned stdout raises `UnicodeEncodeError` and the command dies with
    a traceback instead of printing the path. The pin reconfigures stdout to UTF-8 before anything
    writes, and it was moved above every branch during this build after the `init` branch was
    found writing beneath it. The console here is a text stream over bytes with the `ascii`
    encoding, which is what `PYTHONIOENCODING=ascii` gives the program.
    """
    from periplus.cli import main

    project = tmp_path / "café-π"
    project.mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    console = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    monkeypatch.setattr(sys, "stdout", console)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(config))
    monkeypatch.chdir(project)

    status = main(["init"])

    console.flush()
    assert status == 0
    assert "café-π".encode() in console.buffer.getvalue()  # type: ignore[attr-defined]
    assert (project / ".periplus" / "settings.yml").is_file()


def _init_in(directory: Path, config: Path) -> int:
    """Run ``periplus init`` with ``directory`` as the working directory, and return the status.

    Called in process rather than through the binary, the way the other wiring tests here are, and
    with ``PERIPLUS_CONFIG_DIR`` pointed at an empty directory so no settings file belonging to the
    person running the suite can reach the run.
    """
    from periplus.cli import main

    previous = os.environ.get("PERIPLUS_CONFIG_DIR")
    os.environ["PERIPLUS_CONFIG_DIR"] = str(config)
    here = Path.cwd()
    os.chdir(directory)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return main(["init"])
    finally:
        os.chdir(here)
        if previous is None:
            del os.environ["PERIPLUS_CONFIG_DIR"]
        else:
            os.environ["PERIPLUS_CONFIG_DIR"] = previous


def test_init_prefills_the_pack_it_detected_in_the_directory_it_ran_in(tmp_path: Path) -> None:
    """Init prefills a detected pack, at the surface a person actually types.

    ``test_init.py`` specifies what ``initialise_project`` does with the pins it is handed. Nothing
    there says anything reaches it: the command could detect nothing, pass nothing, and every
    assertion in that file would still hold. This is where the two halves are tied together, and it
    is the one assertion that fails if the wiring in ``cli.main`` is missing.

    The fixture is a ``composer.json`` requiring Drupal core, which is what the bundled drupal
    detector matches. The pin is read out of the settings file the command wrote, through the
    loader, for the reason ``test_init.py`` gives -- the stub already carries ``drupal@0.1.0``
    inside a comment, so a substring search passes against a run that detected nothing.
    """
    from periplus.settings import load_settings_document

    config = tmp_path / "userconf"
    config.mkdir()
    project = tmp_path / "drupal-site"
    project.mkdir()
    (project / "composer.json").write_text(
        '{"require": {"drupal/core-recommended": "^11.1"}}\n', encoding="utf-8"
    )

    status = _init_in(project, config)

    assert status == 0
    document = load_settings_document(project / ".periplus" / "settings.yml")
    packs = document.get("packs")
    assert packs is not None, "`periplus init` in a Drupal checkout declared no `packs:`"
    assert list(packs) == ["drupal_basic@0.3.0"]


def test_init_in_a_directory_matching_no_pack_still_exits_zero(tmp_path: Path) -> None:
    """The same surface when nothing is detected: detecting nothing is a state, not a fault.

    The directory holds a ``composer.json`` that requires something other than Drupal, rather than
    being empty. An empty directory exits 0 whatever detection does -- there is nothing to read and
    nothing to fail on -- so it cannot tell a run that detected nothing from a run that fell over
    on the way. This one gives detection a file to open and a near miss to decline.

    Green when this was written, and kept: it is what fails if detection ever starts reporting a
    non-match, or raising on a repository it does not recognise.
    """
    from periplus.settings import load_settings_document

    config = tmp_path / "userconf"
    config.mkdir()
    project = tmp_path / "symfony-app"
    project.mkdir()
    (project / "composer.json").write_text(
        '{"require": {"symfony/console": "^7.2"}}\n', encoding="utf-8"
    )

    status = _init_in(project, config)

    assert status == 0
    assert (project / ".periplus" / "settings.yml").is_file()
    assert "packs" not in load_settings_document(project / ".periplus" / "settings.yml")
