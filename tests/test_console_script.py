"""The console script's error vocabulary, its dependency check, and the wiring between them.

One of these runs the real command in a subprocess where a required distribution genuinely is not
there, rather than patching one out. The property is about what happens on a broken install, and
a mocked absence is a test of the mock.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pty
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.preflight import REQUIRED, DependencyStatus, check_runtime_dependencies

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"


def _run_child(
    body: str, *, isolated: bool, stdin: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``body`` in a fresh interpreter, optionally with no site-packages at all.

    ``stdin`` defaults to ``None``, which is ``subprocess``'s own default and leaves the five
    existing call sites exactly as they were: the child inherits this process's file descriptor 0.
    Pass ``subprocess.DEVNULL`` to close it. That distinction is the whole point of the parameter —
    inherited, fd 0 is whatever pytest's capture mode left there, ``/dev/null`` under default
    capture and the developer's terminal under ``-s``, so a test asserting "needs no terminal"
    against the inherited descriptor asserts against an unspecified one.

    ``isolated=True`` passes ``-S`` and puts only ``src`` on the path, so no distribution metadata
    is installed as far as the child can see. That is a real absence rather than a patched one:
    ``importlib.metadata.version`` genuinely finds nothing, which is the state a user has when they
    have not installed the dependencies.

    The environment is built rather than inherited, so an inherited ``PYTHONPATH`` cannot put
    site-packages back and quietly turn an absence test into a presence test.
    """
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    argv = [sys.executable, *(["-S"] if isolated else []), "-c", body]
    return subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        argv, capture_output=True, text=True, env=env, check=False, stdin=stdin
    )


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


def test_a_missing_dependency_ends_the_run_at_exit_9_naming_every_one(tmp_path: Path) -> None:
    """A missing dependency, end to end: non-zero, naming which distribution.

    One child carries three properties, because they are three readings of one run. The child is
    ``-S`` with only ``src`` on its path, so no distribution metadata is installed as far as it can
    see: a real absence rather than a patched one, and ``importlib.metadata`` genuinely finds
    nothing for either name.

    The import at the top of the body is the import-graph property, which is a property of a graph
    rather than of a file. A per-file "standard library only" check passes while ``errors`` imports
    ``periplus.settings``, which imports ``ruamel.yaml``: the edge is first-party, the file reads
    clean, and a missing dependency then dies of an ``ImportError`` before the check that exists to
    name it ever runs. An earlier draft of the design declared ``Problem`` in ``resolution.py`` and
    had exactly that defect. Here the import happens where neither distribution can be imported at
    all, so a module-level edge to one raises rather than passing quietly — which is what the
    ``ImportError`` assertion below reads. Run in a subprocess because the import must be the first
    one of this process; importing ``periplus.cli`` in-process would find it already in
    ``sys.modules`` from the imports at the top of this file and assert nothing at all.

    The statuses are written to a file rather than printed, because stdout is itself under
    assertion here.

    "Rather than failing later inside a subcommand" is the half that shapes the design, so the
    assertions cover it directly — no traceback reaches the user, and the failure is a named report
    line rather than an ``ImportError`` from somewhere deeper.

    All three absent names appear, not just the first. A person who installs one distribution and
    re-runs to be told about the next has been made to do the tool's own work. ``jsonschema`` is
    the third since ``periplus validate`` grew a reference validator, and it is the one this
    assertion is most needed for: it arrived last, so it is the name a startup check written for
    two distributions silently omits.

    On stderr, and stdout must stay empty. There is no report on this path — step 2 runs before
    `resolve()` is called, so nothing is constructed and nothing is rendered — which puts the
    message in the design's "what is not part of the report". The empty-stdout assertion is the
    load-bearing half: the stdout rule exists so a consumer parsing `--format json` gets one
    document whether the run succeeded or failed, and a bare text line there would hand that
    consumer a malformed document.

    The argument is ``["status"]`` and not ``[]``. A bare invocation is decided by the parse, above
    this check, so it exits 2 on this install as well — asserting 9 against it would be asserting
    against a path that no longer reaches here.
    """
    statuses = tmp_path / "statuses.json"
    body = (
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "from periplus.cli import main\n"
        "from periplus.preflight import check_runtime_dependencies\n"
        "\n"
        f"Path({str(statuses)!r}).write_text(json.dumps(\n"
        "    [[s.distribution, s.installed, s.present] for s in check_runtime_dependencies()]\n"
        "), encoding='utf-8')\n"
        "raise SystemExit(main(['status']))\n"
    )

    result = _run_child(body, isolated=True)

    assert result.returncode == 9, f"expected 9, got {result.returncode}: {result.stderr}"
    assert json.loads(statuses.read_text(encoding="utf-8")) == [
        ["jsonschema", None, False],
        ["platformdirs", None, False],
        ["ruamel.yaml", None, False],
        ["tree-sitter", None, False],
    ]
    assert "ruamel.yaml" in result.stderr
    assert "platformdirs" in result.stderr
    assert "jsonschema" in result.stderr
    assert result.stdout == "", f"a startup diagnostic reached stdout: {result.stdout!r}"
    assert "Traceback" not in result.stderr, result.stderr
    assert "ImportError" not in result.stdout + result.stderr


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


def test_the_subcommands_are_exactly_init_spec_status_validate_map_and_update() -> None:
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

    assert set(subcommands.choices) == {"init", "spec", "status", "validate", "map", "update"}


def test_the_old_subcommand_name_is_a_usage_error() -> None:
    """``periplus resolve`` exits 2, which is what makes "gone" different from "renamed"."""
    from periplus.cli import main

    with pytest.raises(SystemExit) as refused:
        main(["resolve"])

    assert refused.value.code == 2


@pytest.mark.skipif(sys.platform == "win32", reason="pty and termios are POSIX-only")
def test_a_terminal_receives_the_same_bytes_as_a_pipe_and_no_escape_sequence(
    tmp_path: Path,
) -> None:
    """The two things a terminal can change about this program's output, both forced over a pty.

    First: the report does not change when stdout is a terminal. A test that only pipes cannot
    observe TTY detection at all, which is the mechanism it exists to forbid — colour or
    column-fitting that switches on ``isatty`` makes two runs on one input differ in bytes, and
    every run under pytest takes the pipe branch. ``ONLCR`` is turned off on that pty: the terminal
    line discipline translates every LF the *driver* sees into CRLF, which is not something the
    program wrote, and leaving it on would make this fail for a reason that has nothing to do with
    the report.

    Second: the colour decision, forced rather than hoped for. **On 3.14 only.** Under pytest
    capture and under a pipe ``can_colorize()`` returns false and every run looks plain, so a check
    that leaves the environment alone cannot tell the guarded parser from the default one. The
    second half forces the question instead: it drives the real console script over a pty **and**
    sets ``PYTHON_COLORS=1``, which ``_colorize.can_colorize`` checks before the tty test.

    Two earlier drafts overstated what that buys, and both were measured false:

    * The pty is **not** the only place the difference shows. With the environment below and
      ``stdout`` on a plain pipe, the unguarded parser still emits ``\x1b[1;34musage: ``. It is the
      forced environment doing the work; the pty makes the run resemble the case a person meets.
    * The parser is **not** the only thing that can keep an escape out of this output. On 3.11
      through 3.13 — which ``pyproject.toml`` declares — ``argparse`` has no ``color`` keyword at
      all, so gutting the guard leaves this green because the interpreter keeps the escape out.
      Nothing can regress there. That half bites on 3.14 and is vacuous below it.
    """
    import termios

    # Scoped to this interpreter's own directory. A bare `shutil.which("periplus")` finds whatever
    # is first on PATH -- here a snapshot copy under ~/.local/bin that is neither `src/` nor the
    # environment pytest runs from -- so the test would be about some other build. A decoy shell
    # script printing a usage line and exiting 2 passes every assertion below, which is what makes
    # the unscoped form a hole rather than a nuisance.
    script = shutil.which("periplus", path=str(Path(sys.executable).parent))
    assert script is not None, "run `uv pip install -e '.[dev]'` into this interpreter"

    config = tmp_path / "userconf"
    config.mkdir()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PERIPLUS_CONFIG_DIR": str(config),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    piped = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [script, "status"], capture_output=True, env=env, cwd=tmp_path, check=False
    )

    primary, secondary = pty.openpty()
    attributes = termios.tcgetattr(secondary)
    attributes[1] &= ~termios.ONLCR
    termios.tcsetattr(secondary, termios.TCSANOW, attributes)
    try:
        on_a_terminal = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
            [script, "status"],
            stdout=secondary,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=tmp_path,
            check=False,
        )
        os.close(secondary)
        report_chunks = []
        # A pty with no writer left raises EIO on Linux where a pipe would return b"". Both mean
        # end of stream, and treating the error as anything else would make this test flaky rather
        # than correct.
        try:
            while chunk := os.read(primary, 65536):
                report_chunks.append(chunk)
        except OSError:
            pass
    finally:
        os.close(primary)

    assert piped.returncode == on_a_terminal.returncode == 0
    assert b"".join(report_chunks) == piped.stdout

    primary, secondary = pty.openpty()
    try:
        # **stdout** on the pty, not only stderr. `argparse.py:202` calls `can_colorize()` with no
        # file argument, and it defaults to `sys.stdout` -- so with stdout on /dev/null colour is
        # never enabled and this test passes whatever the parser was built with. An earlier version
        # did exactly that: mutating `_COLOUR` to `{}` left it green, which is a test that cannot
        # fail dressed as the one that forces the condition. stderr is on the pty too because that
        # is where the usage line goes.
        child = subprocess.Popen(  # noqa: S603 - list argv, shell unset, nothing interpolated
            [script],
            stdout=secondary,
            stderr=secondary,
            stdin=subprocess.DEVNULL,
            # The environment is built, not inherited, and it asks for colour as loudly as
            # CPython allows. Inherited, a developer shell carrying `NO_COLOR=1` or
            # `PYTHON_COLORS=0` turns `can_colorize()` off, and this test would pass green under the
            # exact regression it guards -- measured both ways: the
            # mutant fails under an empty ambient environment, `NO_COLOR=1`, `PYTHON_COLORS=0`,
            # `TERM=dumb`, and all three together.
            env={
                "PATH": os.environ.get("PATH", ""),
                "TERM": "xterm-256color",
                "PYTHON_COLORS": "1",
                "FORCE_COLOR": "1",
            },
        )
        # Closed here so the read below sees EOF once the child is gone. Held open, the loop would
        # never end.
        os.close(secondary)
        secondary = -1
        # Read to EOF rather than once. One `os.read` returns one pty buffer, which truncates at
        # about 4 KiB, and a child writing more than the buffer holds would block forever against a
        # reader that has stopped. `Popen` plus a drain plus a bounded `wait` removes both.
        usage_chunks: list[bytes] = []
        while True:
            try:
                chunk = os.read(primary, 65536)
            except OSError:  # the child closed its side
                break
            if not chunk:
                break
            usage_chunks.append(chunk)
        returncode = child.wait(timeout=30)
    finally:
        if secondary != -1:
            os.close(secondary)
        os.close(primary)

    written = b"".join(usage_chunks)

    assert returncode == 2, "a bare invocation is still a usage error"
    assert b"\x1b" not in written, f"argparse wrote an escape sequence: {written!r}"
    assert b"periplus" in written


def test_init_runs_to_completion_with_stdin_closed_and_refuses_a_second_run(
    tmp_path: Path,
) -> None:
    """Init needs no terminal, and a second run's refusal status, at the surface a person types.

    ``init`` asks nothing, so it needs no terminal. ``stdin=subprocess.DEVNULL`` rather than the
    inherited descriptor: inherited, fd 0 is pytest's capture artefact and the assertion would be
    about that rather than about a closed stdin.

    The same command run a second time refuses, and leaves the first run's file byte-identical.
    """
    body = (
        "import os\n"
        f"os.chdir({str(tmp_path)!r})\n"
        "from periplus.cli import main\n"
        "raise SystemExit(main(['init']))\n"
    )

    first = _run_child(body, isolated=False, stdin=subprocess.DEVNULL)
    before = (tmp_path / ".periplus" / "settings.yml").read_bytes()
    second = _run_child(body, isolated=False, stdin=subprocess.DEVNULL)

    assert first.returncode == 0, f"{first.stdout}{first.stderr}"
    assert (tmp_path / ".periplus" / "settings.yml").is_file()
    assert (tmp_path / ".periplus" / "packs").is_dir()
    assert ".periplus" in first.stdout

    assert second.returncode == 10
    assert (tmp_path / ".periplus" / "settings.yml").read_bytes() == before
    assert str(tmp_path) in second.stdout, "the refusal names the file that stopped it"
    assert second.stderr == "", "a refusal is part of the report, so it goes to stdout"


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


def test_a_non_ascii_working_directory_survives_an_ascii_console(tmp_path: Path) -> None:
    """`_pin_the_output_stream()` leads, and this is the run that would fail if it did not.

    Both subcommands print paths taken from the working directory. Under a console whose encoding
    cannot represent them -- `PYTHONIOENCODING=ascii` is how that is reached deliberately -- an
    unpinned stdout raises `UnicodeEncodeError` and the command dies with a traceback instead of
    printing the path. The pin reconfigures stdout to UTF-8 before anything writes, and it was
    moved above every branch during this build after the `init` branch was found writing beneath
    it.
    """
    script = shutil.which("periplus", path=str(Path(sys.executable).parent))
    assert script is not None, "run `uv pip install -e '.[dev]'` into this interpreter"

    project = tmp_path / "café-π"
    project.mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    env = {
        **os.environ,
        "PYTHONIOENCODING": "ascii",
        "PERIPLUS_CONFIG_DIR": str(config),
    }

    finished = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [script, "init"],
        capture_output=True,
        cwd=project,
        env=env,
        check=False,
        timeout=60,
    )

    assert finished.returncode == 0, f"{finished.stdout!r}{finished.stderr!r}"
    assert b"Traceback" not in finished.stderr
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
    assert list(packs) == ["drupal_basic@0.2.0"]


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
