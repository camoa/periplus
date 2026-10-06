"""Creating a project: three paths, a record, and a refusal. The package's first write.

Everything else in this package reads. This module is the first thing in it that creates a
directory or opens a file for writing, which makes it a new class of failure rather than a
variation on an existing one — there was no write path here whose error handling this could
pattern-match against, so the handling is written out rather than borrowed.

**This module used to reach no runtime distribution, and no longer does.** The isolation existed
so ``periplus init`` could run on an install missing ``ruamel.yaml``; it cannot. ``cli.main``
returns exit 9 from the dependency check eight lines above the ``init`` dispatch, so a run on that
install never reaches this module at all — measured. What the isolation cost was a 49-line copy of
``report._escape``, which is now imported.

The renderer at the bottom of this file stays here rather than moving into ``report``. What it
renders is an ``InitReport``, a record ``report``'s two renderers know nothing about, and it has no
columns to align, so none of ``report``'s block machinery applies to it.

The stub is **fixed bytes shipped as package data**, written unchanged. Nothing formats YAML at
runtime, so the file a person opens is the file that was reviewed in the diff. The alternative was
``ruamel.yaml``'s round-trip mode, which can carry comments where the loader's ``typ="safe"``
cannot; it was judged and declined because eight ninths of that file is prose no emitter generates
and this version interpolates no value. The trigger to revisit it is the first interpolated value,
not a preference.
"""

from __future__ import annotations

import importlib.resources
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.detect import Detection
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PACKS_DIRECTORY, PROJECT_MARKER, SETTINGS_FILENAME
from periplus.report import _escape

__all__ = ["InitReport", "TargetExists", "initialise_project", "render_text"]

#: The package-data file this module writes, beside the modules rather than under ``packs/``.
STUB = "settings.stub.yml"

#: The prose that introduces a prefilled ``packs:`` block, and the whole of what this module knows
#: about the settings format. It is a constant rather than a template with a hole in it: the only
#: thing that varies between two runs is the list of pins, and the sentence a person reads about
#: them does not.
_PACKS_PREAMBLE = (
    "# The packs `periplus init` recognised in this repository. An ordinary declaration and not a\n"
    "# record of what was detected: it overrides the commented reference block above, and what a\n"
    "# later run loads is what this list says. Delete a line and that pack stops loading; add one\n"
    "# and it starts. Nothing re-runs detection.\n"
    "packs:\n"
)


class TargetExists(HarnessError):
    """A path this command had to create is already there, and nothing was overwritten.

    One class for five causes, because they are one thing to do about it: look at the path the
    message names, and move or delete what is there. ``detail["cause"]`` says which, and the five
    are:

    * ``settings_file`` — the settings file exists. The ordinary second run.
    * ``marker_not_a_directory`` / ``packs_not_a_directory`` — a regular file sits where a
      directory belongs, which ``mkdir(exist_ok=True)`` refuses because it is not a directory.
    * ``marker_is_a_symlink`` / ``packs_is_a_symlink`` — a symlink sits where a directory belongs
      and was **not** followed. See ``_make_directory``.

    Same shape as ``SettingsUnreadable``, which is one class for four causes on the same grounds.
    The list is enumerated here because a docstring that undercounts its own vocabulary is how the
    next reader learns about a value from a bug report. **Nothing reads these keys by name today** —
    the ``init`` subparser takes no ``--format`` and ``render_text`` prints the message and never
    ``detail`` — so the enumeration is for a person reading this file, not a contract a consumer
    holds.

    It ships here rather than in ``errors.py`` because ``errors.py`` says a subclass arrives with
    the module that raises it.
    """

    code = ExitCode.TARGET_EXISTS


@dataclass(frozen=True, slots=True)
class InitReport:
    """What one ``init`` run did, as a record rather than as formatted text.

    ``settings`` is carried rather than derived. It is the one path the command is about and the
    path a refusal names, so the renderer and any second consumer read one field instead of
    rebuilding it from three constants.

    The packs directory is deliberately **not** a field. It is
    ``root / PROJECT_MARKER / PACKS_DIRECTORY``, it is ensured on every successful path, and a
    second way to reach one fact is where two readers drift.

    ``created`` is a boolean beside the path rather than making ``settings`` optional, following
    ``DependencyStatus``'s ``installed``/``present`` pair: a consumer branching on whether the file
    was written should read a boolean, not infer one from an absence.

    ``detected`` is what framework detection found, carried **with its evidence** rather than as the
    pins alone. A pin in a settings file is a suggestion a person is expected to check, and a
    suggestion with no reason attached cannot be checked: the whole argument for a substring
    detector over a smarter one is that the person can see what matched and disagree with it. It is
    the only field here that is not about a path this command wrote.

    It defaults to ``()``, which is a value and not a placeholder: detecting nothing is the ordinary
    outcome, and it is what every caller that does not detect at all should say. The other three
    fields take no default for the reason this one can: there is no honest empty ``settings`` path.
    """

    root: Path
    settings: Path
    created: bool
    problems: tuple[Problem, ...]
    detected: tuple[Detection, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK``.

        The same expression as ``ResolutionReport.exit_code``, repeated rather than factored out.
        A shared base class between two records that have nothing else in common is an edge that
        lets a change to one report change the other, and the package already declines that trade
        for its two renderers.
        """
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def initialise_project(
    root: Path,
    packs: Sequence[str] | None = None,
    detected: Sequence[Detection] = (),
) -> InitReport:
    """Create ``.periplus/``, ``.periplus/packs/`` and the settings file under ``root``.

    ``root`` is an argument and never ``Path.cwd()``, so a test initialises a temporary tree with
    no monkeypatching anywhere — the same reason ``resolve()`` takes ``start``.

    ``packs`` is the pins to declare in the settings file this run writes and ``detected`` is what
    framework detection found, with the evidence for each. Detection is not done here: deciding
    *what* a repository is belongs to ``detect.py``, and writing a file belongs here, and folding
    the two together would make the one command that creates a project also the one that reads
    every pack manifest on the search path.

    **The two are one fact at the ordinary call site.** ``packs`` defaults to ``None``, meaning "the
    pins of ``detected``", so ``cli`` passes the detections and nothing else and the pins written
    cannot drift from the evidence reported. They stay separable because they are separable
    questions — what to write, and why — and a caller with pins from somewhere other than detection
    is the case a future ``--pack`` flag is. Passing both is that caller saying so out loud; passing
    ``packs=()`` beside a detection writes nothing and reports what was found, which is the honest
    reading of an explicit empty list rather than a state to guard against.

    The pins are written in the order they arrive, not sorted here. ``detect_packs`` already returns
    them sorted by pin, and sorting a second time in the function that writes the file would leave
    two places deciding one order — and would silently reorder a list a future caller assembled on
    purpose.

    Each pin is written as a **double-quoted YAML scalar**, through ``json.dumps``, which is a
    subset of YAML 1.2's double-quoted form. A pin is a pack *directory name*, which on Linux is
    any byte sequence without ``/`` or NUL, so a directory called ``x@1\\n  packs: []`` written
    plainly would forge lines into a file that is committed and reviewed. Quoting is unconditional
    rather than applied when a name looks dangerous: a "needs quoting" rule is a second thing to
    get wrong, and this one costs two characters a person reads past.

    Empty is the ordinary case and writes the shipped stub unchanged, in which ``packs:`` is a
    commented reference block. A pin that is written is written into that file and nowhere else:
    it is a value a person then edits, so what a later run resolves is what the file says, never
    what detection once concluded.

    The stub's own docstring above named the condition for it to stop being fixed bytes — "the
    trigger to revisit it is the first interpolated value" — and this is that value. What it is
    **not** is an emitted file: the stub is still shipped bytes, written first and unchanged, and a
    prefill is appended after it. So a project that detected nothing gets the reviewed file byte for
    byte, and one that detected something gets that same file plus a block at the end. Inserting the
    block beside the commented reference block would read better and would need this module and the
    stub to agree on an anchor line, which is a coupling that breaks silently the first time
    somebody edits the prose.

    **Turns a path that is in the way into a report, and lets an environment failure raise.**
    ``TargetExists`` is raised where the facts are in scope and caught here, folded into
    ``problems`` through ``error.problem()``, exactly as ``resolution._read`` does with
    ``SettingsUnreadable``.

    Two failures deliberately propagate, and this used to claim it "never raises for anything a
    person's input can cause", which was false for both. ``FileNotFoundError`` from a missing
    parent: not a state this command can report on, and manufacturing the whole path instead is
    worse than saying so. ``PermissionError`` from a directory the person cannot write: measured,
    and it propagates out of this function rather than becoming a ``Problem``. Where the root was
    writable but the marker's contents were not, ``.periplus`` is already created when it raises,
    leaving a half-built tree with no report. Once the console script wires this capability, that
    surfaces as an uncaught traceback rather than a named refusal.
    Both are the environment refusing rather than a path being in the way, and neither has an exit
    code in the table. Naming them is the honest position until one does.

    Two filesystem rules, and the asymmetry between them is the design:

    * ``exist_ok=True`` on the directories. A ``.periplus/`` holding no settings file is a
      legitimate state — the same directory holds the project's own packs, so a person may have
      made it to drop one in, and a crashed earlier run leaves exactly this — and the run should
      complete from there, writing only what is missing.
    * ``"x"`` on the file, and never an ``is_file()`` question first. Mode ``x`` is
      ``O_EXCL | O_CREAT``, one kernel operation, so there is no check-then-write to race. The
      package's whole existing filesystem idiom is an existence question, and reaching for it here
      is the one way to introduce a race that is not otherwise there.

    ``parents=False`` because ``pathlib`` creates ancestors permissively whatever ``exist_ok``
    says, so the guard has to be this argument and not that one.

    One window is accepted rather than closed: ``open(..., "x")`` creates at zero bytes and then
    writes, so a crash between them leaves a truncated file the next run refuses to fix. It is a
    single write of about fifteen lines and recovery is one ``rm`` of the file the refusal named.
    ``os.replace()`` would close it and was rejected because it overwrites, which destroys the
    refusal this function exists to make; the ``os.link()`` variant closes it while keeping the
    refusal and is the escalation to take if the window ever matters.
    """
    marker = root / PROJECT_MARKER
    settings = marker / SETTINGS_FILENAME
    found = tuple(detected)
    pins = tuple(packs) if packs is not None else tuple(one.pin for one in found)
    try:
        _create(marker, settings, pins)
    except TargetExists as error:
        return InitReport(
            root=root,
            settings=settings,
            created=False,
            problems=(error.problem(),),
            detected=found,
        )
    return InitReport(root=root, settings=settings, created=True, problems=(), detected=found)


def _create(marker: Path, settings: Path, packs: Sequence[str]) -> None:
    """The three creations, in order, raising ``TargetExists`` for anything in the way."""
    _make_directory(marker, "marker")
    _make_directory(marker / PACKS_DIRECTORY, "packs")

    try:
        with settings.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_stub_text() + _packs_block(packs))
    except FileExistsError as error:
        raise TargetExists(
            f"the settings file already exists and was not changed: {settings}",
            {"path": str(settings), "cause": "settings_file"},
        ) from error


def _make_directory(path: Path, what: str) -> None:
    """One directory, created if absent, refused rather than followed or overwritten.

    Both directories go through here, and the second one used to not. An unwrapped
    ``mkdir`` propagated ``FileExistsError`` for a regular file at ``.periplus/packs``, which
    handed a caller a traceback instead of the refusal this module is built to
    return — falsifying ``initialise_project``'s own "never raises" invariant for one reachable
    state while the suite stayed green.

    **The symlink check is not decoration.** ``mkdir(exist_ok=True)`` swallows the error whenever
    ``is_dir()`` is true, and ``is_dir()`` follows the link, so without this a ``.periplus``
    symlinked elsewhere is silently followed: the settings file and the project's own pack root are
    created outside the tree while the report names the path inside it. A repository can carry a
    symlink, so that turns one ``init`` into a create-a-file-and-a-directory primitive in any
    directory the person running it can write to. Measured, both halves — the follow, and that
    ``open(..., "x")`` refuses a symlinked *file* outright because ``O_EXCL | O_CREAT`` does, which
    is why only the directories needed this.

    The check is a question asked before a syscall, so it is **not atomic**, and the window is
    stated at its real size rather than argued away. An earlier version of this paragraph said an
    attacker who can swap the path already has write access to the tree; that understates it.
    Write access to the checkout is not write access to the swap target, and winning the window
    converts one into the other — ``mkdir(exist_ok=True)`` is a silent no-op through a
    symlink-to-directory, and ``O_EXCL`` refuses a symlink only at the **final** path component,
    following symlinked directory components above it.

    What this check does close is the case that needs no race at all: a repository carrying the
    link before the command is ever run. Closing the window itself needs ``O_NOFOLLOW`` on a
    directory file descriptor, which is a larger change and is the escalation
    to take when the tree is not already trusted.
    """
    if path.is_symlink():
        raise TargetExists(
            f"a symlink is in the way and was not followed: {path}",
            {"path": str(path), "cause": f"{what}_is_a_symlink"},
        )
    try:
        path.mkdir(exist_ok=True, parents=False)
    except FileExistsError as error:
        # `exist_ok=True` still refuses when the path exists and is not a directory. A file where
        # a directory belongs is a mistake for a person to resolve, not something to route around.
        raise TargetExists(
            f"a file is in the way of the {what} directory: {path}",
            {"path": str(path), "cause": f"{what}_not_a_directory"},
        ) from error


def _stub_text() -> str:
    """The shipped stub, read through the package rather than off a path built by hand.

    ``importlib.resources`` is what makes this work from a wheel, a zip install and a source
    checkout alike, and it is already how the bundled pack directory is reached.
    """
    return importlib.resources.files("periplus").joinpath(STUB).read_text(encoding="utf-8")


def _packs_block(packs: Sequence[str]) -> str:
    """The ``packs:`` declaration to append after the stub, or nothing at all.

    **No pins is the empty string and not ``packs: []``.** A commented key is "not declared", which
    the stub says in as many words and ``periplus status`` prints rather than guessing a value for;
    an empty list is a declaration that this project loads no packs. A prefill that ran
    unconditionally would turn the first into the second for every repository that matches nothing,
    which is most of them.

    Two blank lines before it, which is the spacing between every other section of the stub, so the
    appended block reads as one more section rather than as something stapled on.
    """
    if not packs:
        return ""
    pins = "".join(f"  - {json.dumps(pin)}\n" for pin in packs)
    return f"\n\n{_PACKS_PREAMBLE}{pins}"


def render_text(report: InitReport) -> str:
    """The report as the two or three lines a person reads.

    Not a block-structured report: there are no columns to align, so ``report.py``'s ``_block`` is
    neither reused nor reimplemented here.

    **The problems go to stdout with the rest**, which is the package's rule rather than the habit:
    the report is the data *including* the problems it found, and stderr carries only what is not
    part of a report. ``cli``'s missing-distribution lines are the counter-example and stay on
    stderr, because on that path nothing is constructed and nothing is rendered.

    **One ``detected`` line per detection, and none at all when nothing was detected.** The pin
    alone would be the wrong half to print: a pin that was written into the settings file is
    already visible in that file, and what the file cannot say is *why*. So the line carries the
    evidence — ``drupal@0.1.0 via composer.json`` — which is the only form in which the prefill is
    checkable by the person expected to edit it.

    Printed on the created path only. A refused run wrote nothing, so a detection it reports is a
    fact about a file that was not touched, and the one thing that run has to say is which path was
    in the way.

    **Both halves go through ``_escape``, and neither is decoration.** A pin is a pack directory
    name and an evidence path is a string out of a third-party ``pack.yaml``: both are chosen by
    whoever wrote the pack, both reach a terminal, and an ESC in either forges a line of this
    report. ``tests/test_detection_guards.py`` asserts the whole rendered string for both, because
    deleting an ``_escape`` call here is a mutation this package has already shipped once.
    """
    lines = [f"periplus init {'created' if report.created else 'refused'}"]
    if report.created:
        lines.append(f"  settings  {_escape(str(report.settings))}")
        lines.append(f"  packs     {_escape(str(report.settings.parent / PACKS_DIRECTORY))}")
        lines += [
            f"  detected  {_escape(found.pin)} via {_escape(found.path)}"
            for found in report.detected
        ]
    lines += [f"  {int(problem.code)}  {_escape(problem.message)}" for problem in report.problems]
    return "\n".join(lines) + "\n"
