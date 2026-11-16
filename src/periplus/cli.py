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
from collections.abc import Callable, Sequence
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


def add_map(parser: argparse.ArgumentParser, help_text: str) -> None:
    """Add ``--map`` to a subcommand; ``help_text`` says what the command does with the file."""
    parser.add_argument(
        "--map",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"{help_text} (default: .periplus/map.json under the project root)",
    )


def add_limit(parser: argparse.ArgumentParser, default: int, noun: str) -> None:
    """Add ``--limit`` to a subcommand: how many ``noun`` to show, 0 for all."""
    parser.add_argument(
        "--limit",
        type=int,
        default=default,
        metavar="N",
        help=f"{noun} to show; 0 shows all (default: {default})",
    )


def add_walk(parser: argparse.ArgumentParser, default: int | None = 1, said: str = "1") -> None:
    """Add ``--depth`` and ``--kind``, the options of a command that follows edges.

    ``said`` is the default as the help text states it.
    """
    parser.add_argument(
        "--depth",
        type=int,
        default=default,
        metavar="N",
        help=f"edges to follow, 1 or more (default: {said})",
    )
    parser.add_argument(
        "--kind",
        action="append",
        default=[],
        metavar="K",
        help="keep only edges of kind K; repeat for several",
    )


#: The text budget of a walk by cause; ``navigate.walk.BUDGET``, which a test holds equal.
BUDGET = 20_000
#: The hub limit of a walk by cause; ``navigate.walk.HUB``, which a test holds equal.
HUB = 40


def _depth(text: str) -> int | None:
    """A ``--depth`` of a walk: a number, or ``all`` for ``None``."""
    return None if text == "all" else int(text)


def _place(text: str) -> tuple[str, int]:
    """A ``FILE:LINE`` argument as (file, line); a line that is not a whole number above 0 is a
    usage error."""
    file, _, line = text.rpartition(":")
    if not file or not line.isdecimal() or int(line) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not FILE:LINE with a line of 1 or more")
    return file, int(line)


def add_hub(parser: argparse.ArgumentParser) -> None:
    """Add ``--hub`` and ``--through``, the hub options of a walk by cause."""
    parser.add_argument(
        "--hub",
        type=int,
        default=None,
        metavar="N",
        help=f"list but do not walk from a thing with more than N edges to follow; 0 for no "
        f"limit (default: {HUB})",
    )
    parser.add_argument(
        "--through",
        action="append",
        default=[],
        metavar="ID",
        help="walk from this hub all the same; repeat for several",
    )


def add_ids(parser: argparse.ArgumentParser) -> None:
    """Add ``--ids``, which prints one full id a line instead of the report."""
    parser.add_argument(
        "--ids",
        action="store_true",
        help="print only the full ids, one a line, for another periplus command to read with -; "
        "the count and any warning go to standard error",
    )


#: The help of an ID argument that may be ``-``.
IDS_HELP = "a node id or short name; - reads ids from standard input, one a line"


def add_format(parser: argparse.ArgumentParser) -> None:
    """Add ``--format text|json``; a test asserts the choices equal the command's RENDERERS."""
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )


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
        help="check one pack against the shipped schemas, then report what map refuses it for",
        description=(
            "Check a pack against the schemas it is written against, report what periplus map "
            "refuses it for before reading a file, and stop."
        ),
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
    add_map(types, "the map file to read")
    legend = subcommands.add_parser(
        "legend",
        help="say what each edge kind and node type in the written map means",
        description="List the edge kinds and node types the map holds, most frequent first, "
        "each with its count, the types it joins and its pack's description, and stop.",
    )
    legend.add_argument(
        "--kind",
        action="append",
        default=[],
        metavar="K",
        help="print edge kind K in full; repeat for several",
    )
    legend.add_argument(
        "--type",
        action="append",
        default=[],
        metavar="T",
        help="print node type T in full, with the kinds of its edges; repeat for several",
    )
    legend.add_argument(
        "--all",
        action="store_true",
        help="print every kind and type, past the default of about 3 KB",
    )
    legend.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(legend.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    add_map(legend, "the map file to read")
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
    add_map(check, "the map file to check")
    find = subcommands.add_parser(
        "find",
        help="find the nodes whose id, attributes or description hold a text",
        description="List the nodes whose id, string attributes or description hold TEXT, "
        "closest match first, and stop.",
    )
    find.add_argument(
        "text",
        metavar="TEXT",
        nargs="?",
        default="",
        help="the text to look for in node ids, attributes and descriptions; left out, every "
        "node matches, as with --mark alone",
    )
    find.add_argument(
        "--type",
        action="append",
        default=[],
        metavar="T",
        help="keep type T and its subtypes; give it again to keep several types",
    )
    find.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="P",
        help="keep nodes with a file starting with P; give it again to keep several",
    )
    find.add_argument(
        "--mark",
        action="append",
        default=[],
        metavar="TEXT",
        help="keep nodes that carry the mark TEXT, as rows print it in brackets; give it again "
        "to keep several",
    )
    add_limit(find, 50, "rows")
    add_ids(find)
    add_map(find, "the map file to read")
    find.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(find.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    show = subcommands.add_parser(
        "show",
        help="show nodes and the edges at each",
        description="Show each node ID and every edge leaving or arriving at it, and stop.",
    )
    show.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_limit(show, 50, "rows")
    add_ids(show)
    add_map(show, "the map file to read")
    show.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(show.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    depth = subcommands.add_parser(
        "depth",
        help="say how far what an item sets off, and what sets it off, reach",
        description="Walk by cause from ID both ways to the end and print, per direction, the "
        "hops, the things reached, the share within 2, 3 and 5 hops and the hubs stopped at, and "
        "stop.",
    )
    depth.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_hub(depth)
    add_map(depth, "the map file to read")
    depth.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(depth.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    reach = subcommands.add_parser(
        "reach",
        help="print depth, then what an item sets off and what sets it off, in one reply",
        description="Print the depth report of the IDs, then neighbors and affected to the "
        "farthest hops that fit the budget, with the things only returns tagged [only] and the "
        "hubs each walk stopped at as hubs prints them; a part cut short names the command that "
        "prints it in full, and stop.",
    )
    reach.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    reach.add_argument(
        "--direction",
        choices=("off", "by", "both"),
        default="both",
        help="off prints what the ids set off, by what sets them off (default: both)",
    )
    reach.add_argument(
        "--depth",
        type=_depth,
        default=None,
        metavar="N",
        help="the most hops to show, 1 or more, or all (default: all that fit)",
    )
    add_hub(reach)
    reach.add_argument(
        "--touch",
        action="store_true",
        help="add what each thing shown only points at, one hop out, marked [touch]",
    )
    reach.add_argument(
        "--full",
        action="store_true",
        help="print full ids and full paths on every row, not short names",
    )
    add_ids(reach)
    reach.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=f"characters the text may hold before the farthest hops become counts (default: "
        f"{BUDGET}); 0 for no limit",
    )
    add_map(reach, "the map file to read")
    add_format(reach)
    for name, helptext in (
        ("neighbors", "list what an item sets off, hop by hop"),
        ("affected", "list what sets an item off, hop by hop"),
    ):
        walking = subcommands.add_parser(name, help=helptext, description=f"{helptext}, and stop.")
        walking.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
        walking.add_argument(
            "--depth",
            type=_depth,
            default=1,
            metavar="N",
            help="hops to show, 1 or more, or all (default: 1)",
        )
        walking.add_argument(
            "--kind",
            action="append",
            default=[],
            metavar="K",
            help="keep only edges of kind K; repeat for several",
        )
        add_hub(walking)
        walking.add_argument(
            "--touch",
            action="store_true",
            help="add what each thing shown only points at, one hop out, marked [touch]",
        )
        walking.add_argument(
            "--full",
            action="store_true",
            help="print full ids and full paths on every row, not short names",
        )
        add_ids(walking)
        walking.add_argument(
            "--raw",
            action="store_true",
            help="follow every edge by its own direction, from one ID, as before 0.9",
        )
        walking.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            help="characters the text may hold before the farthest hops become counts "
            f"(default: {BUDGET}), or with --raw the rows to show (default: 50); 0 for no limit",
        )
        add_map(walking, "the map file to read")
        walking.add_argument(
            "--format",
            # A literal for the reason `types`' is; a test asserts it equals the RENDERERS.
            choices=("text", "json"),
            default="text",
            help="how to print the report (default: text)",
        )
    only = subcommands.add_parser(
        "only",
        help="list what the ids set off that nothing else sets off",
        description="Walk by cause from the IDs toward what they set off, and list the things "
        "every one of whose setting-off chains passes through an ID, and stop.",
    )
    only.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_hub(only)
    add_ids(only)
    add_map(only, "the map file to read")
    add_format(only)
    hubs = subcommands.add_parser(
        "hubs",
        help="list the hubs the walk by cause from the ids stops at",
        description="Walk by cause from the IDs and list each hub it stops at: name, type, hop "
        "and fan, and stop.",
    )
    hubs.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    hubs.add_argument(
        "--direction",
        choices=("off", "by"),
        default="off",
        help="off walks what the ids set off, as neighbors; by what sets them off, as affected "
        "(default: off)",
    )
    hubs.add_argument(
        "--depth",
        type=_depth,
        default=None,
        metavar="N",
        help="hops to look within, 1 or more, or all (default: all)",
    )
    hubs.add_argument(
        "--hub",
        type=int,
        default=None,
        metavar="N",
        help=f"a hub has more than N edges to follow (default: {HUB})",
    )
    hubs.add_argument(
        "--through",
        action="append",
        default=[],
        metavar="ID",
        help="walk from this hub all the same; repeat for several",
    )
    add_ids(hubs)
    add_map(hubs, "the map file to read")
    add_format(hubs)
    held = subcommands.add_parser(
        "members",
        help="list what a container holds, by the map's grouping kinds",
        description="Count each container ID's members by type and list them, and stop.",
    )
    held.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    held.add_argument(
        "--type",
        action="append",
        default=[],
        metavar="T",
        help="keep members of type T and its subtypes; repeat for several",
    )
    add_ids(held)
    add_map(held, "the map file to read")
    add_format(held)
    pieces = subcommands.add_parser(
        "pieces",
        help="split ids into the groups that edges among them join",
        description="Split the things the IDs name into pieces, two in one piece when an edge "
        "of any kind joins them directly or through others of the IDs, and stop.",
    )
    pieces.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_ids(pieces)
    add_map(pieces, "the map file to read")
    add_format(pieces)
    count = subcommands.add_parser(
        "count",
        help="count the things ids name, by type and state, and the edges among them",
        description="Count the things the IDs name by type and by state, the edges among them by "
        "kind, and list the IDs that name no node, and stop.",
    )
    count.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_map(count, "the map file to read")
    add_format(count)
    held_in = subcommands.add_parser(
        "in",
        help="list the things the map holds in each file, in line order",
        description="List the things the map locates in each FILE, by line, and stop.",
    )
    held_in.add_argument("file", metavar="FILE", nargs="+", help="a file as the map names it")
    held_in.add_argument(
        "--type",
        action="append",
        default=[],
        metavar="T",
        help="keep things of type T and its subtypes; repeat for several",
    )
    add_ids(held_in)
    add_map(held_in, "the map file to read")
    add_format(held_in)
    placed = subcommands.add_parser(
        "at",
        help="name the mapped thing at a file and line, and what holds it",
        description="Name the mapped things on the line of FILE:LINE, or on the nearest line "
        "above it that holds one, then what holds them, and stop.",
    )
    placed.add_argument(
        "place", metavar="FILE:LINE", nargs="+", type=_place, help="a file and a line number"
    )
    add_ids(placed)
    add_map(placed, "the map file to read")
    add_format(placed)
    holding = subcommands.add_parser(
        "files",
        help="list the files that hold a set of things, most first",
        description="Count the things the IDs name by file, most first, and stop.",
    )
    holding.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_map(holding, "the map file to read")
    add_format(holding)
    bare = subcommands.add_parser(
        "undescribed",
        help="count the main things with no description, by file, type or container",
        description="Count the main things of the map, or of the IDs, that the descriptions "
        "file does not describe, and stop.",
    )
    bare.add_argument("id", metavar="ID", nargs="*", help=IDS_HELP + "; none counts the whole map")
    bare.add_argument(
        "--by",
        choices=("file", "type", "container"),
        default="file",
        help="what to count the undescribed things by (default: file)",
    )
    add_ids(bare)
    add_map(bare, "the map file to read")
    add_format(bare)
    stamp = subcommands.add_parser(
        "stamp",
        help="write a fingerprint of its code into each node entry of the descriptions file",
        description="Write the fingerprint of the code each node entry describes into the entries "
        "that have none, and stop. Nothing else in the file changes.",
    )
    stamp.add_argument(
        "--all", action="store_true", help="write a fresh fingerprint into every node entry"
    )
    add_map(stamp, "the map file to read")
    add_format(stamp)
    stale = subcommands.add_parser(
        "stale",
        help="list the node entries whose code changed or whose node is gone",
        description="Compare each stamped node entry's fingerprint with its code now, list the "
        "entries that differ and those whose node the map no longer holds, and stop.",
    )
    add_ids(stale)
    add_map(stale, "the map file to read")
    add_format(stale)
    order = subcommands.add_parser(
        "order",
        help="list a set so that each thing comes after what it calls or uses",
        description="Print the things the IDs name so that each comes after the things of the set "
        "it sets off or uses, loops together and marked, and stop.",
    )
    order.add_argument("id", metavar="ID", nargs="+", help=IDS_HELP)
    add_ids(order)
    add_map(order, "the map file to read")
    add_format(order)
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
    add_limit(path, 10, "chains")
    add_map(path, "the map file to read")
    path.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(path.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    cut = subcommands.add_parser(
        "slice",
        help="print the piece of the map around some words, ids or a path, or write it to a file",
        description="Start from the nodes that IDs name or that WORDS find, as find finds them, "
        "and print the items reached from them along edges, hop by hop, each under the node it "
        "was reached from, in pieces: the items edges join. With --out, write the piece to a map "
        "file instead. Then stop.",
    )
    cut.add_argument(
        "id",
        metavar="WORDS",
        nargs="*",
        help="a node id or short name to start from; any other text is searched as find does",
    )
    cut.add_argument(
        "--from",
        dest="start",
        nargs="+",
        default=None,
        metavar="ID",
        help="start from these ids alone and search no words; - reads ids from standard input, "
        "one a line",
    )
    cut.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="PREFIX",
        help="with words, keep starts with a file starting with PREFIX; without, also start "
        "from nodes whose first file starts with PREFIX; repeat for several",
    )
    cut.add_argument(
        "--type",
        action="append",
        default=[],
        metavar="T",
        help="keep starts the words find of type T and its subtypes; repeat for several",
    )
    cut.add_argument(
        "--starts",
        type=int,
        default=None,
        metavar="N",
        help="most start nodes the words pick, at most two of one type (default: 12)",
    )
    cut.add_argument(
        "--support",
        action="store_true",
        help="print nodes in supporting code, as tests, and let a start come from it; by default "
        "each piece counts them in one line",
    )
    cut.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="FILE",
        help="write the piece to FILE as a map instead of printing it",
    )
    cut.add_argument(
        "--direction",
        choices=("out", "in", "both"),
        default="both",
        help=(
            "out or in follows one direction; both follows an edge either way at every hop "
            "(default: both)"
        ),
    )
    add_walk(cut, None, "2 from the first 8 starts and 1 from the rest, or 1 with --out")
    cut.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="most rows to print (default: 50), or with --out the most items the slice may "
        "hold (default: 500); 0 for no limit",
    )
    add_map(cut, "the map file to read")
    cut.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(slice.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the report (default: text)",
    )
    export = subcommands.add_parser(
        "export",
        help="print the map as GraphML, DOT or Mermaid",
        description="Print the map in another format, and stop.",
    )
    export.add_argument(
        "--format",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(export.WRITERS)`.
        choices=("graphml", "dot", "mermaid"),
        required=True,
        help="the format to print",
    )
    add_map(export, "the map file to read")
    export.add_argument(
        "--report",
        # A literal for the reason `types`' is; a test asserts it equals `tuple(export.RENDERERS)`.
        choices=("text", "json"),
        default="text",
        help="how to print the warnings and problems to standard error (default: text)",
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
    """Run ``_dispatch`` and flush standard output, and return the process status.

    When the reader of standard output has closed it, as ``| head`` does, the write or the flush
    raises ``BrokenPipeError``. Standard output then points at the null device, so the flush at
    the interpreter's exit raises nothing, and the status is ``OUTPUT_CLOSED``.
    """
    try:
        code = _dispatch(argv)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return ExitCode.OUTPUT_CLOSED
    return code


def _dispatch(argv: Sequence[str] | None = None) -> int:
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
        from periplus.detect import detect, place
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
        created = initialise_project(
            here, detected=detected, placed=place(here, os.environ, dependencies, detected)
        )
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
    # first two. No test guards this now: after `import periplus.cli`, neither
    # `periplus.validate` nor `jsonschema` may be in `sys.modules`.
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

    if getattr(args, "ids", False) and getattr(args, "format", "text") != "text":
        parser.error("--ids prints ids; it takes no --format")
    # slice searches its arguments as words, so a - there is a word; its --from takes ids.
    field = "start" if args.command == "slice" else "id"
    given = getattr(args, field, None)
    args.piped = isinstance(given, list) and "-" in given
    given = given or []
    if args.piped:
        from periplus.navigate.ids import read_ids

        setattr(args, field, read_ids(given, sys.stdin))
        if not getattr(args, field):
            parser.error("- read no ids from standard input")
    if (getattr(args, "limit", 0) or 0) < 0:
        parser.error("--limit must be 0 or more")
    # None is slice's own default, which depends on --out.
    if (depth := getattr(args, "depth", 1)) is not None and depth < 1:
        parser.error("--depth must be 1 or more")
    if (starts := getattr(args, "starts", 1)) is not None and starts < 1:
        parser.error("--starts must be 1 or more")

    # Imported here for the reason `map` is: `periplus.navigate` imports `jsonschema`.
    if args.command == "types":
        from periplus.navigate.types import RENDERERS as TYPES_RENDERERS
        from periplus.navigate.types import run as run_types

        listed = run_types(start=Path.cwd(), env=os.environ, map_path=args.map)
        sys.stdout.write(TYPES_RENDERERS[args.format](listed))
        return listed.exit_code

    if args.command == "legend":
        from periplus.navigate.legend import RENDERERS as LEGEND_RENDERERS
        from periplus.navigate.legend import run as run_legend

        told = run_legend(
            start=Path.cwd(),
            env=os.environ,
            map_path=args.map,
            kinds=args.kind,
            types=args.type,
            everything=args.all,
        )
        sys.stdout.write(LEGEND_RENDERERS[args.format](told))
        return told.exit_code

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
            types=args.type,
            limit=0 if args.ids else args.limit,
            map_path=args.map,
            paths=args.path,
            marks=args.mark,
        )
        return _emit(args, FIND_RENDERERS, found, lambda r: [row.id for row in r.matches.items])

    if args.command == "show":
        from periplus.navigate.show import MANY_RENDERERS as SHOW_RENDERERS
        from periplus.navigate.show import listed as show_listed
        from periplus.navigate.show import run_many as run_show

        shown = run_show(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            limit=0 if args.ids else args.limit,
            map_path=args.map,
        )
        return _emit(args, SHOW_RENDERERS, shown, show_listed)

    if (getattr(args, "hub", None) or 0) < 0:
        parser.error("--hub must be 0 or more")

    if args.command == "depth":
        from periplus.navigate.depth import RENDERERS as DEPTH_RENDERERS
        from periplus.navigate.depth import run as run_depth

        measured = run_depth(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            map_path=args.map,
            hub=HUB if args.hub is None else args.hub,
            through=args.through,
            piped=args.piped,
        )
        sys.stdout.write(DEPTH_RENDERERS[args.format](measured))
        return measured.exit_code

    if args.command == "reach":
        from periplus.navigate.reach import RENDERERS as REACH_RENDERERS
        from periplus.navigate.reach import listed as reach_listed
        from periplus.navigate.reach import run as run_reach

        reached = run_reach(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            map_path=args.map,
            direction=args.direction,
            depth=args.depth,
            hub=HUB if args.hub is None else args.hub,
            through=args.through,
            touch=args.touch,
            full=args.full,
            limit=0 if args.ids else args.limit,
            piped=args.piped,
        )
        return _emit(args, REACH_RENDERERS, reached, reach_listed)

    if args.command in ("neighbors", "affected"):
        from periplus.navigate.walk import RENDERERS as WALK_RENDERERS
        from periplus.navigate.walk import CauseReport, WalkReport, run_cause
        from periplus.navigate.walk import listed as walk_listed
        from periplus.navigate.walk import run as run_walk

        walked: WalkReport | CauseReport
        if args.raw:
            if args.hub is not None or args.through or args.touch or args.full:
                parser.error("--hub, --through, --touch and --full walk by cause; --raw takes none")
            if len(args.id) != 1:
                parser.error("--raw walks from one ID")
            walked = run_walk(
                start=Path.cwd(),
                env=os.environ,
                node_id=args.id[0],
                direction="out" if args.command == "neighbors" else "in",
                depth=args.depth,
                kinds=args.kind,
                limit=0 if args.ids else 50 if args.limit is None else args.limit,
                map_path=args.map,
            )
        else:
            walked = run_cause(
                start=Path.cwd(),
                env=os.environ,
                ids=args.id,
                toward="off" if args.command == "neighbors" else "by",
                depth=args.depth,
                kinds=args.kind,
                limit=0 if args.ids else args.limit,
                map_path=args.map,
                hub=HUB if args.hub is None else args.hub,
                through=args.through,
                touch=args.touch,
                full=args.full,
                piped=args.piped,
            )
        return _emit(args, WALK_RENDERERS, walked, walk_listed)

    if args.command == "only":
        from periplus.navigate.only import RENDERERS as ONLY_RENDERERS
        from periplus.navigate.only import listed as only_listed
        from periplus.navigate.only import run as run_only

        kept = run_only(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            map_path=args.map,
            hub=HUB if args.hub is None else args.hub,
            through=args.through,
        )
        return _emit(args, ONLY_RENDERERS, kept, only_listed)

    if args.command == "hubs":
        from periplus.navigate.hubs import RENDERERS as HUBS_RENDERERS
        from periplus.navigate.hubs import listed as hubs_listed
        from periplus.navigate.hubs import run as run_hubs

        stopped = run_hubs(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            toward=args.direction,
            depth=args.depth,
            hub=HUB if args.hub is None else args.hub,
            map_path=args.map,
            through=args.through,
        )
        return _emit(args, HUBS_RENDERERS, stopped, hubs_listed)

    if args.command == "members":
        from periplus.navigate.members import RENDERERS as MEMBERS_RENDERERS
        from periplus.navigate.members import listed as members_listed
        from periplus.navigate.members import run as run_members

        held = run_members(
            start=Path.cwd(), env=os.environ, ids=args.id, types=args.type, map_path=args.map
        )
        return _emit(args, MEMBERS_RENDERERS, held, members_listed)

    if args.command == "pieces":
        from periplus.navigate.pieces import RENDERERS as PIECES_RENDERERS
        from periplus.navigate.pieces import listed as pieces_listed
        from periplus.navigate.pieces import run as run_pieces

        split = run_pieces(start=Path.cwd(), env=os.environ, ids=args.id, map_path=args.map)
        return _emit(args, PIECES_RENDERERS, split, pieces_listed, grouped=True)

    if args.command == "count":
        from periplus.navigate.count import RENDERERS as COUNT_RENDERERS
        from periplus.navigate.count import run as run_count

        counted = run_count(start=Path.cwd(), env=os.environ, ids=args.id, map_path=args.map)
        sys.stdout.write(COUNT_RENDERERS[args.format](counted))
        return counted.exit_code

    if args.command == "in":
        from periplus.navigate.inside import RENDERERS as IN_RENDERERS
        from periplus.navigate.inside import listed as in_listed
        from periplus.navigate.inside import run as run_in

        found_in = run_in(
            start=Path.cwd(), env=os.environ, paths=args.file, types=args.type, map_path=args.map
        )
        return _emit(args, IN_RENDERERS, found_in, in_listed)

    if args.command == "at":
        from periplus.navigate.at import RENDERERS as AT_RENDERERS
        from periplus.navigate.at import listed as at_listed
        from periplus.navigate.at import run as run_at

        found_at = run_at(start=Path.cwd(), env=os.environ, places=args.place, map_path=args.map)
        return _emit(args, AT_RENDERERS, found_at, at_listed)

    if args.command == "files":
        from periplus.navigate.files import RENDERERS as FILES_RENDERERS
        from periplus.navigate.files import run as run_files

        holding = run_files(start=Path.cwd(), env=os.environ, ids=args.id, map_path=args.map)
        sys.stdout.write(FILES_RENDERERS[args.format](holding))
        return holding.exit_code

    if args.command == "undescribed":
        from periplus.navigate.undescribed import RENDERERS as BARE_RENDERERS
        from periplus.navigate.undescribed import listed as bare_listed
        from periplus.navigate.undescribed import run as run_bare

        bare = run_bare(
            start=Path.cwd(), env=os.environ, ids=args.id, by=args.by, map_path=args.map
        )
        return _emit(args, BARE_RENDERERS, bare, bare_listed)

    if args.command == "stamp":
        from periplus.navigate.fingerprint import STAMP_RENDERERS
        from periplus.navigate.fingerprint import stamp as run_stamp

        stamped = run_stamp(start=Path.cwd(), env=os.environ, every=args.all, map_path=args.map)
        sys.stdout.write(STAMP_RENDERERS[args.format](stamped))
        return stamped.exit_code

    if args.command == "stale":
        from periplus.navigate.fingerprint import STALE_RENDERERS
        from periplus.navigate.fingerprint import listed as stale_listed
        from periplus.navigate.fingerprint import stale as run_stale

        aged = run_stale(start=Path.cwd(), env=os.environ, map_path=args.map)
        return _emit(args, STALE_RENDERERS, aged, stale_listed)

    if args.command == "order":
        from periplus.navigate.order import RENDERERS as ORDER_RENDERERS
        from periplus.navigate.order import listed as order_listed
        from periplus.navigate.order import run as run_order

        ordered = run_order(start=Path.cwd(), env=os.environ, ids=args.id, map_path=args.map)
        return _emit(args, ORDER_RENDERERS, ordered, order_listed)

    if args.command == "slice":
        from periplus.navigate.slice import RENDERERS as SLICE_RENDERERS
        from periplus.navigate.slice import run as run_slice

        if args.start and args.id:
            parser.error("--from takes the starts; give no WORDS with it")
        sliced = run_slice(
            start=Path.cwd(),
            env=os.environ,
            ids=args.id,
            prefixes=args.path,
            direction=args.direction,
            depth=args.depth,
            kinds=args.kind,
            limit=args.limit,
            out=args.out,
            map_path=args.map,
            types=args.type,
            starts=args.starts,
            support=args.support,
            from_ids=args.start or (),
            piped=args.piped,
        )
        sys.stdout.write(SLICE_RENDERERS[args.format](sliced))
        return sliced.exit_code

    if args.command == "export":
        from periplus.navigate.export import RENDERERS as EXPORT_RENDERERS
        from periplus.navigate.export import run as run_export

        exported = run_export(
            start=Path.cwd(), env=os.environ, format=args.format, map_path=args.map
        )
        sys.stdout.write(exported.text)
        sys.stderr.write(EXPORT_RENDERERS[args.report](exported))
        return exported.exit_code

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


def _emit(
    args: argparse.Namespace,
    renderers: Any,
    report: Any,
    listed: Callable[[Any], Any],
    grouped: bool = False,
) -> int:
    """Write ``report`` as ``--format`` picks, or with ``--ids`` the ids ``listed`` gives to
    standard output and the count, warnings and problems to standard error; return its code.

    ``grouped`` says ``listed`` gives groups of ids, printed with a blank line between two.
    """
    if not args.ids:
        sys.stdout.write(renderers[args.format](report))
        return int(report.exit_code)
    from periplus.navigate.ids import id_output

    found = listed(report)
    out, err = id_output(found if grouped else [found], report.warnings, report.problems)
    sys.stdout.write(out)
    sys.stdout.flush()
    sys.stderr.write(err)
    return int(report.exit_code)


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
