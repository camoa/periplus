"""``periplus spec``: publish the contract a pack is authored against, and stop.

The consumer is a model. It types one command and has to come away with everything it needs to
write a pack: the four schemas that say what a pack file may contain, the two prose documents that
say what a rule is and what the engine does with it, and an honest list of what the schema language
cannot yet express. So the whole contract is emitted, not a summary of it and not a pointer to a
path — a path is a second command a model has to guess at, and a summary is prose nobody reviewed
standing in for prose somebody did.

**Everything published here is read out of the installed package**, through
``importlib.resources``, never from a path assembled relative to this file. That is what makes the
command work from a wheel, a zip install and a source checkout alike, and it is the same route
``init`` reaches its stub through and ``packs`` reaches the bundled pack root through.

Two things this module deliberately does not do.

It does **not** read a pack's node types and edge kinds. ``periplus spec <pack>`` reports what that
pack's manifest declares and what it inherits *from*; the vocabulary itself needs a reader that
walks a pack's rule files, and that reader does not exist. Where the answer is knowable without one
it is given: a pack whose manifest declares no ``depends`` has an empty dependency closure, so the
union of what it inherits is empty by arithmetic rather than by a stub. Where it is not knowable,
``SpecReport.inherited`` is ``None`` and the renderers say the vocabulary has not been read. A
tuple of nothing and "nothing has been read" are different facts and this module refuses to print
the first when it means the second.

It does **not** validate anything. A manifest that names itself something other than its directory,
a ``depends`` that is a string rather than a list — all of that loads exactly as ``manifest.py``
loads it, which is to say permissively, and is the validator's to refuse.

One rule decides what goes through ``report._escape`` and what does not, because the two halves of
this output have different provenance:

* **Package data is emitted verbatim.** The contract documents are the artifact being published —
  escaping them would hand a reader a document that is not the document — and a gap's text is a
  slice of the same bytes. They ship inside the wheel; a person's input cannot reach them.
* **Everything else is escaped.** A pack name comes off the command line, a directory name comes
  off a filesystem where any byte but ``/`` and NUL is legal, and a problem message quotes both.
  Those are attacker-influenced text and go through ``_escape`` exactly as they do in ``report``
  and ``init``.

Determinism, which is a stated property of the project rather than a nicety. Three sorts are
written in this module and they are not worth the same, so which is which is recorded here rather
than left for a reader to work out from the call sites:

* **``read_contract``'s sort over documents is load-bearing.** It is the one place filesystem
  order could reach this output. ``Traversable.iterdir`` declares no order and on ext4 with hashed
  directories it is arbitrary, so without it two machines holding one install print the contract
  in two orders. Sorted after the walk rather than during it, so it is a single statement a test
  can remove; ``test_the_contract_comes_out_in_path_order_whatever_order_the_package_lists_it_in``
  removes it by reading the same tree through a ``Traversable`` that lists in reverse.
* **``describe_contract``'s sort over problems is load-bearing.** ``resolve_pack_order`` emits
  problems in the order its walk finds them, which is graph order and not code order: a pack whose
  ``depends`` names both a cycle and a pack nobody installed hands back ``DEPENDS_CYCLE`` before
  ``DEPENDS_UNMATCHED``, and this sort is what turns that into ``12`` then ``14``.
  ``test_two_problems_are_printed_in_code_order_and_not_in_the_order_the_walk_found_them``
  builds exactly that pack and fails if the sort goes.
* **``_describe_pack``'s ``entries = sorted(...)`` is belt and braces, and nothing observes it.**
  Its result feeds ``match_pins``, whose problems are sorted by the bullet above and whose
  directories ``manifest._sorted_directories`` sorts again before either is printed. It is kept
  because a determinism property that holds only because two downstream modules happen to sort is
  a property held by a coincidence, but it is not defended by a test, and a reader should not go
  looking for the one that defends it.

Nothing else here iterates a set: the gaps come out in the order their document writes them, which
is a function of the file's bytes, and the pack names come from ``manifest.resolve_pack_order``,
which already sorts.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path

import periplus
from periplus.errors import ExitCode, Problem
from periplus.manifest import LoadedPack, resolve_pack_order
from periplus.packs import PackCandidate, match_pins
from periplus.preflight import DependencyStatus
from periplus.report import _escape
from periplus.resolution import resolve

__all__ = [
    "CONTRACT_DIRECTORY",
    "RENDERERS",
    "SUMMARY_RENDERERS",
    "ContractDocument",
    "Gap",
    "InheritedVocabulary",
    "PackSubject",
    "SpecReport",
    "contract_root",
    "describe_contract",
    "read_contract",
    "render_json",
    "render_json_summary",
    "render_text",
    "render_text_summary",
    "spec",
]

#: The directory inside the package that holds the contract. One name, read by this module and by
#: nothing else today; ``tests/test_packaging.py`` declares the file list the wheel may carry under
#: it, which is the bound on what this command can publish.
CONTRACT_DIRECTORY = "contract"

#: A heading that opens a list of things the contract cannot yet express. Two documents write it
#: two ways — ``## Still open`` in ``rules.md`` and ``## Open, and deliberately not decided here``
#: in ``engine.md`` — so this matches the shape rather than either literal.
#:
#: It is an **address**, not content. The four gaps themselves are not written down anywhere in
#: this package: they are read out of the shipped Markdown every run, so adding a fifth bullet to
#: either document publishes a fifth gap with no edit here. That is the whole reason this parser
#: exists instead of a tuple of strings.
#:
#: The shape is ``open`` as the **last word of a clause**: the heading ends there, or a comma,
#: colon, semicolon or full stop does. ``## Still open`` and ``## Open, and deliberately not
#: decided here`` are the two written today and both are that shape. What the shape excludes is a
#: heading where ``open`` is an adjective on some other subject — ``## Open questions for
#: reviewers``, ``## Open source dependencies``, ``## open-ended`` — every one of which a
#: ``\b`` after the word accepted. That is not a hypothetical over-match: the day somebody adds an
#: ``## Open source dependencies`` section to ``engine.md``, every bullet under it would have been
#: published as a limit of the schema language, with nothing in the output saying so.
_GAP_HEADING = re.compile(r"^\#{1,2} (?:still )?open\s*(?:[,:;.]|$)", re.IGNORECASE)

#: A heading at the level that ends a section. A ``###`` subsection stays inside its ``##`` parent.
_SECTION_HEADING = re.compile(r"^\#{1,2} ")

#: A bullet's bolded lead, as its title. ``- **Cardinality.** Nothing says …`` has the title
#: ``Cardinality``; the trailing full stop belongs to the sentence and not to the name. A bullet
#: with no bolded lead has no title, which is a fact about the bullet rather than an error.
_GAP_TITLE = re.compile(r"^\*\*(?P<title>.+?)\.?\*\*\s*")


@dataclass(frozen=True, slots=True)
class ContractDocument:
    """One file shipped under ``contract/``, and its bytes as text.

    ``path`` is relative to ``contract/`` and joined with ``/`` on every platform, because it names
    a resource inside a package and not a location on a disk. ``schema/map.schema.json`` is the
    same string whatever ran the command.
    """

    path: str
    text: str


@dataclass(frozen=True, slots=True)
class Gap:
    """One thing the schema language cannot yet express, as the document states it.

    ``title`` is the bullet's bolded lead, or an empty string when it has none. ``text`` is the
    rest of the bullet with its continuation lines joined into one, so a listing prints one gap per
    line and a name carrying a line break cannot forge a second.

    Both are shipped package data and are emitted verbatim. See the module docstring.
    """

    document: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class InheritedVocabulary:
    """The node types and edge kinds a pack may name because something it depends on declares them.

    Empty tuples mean the vocabulary was worked out and is empty. That is not the same as
    ``SpecReport.inherited`` being ``None``, which means it was not worked out at all — the record
    exists so a consumer has to branch on the difference instead of reading an absence as a zero.

    **This is the seam the next unit fills.** Resolving a non-empty ``depends`` chain into names
    needs a reader that opens a pack's rule files, and there is none. When there is, it produces
    one of these and the ``None`` branch in ``_describe_pack`` goes away; nothing else in this
    module, and nothing in either renderer, has to change shape.
    """

    node_types: tuple[str, ...]
    edge_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PackSubject:
    """The pack the command was asked about, as the search path and its own manifest describe it.

    ``requested`` is the name off the command line, kept whatever became of it, so a report about a
    pack that is not installed still says which one was asked for.

    ``directory`` is ``None`` when no directory on the search path carries the name, or when the
    one that does has a manifest that could not be read. Both are reported as a problem beside it.

    ``declares`` and ``version`` are what the manifest says about itself, which is deliberately not
    checked against ``requested``: ``manifest.py`` carries the directory's name and the file's own
    name side by side and lets neither win, because choosing between them is the validator's, and
    this module is a consumer of that record rather than a second place the judgment is made.

    ``depends`` is the parsed list, sorted and de-duplicated. ``inherits_from`` is every other pack
    the dependency walk actually reached, which is a different fact: a ``depends`` entry naming a
    pack that is not installed appears in the first and not in the second.
    """

    requested: str
    directory: str | None
    declares: str | None
    version: str | None
    depends: tuple[str, ...]
    inherits_from: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpecReport:
    """One ``spec`` run: the contract, what is open in it, and the pack it was asked about.

    ``pack`` is ``None`` when no pack was named. ``inherited`` is then the empty vocabulary rather
    than ``None``, and the distinction is the point: nothing was named, so nothing is inherited,
    and that is an answer rather than an absence.
    """

    tool_version: str
    documents: tuple[ContractDocument, ...]
    gaps: tuple[Gap, ...]
    pack: PackSubject | None
    inherited: InheritedVocabulary | None
    problems: tuple[Problem, ...]

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK``.

        The same expression as ``ResolutionReport.exit_code`` and ``InitReport.exit_code``,
        repeated rather than factored out, for the reason ``init.py`` records: a shared base class
        between records that have nothing else in common is an edge that lets a change to one
        report change another.
        """
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def contract_root() -> Traversable:
    """The shipped ``contract/`` directory, reached through the package rather than a built path.

    ``importlib.resources`` and never ``Path(__file__).parent``: the second works in a checkout and
    is wrong everywhere else, and it is the exact defect ``tests/test_contract.py`` installs a real
    wheel to rule out.
    """
    return importlib.resources.files("periplus") / CONTRACT_DIRECTORY


def read_contract(root: Traversable) -> tuple[ContractDocument, ...]:
    """Every file under ``contract/``, recursively, in path order.

    The walk is unconditional rather than a lookup of six known names. A seventh contract file
    added to the package is published by this command with no edit here, which is the same posture
    ``tests/test_contract.py`` takes when it asserts set equality over what an install exposes
    rather than looking up the names it expects.

    Sorted **after** the walk and not during it. One sort over the whole result is one statement a
    reader can find and a test can delete, where a sort per directory level is three places the
    property lives; ``Traversable.iterdir`` has no declared order and on ext4 with hashed
    directories it is arbitrary, so without this two machines holding one install would print the
    contract in two orders.

    Nothing here is caught. A file under ``contract/`` that cannot be read or decoded means the
    install is damaged, which is not a state a person's input can reach and has no remedy this
    command could print; it raises, and the interpreter's own status and traceback say more than a
    ``Problem`` would.
    """
    documents: list[ContractDocument] = []
    _visit(root, "", documents)
    return tuple(sorted(documents, key=lambda document: document.path))


def _visit(node: Traversable, path: str, documents: list[ContractDocument]) -> None:
    """Append every file at or under ``node``, naming each by its path relative to the root."""
    if node.is_dir():
        for child in node.iterdir():
            _visit(child, f"{path}/{child.name}" if path else child.name, documents)
        return
    documents.append(ContractDocument(path=path, text=node.read_text(encoding="utf-8")))


def read_gaps(documents: Sequence[ContractDocument]) -> tuple[Gap, ...]:
    """Everything the contract says it cannot yet express, read out of the contract.

    A gap is a bullet under a heading that opens an open-questions section — ``## Still open`` in
    ``rules.md``, ``## Open, and deliberately not decided here`` in ``engine.md``. Neither the
    headings' exact wording nor any gap's text is written down in this package: the heading is
    matched by shape and the bullets are read, so **adding a bullet to either document adds a gap
    to this command's output with no change here**. That is the property, and it is why this is a
    parser rather than a tuple of strings that would have to be edited in lockstep with the prose.

    Every document is offered to the parser, including the schemas. A JSON document has no line
    starting with ``## `` — a JSON string cannot carry a raw newline — so the parser finds nothing
    in one, and that costs a scan of bytes already in memory and saves a rule about which
    extensions are prose. A seventh contract document written in Markdown contributes its own open
    questions the day it ships.

    Documents come in path order and each document's gaps come out in the order it writes them.
    That order is the document's own and is a function of its bytes, so it is stable across
    machines the way a sort would be, and it keeps a list a person wrote reading the way they wrote
    it — the same call ``report._match_rows`` makes about the order of a ``packs:`` list.
    """
    return tuple(gap for document in documents for gap in _document_gaps(document))


def _document_gaps(document: ContractDocument) -> list[Gap]:
    """One document's open-questions bullets, in the order the document writes them.

    A section runs from its heading to the next heading at the same level or above, so a ``###``
    subsection inside it is part of it. A bullet runs from its ``- `` to the next bullet, the next
    heading or a blank line, with continuation lines stripped of their indentation and joined by
    single spaces. An indented sub-bullet therefore folds into its parent's text rather than
    becoming a gap of its own; no document does that today, and folding is the harmless reading.
    """
    gaps: list[Gap] = []
    bullet: list[str] = []
    inside = False

    def flush() -> None:
        if bullet:
            gaps.append(_gap(document.path, " ".join(bullet)))
            bullet.clear()

    for line in document.text.splitlines():
        if _SECTION_HEADING.match(line):
            flush()
            inside = bool(_GAP_HEADING.match(line))
            continue
        if not inside:
            continue
        if line.startswith("- "):
            flush()
            bullet.append(line[2:].strip())
        elif not line.strip():
            flush()
        elif bullet:
            bullet.append(line.strip())
    flush()
    return gaps


def _gap(document: str, text: str) -> Gap:
    """One bullet split into its bolded lead and the rest of what it says."""
    lead = _GAP_TITLE.match(text)
    if lead is None:
        return Gap(document=document, title="", text=text)
    return Gap(document=document, title=lead.group("title"), text=text[lead.end() :])


def describe_contract(
    contract: Traversable,
    tool_version: str,
    requested: str | None = None,
    candidates: Sequence[PackCandidate] = (),
    problems: Sequence[Problem] = (),
) -> SpecReport:
    """Assemble one report from a contract directory and, optionally, a pack to describe.

    ``contract`` is a ``Traversable`` and not a path this function builds, for the same reason
    ``resolve()`` takes ``start``: a test drives it against a temporary tree with no monkeypatching
    anywhere, which is what makes "add a fifth open question and it appears" a test that edits a
    file rather than a claim in a docstring.

    ``candidates`` are ignored when no pack was named, and ``spec()`` does not gather them on that
    path at all. See its docstring for why that is a property and not an optimisation.

    ``problems`` are the ones the caller already found — resolving the search path is the only
    source today — and they are folded in and sorted with this function's own, so the record
    carries every fault of the run and the status is the lowest code among all of them.
    """
    documents = read_contract(contract)
    gaps = read_gaps(documents)
    found: list[Problem] = list(problems)
    subject: PackSubject | None = None
    inherited: InheritedVocabulary | None = InheritedVocabulary(node_types=(), edge_kinds=())
    if requested is not None:
        subject, inherited = _describe_pack(requested, candidates, found)
    return SpecReport(
        tool_version=tool_version,
        documents=documents,
        gaps=gaps,
        pack=subject,
        inherited=inherited,
        # Sorted by code then message, once, at the end — the same key ``resolve()`` sorts its own
        # problems by, so a problem reads the same wherever a person meets it.
        problems=tuple(sorted(found, key=lambda problem: (int(problem.code), problem.message))),
    )


def _describe_pack(
    requested: str,
    candidates: Sequence[PackCandidate],
    problems: list[Problem],
) -> tuple[PackSubject, InheritedVocabulary | None]:
    """One pack name resolved to a directory, its manifest, and what it inherits.

    A name and not a ``<pack>@<version>`` pin: a person authoring a pack knows what their pack is
    called and need not know which version of a dependency is installed. Every ``named`` candidate
    whose pack half equals the name becomes a pin, and ``match_pins`` turns those into matches, so
    the one rule about how a directory name is read lives in ``packs.py`` and is not restated here.

    Two directories carrying the name are reported and neither is chosen, by
    ``resolve_pack_order``, which keys its graph by pack name and cannot hold one name as two
    packs. A single directory found under two roots is reported twice, once by ``match_pins`` as a
    duplicated pin and once by the walk as a duplicated name; they are two true statements about
    one tree — the pin matched in two places, and the name resolves to two directories — and
    suppressing either would need this module to decide which of a person's faults is the real one.
    """
    entries = sorted(
        {
            candidate.entry
            for candidate in candidates
            if candidate.status == "named"
            and candidate.name is not None
            and candidate.name.pack == requested
        }
    )
    absent = PackSubject(
        requested=requested,
        directory=None,
        declares=None,
        version=None,
        depends=(),
        inherits_from=(),
    )
    if not entries:
        problems.append(_unknown_pack(requested, candidates))
        return absent, None

    matches, pin_problems = match_pins(entries, candidates)
    order, walk_problems = resolve_pack_order(matches, candidates)
    problems.extend(pin_problems)
    problems.extend(walk_problems)

    loaded = next((pack for pack in order if pack.name.pack == requested), None)
    if loaded is None:
        # Every reason the walk could not produce it — a duplicated name, an unreadable manifest —
        # has already appended its own problem, so this branch adds none and would be lying if it
        # invented one.
        return absent, None
    subject = PackSubject(
        requested=requested,
        directory=loaded.path,
        declares=loaded.manifest.pack,
        version=loaded.manifest.version,
        depends=tuple(sorted(set(loaded.manifest.depends))),
        inherits_from=tuple(
            sorted({pack.name.pack for pack in order if pack.name.pack != requested})
        ),
    )
    return subject, _inherited(loaded)


def _inherited(loaded: LoadedPack) -> InheritedVocabulary | None:
    """The empty vocabulary for a pack that depends on nothing, and ``None`` for every other pack.

    A pack whose manifest declares no ``depends`` has an empty dependency closure, so the union of
    the node types and edge kinds it inherits is empty. That is arithmetic over an empty set and
    needs no reader, which is why this one answer can be given today and the other cannot.

    The question is asked of the **raw** ``depends`` value and not of ``PackManifest.depends``,
    and the difference is the difference between a true and a false statement.
    ``manifest.py`` deliberately parses ``depends: "php"`` to ``()`` — dropping a mistyped value
    rather than reading it as three dependencies named ``p``, ``h`` and ``p`` — so its empty tuple
    covers two files: one that declares no dependencies, and one whose declaration could not be
    read. Only the first inherits nothing. The second is unknown, and unknown is ``None``.
    """
    declared = loaded.manifest.document.get("depends")
    if declared is None or (isinstance(declared, list | tuple) and not declared):
        return InheritedVocabulary(node_types=(), edge_kinds=())
    return None


def _unknown_pack(requested: str, candidates: Sequence[PackCandidate]) -> Problem:
    """A name no directory on the pack search path carries.

    ``available`` is every pack name discovery found, sorted, rather than a guess at which was
    meant — the same call ``manifest._unmatched`` makes, and for the same reason: a rule that
    decides ``twigg`` meant ``twig`` will one day decide it meant ``php``.
    """
    available = sorted(
        {
            candidate.name.pack
            for candidate in candidates
            if candidate.status == "named" and candidate.name is not None
        }
    )
    return Problem(
        code=ExitCode.PACK_UNKNOWN,
        message=f"no pack on the pack search path is named {requested!r}",
        detail={"pack": requested, "available": ", ".join(available)},
    )


def spec(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
    requested: str | None = None,
) -> SpecReport:
    """The command's entry point: the contract, and a pack only when one was named.

    **With no pack named this reads nothing outside the installed package.** No settings file is
    located, no project root is walked to, no pack directory is listed — because there is no
    question that needs them. That is a stated property rather than a saving: the contract is
    package data, and a command that publishes it must work on a machine with no project, no
    configuration and no packs installed, which is the machine a model authoring its first pack is
    sitting at. A test plants an unparseable settings file above the working directory and asserts
    this run still exits 0, which is what makes the property observable rather than argued.

    With a pack named, the search path is resolved **exactly as ``status`` resolves it**, by
    calling ``resolve()`` — one definition of where packs live, rather than a second one here that
    would drift and would miss a ``pack_paths`` root a settings file added.

    That means this run inherits every problem resolution found, including ones about pins it did
    not need, and the status is the lowest code among all of them. The alternative is a filter
    deciding which of a project's faults are allowed to matter, and there is no honest rule for
    writing one: a settings file that could not be read is a pack search path the tool cannot vouch
    for, and a report that described a pack found on a path it could not compute would be a report
    that lies about where it looked.
    """
    if requested is None:
        return describe_contract(contract_root(), periplus.__version__)
    resolution = resolve(start=start, env=env, dependencies=dependencies)
    return describe_contract(
        contract_root(),
        periplus.__version__,
        requested,
        resolution.candidates,
        resolution.problems,
    )


# ---------------------------------------------------------------------------------------------
# The text form
# ---------------------------------------------------------------------------------------------


def render_text(report: SpecReport) -> str:
    """The contract as the bytes a model reads: the summary, then every document in full.

    **This is the default form and stays the default form.** The consumer is a model authoring a
    pack, and it needs the schemas themselves; a form that named the documents and stopped would
    cost that consumer a second command and a second round trip to reach what it came for, which
    is a real price paid on every run to save bytes nobody was short of.

    The summary comes first and the documents last, because the summary is what a person scanning
    the output needs and the documents are what a model reading all of it needs. Neither is
    truncated: a contract published in part is a contract an author writes against in part.

    Each document is introduced by a ruled line naming its path and is then emitted **byte for
    byte**. It is the artifact, and a transformed artifact is not the artifact — a Markdown fence
    re-indented or a schema re-serialised is a document the author of a pack would then be building
    against by inference.
    """
    text = render_text_summary(report)
    for document in report.documents:
        text += f"\n{'-' * 8} {document.path} {'-' * 8}\n\n{document.text}"
    return text


def render_text_summary(report: SpecReport) -> str:
    """The summary block alone: what was published, the pack, the gaps, the problems.

    ``--summary``. It is the same bytes ``render_text`` opens with, and that is the whole
    definition — the two forms cannot drift, because there is one function and the whole form is
    this one plus the documents appended to it.

    Nothing here is a digest of a document. Every path is named in full, so a reader who wants one
    of them knows exactly what to ask for, and no line of this block stands in for prose it
    summarises. What is dropped is the documents' bytes and nothing else.
    """
    lines: list[str] = [f"periplus {_escape(report.tool_version)} pack contract"]
    lines += _section("Contract documents", [document.path for document in report.documents])
    lines += _section("Pack", _pack_lines(report.pack))
    lines += _section("Inherited vocabulary", _vocabulary_lines(report.inherited))
    lines += _section("Not yet expressible", _gap_lines(report.gaps))
    lines += _section("Problems", _problem_lines(report.problems))
    return "\n".join(lines) + "\n"


def _section(heading: str, rows: Sequence[str]) -> list[str]:
    """One block: a blank line, its heading, and its rows indented under it.

    No column alignment and no width computed from anything. ``report._block`` aligns because a
    resolution report is a table; this output is a list of labelled facts followed by whole
    documents, so borrowing that machinery would be borrowing a decision this form does not make.
    An empty block prints ``none`` rather than nothing, because a section a reader cannot find is
    indistinguishable from a section that does not exist.
    """
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]


def _labelled(label: str, value: str) -> str:
    """One fact under a heading, its label padded to a fixed width written here and nowhere else."""
    return f"{label:<12}{value}"


def _pack_lines(pack: PackSubject | None) -> list[str]:
    """The pack that was asked about, or that none was.

    Every value comes off a command line, a filesystem or a manifest, so every value is escaped.
    """
    if pack is None:
        return ["no pack was named"]
    declared = (
        "not declared"
        if pack.declares is None
        else f"{_escape(pack.declares)} {_escape(pack.version or 'no version')}"
    )
    return [
        _labelled("requested", _escape(pack.requested)),
        _labelled("directory", _escape(pack.directory or "not found on the pack search path")),
        _labelled("declares", declared),
        _labelled("depends", _joined(pack.depends) or "none"),
        _labelled("inherits", _joined(pack.inherits_from) or "none"),
    ]


def _vocabulary_lines(inherited: InheritedVocabulary | None) -> list[str]:
    """What the pack may name because a dependency declares it, or that nobody has read it.

    The ``None`` case says which reader is missing rather than printing an empty list. An empty
    list would be a claim, and the claim would be false.
    """
    if inherited is None:
        return ["not read - no reader opens a pack's rule files for its node types and edge kinds"]
    return [
        _labelled("node types", _joined(inherited.node_types) or "none"),
        _labelled("edge kinds", _joined(inherited.edge_kinds) or "none"),
    ]


def _gap_lines(gaps: Sequence[Gap]) -> list[str]:
    """One line per open question, naming the document that states it.

    Package data, emitted verbatim. The join in ``_document_gaps`` has already made each one line,
    so there is no line here for a document to forge — and the documents ship inside the wheel,
    which is the reason nothing here is escaped and the pack lines above all are.
    """
    return [
        f"{gap.document}  {gap.title}{': ' if gap.title else ''}{gap.text}".rstrip() for gap in gaps
    ]


def _problem_lines(problems: Sequence[Problem]) -> list[str]:
    """One line per problem, its code first, with its named facts under it."""
    lines: list[str] = []
    for problem in problems:
        lines.append(f"{int(problem.code)}  {_escape(problem.message)}")
        lines += [
            f"    {_escape(key)}: {_escape(problem.detail[key])}" for key in sorted(problem.detail)
        ]
    return lines


def _joined(values: Sequence[str]) -> str:
    """A list of names as one line, each escaped, because each came from outside the package."""
    return ", ".join(_escape(value) for value in values)


# ---------------------------------------------------------------------------------------------
# The JSON form
# ---------------------------------------------------------------------------------------------


def render_json(report: SpecReport) -> str:
    """The report as one JSON document, keys sorted, every contract file carried in full.

    An explicit projection rather than a walk over the dataclasses, for the reason
    ``report.render_json`` gives: adding a field to a record must not silently add a key whose type
    nobody chose. The whole record is JSON primitives already, so nothing here converts a value —
    the projection is here to name the keys, not to rescue them.

    ``ensure_ascii=True``, matching the other form of every report this tool prints. A pack name
    and a directory name come off a filesystem where a name need not be valid UTF-8, and under
    ``ensure_ascii`` a surrogate escape encodes cleanly instead of raising out of the encoder.

    Nothing is passed through ``_escape`` here, exactly as in ``report.render_json``: that helper
    stops a name forging a *line*, and this document has no lines to forge. The encoder escapes a
    newline itself, losslessly and reversibly, which is what a consumer of this form needs.
    """
    return _json(
        report, [{"path": document.path, "text": document.text} for document in report.documents]
    )


def render_json_summary(report: SpecReport) -> str:
    """The same document with every ``text`` dropped, and nothing else changed.

    ``--summary --format json``, and this is the form the flag exists for. A consumer that wants
    the ``gaps`` array today parses some seventy kilobytes of escaped document text to reach it,
    all of which it then discards; here the whole document is the part it wanted.

    ``documents`` stays a **list of objects**, each carrying its ``path``, rather than collapsing
    to a list of strings. One expression — ``[d["path"] for d in payload["documents"]]`` — then
    reads the paths out of either form, where a type that changed with a flag would make a
    consumer branch on which flag it passed. A consumer that reaches for ``text`` gets a
    ``KeyError``, which is the loud failure and the right one: the bytes are genuinely not here,
    and a key holding an empty string or a null would say they were and were empty.
    """
    return _json(report, [{"path": document.path} for document in report.documents])


def _json(report: SpecReport, documents: list[dict[str, str]]) -> str:
    """One JSON document over a report and whichever projection of its contract files."""
    payload = {
        "tool_version": report.tool_version,
        "documents": documents,
        "gaps": [
            {"document": gap.document, "title": gap.title, "text": gap.text} for gap in report.gaps
        ],
        "pack": _json_pack(report.pack),
        "inherited": _json_vocabulary(report.inherited),
        "problems": [
            {
                "code": int(problem.code),
                "message": problem.message,
                "detail": dict(problem.detail),
            }
            for problem in report.problems
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _json_pack(pack: PackSubject | None) -> dict[str, object] | None:
    """The pack that was asked about, or ``null`` when none was named."""
    if pack is None:
        return None
    return {
        "requested": pack.requested,
        "directory": pack.directory,
        "declares": pack.declares,
        "version": pack.version,
        "depends": list(pack.depends),
        "inherits_from": list(pack.inherits_from),
    }


def _json_vocabulary(inherited: InheritedVocabulary | None) -> dict[str, object] | None:
    """The inherited vocabulary, or ``null`` when no reader has worked it out.

    ``null`` and an object of empty arrays are different facts and both occur: the first means
    nothing read it, the second means it was read and is empty.
    """
    if inherited is None:
        return None
    return {
        "node_types": list(inherited.node_types),
        "edge_kinds": list(inherited.edge_kinds),
    }


#: The formats ``spec --format`` offers, in the order they are offered. ``cli.build_parser`` writes
#: the same two names as a literal for the reason ``report.RENDERERS`` records — ``cli`` may not
#: import this module, because it reaches ``ruamel.yaml`` — and a test asserts the two agree.
RENDERERS: Mapping[str, Callable[[SpecReport], str]] = {
    "text": render_text,
    "json": render_json,
}

#: The same two formats under ``--summary``. A second table keyed by the same names, rather than a
#: ``summary`` argument threaded through both renderers: ``cli`` picks a table and then looks a
#: format up in it, so the flag is decided once at the call site and neither renderer carries a
#: branch. Both names are driven through ``--summary`` by a test, so a format present in one table
#: and not the other is a ``KeyError`` in the suite rather than in somebody's terminal.
SUMMARY_RENDERERS: Mapping[str, Callable[[SpecReport], str]] = {
    "text": render_text_summary,
    "json": render_json_summary,
}
