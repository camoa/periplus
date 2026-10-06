"""``periplus validate <pack>``: check a pack against the shipped schemas, and stop.

The names come from ``spec.py``, which is the command this one sits beside: a frozen record per
failure, one report record, two renderers in a ``RENDERERS`` table keyed by ``--format``'s two
choices, and an ``exit_code`` property on the report. A person who has read ``spec`` should not
have to learn a second shape here.

Three properties this module has to hold, all of them asserted by tests already written:

**It is imported lazily, inside ``main()``.** ``errors.py`` states the package's central
constraint — nothing on ``cli``'s module-level import path imports a runtime distribution — and
this module reaches ``jsonschema``, so a module-level ``import periplus.validate`` in ``cli.py``
would put that distribution on the path the dependency check exists to keep clear.
``cli.py`` already imports ``init`` and ``spec`` this way.

**Its output is deterministic.** Determinism binds every command.
``Draft202012Validator.iter_errors`` declares no order, ``Path.rglob`` returns filesystem order,
and neither is stable across machines. So every error found across every file in the pack is
collected and then sorted once, by ``(file, pointer, message, keyword)``, before anything is
rendered. The keyword is the fourth component because path, pointer and message together do not
order two errors that differ only in which keyword failed.

**A branch failure names the keys under it.** ``pack-file.schema.json`` holds seven ``oneOf`` and
four ``anyOf``. A failure inside one produces a parent error reading "is not valid under any of
the given schemas", which names no key at all — so the sub-errors ``jsonschema`` carries in
``ValidationError.context`` are rendered beneath their parent, sorted by the same key.
Validate has to name what failed, and a line naming only the branch does not.

Two things this module does not do, recorded so a reader does not go looking for them.

It does **not** check a pack's vocabulary against its dependencies — that a rule may only name a
type its own pack or a pack it depends on declares. That is the graph validator, it needs the
reader ``spec.InheritedVocabulary`` is waiting on, and it is the next unit. What is checked here is
one file against one document, which is every check the two shipped schemas can express.

It does **not** validate the packs a pack depends on. ``periplus validate drupal`` reads
``drupal``'s files and no others, although resolving the name walks the ``depends`` graph and
inherits whatever that walk reported. A pack is validated by naming it, which is also the command
a CI step runs once per pack.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, Problem
from periplus.manifest import MANIFEST_FILENAME, resolve_pack_order
from periplus.packs import PackCandidate, match_pins
from periplus.preflight import DependencyStatus
from periplus.report import _escape
from periplus.resolution import resolve
from periplus.spec import _unknown_pack, contract_root

__all__ = [
    "MANIFEST_SCHEMA",
    "PACK_FILE_SCHEMA",
    "RENDERERS",
    "SchemaError",
    "ValidationReport",
    "render_json",
    "render_text",
    "validate",
]

#: The problem name for a bare pack name that two or more copies on the search path carry.
PACK_AMBIGUOUS = "PACK_AMBIGUOUS"

#: The shipped schema a ``pack.yaml`` is checked against, named by its path under ``contract/``.
#: Read through ``spec.contract_root()`` rather than through a second reader.
MANIFEST_SCHEMA = "schema/pack-manifest.schema.json"

#: The shipped schema every other ``*.yaml`` / ``*.yml`` in a pack directory is checked against.
#:
#: The rule that decides which of the two applies — ``pack.yaml`` is the manifest, everything else
#: is a pack file — is engine knowledge a pack cannot override, and it is a recorded limit of this
#: task rather than a solved problem. A pack shipping a YAML file that is not rules has no way to
#: say so, and no bundled pack does this today.
PACK_FILE_SCHEMA = "schema/pack-file.schema.json"

#: The two suffixes a file in a pack directory is read for. Written here rather than at the one
#: call site, because it is half of the classification rule the constant above records the other
#: half of, and a reader looking for "which files does this open" should find one answer.
_YAML_SUFFIXES = (".yaml", ".yml")


@dataclass(frozen=True, slots=True)
class SchemaError:
    """One disagreement between a file in a pack and the schema it is written against.

    ``file`` is the file's path relative to the pack directory, joined with ``/`` on every
    platform, because it names a place inside a pack and not a location on a disk.

    ``pointer`` addresses the failing key inside that file — ``$.rules[0]`` for the first rule,
    ``$`` for the document itself. ``keyword`` is the validator keyword that failed, carried
    because it is the fourth component of the sort key and because ``required`` and ``oneOf``
    failing at one pointer are two different faults.

    ``context`` holds the sub-errors of a branch failure, already sorted. It is empty for every
    other kind, which is a value and not a placeholder.
    """

    file: str
    pointer: str
    keyword: str
    message: str
    context: tuple[SchemaError, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """One ``validate`` run: what was checked, what disagreed, and what else went wrong.

    ``checked`` names every file the run opened, relative to the pack directory and sorted. It is
    carried rather than counted, because "no errors" and "no files" are different answers and a
    report that gave only the first could not tell them apart.

    ``version`` is the version half of the directory name that was checked, ``None`` when no
    directory was found; with ``directory`` it says which copy of the pack the run opened.

    ``problems`` are the resolution faults the run inherited — an unreadable settings file, a pin
    matching nothing — kept apart from ``errors`` because they are faults in a different file with
    a different owner.
    """

    pack: str
    directory: str | None
    checked: tuple[str, ...]
    errors: tuple[SchemaError, ...]
    problems: tuple[Problem, ...]
    version: str | None = None

    @property
    def exit_code(self) -> ExitCode:
        """``SCHEMA_INVALID`` whenever anything disagreed, else the lowest problem code, else OK.

        **This departs from the ``min()`` aggregation every other report uses, deliberately.**
        ``SCHEMA_INVALID`` is the highest number in the table, so under ``min()`` it would be
        masked by every existing code and a ``validate`` run in a project with an unresolvable pin
        would exit 5 — reporting a fault in the settings file as the answer to a question about a
        pack. A schema error is this command's entire subject, so it takes the status.
        """
        if self.errors:
            return ExitCode.SCHEMA_INVALID
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def validate(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
    requested: str,
) -> ValidationReport:
    """Resolve one pack name, check every YAML file it carries, and report.

    The pack is resolved through the pack search path exactly as ``spec`` resolves it, by calling
    ``resolve()`` — one definition of where packs live rather than a second one here. A name no
    directory on the path carries is ``PACK_UNKNOWN``, which already means "an argument names a
    pack nothing carries".

    Pack YAML is parsed at ``typ='safe'``, as ``settings.py`` and ``manifest.py`` parse theirs.
    ``_load`` records what that buys and what it does not; the short form is that the round-trip
    loader constructs Python objects out of a pack's own tags and the safe one refuses.

    Every problem ``resolve()`` found is carried, including ones about pins this run did not need,
    for the reason ``spec()`` records: a settings file that could not be read is a pack search path
    the tool cannot vouch for, and a report describing a pack found on a path it could not compute
    would be a report that lies about where it looked.
    """
    resolution = resolve(start=start, env=env, dependencies=dependencies)
    problems: list[Problem] = list(resolution.problems)
    pins = (
        resolution.settings.packs.value if resolution.settings and resolution.settings.packs else ()
    )
    directory, path, version = _locate(requested, resolution.candidates, pins, problems)
    if directory is None:
        return _report(requested, None, (), (), problems)
    checked, errors = _check_directory(directory, problems)
    return _report(requested, path, checked, errors, problems, version)


def _report(
    requested: str,
    path: str | None,
    checked: tuple[str, ...],
    errors: tuple[SchemaError, ...],
    problems: Sequence[Problem],
    version: str | None = None,
) -> ValidationReport:
    """One report, with its problems sorted by code then message.

    The same key ``resolve()`` and ``describe_contract()`` sort their own problems by, so a problem
    reads the same wherever a person meets it.
    """
    return ValidationReport(
        pack=requested,
        directory=path,
        checked=checked,
        errors=errors,
        problems=tuple(sorted(problems, key=lambda problem: (int(problem.code), problem.message))),
        version=version,
    )


def _locate(
    requested: str,
    candidates: Sequence[PackCandidate],
    pins: Sequence[str],
    problems: list[Problem],
) -> tuple[Traversable | None, str | None, str | None]:
    """One pack name, or ``name@version``, resolved to the directory that carries it, or to nothing.

    ``name@version`` names the copy. A bare name with one copy on the path names that copy. A bare
    name with several copies takes the copy the project pins, and with no pin among them stops with
    ``PACK_AMBIGUOUS`` listing every copy, rather than checking one and saying nothing about which.
    A version no copy carries is ``PACK_UNKNOWN`` naming the versions that are on the path.

    The same three calls ``spec._describe_pack`` makes, in the same order and for the same reasons:
    every ``named`` candidate whose pack half equals the name becomes a pin, ``match_pins`` turns
    those into matches, and ``resolve_pack_order`` turns a match into a ``LoadedPack`` — which is
    the one record carrying the pack directory as a ``Traversable``. That handle is what makes this
    work under an install where the bundled root is not a ``Path``.

    ``_unknown_pack`` is imported from ``spec`` rather than written again. It is the same fault
    with the same remedy and the same ``detail`` keys, and two copies of one message is how the two
    commands come to answer one mistake differently.

    A ``None`` directory adds no problem of its own beyond the one already appended. Every reason
    the walk could not produce the pack — a duplicated name, an unreadable manifest — has reported
    itself, and inventing a second would be describing one fault twice.
    """
    name, _, version = requested.partition("@")
    copies = [
        candidate
        for candidate in candidates
        if candidate.status == "named"
        and candidate.name is not None
        and candidate.name.pack == name
    ]
    entries = sorted({candidate.entry for candidate in copies})
    if not entries:
        problems.append(_unknown_pack(name, candidates))
        return None, None, None
    if version:
        entries = [entry for entry in entries if entry == requested]
        if not entries:
            versions = ", ".join(sorted({c.name.version for c in copies if c.name}))
            problems.append(
                Problem(
                    code=ExitCode.PACK_UNKNOWN,
                    message=f"no copy of {name!r} on the pack search path is version {version!r}",
                    detail={"pack": name, "version": version, "available": versions},
                )
            )
            return None, None, None
    elif len(entries) > 1:
        pinned = [entry for entry in entries if entry in pins]
        if not pinned:
            problems.append(_ambiguous(name, copies))
            return None, None, None
        entries = pinned

    matches, pin_problems = match_pins(entries, candidates)
    order, walk_problems = resolve_pack_order(matches, candidates)
    problems.extend(pin_problems)
    problems.extend(walk_problems)

    loaded = next((pack for pack in order if pack.name.pack == name), None)
    if loaded is None:
        return None, None, None
    return loaded.directory, loaded.path, loaded.name.version


def _ambiguous(name: str, copies: Sequence[PackCandidate]) -> Problem:
    """Two or more copies of a name and nothing to choose between them, each copy listed.

    ``PACK_AMBIGUOUS`` is the problem's own name, in ``detail``; its exit code is
    ``PACK_UNKNOWN``'s, 15, because ``errors.ExitCode`` has no member of its own for it.
    """
    listed = sorted(
        f"{c.entry} at {Path(c.root.display) / c.entry}" for c in copies if c.name is not None
    )
    return Problem(
        code=ExitCode.PACK_UNKNOWN,
        message=(
            f"{PACK_AMBIGUOUS}: {len(listed)} copies of {name!r} are on the pack search path "
            f"({'; '.join(listed)}); name one as {name}@<version>"
        ),
        detail={"problem": PACK_AMBIGUOUS, "pack": name, "copies": "; ".join(listed)},
    )


def _check_directory(
    directory: Traversable,
    problems: list[Problem],
) -> tuple[tuple[str, ...], tuple[SchemaError, ...]]:
    """Every YAML file under one pack directory, checked, with one sort over the whole result.

    **One sort, across every file at once, and that is the load-bearing statement in this module.**
    The walk below returns files in the order the filesystem lists them, which on ext4 with hashed
    directories is arbitrary and differs between two machines holding one tree; ``iter_errors``
    declares no order of its own. Sorting per file would leave the order the *files* were walked in
    deciding the output. Sorting once at the end absorbs both.

    Each validator is built once and used for every file it applies to. That is not a saving: a
    validator built per file would re-resolve the same ``$ref`` graph forty-eight times for
    ``drupal``, and the reason to say so here is that a reader should not move it back.
    """
    manifest = Draft202012Validator(_schema(MANIFEST_SCHEMA))
    pack_file = Draft202012Validator(_schema(PACK_FILE_SCHEMA))

    checked: list[str] = []
    errors: list[SchemaError] = []
    for relative, node in _yaml_files(directory):
        # `readable`, and never `document is None`. A file that would not parse and a file that
        # parsed and holds `null` both give a document of `None`, and reading the second as the
        # first is how an empty file, a comment-only file and one holding `--- null` were dropped
        # from a run with no record: unchecked, unreported, and the command exiting 0. A null
        # document is a schema error the shipped schema already expresses, so it goes to the
        # validator like any other and comes back as `None is not of type 'object'`.
        document, readable = _load(node, problems)
        if not readable:
            continue
        checked.append(relative)
        validator = manifest if relative.rsplit("/", 1)[-1] == MANIFEST_FILENAME else pack_file
        errors.extend(_error(relative, found) for found in validator.iter_errors(document))
    return tuple(sorted(checked)), tuple(sorted(errors, key=_sort_key))


def _schema(name: str) -> Mapping[str, object]:
    """One shipped schema, read out of the installed package through ``spec``'s own reader.

    ``contract_root()`` and not a second ``importlib.resources`` call: ``spec`` already publishes
    these four documents from that directory, and two readers of one directory is where a wheel
    install and a source checkout come to disagree about what shipped.

    The name is split on ``/`` rather than passed whole. ``Traversable.joinpath`` is not required
    to accept a path with a separator in it, and the bundled contract is reached through whatever
    ``importlib.resources`` hands back on the install this is running from.
    """
    node = contract_root()
    for segment in name.split("/"):
        node = node / segment
    # Annotated rather than returned straight out of `json.loads`, whose declared return is `Any`.
    # Under mypy strict an `Any` returned from a typed function is an error, and the annotation is
    # the claim being made: these four documents are objects, and `check_schema` in
    # `tests/test_contract.py` is what holds that claim rather than a runtime branch here.
    document: Mapping[str, object] = json.loads(node.read_text(encoding="utf-8"))
    return document


def _yaml_files(directory: Traversable) -> list[tuple[str, Traversable]]:
    """Every ``*.yaml`` and ``*.yml`` at or under a pack directory, each named relative to it.

    Relative and joined with ``/`` on every platform, because the name says where a file sits
    inside a pack and a pack is the same pack wherever it was unpacked.

    **This is where filesystem order enters, so it is where filesystem order has to stop.**
    ``Traversable.iterdir`` declares no order and on ext4 with hashed directories it is arbitrary,
    so without this sort two machines holding one pack walk its files in two orders.

    **No test defends it.** In particular,
    ``test_an_unmodified_bundled_pack_validates_clean_and_says_what_it_opened`` does not: with
    ``return found`` in place of the sort, the whole suite passes. That test compares
    ``set(payload["checked"])`` against a set, and ``checked`` is sorted again downstream, so the
    walk order cannot reach it. A green suite after deleting the sort is not permission to delete
    it.

    What a mutation does reach is ``errors`` order, and only in combination: with this sort gone
    *and* the ``file`` component dropped from ``_sort_key``, two errors print in
    ``iterdir`` order. Neither mutation alone is observed by anything. That the sort key's
    components are undefended is recorded as a known gap and is not closed here.

    ``_check_directory``'s ``sorted(checked)`` is the redundant one — deleting it fails nothing,
    because this function has already sorted. It is kept for the reason ``spec._describe_pack``
    keeps its own unobserved sort: a determinism property that holds only because an upstream
    function happens to sort is held by a coincidence.
    """
    found: list[tuple[str, Traversable]] = []
    _walk(directory, "", found)
    return sorted(found, key=lambda entry: entry[0])


def _walk(node: Traversable, path: str, found: list[tuple[str, Traversable]]) -> None:
    """Append every YAML file at or under ``node``. Nothing else in the tree is opened."""
    if node.is_dir():
        for child in node.iterdir():
            _walk(child, f"{path}/{child.name}" if path else child.name, found)
        return
    if any(node.name.endswith(suffix) for suffix in _YAML_SUFFIXES):
        found.append((path, node))


def _load(node: Traversable, problems: list[Problem]) -> tuple[object, bool]:
    """One pack file as a parsed document, and whether it could be read at all.

    **The second half of that pair is the whole point of the signature.** A
    file that will not parse and a file that parses to ``null`` both give a document of ``None``,
    so a caller branching on ``document is None`` treats the second as the first. Then an empty
    file, a comment-only file and one holding ``--- null`` in a pack would be
    dropped from the run with no record — not in ``checked``, not in ``errors``, not in
    ``problems``, and the command would exit 0. Returning the flag separately is what makes a null
    document reach the validator, where ``pack-file.schema.json``'s top-level ``"type": "object"``
    already has the answer: ``None is not of type 'object'``.

    ``YAML(typ='safe', pure=True)``, the configuration ``settings.py`` and ``manifest.py`` both
    use, for the three reasons ``load_manifest`` records. The first of the three is the one that
    matters here, and stated exactly: **a pack is third-party data, and the safe loader refuses a
    tag it does not know where the round-trip loader accepts it as data.** Measured on ruamel
    0.19.1, all three loaders, against ``!!python/object/apply:os.system [...]``:

    * ``safe`` raises ``ConstructorError``.
    * ``rt`` returns a ``CommentedSeq`` carrying the tag. Nothing is constructed and nothing runs.
    * ``unsafe`` executes it. The marker file appeared.

    **What the tag then costs is a silent pass, not a confusing error.** ``jsonschema`` sees the
    node underneath and not the tag, so a tagged value whose underlying node matches the declared
    type validates clean with the tag still on it. Measured, same version::

        rt-load   a: !!python/object/apply:os.system ['echo hi']
        validate  {"type": "array", "items": {"type": "string"}}
        result    no errors; value is CommentedSeq(['echo hi']) tagged
                  tag:yaml.org,2002:python/object/apply:os.system

    Under ``safe`` those bytes never become a document at all. So the tag is refused where an
    author sees it, rather than carried into a map by a validator that had no way to object.

    **Three plausible claims about these loaders are false, and only measurement shows it.**
    ``rt`` does not construct the Python object — ``unsafe`` is the loader that does. A
    ``TaggedScalar`` is not an object that no keyword describes — every keyword tried describes it,
    including the shipped manifest schema, which reports ``$.pack  type`` for a tagged scalar. And
    ``CommentedMap.__repr__`` does not differ from ``dict``'s: measured on ruamel 0.19.1, the two
    reprs are byte-identical — ``CommentedMap`` renders as ``{'a': 1}`` exactly as ``dict`` does —
    so no error text that ``jsonschema`` interpolates through ``{instance!r}`` into ``enum``,
    ``type`` and every branch message depends on which of the two loaders ran. Swapping them leaves
    the whole suite green, which is the same fact from the other side. A reader tempted to restate
    any of this from what the names suggest should run it first. ``settings.py`` and ``manifest.py``
    claim only "safe refuses arbitrary object construction", which is accurate.

    **A file that will not parse is a ``Problem`` at ``UNREADABLE_MANIFEST`` and not a
    ``SchemaError``,** and the code is shared with ``manifest.py`` deliberately. A ``SchemaError``
    names a key and a pointer inside a document, and there is no document here to point into. The
    fault is the same one that member already covers — a file a pack author shipped could not be
    turned into a mapping — with the same one remedy, open the named path. What it costs is that
    the member's name says "manifest" about a rule file; a code of its own would have been a new
    number for a remedy already written down.
    """
    display = str(node)
    yaml = YAML(typ="safe", pure=True)
    try:
        with node.open("r", encoding="utf-8") as stream:
            # Annotated for the reason `_schema` records: `YAML.load` is declared `Any`, and what
            # comes back is genuinely unknown -- a mapping, a list, a string or `None`, whatever
            # the file holds. `object` is the honest type and the validator takes it from here.
            document: object = yaml.load(stream)
        return document, True
    except YAMLError as error:
        problems.append(_unreadable(display, "parser", "could not be parsed", error))
    except UnicodeDecodeError as error:
        problems.append(_unreadable(display, "encoding", "is not valid UTF-8", error))
    except OSError as error:
        problems.append(_unreadable(display, "read", "could not be read", error))
    return None, False


def _unreadable(display: str, cause: str, said: str, error: Exception) -> Problem:
    """One file in a pack that could not be turned into a document, named by its cause.

    The same four ``detail`` keys ``manifest.ManifestUnreadable`` populates, so a consumer of
    ``--format json`` reads one shape for the two commands that report this code.
    """
    return Problem(
        code=ExitCode.UNREADABLE_MANIFEST,
        message=f"a file in the pack {said}: {display}",
        detail={"path": display, "cause": cause, "detail": str(error)},
    )


def _error(file: str, error: ValidationError) -> SchemaError:
    """One ``jsonschema`` error as a record, with its branch sub-errors beneath it.

    ``json_path`` rather than a pointer assembled here: ``$.rules[0]`` is the address the
    reference implementation itself prints, so a person reading this output and a person reading
    ``jsonschema``'s are reading one notation.

    ``context`` is walked recursively because a branch can hold a branch. Each level is sorted by
    the same four-part key as the top level, so the whole tree has one order and it is not the
    order ``iter_errors`` happened to yield.
    """
    return SchemaError(
        file=file,
        pointer=error.json_path,
        # `validator` is the keyword's name for every error a schema produces, and a sentinel on
        # the errors `jsonschema` raises about a schema rather than about an instance. `str` is
        # what makes the sort key a string in both cases rather than raising on the second.
        keyword=str(error.validator),
        message=error.message,
        context=tuple(sorted((_error(file, sub) for sub in error.context), key=_sort_key)),
    )


def _sort_key(error: SchemaError) -> tuple[str, str, str, str]:
    """File, pointer, message, then keyword. The fourth component is not an afterthought.

    Path, pointer and message together do not order two errors that differ only in which keyword
    failed — ``required`` and ``oneOf`` can fail at one pointer with one message shape — and
    falling back to ``iter_errors`` order there is the guarantee ``jsonschema`` does not give.
    """
    return (error.file, error.pointer, error.message, error.keyword)


# ---------------------------------------------------------------------------------------------
# The text form
# ---------------------------------------------------------------------------------------------


def render_text(report: ValidationReport) -> str:
    """The report as the lines a person reads: the file, the pointer, and what disagreed.

    Every error names the failing key and its path in the file. A branch failure's sub-errors are
    indented beneath it.

    Every value here is escaped. A pack name comes off the command line, a file name comes off a
    filesystem where any byte but ``/`` and NUL is legal, and a schema message quotes the contents
    of a pack file — all three are attacker-influenced text and go through ``_escape`` exactly as
    they do in ``report``, ``init`` and ``spec``.
    """
    lines: list[str] = [f"periplus validate {_escape(report.pack)}"]
    lines += _section("Pack", _pack_lines(report))
    lines += _section("Checked", [_escape(name) for name in report.checked])
    lines += _section("Schema errors", _error_lines(report.errors, ""))
    lines += _section("Problems", _problem_lines(report.problems))
    return "\n".join(lines) + "\n"


def _section(heading: str, rows: Sequence[str]) -> list[str]:
    """One block: a blank line, its heading, and its rows indented under it.

    The same shape as ``spec._section``, and empty prints ``none`` for the same reason: a section
    a reader cannot find is indistinguishable from a section that does not exist.
    """
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]


def _pack_lines(report: ValidationReport) -> list[str]:
    """What was asked about and where it was found, with each label padded to a fixed width."""
    return [
        f"{'pack:':<12}{_escape(report.pack)}",
        f"{'version:':<12}{_escape(report.version or 'not found')}",
        f"{'directory:':<12}{_escape(report.directory or 'not found on the pack search path')}",
        f"{'files':<12}{len(report.checked)}",
    ]


def _error_lines(errors: Iterable[SchemaError], indent: str) -> list[str]:
    """One line per disagreement, its sub-errors indented two spaces further beneath it.

    The file is named on every **top-level** line rather than grouped under a heading per file. A
    person reading a failure copies one line into an editor, and a line naming only a pointer
    sends them looking upward for the file it belongs to.

    A sub-error's line drops the file and keeps the pointer. The file is the parent's, three lines
    of ten repeating one path is noise a reader has to look past, and the pointer stays because a
    sub-error can sit deeper in the document than the branch that carries it.
    """
    lines: list[str] = []
    for error in errors:
        located = f"{_escape(error.file)}  " if not indent else ""
        lines.append(
            f"{indent}{located}{_escape(error.pointer)}  "
            f"{_escape(error.keyword)}  {_escape(error.message)}"
        )
        lines += _error_lines(error.context, f"{indent}  ")
    return lines


def _problem_lines(problems: Sequence[Problem]) -> list[str]:
    """One line per problem, its code first, with its named facts under it."""
    lines: list[str] = []
    for problem in problems:
        lines.append(f"{int(problem.code)}  {_escape(problem.message)}")
        lines += [
            f"    {_escape(key)}: {_escape(problem.detail[key])}" for key in sorted(problem.detail)
        ]
    return lines


# ---------------------------------------------------------------------------------------------
# The JSON form
# ---------------------------------------------------------------------------------------------


def render_json(report: ValidationReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``.

    An explicit projection rather than a walk over the dataclasses, for the reason
    ``spec.render_json`` gives: adding a field to a record must not silently add a key whose type
    nobody chose.

    ``ensure_ascii=True``, matching every other form this tool prints: a pack file name comes off a
    filesystem where a name need not be valid UTF-8, and under ``ensure_ascii`` a surrogate escape
    encodes cleanly instead of raising out of the encoder.

    Nothing is passed through ``_escape``, exactly as in ``spec.render_json``: that helper stops a
    name forging a *line*, and this document has no lines to forge.
    """
    payload = {
        "pack": report.pack,
        "directory": report.directory,
        "version": report.version,
        "checked": list(report.checked),
        "errors": [_json_error(error) for error in report.errors],
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


def _json_error(error: SchemaError) -> dict[str, object]:
    """One disagreement as an object, carrying its sub-errors in the same shape.

    ``context`` is always present and is an empty list when there is none, rather than being
    omitted. A consumer then reads one shape for every error instead of branching on whether a key
    is there, and an empty list says what the record says: this error has no sub-errors.
    """
    return {
        "file": error.file,
        "pointer": error.pointer,
        "keyword": error.keyword,
        "message": error.message,
        "context": [_json_error(sub) for sub in error.context],
    }


#: The formats ``validate --format`` offers, in the order they are offered. ``cli.build_parser``
#: writes the same two names as a literal, for the reason ``report.RENDERERS`` records: ``cli`` may
#: not import this module. A test asserts the two agree.
RENDERERS: Mapping[str, Callable[[ValidationReport], str]] = {
    "text": render_text,
    "json": render_json,
}
