"""The console script: argument parsing and wiring, and nothing else.

Every unit of logic lives in the package. This module reads ``sys.argv``, calls one entry point,
and turns what comes back into a process status. A branch here that is not parsing or wiring
belongs in a module beside this one.

Three modules are imported at module level and no others: ``errors``, ``preflight``, and the
standard library. Everything else is imported inside ``main()``, after the dependency check has
run. That ordering is the whole of "a missing dependency fails at startup, named" — a module-level
``import periplus.resolution`` would pull ``ruamel.yaml`` onto this file's import path and the run
would die of an ``ImportError`` before the check that exists to name the problem ever executed.

``periplus.report`` is imported inside ``main()`` for the same reason, and that is also why
``--format``'s choices are written here as a literal rather than read off ``report.RENDERERS``. A
test asserts the two agree.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import periplus
from periplus.errors import ExitCode
from periplus.preflight import check_runtime_dependencies

__all__ = ["build_parser", "main"]

#: argparse gained ``color`` in 3.14 and defaults it to ``True``, consulting ``os.isatty()`` — so
#: the same source writes ANSI escapes into a usage line on 3.14 and plain text on 3.11. This tool
#: declares 3.11 through 3.14 and promises output that does not depend on where it ran,
#: and `_pin_the_output_stream` below already pays for the same property on stdout.
#:
#: A mapping rather than a branch inside ``build_parser``, because on 3.11 through 3.13 the keyword
#: is a ``TypeError`` and the parser has to be built without it — measured on both interpreters.
#:
#: ``dict[str, Any]`` and not ``dict[str, bool]``: a ``**mapping`` splat is checked against every
#: parameter of the callee, so the narrower type is four ``arg-type`` errors rather than none —
#: measured — against ``prog``, ``usage``, ``parents`` and ``formatter_class``, only two of which
#: are strings. What that gives up is that a misspelled key typechecks — inert below 3.14, a
#: ``TypeError`` on every invocation above it. That trade is recorded here and asserted nowhere:
#: no test reads the mapping's contents.
#: The parser is built from configuration the way ``MERGE_RULES`` is a table rather than a chain of
#: conditions, and ``build_parser`` stays a sequence of ``add_argument`` calls.
#:
#: One keyword on the top parser covers the subparsers too: ``add_subparsers`` assigns
#: ``action._color = self.color``, overriding the ``True`` that ``_SubParsersAction.__init__``
#: hardcodes. Verified by running the coloured and uncoloured cases in one command.
_COLOUR: dict[str, Any] = {"color": False} if sys.version_info >= (3, 14) else {}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser.

    ``--version`` is a plain flag rather than ``action="version"`` on purpose: argparse's version
    action calls ``sys.exit`` from inside the parser, and the entrypoint contract says ``main``
    returns an integer and never exits the process. A test that called a parser which exits could
    only assert on ``SystemExit``, which is a worse test of the same thing.

    The subparsers are added without ``required=True``, and that is forced rather than chosen.
    argparse checks a required subcommand *after* it has consumed the options, so
    ``periplus --version`` on a required-subparser parser is a usage error — which would break
    the two tests that pin ``main(["--version"]) == 0``. ``main`` raises the
    usage error itself, through ``parser.error``, which is argparse's own message, argparse's own
    stream and argparse's own status; what it is not is argparse's own *decision*.
    """
    parser = argparse.ArgumentParser(
        prog="periplus",
        description="A schema-first, deterministic codebase mapper, configurable to any stack.",
        **_COLOUR,
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed version and exit",
    )
    # No hand-written ``metavar``. It read ``{resolve}`` and existed only because a one-member
    # list read badly; with three members argparse's own default renders ``{init,spec,status}``.
    # Deleting it is the twelfth rename site, and the one a search for the quoted literal misses
    # because the name sat inside a longer string.
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser(
        "init",
        help="create this project's .periplus directory and a stub settings file",
        description="Create the project directory, its pack directory and a stub settings file.",
    )
    spec = subcommands.add_parser(
        "spec",
        help="print the pack contract: the schemas, the rule format, the engine, and what is open",
        description="Publish the contract a pack is authored against, and stop.",
    )
    spec.add_argument(
        "pack",
        nargs="?",
        default=None,
        metavar="PACK",
        help="a pack name, to add what its manifest declares and what it inherits",
    )
    spec.add_argument(
        "--format",
        # The same two names again, written out for the same reason the block below gives:
        # `periplus.spec` imports `report`, which reaches `ruamel.yaml`, so reading
        # `spec.RENDERERS` here would put a runtime distribution on this module's import path. A
        # test asserts these two names equal `tuple(spec.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the contract (default: text)",
    )
    spec.add_argument(
        "--summary",
        action="store_true",
        help="print the summary block only, without the documents' contents",
    )
    check = subcommands.add_parser(
        "validate",
        help="check one pack's files against the shipped schemas and name what disagrees",
        description="Check a pack against the schemas it is written against, and stop.",
    )
    # Required, unlike `spec`'s. A bare `periplus validate` would check the file `init` writes,
    # and a test that loads that file asserts that property rather than a second command surface.
    check.add_argument(
        "pack",
        metavar="PACK",
        help="the pack to check: NAME, or NAME@VERSION to name one of several copies",
    )
    check.add_argument(
        "--format",
        # The same two names as a literal, for the third time and for the reason the two blocks
        # around it give: `periplus.validate` imports `jsonschema` and reaches `ruamel.yaml`
        # through `resolution`, so reading `validate.RENDERERS` here would put two runtime
        # distributions on this module's import path. A test asserts these two names equal
        # `tuple(validate.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the findings (default: text)",
    )
    refresh = subcommands.add_parser(
        "update",
        help="move this project's pins to the rutter versions that are installed",
        description="Rewrite each pin whose rutter is installed at another version, and stop.",
    )
    refresh.add_argument(
        "--format",
        # A literal for the reason `validate`'s is: `periplus.update` reaches `ruamel.yaml`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    extract = subcommands.add_parser(
        "map",
        help="extract the map of this project and write it",
        description="Run the loaded packs' rules over the project, write the map, and stop.",
    )
    extract.add_argument(
        "--format",
        # The same two names as a literal, for the reason the blocks above give: `periplus.map`
        # imports `jsonschema`. A test asserts these two names equal `tuple(map.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    extract.add_argument(
        "--settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="the project settings file to read, instead of the one the project root implies",
    )
    extract.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="where to write the map (default: .periplus/map.json under the project root)",
    )
    types = subcommands.add_parser(
        "types",
        help="list the node types and edge kinds in the written map",
        description="Count the node types and edge kinds the map holds, and stop.",
    )
    types.add_argument(
        "--format",
        # A literal for the reason `map`'s is: `periplus.navigate` imports `jsonschema`. A test
        # asserts these names equal `tuple(types.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    types.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help="the map file to read (default: .periplus/map.json under the project root)",
    )
    check = subcommands.add_parser(
        "check-map",
        help="check the written map against the map schema",
        description="Check every node and edge of the map against the map schema, and stop.",
    )
    check.add_argument(
        "--format",
        # A literal for the reason `map`'s is: `periplus.checkmap` imports `jsonschema`. A test
        # asserts these names equal `tuple(checkmap.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    check.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help="the map file to check (default: .periplus/map.json under the project root)",
    )
    find = subcommands.add_parser(
        "find",
        help="find the nodes whose id holds a text",
        description="List the nodes whose id holds TEXT, closest match first, and stop.",
    )
    find.add_argument("text", metavar="TEXT", help="the text to look for in node ids")
    find.add_argument("--type", default=None, metavar="T", help="keep type T and its subtypes")
    find.add_argument(
        "--limit", type=int, default=50, metavar="N", help="rows to show; 0 shows all (default: 50)"
    )
    find.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help="the map file to read (default: .periplus/map.json under the project root)",
    )
    find.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(find.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    show = subcommands.add_parser(
        "show",
        help="show one node and the edges at it",
        description="Show the node ID and every edge leaving or arriving at it, and stop.",
    )
    show.add_argument("id", metavar="ID", help="the node id, as periplus find prints it")
    show.add_argument(
        "--limit", type=int, default=50, metavar="N", help="rows to show; 0 shows all (default: 50)"
    )
    show.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help="the map file to read (default: .periplus/map.json under the project root)",
    )
    show.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(show.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    for name, helptext in (
        ("neighbors", "list the items an item's edges lead to"),
        ("affected", "list the items whose edges lead to an item"),
    ):
        walking = subcommands.add_parser(name, help=helptext, description=f"{helptext}, and stop.")
        walking.add_argument("id", metavar="ID", help="the node id, as periplus find prints it")
        walking.add_argument(
            "--depth",
            type=int,
            default=1,
            metavar="N",
            help="edges to follow, 1 or more (default: 1)",
        )
        walking.add_argument(
            "--kind",
            action="append",
            default=[],
            metavar="K",
            help="keep only edges of kind K; repeat for several",
        )
        walking.add_argument(
            "--limit",
            type=int,
            default=50,
            metavar="N",
            help="rows to show; 0 shows all (default: 50)",
        )
        walking.add_argument(
            "--map",
            type=Path,
            default=None,
            metavar="PATH",
            help="the map file to read (default: .periplus/map.json under the project root)",
        )
        walking.add_argument(
            "--format",
            # A literal for the reason `types`' is; a test asserts it equals the RENDERERS.
            choices=("text", "json"),
            default="text",
            help="how to print the report (default: text)",
        )
    path = subcommands.add_parser(
        "path",
        help="show every shortest chain of edges from one item to another",
        description="Show the shortest directed chains of edges from FROM to TO, and stop.",
    )
    path.add_argument("source", metavar="FROM", help="the node id the chains start at")
    path.add_argument("target", metavar="TO", help="the node id the chains end at")
    path.add_argument(
        "--kind",
        action="append",
        default=[],
        metavar="K",
        help="follow only edges of kind K; repeat for several",
    )
    path.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="chains to show; 0 shows all (default: 10)",
    )
    path.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help="the map file to read (default: .periplus/map.json under the project root)",
    )
    path.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(path.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    status = subcommands.add_parser(
        "status",
        help="report the settings, the pack search path and the directories on it",
        description="Report what this project resolves to, and stop.",
    )
    status.add_argument(
        "--format",
        # The two names are written out here and read off `report.RENDERERS` nowhere. Reading them
        # would put `from periplus.report import RENDERERS` on this module's import path, and
        # `report` imports `resolution`, which imports `settings`, which imports `ruamel.yaml` — so
        # a missing distribution would raise `ImportError` before the check that exists to name it.
        # That is the one property this whole package is arranged around. A test asserts these two
        # names equal `tuple(RENDERERS)`, which is the tie that a duplicated constant needs.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    status.add_argument(
        "--settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="the project settings file to read, instead of the one the project root implies",
    )
    skills = subcommands.add_parser(
        "skills",
        help="manage the Claude skills this package ships",
        description="Manage the Claude skills this package ships.",
    )
    skills_actions = skills.add_subparsers(dest="skills_command", required=True)
    skills_actions.add_parser(
        "install",
        help="copy the skills into ~/.claude/skills, replacing older copies",
        description="Copy every shipped skill into ~/.claude/skills, and stop.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, dispatch, and return the process status.

    Returns an integer for every path this function decides, and the interpreter turns it into
    the exit status because ``[project.scripts]`` points here.

    One honest limit, because an earlier version of this docstring overstated it: ``SystemExit`` is
    raised from inside argparse for ``--help``, for an unrecognised argument, and now for a bare
    ``periplus`` — the last through the ``parser.error`` call below, which is argparse's own way of
    reporting a usage error. The design accepts that for usage errors. So the guarantee is that
    nothing *here* exits the process for a result it computed, not that no call under it can — an
    embedder calling ``main(["--help"])`` or ``main([])`` gets ``SystemExit``, and a test asserting
    on those paths must expect it.
    """
    # Before `parse_args`, and not merely before the branches below it. argparse writes `--help`
    # to stdout from inside `parse_args` and exits there, so a pin placed after it leaves that one
    # path writing through whatever the console handed over — measured: `main(["--help"])` left
    # `sys.stdout.encoding` at `ascii` and emitted CRLF terminators, while `main(["--version"])`
    # left it `utf-8`. This is the first statement in the function for that reason.
    _pin_the_output_stream()

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        # Through the package's own accessor rather than a second importlib.metadata call.
        # Two code paths reading one number is how they drift, and the accessor exists for this.
        # Answered before the dependency check, so `--version` works on a broken install — which
        # is what a person runs first when they are trying to find out what they have.
        print(periplus.__version__)
        return ExitCode.OK

    # Startup step 1, still. A bare `periplus` is a usage error and is decided here, above the
    # dependency check, so it exits 2 on a broken install as well as on a working one. The two
    # paths cannot reach each other: the parse decides the bare case and the check decides the
    # broken-install case.
    if args.command is None:
        parser.error("a subcommand is required")

    # Startup step 2. Every absent distribution is named, not just the first, because a person who
    # installs one and re-runs to be told about the second has been made to do the tool's work.
    #
    # To stderr, and stdout stays empty. The design's rule is that the report is the data and goes
    # to stdout in whichever format, *including the problems it found*, and that stderr carries
    # only what is not part of the report. This message is not part of the report, because on this
    # path there is no report: step 2 runs before step 3 calls `resolve()`, nothing is constructed
    # and nothing is rendered. It is a startup diagnostic about an install, not a finding about a
    # codebase.
    #
    # The rule's own purpose settles it the same way. It exists so that "a consumer parsing
    # --format json reads one stream and gets one document whether the run succeeded or failed".
    # A bare text line on stdout would hand that consumer a malformed document — strictly worse
    # than an empty stdout and a status of 9.
    dependencies = check_runtime_dependencies()
    missing = [status.distribution for status in dependencies if not status.present]
    if missing:
        for distribution in missing:
            print(
                f"{parser.prog}: required distribution is not installed: {distribution}",
                file=sys.stderr,
            )
        return ExitCode.MISSING_DEPENDENCY

    if args.command == "skills":
        from periplus.skills_install import SkillsUnwritable, install_skills

        try:
            installed = install_skills(home=Path.home())
        except SkillsUnwritable as error:
            print(f"{parser.prog}: {error}", file=sys.stderr)
            return error.problem().code
        for folder in installed:
            print(folder)
        return ExitCode.OK

    # This lazy import is load-bearing, not tidiness. `init.py` imports `_escape`
    # from `periplus.report`, which pulls `resolution`, `settings` and `packs` behind it, so
    # `import periplus.init` reaches both runtime distributions. At module level that would put
    # `ruamel.yaml` and `platformdirs` on this file's import path and the run would die of an
    # `ImportError` before the check above ever executed — the exact failure "a missing dependency
    # fails at startup, named" exists to stop. Measured, not reasoned: with a module-level import
    # reaching a runtime distribution planted here,
    # `test_a_missing_dependency_ends_the_run_at_exit_9_naming_every_one` fails on its
    # `ImportError` assertion.
    #
    # `periplus init` therefore exits 9 on an install missing either distribution: one startup order
    # for the whole tool rather than a branch deciding which subcommand is exempt, and `--version`
    # above remains the question answered before any check.
    if args.command == "init":
        from periplus.detect import detect
        from periplus.init import initialise_project, render_text

        # Detection runs here rather than inside `initialise_project`, so that the command that
        # creates a directory is not also the command that reads every pack manifest on the search
        # path. `detect` never raises and reports nothing: a repository it recognises nothing in is
        # the ordinary case, and `periplus status` is what reports on the search path.
        here = Path.cwd()
        detected = detect(here, os.environ, dependencies)
        # Named apart from the resolution report below. One `report` for both is a type error
        # under strict, and it would read as one thing being two.
        # The detections, not their pins. `initialise_project` derives what to write from what was
        # found, so the pins in the file and the evidence in the report cannot disagree.
        created = initialise_project(here, detected=detected)
        sys.stdout.write(render_text(created))
        return created.exit_code

    # Imported here for the same reason `init` is, and dispatched here rather than below because
    # `spec` is not a resolution report and shares no rendering with one. Whether this run touches
    # the filesystem outside the package at all is `spec()`'s decision and not a branch in this
    # file: with no pack named there is nothing to look up, and the module states that as a
    # property with a test behind it.
    if args.command == "spec":
        from periplus.spec import RENDERERS as SPEC_RENDERERS
        from periplus.spec import SUMMARY_RENDERERS as SPEC_SUMMARY_RENDERERS
        from periplus.spec import spec

        contract = spec(
            start=Path.cwd(),
            env=os.environ,
            dependencies=dependencies,
            requested=args.pack,
        )
        # `--summary` picks the table and `--format` picks the entry in it, so the flag is one
        # lookup here rather than an argument threaded through two renderers. Whole documents stay
        # the default: the consumer is a model, and making it run the command twice to reach the
        # schemas it came for costs more than the bytes it saves.
        renderers = SPEC_SUMMARY_RENDERERS if args.summary else SPEC_RENDERERS
        sys.stdout.write(renderers[args.format](contract))
        return contract.exit_code

    # Imported here for the same reason `init` and `spec` are, and more sharply: `periplus.validate`
    # imports `jsonschema` at its module level. That is the third runtime distribution, it arrived
    # after this file's arrangement was settled, and a module-level import of this module here would
    # break the startup property for it exactly as one reaching `ruamel.yaml` broke it for the
    # first two. A test imports `periplus.cli` in a child and asserts that neither
    # `periplus.validate` nor `jsonschema` is in `sys.modules` afterwards.
    if args.command == "validate":
        from periplus.validate import RENDERERS as VALIDATE_RENDERERS
        from periplus.validate import validate

        findings = validate(
            start=Path.cwd(),
            env=os.environ,
            dependencies=dependencies,
            requested=args.pack,
        )
        sys.stdout.write(VALIDATE_RENDERERS[args.format](findings))
        return findings.exit_code

    # Imported here because `periplus.update` imports `ruamel.yaml`.
    if args.command == "update":
        from periplus.update import RENDERERS as UPDATE_RENDERERS
        from periplus.update import update_pins

        updated = update_pins(start=Path.cwd(), env=os.environ, dependencies=dependencies)
        sys.stdout.write(UPDATE_RENDERERS[args.format](updated))
        return updated.exit_code

    # Imported here for the reason `validate` is: `periplus.map` imports `jsonschema`.
    if args.command == "map":
        from periplus.map import RENDERERS as MAP_RENDERERS
        from periplus.map import run

        written = run(
            start=Path.cwd(),
            env=os.environ,
            dependencies=dependencies,
            settings_path=args.settings,
            output=args.output,
        )
        sys.stdout.write(MAP_RENDERERS[args.format](written))
        return written.exit_code

    if getattr(args, "limit", 0) < 0:
        parser.error("--limit must be 0 or more")

    # Imported here for the reason `map` is: `periplus.navigate` imports `jsonschema`.
    if args.command == "types":
        from periplus.navigate.types import RENDERERS as TYPES_RENDERERS
        from periplus.navigate.types import run as run_types

        listed = run_types(start=Path.cwd(), env=os.environ, map_path=args.map)
        sys.stdout.write(TYPES_RENDERERS[args.format](listed))
        return listed.exit_code

    if args.command == "check-map":
        from periplus.checkmap import RENDERERS as CHECK_RENDERERS
        from periplus.checkmap import run as run_check

        checked = run_check(start=Path.cwd(), env=os.environ, map_path=args.map)
        sys.stdout.write(CHECK_RENDERERS[args.format](checked))
        return checked.exit_code

    if args.command == "find":
        from periplus.navigate.find import RENDERERS as FIND_RENDERERS
        from periplus.navigate.find import run as run_find

        found = run_find(
            start=Path.cwd(),
            env=os.environ,
            text=args.text,
            type_name=args.type,
            limit=args.limit,
            map_path=args.map,
        )
        sys.stdout.write(FIND_RENDERERS[args.format](found))
        return found.exit_code

    if args.command == "show":
        from periplus.navigate.show import RENDERERS as SHOW_RENDERERS
        from periplus.navigate.show import run as run_show

        shown = run_show(
            start=Path.cwd(),
            env=os.environ,
            node_id=args.id,
            limit=args.limit,
            map_path=args.map,
        )
        sys.stdout.write(SHOW_RENDERERS[args.format](shown))
        return shown.exit_code

    if args.command in ("neighbors", "affected"):
        from periplus.navigate.walk import RENDERERS as WALK_RENDERERS
        from periplus.navigate.walk import run as run_walk

        if args.depth < 1:
            parser.error("--depth must be 1 or more")
        walked = run_walk(
            start=Path.cwd(),
            env=os.environ,
            node_id=args.id,
            direction="out" if args.command == "neighbors" else "in",
            depth=args.depth,
            kinds=args.kind,
            limit=args.limit,
            map_path=args.map,
        )
        sys.stdout.write(WALK_RENDERERS[args.format](walked))
        return walked.exit_code

    if args.command == "path":
        from periplus.navigate.path import RENDERERS as PATH_RENDERERS
        from periplus.navigate.path import run as run_path

        chained = run_path(
            start=Path.cwd(),
            env=os.environ,
            from_id=args.source,
            to_id=args.target,
            kinds=args.kind,
            limit=args.limit,
            map_path=args.map,
        )
        sys.stdout.write(PATH_RENDERERS[args.format](chained))
        return chained.exit_code

    # Startup step 3. Imported here and never at module level: everything below this line reaches
    # `ruamel.yaml` and `platformdirs`, and the check above is what makes reaching them safe.
    from periplus.report import RENDERERS
    from periplus.resolution import resolve

    # Step 2's tuple is passed forward rather than recomputed. It is the only call site, and a
    # second call from inside `resolve` would run the check after the failure it exists to prevent.
    report = resolve(
        start=Path.cwd(),
        env=os.environ,
        dependencies=dependencies,
        settings_path=args.settings,
        pack_checks=True,
    )

    # Startup step 4. The report is the data, so it goes to stdout in whichever format, including
    # the problems it found, and the status carries the verdict.
    sys.stdout.write(RENDERERS[args.format](report))
    return report.exit_code


def _pin_the_output_stream() -> None:
    """Write UTF-8 with LF line endings, whatever the console would otherwise have done.

    Two different failures, one call. A non-UTF-8 default console encoding mangles or refuses a
    directory name; Windows text mode translates every LF into CRLF, which breaks the report's "LF
    line endings" rule outright and would make two runs on two platforms differ in bytes.

    **Neither half is reproducible on this machine.** This is Linux, where the default is already
    UTF-8 with LF, so this is reasoned from documented CPython behaviour rather than observed. It
    is also belt and braces for the encoding half: ``render_text`` emits ASCII only, and
    ``render_json`` is called with ``ensure_ascii=True``, so there is nothing in either document
    that a console encoding could refuse.

    Guarded by the type rather than by ``hasattr``, because the guard is a real case and not a
    workaround. The case is **not** pytest's capture, as instrumenting it
    shows: ``EncodedFile`` and ``CaptureIO`` both subclass ``io.TextIOWrapper``, and
    across the whole suite the guard excluded capture zero times. What it does exclude is a plain
    ``io.StringIO`` — the shape a caller gets from ``contextlib.redirect_stdout``, which one test
    here uses — and that has no stream to reconfigure.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
