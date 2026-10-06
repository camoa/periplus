"""Reading a pack manifest, and walking `depends` into an order.

Two tiers, and each behaviour is tested at the cheapest one that can see it.

Reading a manifest is a question about bytes on disk, so every reading test writes a real file
under `tmp_path` and reads it back — there is no cheaper tier, because a parser refusal and a
decode failure are only true of real bytes. The one exception reads the *bundled* drupal manifest
instead of a written fixture: what a shipped pack declares is a fact about the file that ships, and
a fixture asserting it would only confirm what the fixture itself wrote.

Walking `depends` is a question about a graph, and every graph here is built out of real pack
directories under `tmp_path` rather than out of constructed records. That is one tier up from
constructing `LoadedPack` values by hand, and it is bought deliberately: the walk resolves a name
to a directory and then opens the file inside it, so a test that hands it pre-loaded packs would
skip the half of the function where a name becomes a file.

The fixtures are written packs, never edits to the five that ship. A cycle or a missing dependency
introduced into a bundled pack would be a change to the product to suit a test, and the bundled
five are read by four other suites.

`pack.yaml` is spelled out in `_write_pack` rather than taken from `MANIFEST_FILENAME`. A fixture
that names the file the way the module names it agrees with the module whatever either is renamed
to, and the name is a fact about the pack format rather than an internal detail.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import pytest

from periplus.errors import ExitCode
from periplus.manifest import (
    LoadedPack,
    ManifestUnreadable,
    load_manifest,
    resolve_pack_order,
)
from periplus.packs import PACKS_DIRECTORY, PackRoot, discover_candidates, match_pins


def _pack_root(directory: Path) -> PackRoot:
    """A root record for a directory a test built.

    Constructed rather than produced by `resolve_pack_roots`, which would put the bundled root on
    the search path beside the fixture and let the five shipped packs answer a fixture's `depends`.
    Everything below the root is real: `discover_candidates` lists it, parses the names and
    classifies the entries exactly as it does for an installed root.
    """
    return PackRoot(
        kind="project",
        display=str(directory),
        traversable=directory,
        exists=directory.is_dir(),
        source=None,
    )


def _write_pack(root: Path, entry: str, manifest: str | None) -> Path:
    """One pack directory under `root`, with the given `pack.yaml` or with none at all."""
    directory = root / entry
    directory.mkdir(parents=True)
    if manifest is not None:
        (directory / "pack.yaml").write_text(manifest, encoding="utf-8")
    return directory


def _manifest(pack: str, depends: str = "[]") -> str:
    """The smallest manifest that declares an identity and a dependency list."""
    return f"pack: {pack}\nversion: 0.1.0\ndepends: {depends}\n"


def _resolve(
    root: Path, *pins: str
) -> tuple[tuple[LoadedPack, ...], tuple[tuple[ExitCode, str], ...]]:
    """Discover, match the pins and walk, the way a caller would. Problems as code and pack name.

    The problems come back as `(code, detail["pack"])` pairs rather than as records, because those
    two are the facts a caller acts on and the message is prose that may be reworded. A cycle
    carries no `pack` key and comes back with its `cycle`.
    """
    candidates = discover_candidates((_pack_root(root),))
    matched, _ = match_pins(list(pins), candidates)
    order, problems = resolve_pack_order(matched, candidates)
    return order, tuple(
        (problem.code, problem.detail.get("pack") or problem.detail["cycle"])
        for problem in problems
    )


def _bundled_pack(entry: str) -> Path:
    """One pack directory inside the installed package, reached the way the harness reaches it."""
    directory = importlib.resources.files("periplus") / PACKS_DIRECTORY / entry
    return Path(str(directory))


def test_the_bundled_drupal_manifest_reads_back_what_the_shipped_file_declares() -> None:
    """A real manifest, transcribed from the pack that ships rather than from a fixture.

    Two claims in one, because they are the two halves of "reader": the fields this module names
    come back typed, and the blocks it does not name survive in `document`. The second is what the
    consumers this reader exists for — `periplus spec`, framework detection — will read, and a
    reader that parsed a manifest and kept only three keys would pass every other test here.
    """
    manifest = load_manifest(_bundled_pack("drupal@0.1.0"))

    assert manifest.pack == "drupal"
    assert manifest.version == "0.1.0"
    assert manifest.depends == ("php", "yaml")
    assert manifest.document["folders"] == {
        "config": "./config/sync",
        "custom_module": "./web/modules/custom",
        "custom_theme": "./web/themes/custom",
        "module_config": "{custom_module}/*/config/install",
    }
    assert "boundary" in manifest.document


def test_a_pack_directory_with_no_manifest_is_refused_rather_than_read_as_empty(
    tmp_path: Path,
) -> None:
    """A directory named like a pack with nothing inside it is not a pack with no dependencies.

    The distinction is the whole reason `missing` is a cause rather than being folded into `read`:
    an empty `depends` and an absent file would otherwise be the same answer, and the second one
    means somebody's pack never got written.
    """
    directory = _write_pack(tmp_path, "alpha@0.1.0", None)

    with pytest.raises(ManifestUnreadable) as raised:
        load_manifest(directory)

    assert raised.value.problem().code is ExitCode.UNREADABLE_MANIFEST
    assert raised.value.detail["cause"] == "missing"


def test_a_manifest_that_will_not_parse_is_refused_rather_than_partially_read(
    tmp_path: Path,
) -> None:
    """Bytes the parser rejects produce no manifest at all, not a manifest of whatever parsed."""
    directory = _write_pack(tmp_path, "alpha@0.1.0", "pack: alpha\ndepends: [unclosed\n")

    with pytest.raises(ManifestUnreadable) as raised:
        load_manifest(directory)

    assert raised.value.detail["cause"] == "parser"


def test_a_duplicate_key_is_refused_rather_than_silently_keeping_the_last_value(
    tmp_path: Path,
) -> None:
    """The YAML 1.2 property `ruamel` is in this project for, asserted on a manifest.

    Under PyYAML this file loads with `pack: beta` and no complaint, so a pack that declares itself
    twice would resolve as whichever declaration came last. It is a separate test from the
    unparseable one because it is a separate guarantee: those bytes are well-formed YAML 1.1.
    """
    directory = _write_pack(tmp_path, "alpha@0.1.0", "pack: alpha\npack: beta\nversion: 0.1.0\n")

    with pytest.raises(ManifestUnreadable) as raised:
        load_manifest(directory)

    assert raised.value.detail["cause"] == "parser"


def test_the_parser_refuses_to_construct_an_arbitrary_object(tmp_path: Path) -> None:
    """A `!!python/object/apply:` tag in a `pack.yaml` is exit 11, not a call.

    `tests/test_settings.py` pins this same property for a settings file. It is pinned again here
    because the two files have different authors: a person writes their own settings, and a
    `pack.yaml` arrives from whoever wrote the pack — so this is the file where a construction tag
    is a third party's code running on somebody's machine. Nothing else in this suite reaches the
    property. The duplicate key above is YAML 1.2, which `rt` satisfies as well, so a `typ`
    loosened to `rt` or to `unsafe` would leave every other test in this file passing and open
    exactly this.

    The command the tag would run is `touch`, and its file is asserted absent as well as the load
    refused. The refusal is what the reader does; not running the command is the property, and only
    the second is still true of a loader that constructs the object and then fails on something
    after it.
    """
    evidence = tmp_path / "constructed"
    directory = _write_pack(
        tmp_path,
        "alpha@0.1.0",
        f'pack: !!python/object/apply:os.system ["touch {evidence}"]\nversion: 0.1.0\n',
    )

    with pytest.raises(ManifestUnreadable) as raised:
        load_manifest(directory)

    assert raised.value.problem().code is ExitCode.UNREADABLE_MANIFEST
    assert raised.value.detail["cause"] == "parser"
    assert "constructor" in raised.value.detail["detail"]
    assert not evidence.exists()


@pytest.mark.parametrize(
    ("body", "shape"),
    [("", "NoneType"), ("- alpha\n- beta\n", "list"), ("alpha\n", "str")],
    ids=["empty", "list", "scalar"],
)
def test_a_document_that_is_not_a_mapping_is_refused(tmp_path: Path, body: str, shape: str) -> None:
    """Three files that are valid YAML and are not manifests, refused as one cause.

    An empty `pack.yaml` is the interesting one: it is the file somebody creates and has not filled
    in, and loading it as a manifest with every field absent would let a half-written pack take part
    in a dependency graph.
    """
    directory = _write_pack(tmp_path, "alpha@0.1.0", body)

    with pytest.raises(ManifestUnreadable) as raised:
        load_manifest(directory)

    assert raised.value.detail["cause"] == "shape"
    assert raised.value.detail["detail"] == shape


@pytest.mark.parametrize(
    "declared",
    ["", "depends: []\n", 'depends: "php"\n', "depends: {php: 1}\n", "depends: [php, 3]\n"],
    ids=["absent", "empty", "string", "mapping", "mixed"],
)
def test_a_depends_that_is_not_a_list_of_strings_contributes_nothing(
    tmp_path: Path, declared: str
) -> None:
    """No dependency is read out of a `depends` that is not the declared shape.

    `depends: "php"` is the case that matters. A string is a sequence, so a reader that took it at
    face value would produce three dependencies named `p`, `h` and `p` — the tuple-of-characters
    failure `settings.py` names. The remaining shapes are refused for the same reason and none of
    them is coerced into something plausible.
    """
    directory = _write_pack(tmp_path, "alpha@0.1.0", f"pack: alpha\nversion: 0.1.0\n{declared}")

    assert load_manifest(directory).depends == ()


def test_an_identity_that_is_not_two_strings_is_absent_rather_than_coerced(
    tmp_path: Path,
) -> None:
    """A missing `pack` and an unquoted `version` are `None`, which is what the file says.

    `version: 0.1.0` is a string only because it has two dots; written `0.1` it is a float, and a
    reader that called `str()` on it would report a version nobody typed. The manifest schema
    requires both keys and constrains both patterns — `required` is line 9 of
    `pack-manifest.schema.json` — and enforcing that is the validator's, not this module's.
    """
    directory = _write_pack(tmp_path, "alpha@0.1.0", "version: 0.1\ndepends: []\n")

    manifest = load_manifest(directory)

    assert manifest.pack is None
    assert manifest.version is None


def test_a_pinned_pack_comes_after_every_pack_it_depends_on() -> None:
    """The bundled graph, walked: drupal depends on php and yaml, and arrives last.

    Read off the shipped packs rather than a fixture, so the headline behaviour is proved against
    the only real dependency graph this project has.
    """
    root = _pack_root(Path(str(importlib.resources.files("periplus") / PACKS_DIRECTORY)))
    candidates = discover_candidates((root,))
    matched, _ = match_pins(["drupal@0.1.0"], candidates)

    order, problems = resolve_pack_order(matched, candidates)

    assert problems == ()
    assert [pack.name.pack for pack in order] == ["php", "yaml", "drupal"]


def test_the_order_does_not_depend_on_the_order_the_inputs_arrive_in(tmp_path: Path) -> None:
    """Two calls over one graph, with the arguments reversed, produce the same sequence.

    Determinism is a stated property of this project, and the two places
    it could leak in here are the order candidates were discovered in and the order the pins were
    written in. Reversing both at once is the check: a walk that followed either would come back
    reordered, and the assertion is against the first call's own answer rather than a list written
    out here, so it cannot pass by agreeing with a hardcoded expectation.

    `zeta` is pinned and depends on nothing, which is what makes the pin order observable at all.
    With every pinned pack inside one connected graph, the walk reaches the same packs in the same
    order whichever pin it starts from, and reversing the list changes nothing — a fixture that
    cannot fail is the version of this test that shipped first.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[beta, gamma]"))
    _write_pack(tmp_path, "beta@0.1.0", _manifest("beta", "[delta]"))
    _write_pack(tmp_path, "gamma@0.1.0", _manifest("gamma", "[delta]"))
    _write_pack(tmp_path, "delta@0.1.0", _manifest("delta"))
    _write_pack(tmp_path, "zeta@0.1.0", _manifest("zeta"))
    candidates = discover_candidates((_pack_root(tmp_path),))
    matched, _ = match_pins(["alpha@0.1.0", "delta@0.1.0", "zeta@0.1.0"], candidates)

    forward, _ = resolve_pack_order(matched, candidates)
    backward, _ = resolve_pack_order(tuple(reversed(matched)), tuple(reversed(candidates)))

    assert [pack.path for pack in forward] == [pack.path for pack in backward]


def test_a_pack_two_others_depend_on_appears_once_and_before_both(tmp_path: Path) -> None:
    """A diamond: every pack is emitted exactly once, and after each pack it depends on.

    Asserted as the two structural facts rather than as one expected sequence, so the test says
    what a dependency order *is* instead of restating what this implementation happens to emit —
    a different but still correct tie-break would keep this passing and would break a hardcoded
    list.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[beta, gamma]"))
    _write_pack(tmp_path, "beta@0.1.0", _manifest("beta", "[delta]"))
    _write_pack(tmp_path, "gamma@0.1.0", _manifest("gamma", "[delta]"))
    _write_pack(tmp_path, "delta@0.1.0", _manifest("delta"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0")

    assert problems == ()
    emitted = [pack.name.pack for pack in order]
    assert sorted(emitted) == ["alpha", "beta", "delta", "gamma"]
    for pack in order:
        for dependency in pack.manifest.depends:
            assert emitted.index(dependency) < emitted.index(pack.name.pack)


def test_a_depends_naming_a_pack_that_is_not_installed_is_reported_once(tmp_path: Path) -> None:
    """Two packs depending on one absent pack produce one problem, not one per dependent.

    The count is the property. A name that resolves to nothing is a settled fact about the search
    path, and repeating it per referrer would grow a report with the size of the graph rather than
    with the number of things wrong with it. Both dependents are still returned: their own
    manifests read, and withholding them would report a second failure that did not happen.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[ghost]"))
    _write_pack(tmp_path, "beta@0.1.0", _manifest("beta", "[ghost]"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0", "beta@0.1.0")

    assert problems == ((ExitCode.DEPENDS_UNMATCHED, "ghost"),)
    assert [pack.name.pack for pack in order] == ["alpha", "beta"]


def test_a_cycle_is_reported_with_the_packs_in_it_and_the_walk_still_finishes(
    tmp_path: Path,
) -> None:
    """`alpha` depends on `beta` depends on `alpha`: one problem naming the loop, and no hang.

    Both packs still come back. The back edge is the only thing dropped, so what is returned is the
    order of the graph without it — the same posture `match_pins` takes with a duplicated pin,
    where both matches are returned and the problem is what stays unresolved.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[beta]"))
    _write_pack(tmp_path, "beta@0.1.0", _manifest("beta", "[alpha]"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0")

    assert problems == ((ExitCode.DEPENDS_CYCLE, "alpha -> beta -> alpha"),)
    assert sorted(pack.name.pack for pack in order) == ["alpha", "beta"]


def test_a_pack_that_depends_on_itself_is_reported_as_a_cycle(tmp_path: Path) -> None:
    """The shortest cycle there is, and the manifest schema does not forbid it.

    `depends` items are matched against a name pattern and nothing in the schema compares them to
    the pack's own `pack:` field, so `depends: [alpha]` inside `alpha` is a document a validator
    would accept. It gets no guard of its own here — the same back-edge test finds it — and this
    test is what says so.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[alpha]"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0")

    assert problems == ((ExitCode.DEPENDS_CYCLE, "alpha -> alpha"),)
    assert [pack.name.pack for pack in order] == ["alpha"]


def test_the_emitted_order_is_the_same_for_two_ways_of_writing_one_graph(tmp_path: Path) -> None:
    """`depends: [beta, gamma]` and `depends: [gamma, beta]` are one graph and one order.

    A walk that followed the written order would emit `beta` first from one tree and `gamma` first
    from the other, so two repositories declaring the same dependencies would produce two orders —
    and a check that runs one tree twice would never see it. The two trees are
    otherwise identical, so the written list is the only variable.
    """
    forward = tmp_path / "forward"
    backward = tmp_path / "backward"
    for root, declared in ((forward, "[beta, gamma]"), (backward, "[gamma, beta]")):
        _write_pack(root, "alpha@0.1.0", _manifest("alpha", declared))
        _write_pack(root, "beta@0.1.0", _manifest("beta"))
        _write_pack(root, "gamma@0.1.0", _manifest("gamma"))

    from_forward, _ = _resolve(forward, "alpha@0.1.0")
    from_backward, _ = _resolve(backward, "alpha@0.1.0")

    assert [pack.name.pack for pack in from_forward] == [pack.name.pack for pack in from_backward]


def test_one_directory_pinned_twice_is_one_pack_and_not_a_duplicate(tmp_path: Path) -> None:
    """A `packs:` list naming the same pin twice must not manufacture a conflict.

    `match_pins` matches each pin independently, so a repeated pin comes back as two matches of one
    directory. Reading those as two directories carrying the pack name would fail the run at
    `DEPENDS_DUPLICATED` over a duplicate that exists only in the settings file.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0", "alpha@0.1.0")

    assert problems == ()
    assert [pack.name.pack for pack in order] == ["alpha"]


def test_a_pack_name_two_directories_carry_is_reported_rather_than_resolved(
    tmp_path: Path,
) -> None:
    """`depends: [php]` beside a `php@0.1.0` and a `php@0.2.0` picks neither.

    A `depends` entry carries no version, so nothing in the manifest says which of the two was
    meant, and choosing the higher one — or the first one listed — would be the harness deciding a
    version on the author's behalf and never saying so. The problem names both directories.

    The two are under two roots, and the root holding the *later* path is searched first, so the
    order the problem names them in cannot be the order they were discovered in. A report whose
    contents depend on which root came first is a determinism defect wearing a correct answer.
    """
    first = tmp_path / "b"
    second = tmp_path / "a"
    _write_pack(first, "alpha@0.1.0", _manifest("alpha", "[php]"))
    _write_pack(first, "php@0.1.0", _manifest("php"))
    _write_pack(second, "php@0.2.0", _manifest("php"))

    candidates = discover_candidates((_pack_root(first), _pack_root(second)))
    matched, _ = match_pins(["alpha@0.1.0"], candidates)
    order, problems = resolve_pack_order(matched, candidates)

    assert [problem.code for problem in problems] == [ExitCode.DEPENDS_DUPLICATED]
    assert problems[0].detail["directories"] == ", ".join(
        [str(second / "php@0.2.0"), str(first / "php@0.1.0")]
    )
    assert [pack.name.pack for pack in order] == ["alpha"]


def test_a_pin_settles_the_version_a_depends_entry_could_not(tmp_path: Path) -> None:
    """Pinning `php@0.1.0` makes `depends: [php]` resolvable where it was ambiguous.

    The rule the module states: a pin is a version somebody chose and a `depends` entry is not, so
    the pin is the only stated preference available. Same tree as the test above, one line of
    `packs:` different, and the ambiguity is gone rather than resolved silently.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[php]"))
    _write_pack(tmp_path, "php@0.1.0", _manifest("php"))
    _write_pack(tmp_path, "php@0.2.0", _manifest("php"))

    order, problems = _resolve(tmp_path, "alpha@0.1.0", "php@0.1.0")

    assert problems == ()
    assert [(pack.name.pack, pack.name.version) for pack in order] == [
        ("php", "0.1.0"),
        ("alpha", "0.1.0"),
    ]


def test_an_unreadable_manifest_beneath_a_pinned_pack_does_not_stop_the_walk(
    tmp_path: Path,
) -> None:
    """A dependency whose `pack.yaml` will not parse is one problem, and the rest still resolves.

    The pinned pack read fine and everything else beneath it read fine. A walk that raised here
    would report one broken file by returning nothing at all, which is the report shape this module
    returns `Problem` records to avoid.
    """
    _write_pack(tmp_path, "alpha@0.1.0", _manifest("alpha", "[beta, gamma]"))
    _write_pack(tmp_path, "beta@0.1.0", "pack: beta\ndepends: [unclosed\n")
    _write_pack(tmp_path, "gamma@0.1.0", _manifest("gamma"))

    candidates = discover_candidates((_pack_root(tmp_path),))
    matched, _ = match_pins(["alpha@0.1.0"], candidates)
    order, problems = resolve_pack_order(matched, candidates)

    assert [problem.code for problem in problems] == [ExitCode.UNREADABLE_MANIFEST]
    assert problems[0].detail["path"] == str(tmp_path / "beta@0.1.0" / "pack.yaml")
    assert [pack.name.pack for pack in order] == ["gamma", "alpha"]


def test_nothing_pinned_walks_nothing(tmp_path: Path) -> None:
    """With no pins there is no starting point, so no manifest is opened and nothing is reported.

    A pack directory sitting on the search path that no pin names is not a pack this run uses. The
    fixture below would raise on being read, so an implementation that walked every candidate
    rather than the pinned ones would produce a problem here instead of an empty result.
    """
    _write_pack(tmp_path, "alpha@0.1.0", "pack: alpha\ndepends: [unclosed\n")

    order, problems = _resolve(tmp_path)

    assert order == ()
    assert problems == ()
