"""``periplus spec``: what it publishes, what it refuses to claim, and what it must not vary with.

Four properties are tested here and each one gets the cheapest tier that can answer it. Whether the
contract is emitted whole is a question about bytes and is answered in this process. Whether it is
emitted identically from two directories under two locales is a question about a process's
environment and needs two of them. Whether it reaches a user at all is a question about packaging
and needs a real install, which is the one test here that builds a virtualenv.

The fifth-gap test is the sharp one and it is deliberately not a claim in a docstring: it copies
the shipped contract into a temporary directory, appends a bullet to ``spec/rules.md``, and asserts
the new gap comes out. That is only testable because ``describe_contract`` takes the contract
directory as an argument rather than reaching for the package's own — the same reason ``resolve()``
takes ``start``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_packaging import PROJECT_ROOT, UV, _run_or_fail, _scripts_dir

from periplus.errors import ExitCode
from periplus.manifest import resolve_pack_order
from periplus.packs import PackRoot, discover_candidates, match_pins
from periplus.spec import (
    ContractDocument,
    InheritedVocabulary,
    contract_root,
    describe_contract,
    read_contract,
    render_json,
    render_text,
    render_text_summary,
    spec,
)

SRC = PROJECT_ROOT / "src"
SHIPPED_CONTRACT = SRC / "periplus" / "contract"

#: The bundled packs whose manifests declare ``depends: []``: four of the five;
#: ``drupal`` is the fifth and is the counter-case, not an omission — it declares two dependencies,
#: so it is the pack whose inherited vocabulary must come back unread rather than empty.
INDEPENDENT_PACKS = ("go", "php", "twig", "yaml")

#: A settings file that will not parse. ``ruamel.yaml`` at ``typ='safe'`` is YAML 1.2 and refuses a
#: duplicate key where PyYAML would keep the last value, so this is unreadable by construction
#: rather than by a syntax error somebody hopes is still a syntax error next release.
UNREADABLE_SETTINGS = "periplus_version: 0\nperiplus_version: 1\n"

#: One more bullet for ``## Still open``, in the shape the four already there are written in.
FIFTH_GAP = (
    "- **Provenance.** Nothing says which pack contributed a node when two packs contribute\n"
    "  rules to one type, and a map is reviewed in a pull request by people who need to know.\n"
)

_CHILD = """
import os, sys
from pathlib import Path

from periplus.spec import RENDERERS, spec

sys.stdout.write(RENDERERS[sys.argv[2]](spec(Path.cwd(), os.environ, (), sys.argv[1] or None)))
"""


@pytest.fixture
def contract(tmp_path: Path) -> Path:
    """A writable copy of the shipped contract, so a test can edit a document and re-read it."""
    target = tmp_path / "contract"
    shutil.copytree(SHIPPED_CONTRACT, target)
    return target


@pytest.fixture
def elsewhere(tmp_path: Path) -> Iterator[tuple[Path, dict[str, str]]]:
    """A directory that is not a project, and an environment whose user layer is empty.

    ``PERIPLUS_CONFIG_DIR`` is set rather than left to ``platformdirs``, so the machine running
    this suite cannot contribute a settings file or a pack of its own and change what is on the
    search path. Without it these tests would pass or fail according to what is in the developer's
    home directory.
    """
    start = tmp_path / "elsewhere"
    start.mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    yield start, {"PERIPLUS_CONFIG_DIR": str(config)}


def _shipped(name: str) -> str:
    """One shipped contract document's text, read from the working tree."""
    return (SHIPPED_CONTRACT / name).read_text(encoding="utf-8")


def _titles(documents: Path) -> list[str]:
    """Every open question a contract directory states, as ``document: title`` pairs."""
    report = describe_contract(documents, "0.0.0")
    return [f"{gap.document}: {gap.title}" for gap in report.gaps]


def test_the_command_publishes_every_shipped_document_whole_and_unaltered() -> None:
    """``periplus spec`` emits the four schemas and the two specs, byte for byte, out of the
    package.

    Whole and unaltered is the property, and it is not "the output mentions them". A pack author —
    a model, in the case this command exists for — writes a ``pack.yaml`` against
    ``pack-manifest.schema.json``'s actual ``properties`` block, so an output that summarised it,
    re-indented it or truncated it would be a contract nobody reviewed standing in for one somebody
    did.

    Read through ``contract_root()``, which is ``importlib.resources``, and compared against the
    working tree. That comparison is what ``tests/test_contract.py`` already makes against a real
    install; here it establishes that the *command* carries what the *package* holds, so the two
    together say that what a user runs emits what was reviewed.
    """
    report = describe_contract(contract_root(), "0.1.0")
    emitted = render_text(report)

    assert [document.path for document in report.documents] == [
        "schema/map.schema.json",
        "schema/pack-file.schema.json",
        "schema/pack-manifest.schema.json",
        "schema/project-settings.schema.json",
        "spec/engine.md",
        "spec/rules.md",
    ]
    for document in report.documents:
        assert document.text == _shipped(document.path), document.path
        assert document.text in emitted, f"{document.path} is named but not emitted in full"


def test_the_output_carries_the_two_rule_relationships_and_the_reads_mechanism() -> None:
    """The distinction a pack author cannot write a complementary rule without.

    ``supplementary``/``complementary`` is the whole of rule ordering, and ``reads: file`` versus
    ``reads: map`` is the mechanism that makes it decidable. This is the one thing the requirement
    names by name, so it is asserted by name.

    It is not a duplicate of the test above. That one says the file that carries this is emitted
    whole; this one says the file still carries it. Delete rule 2 from ``rules.md`` and that test
    stays green — the document is emitted, whatever is left of it — and this one fails.
    """
    emitted = render_text(describe_contract(contract_root(), "0.1.0"))

    for phrase in ("supplementary", "complementary", "reads: file", "reads: map"):
        assert phrase in emitted, f"the contract no longer publishes {phrase!r}"


def test_no_pack_named_reads_nothing_outside_the_installed_package(
    tmp_path: Path, elsewhere: tuple[Path, dict[str, str]]
) -> None:
    """``periplus spec`` alone touches no settings file, and ``periplus spec php`` does.

    Both halves in one test, because the first is worthless alone. A settings file that cannot be
    parsed is planted at the project root above the working directory; if ``spec`` reads it, the
    run reports it and exits 4. The no-pack run exits 0 with no problems, which is the property.

    The second half is what makes that a fact rather than a fixture that never worked: the same
    file, the same directory, the same environment, with a pack named — and the run *does* report
    it. So the first assertion is about a settings file that was genuinely there and genuinely
    unreadable, not about one the fixture failed to put on the path.
    """
    start, env = elsewhere
    marker = start / ".periplus"
    marker.mkdir()
    (marker / "settings.yml").write_text(UNREADABLE_SETTINGS, encoding="utf-8")

    published = spec(start=start, env=env, dependencies=(), requested=None)
    with_a_pack = spec(start=start, env=env, dependencies=(), requested="php")

    assert published.problems == ()
    assert published.exit_code is ExitCode.OK
    assert ExitCode.UNREADABLE_SETTINGS in [problem.code for problem in with_a_pack.problems], (
        "the planted settings file was not read even when a pack was named, so the run above "
        "proves nothing about what `spec` declines to read"
    )


@pytest.mark.parametrize("pack", [None, *INDEPENDENT_PACKS])
def test_a_pack_that_depends_on_nothing_inherits_an_empty_vocabulary_and_exits_zero(
    pack: str | None, elsewhere: tuple[Path, dict[str, str]]
) -> None:
    """Over the four independent bundled packs and over no pack at all.

    An empty inherited vocabulary is an *answer* here rather than a placeholder: a pack whose
    manifest declares no ``depends`` has an empty dependency closure, so the union of what it
    inherits is empty by arithmetic. Nothing has to read a rule file to know that, which is why
    this case can be answered today and ``drupal`` cannot.
    """
    start, env = elsewhere

    report = spec(start=start, env=env, dependencies=(), requested=pack)

    assert report.exit_code is ExitCode.OK, [problem.message for problem in report.problems]
    assert report.inherited == InheritedVocabulary(node_types=(), edge_kinds=())
    assert report.documents, "the contract was not published"


def test_a_pack_that_declares_dependencies_reports_them_and_refuses_to_claim_it_read_them(
    elsewhere: tuple[Path, dict[str, str]],
) -> None:
    """``drupal`` depends on two packs, so its inherited vocabulary is unread rather than empty.

    This is the counter-case that keeps the test above honest. Without it, ``_inherited`` could
    return the empty vocabulary unconditionally — a stub that says every pack inherits nothing —
    and every assertion above would still pass.

    ``depends`` and ``inherits_from`` are asserted separately because they are different facts:
    the first is what the manifest declares, the second is what the walk actually reached.
    """
    start, env = elsewhere

    report = spec(start=start, env=env, dependencies=(), requested="drupal")

    assert report.exit_code is ExitCode.OK, [problem.message for problem in report.problems]
    assert report.pack is not None
    assert report.pack.depends == ("php", "yaml")
    assert report.pack.inherits_from == ("php", "yaml")
    assert report.inherited is None, (
        "no reader opens a pack's rule files, so a non-empty dependency closure cannot yet be "
        "resolved into node types and edge kinds, and claiming it is empty would be false"
    )


def test_a_fifth_open_question_added_to_a_shipped_document_is_published_with_no_code_change(
    contract: Path,
) -> None:
    """The gaps are read out of the Markdown every run, and are written down nowhere in the engine.

    The test edits a shipped document. That is the point: a fifth bullet is appended to
    ``rules.md``'s ``## Still open`` section and the same code, unchanged, publishes five gaps from
    that document where it published four. A tuple of gap titles in Python would pass every other
    assertion in this file and fail this one.

    The four named here are asserted present first, so that a parser which found nothing
    at all could not satisfy the "one more than before" comparison by going from zero to one.
    """
    before = _titles(contract)

    assert "spec/rules.md: Cardinality" in before
    assert "spec/rules.md: Descriptions" in before
    assert "spec/rules.md: Addressing inside a data file" in before
    assert "spec/rules.md: Resolution" in before

    rules = contract / "spec" / "rules.md"
    rules.write_text(rules.read_text(encoding="utf-8") + FIFTH_GAP, encoding="utf-8")
    after = _titles(contract)

    assert after == [*before, "spec/rules.md: Provenance"]
    assert "Nothing says which pack contributed a node" in render_text(
        describe_contract(contract, "0.0.0")
    )


class _ReverseListing:
    """A ``Traversable`` over a real directory that lists its entries in reverse name order.

    Not a mock of the walk: every call it answers is answered by the filesystem, and the one thing
    it changes is the order ``iterdir`` hands entries back in. That is the thing a package's own
    ``Traversable`` gives no guarantee about — on ext4 with hashed directories it is arbitrary —
    and the only way to observe it from a test is to choose it.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def name(self) -> str:
        return self._path.name

    def is_dir(self) -> bool:
        return self._path.is_dir()

    def iterdir(self) -> list[_ReverseListing]:
        entries = sorted(self._path.iterdir(), key=lambda entry: entry.name, reverse=True)
        return [_ReverseListing(entry) for entry in entries]

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._path.read_text(encoding=encoding)


def test_the_contract_comes_out_in_path_order_whatever_order_the_package_lists_it_in(
    contract: Path,
) -> None:
    """The documents are sorted by path, and the sort is observable rather than coincidental.

    The listing that reaches this output is the one place filesystem order could — and a
    byte-comparison of two runs on one machine cannot see it, because one machine lists one
    directory the same way twice. So the order is chosen instead: the same tree is read through a
    ``Traversable`` that lists in reverse, and the result has to be identical.

    Deleting the ``sorted()`` in ``read_contract`` fails this test on any filesystem, because the
    order it reads the tree in is chosen here rather than observed. It failed three others when it
    was deleted — the whole-document test above, the fifth-gap test, and
    ``test_a_document_with_no_open_section_contributes_no_gaps`` — and that is this checkout's luck
    rather than coverage: those three assert against whatever ``iterdir`` hands back, which on this
    ext4 directory happens to be ``schema/map, schema/project-settings, schema/pack-file,
    schema/pack-manifest, spec/rules, spec/engine`` and on another machine may already be path
    order. This is the one that cannot pass with the sort gone.
    """
    forwards = read_contract(contract)
    backwards = read_contract(_ReverseListing(contract))  # type: ignore[arg-type]

    assert backwards == forwards
    assert [document.path for document in forwards] == sorted(
        document.path for document in forwards
    )
    assert len(forwards) == 6, "the fixture is not the shipped contract"


def _emit_in_a_child(cwd: Path, config: Path, fmt: str, pack: str, **overrides: str) -> str:
    """Emit in a fresh interpreter, so hash seed, locale and working directory are this call's."""
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PERIPLUS_CONFIG_DIR": str(config),
        **overrides,
    }
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _CHILD, pack, fmt],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    return result.stdout


@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("pack", ["drupal", "nope"])
def test_two_processes_from_two_directories_under_two_locales_emit_the_same_bytes(
    tmp_path: Path, fmt: str, pack: str
) -> None:
    """The same bytes from two directories under two locales, built so that a set reaching the
    output would break it.

    Two operating-system processes, because two calls inside one pytest process share one hash
    seed, one locale and one dict ordering by construction — a byte-comparison of those cannot
    fail for the reason its name gives. The same argument ``test_report.py`` records.

    The two packs are chosen for what they put a set through, not for coverage:

    * ``drupal`` declares two dependencies, and both ``depends`` and ``inherits_from`` are built
      from a set of pack names and printed. Drop either ``sorted()`` and the two names come out in
      hash-seed order.
    * ``nope`` is on no search path, so the problem it produces lists every pack name that *is*
      there — five of them, out of a set, printed as one line.

    The seeds are 0 and 2, the pair ``test_report.py`` verified distinguishes a small set of short
    names; the locale is one installed on this machine rather than a hypothetical one. Two seeds
    are two samples and not a proof.
    """
    config = tmp_path / "userconf"
    config.mkdir()
    here = tmp_path / "here"
    there = tmp_path / "there" / "deeper"
    here.mkdir()
    there.mkdir(parents=True)

    first = _emit_in_a_child(here, config, fmt, pack, PYTHONHASHSEED="0", LC_ALL="C")
    second = _emit_in_a_child(there, config, fmt, pack, PYTHONHASHSEED="2", LC_ALL="C")
    third = _emit_in_a_child(there, config, fmt, pack, PYTHONHASHSEED="0", LC_ALL="es_ES.utf8")

    assert first == second
    assert first == third


def test_a_pack_name_no_directory_carries_exits_fifteen_and_names_what_is_there(
    elsewhere: tuple[Path, dict[str, str]],
) -> None:
    """A misspelled pack is a refusal with its own status, and the contract is published anyway.

    Published anyway because the contract does not depend on the pack: a person who mistyped a
    name still gets the schemas they asked for, and the status is what tells them the pack half of
    their question went unanswered. Exit 0 here would say a pack exists that does not.

    ``available`` lists what is on the path rather than guessing what was meant, which is the call
    ``manifest._unmatched`` already makes: a rule that decides ``twigg`` meant ``twig`` will one
    day decide it meant ``php``.
    """
    start, env = elsewhere

    report = spec(start=start, env=env, dependencies=(), requested="twigg")

    assert report.exit_code is ExitCode.PACK_UNKNOWN
    assert report.pack is not None
    assert report.pack.requested == "twigg"
    assert report.pack.directory is None
    assert report.inherited is None
    assert report.documents, "a bad pack name suppressed the contract"
    problem = next(p for p in report.problems if p.code is ExitCode.PACK_UNKNOWN)
    assert problem.detail["available"] == (
        "drupal, drupal_basic, go, go_basic, laravel_basic, php, php_basic, twig, twig_basic, "
        "yaml, yaml_basic"
    )


def test_the_json_form_carries_the_documents_and_keeps_unread_apart_from_empty(
    elsewhere: tuple[Path, dict[str, str]],
) -> None:
    """A consumer parsing ``--format json`` reads the documents whole, and can tell the two apart.

    ``null`` and an object of empty arrays are different facts and this is where a consumer meets
    them: ``php`` inherits nothing and says so with a value, ``drupal``'s vocabulary has not been
    read and says so with an absence. A single shape for both would make a consumer read "unread"
    as "empty", which is the failure this whole record is arranged to prevent.
    """
    start, env = elsewhere

    independent = json.loads(render_json(spec(start, env, (), "php")))
    dependent = json.loads(render_json(spec(start, env, (), "drupal")))

    assert independent["inherited"] == {"node_types": [], "edge_kinds": []}
    assert dependent["inherited"] is None
    assert {document["path"] for document in independent["documents"]} == {
        "schema/map.schema.json",
        "schema/pack-file.schema.json",
        "schema/pack-manifest.schema.json",
        "schema/project-settings.schema.json",
        "spec/engine.md",
        "spec/rules.md",
    }
    for document in independent["documents"]:
        assert document["text"] == _shipped(document["path"]), document["path"]


def test_the_spec_format_choices_are_exactly_the_renderers_the_spec_module_offers() -> None:
    """``spec --format``'s choices and ``spec.RENDERERS`` name the same two formats, in order.

    Two constants for the reason the ``status`` version of this test records: ``cli`` may not
    import ``periplus.spec``, which reaches ``ruamel.yaml`` through ``report``, so the console
    script would die of an ``ImportError`` before the dependency check that exists to name it.

    Asserted through the parser's behaviour as well as its declaration, so that "these are the
    accepted values" is said as well as "these are the declared ones".
    """
    from periplus.cli import build_parser
    from periplus.spec import RENDERERS

    parser = build_parser()
    # argparse internals, for the reason the `status` test gives: there is no public way to read a
    # subparser's declared choices back, and this is the tie the duplicated constant needs.
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(action for action in subcommands.choices["spec"]._actions if action.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(RENDERERS) == ("text", "json")
    assert fmt.default == next(iter(RENDERERS))
    for name in RENDERERS:
        assert parser.parse_args(["spec", "--format", name]).format == name
    assert parser.parse_args(["spec"]).pack is None
    assert parser.parse_args(["spec", "php"]).pack == "php"


@pytest.mark.slow
def test_the_contract_is_publishable_out_of_an_installed_wheel(tmp_path: Path) -> None:
    """End to end: the installed console script publishes the contract from anywhere.

    Not editable, and run from a working directory nowhere near the project, for the reason
    ``tests/test_contract.py`` gives: ``uv pip install -e .`` leaves the package pointing at
    ``src/periplus``, and every read would come back out of the working tree while the wheel could
    be shipping nothing at all.

    ``PERIPLUS_CONFIG_DIR`` points at a directory that does not exist and the working directory is
    not a project, so there is no settings file and no pack root anywhere except the install's own.
    A run that needed either would have nothing to find; this one exits 0 and prints the contract,
    which is what "without reading anything outside the installed package" means for a person.
    """
    if UV is None:
        pytest.fail("uv is not on PATH, so the contract cannot be published from a real install")

    venv = tmp_path / "venv"
    _run_or_fail([UV, "venv", str(venv)], "uv venv")
    python = _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")
    _run_or_fail(
        [UV, "pip", "install", "--python", str(python), str(PROJECT_ROOT)],
        "uv pip install . (not -e)",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [str(_scripts_dir(venv) / ("periplus.exe" if os.name == "nt" else "periplus")), "spec"],
        capture_output=True,
        text=True,
        cwd=str(elsewhere),
        env={
            "PATH": os.environ.get("PATH", ""),
            "PERIPLUS_CONFIG_DIR": str(tmp_path / "no-such-directory"),
        },
        check=False,
    )

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    for phrase in ("supplementary", "complementary", "reads: file", "reads: map"):
        assert phrase in result.stdout, f"an install does not publish {phrase!r}"
    for name in ("schema/pack-file.schema.json", "spec/engine.md", "spec/rules.md"):
        assert _shipped(name) in result.stdout, f"an install does not publish {name} in full"


def test_a_document_with_no_open_section_contributes_no_gaps(tmp_path: Path) -> None:
    """The parser reads a heading it recognises and nothing else, including the schemas.

    Every contract document is offered to the gap parser, schemas included, because a rule about
    which extensions are prose is a rule that a seventh Markdown document would have to be added
    to. This is what makes that safe: a document with no open-questions heading contributes
    nothing, and one whose bullets sit under some other heading contributes nothing either.
    """
    root = tmp_path / "contract"
    root.mkdir()
    (root / "quiet.md").write_text(
        "# A document\n\n## Decided\n\n- **Not a gap.** This was settled.\n",
        encoding="utf-8",
    )
    (root / "loud.md").write_text(
        "# Another\n\n## Still open\n\n- **A gap.** This was not.\n"
        "\n## Decided\n\n- **Nor this.**\n",
        encoding="utf-8",
    )

    report = describe_contract(root, "0.0.0")

    assert report.documents == (
        ContractDocument(path="loud.md", text=(root / "loud.md").read_text(encoding="utf-8")),
        ContractDocument(path="quiet.md", text=(root / "quiet.md").read_text(encoding="utf-8")),
    )
    assert [(gap.document, gap.title, gap.text) for gap in report.gaps] == [
        ("loud.md", "A gap", "This was not.")
    ]


def test_a_heading_that_only_begins_with_open_contributes_no_gaps(tmp_path: Path) -> None:
    """The heading pattern is an address, and an address that matches too much publishes fiction.

    ``## Open source dependencies`` added to ``engine.md`` one day would have had every bullet
    under it published as a limit of the schema language, with nothing in the output saying so —
    ``^#{1,2} (?:still )?open\\b`` matched it, and matched ``## Open questions for reviewers`` and
    ``## open-ended`` too. Those three are the over-matches and they are asserted by name.

    Both sides in one test, because either alone is worthless. A pattern that matched nothing at
    all would satisfy the rejections; the two headings the shipped documents actually write are
    asserted to still be read, so tightening cannot become deleting.
    """
    root = tmp_path / "contract"
    root.mkdir()
    (root / "loose.md").write_text(
        "# A document\n\n"
        "## Open questions for reviewers\n\n- **Not a gap.** A note to a reviewer.\n\n"
        "## Open source dependencies\n\n- **Nor this.** `ruamel.yaml`, and `platformdirs`.\n\n"
        "## open-ended\n\n- **Nor this either.** A musing about scope.\n",
        encoding="utf-8",
    )
    (root / "real.md").write_text(
        "# Another\n\n"
        "## Still open\n\n- **A gap.** The heading `rules.md` writes.\n\n"
        "## Open, and deliberately not decided here\n\n"
        "- **Another gap.** The heading `engine.md` writes.\n",
        encoding="utf-8",
    )

    report = describe_contract(root, "0.0.0")

    assert [(gap.document, gap.title) for gap in report.gaps] == [
        ("real.md", "A gap"),
        ("real.md", "Another gap"),
    ]


def test_two_problems_are_printed_in_code_order_and_not_in_the_order_the_walk_found_them(
    tmp_path: Path,
) -> None:
    """``describe_contract`` sorts its problems, and one report carrying two is where that shows.

    Every other test in this file produces at most one problem, so the sort is unobservable in all
    of them. This is the pack that produces two out of order: ``a`` declares ``b`` and ``zzz``, and
    ``b`` declares ``a`` back, so the walk meets the cycle before it meets the dependency nobody
    installed and hands back ``DEPENDS_CYCLE`` then ``DEPENDS_UNMATCHED`` — 14 before 12.

    The walk's own order is asserted first, so that the report's order is being compared against a
    fixture that demonstrably produces the two backwards. Without that, a fixture that quietly
    produced one problem, or produced them already sorted, would satisfy the assertion below and
    say nothing.
    """
    root = tmp_path / "packs"
    for entry, document in (
        ("a@1.0.0", "pack: a\nversion: 1.0.0\ndepends: [b, zzz]\n"),
        ("b@1.0.0", "pack: b\nversion: 1.0.0\ndepends: [a]\n"),
    ):
        (root / entry).mkdir(parents=True)
        (root / entry / "pack.yaml").write_text(document, encoding="utf-8")
    candidates = discover_candidates(
        (
            PackRoot(
                kind="configured",
                display=str(root),
                traversable=root,
                exists=True,
                source=None,
            ),
        )
    )
    matched, _ = match_pins(["a@1.0.0"], candidates)
    _, walked = resolve_pack_order(matched, candidates)
    assert [int(problem.code) for problem in walked] == [
        ExitCode.DEPENDS_CYCLE,
        ExitCode.DEPENDS_UNMATCHED,
    ], "the fixture does not hand the walk's two problems back in the wrong order"

    report = describe_contract(contract_root(), "0.0.0", "a", candidates)

    assert [int(problem.code) for problem in report.problems] == [
        ExitCode.DEPENDS_UNMATCHED,
        ExitCode.DEPENDS_CYCLE,
    ]
    printed = render_text_summary(report)
    assert printed.index("\n  12  ") < printed.index("\n  14  ")


def _emitted(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    """One ``main()`` run's stdout, so the flag is read off the command line and not from a call."""
    from periplus.cli import main

    assert main(argv) == 0, capsys.readouterr().err
    return capsys.readouterr().out


def test_summary_drops_the_documents_bytes_and_nothing_else_in_either_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--summary`` is the summary block alone, and the whole document stays the default.

    Driven through ``main`` rather than through the renderers, because the thing that could break
    is the wiring: a flag parsed and then ignored is exactly the defect a renderer-level test
    cannot see. So the default run is asserted to still carry the documents in full, which is what
    makes "the default did not change" a measurement.

    The two forms are compared against each other rather than against a transcript. In text the
    summary has to be the bytes the whole form opens with — one function produces both, and this
    says so. In JSON the summary document has to equal the whole document with every ``text`` key
    dropped and nothing else touched, which is the strongest form of "the same report, smaller":
    a renderer that also dropped ``gaps``, renamed a key or reordered the documents fails it.
    """
    whole_text = _emitted(["spec"], capsys)
    summary_text = _emitted(["spec", "--summary"], capsys)
    whole_json = json.loads(_emitted(["spec", "--format", "json"], capsys))
    summary_json = json.loads(_emitted(["spec", "--summary", "--format", "json"], capsys))

    shipped = describe_contract(contract_root(), "0.0.0")
    assert whole_text.startswith(summary_text)
    for document in shipped.documents:
        assert document.path in summary_text, f"{document.path} is not named in the summary"
        assert document.text in whole_text, f"{document.path} is not emitted whole by default"
        assert document.text not in summary_text, f"{document.path} is carried by the summary"
    # Every block the flag promises, named. Without this a summary that quietly stopped printing
    # the open questions passes every other assertion here — measured, by deleting that line.
    for block in (
        "Contract documents:",
        "Pack:",
        "Inherited vocabulary:",
        "Not yet expressible:",
        "Problems:",
    ):
        assert block in summary_text, f"the summary has no {block!r} block"
    for gap in shipped.gaps:
        assert gap.text in summary_text, f"the summary drops the {gap.title!r} open question"

    assert summary_json == {
        **whole_json,
        "documents": [{"path": document["path"]} for document in whole_json["documents"]],
    }
    assert summary_json["gaps"], "the summary form carries no gaps, which is what it exists for"
    assert len(summary_text) < len(whole_text) // 10
