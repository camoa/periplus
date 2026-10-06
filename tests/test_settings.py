"""Locating the two settings files, reading one, and merging them.

Every test here runs against real files in a temporary tree rather than against hand-built
documents, because three of the properties under test — which file was found, what a relative path
in it anchors to, and which file a value is attributed to — are only true of a file that exists
somewhere. A merge fed two dictionaries would pass while ``locate_settings`` reported both layers
absent, and the sources it printed would name paths nothing had read.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import platformdirs
import pytest
from jsonschema import Draft202012Validator

from periplus.errors import ExitCode
from periplus.init import initialise_project
from periplus.settings import (
    MERGE_RULES,
    FirstParty,
    ResolvedSettings,
    SettingsSource,
    SettingsUnreadable,
    SourceRef,
    find_project_root,
    load_settings_document,
    locate_settings,
    resolve_settings,
    user_config_dir,
)

#: The stub `init` ships and writes, as it sits in the source tree. Reached through the source
#: path rather than through `importlib.resources`, because this test is about the file the diff
#: reviewed; whether the packaging carries it into the wheel is `test_packaging.py`'s question.
STUB_PATH = Path(__file__).resolve().parent.parent / "src" / "periplus" / "settings.stub.yml"

#: The shipped settings schema, reached the same way and for the same reason as the stub.
SETTINGS_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "periplus"
    / "contract"
    / "schema"
    / "project-settings.schema.json"
)


def _settings_schema() -> dict[str, object]:
    """The parsed settings schema. One read, so a test never compares two parses of one file."""
    return json.loads(SETTINGS_SCHEMA_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _declared_settings_keys() -> set[str]:
    """The keys ``project-settings.schema.json`` declares, at the **top level only**.

    The schema serves as an independent copy that can disagree with ``MERGE_RULES``, and it is a
    better copy than a set of names typed into this file: it is a separate shipped artifact with a
    separate author and a separate review, and it is the document a pack author actually reads. What
    it adds is the direction a hand-typed set could never give — a key planted in the schema and
    nowhere else fails the suite. A rename applied consistently across the schema, ``MERGE_RULES``,
    ``ResolvedSettings`` and the stub needs no fourth edit here, and the schema is reviewed in a
    pull request.

    **Top level only, and never a recursive walk.** ``properties`` also appears under
    ``first_party`` and under ``accepted_unknowns.items``; a walk returns fourteen names — the nine
    settings keys plus ``include``, ``exclude``, ``id``, ``rule`` and the rest of an accepted
    unknown's fields — and would compare the merge table against the interior of two values.
    """
    properties = _settings_schema()["properties"]
    assert isinstance(properties, dict)
    return set(properties)


def _tree(
    tmp_path: Path, *, user: str | None = None, project: str | None = None
) -> tuple[Path, Path]:
    """A user configuration directory and a project root, with the settings files that were given.

    Returns both directories. A layer whose text is ``None`` has no file, which is how the "with one
    file present" and "with neither" cases are built.
    """
    user_dir = tmp_path / "userconf"
    user_dir.mkdir(parents=True)
    root = tmp_path / "repo"
    (root / ".periplus").mkdir(parents=True)
    if user is not None:
        (user_dir / "settings.yml").write_text(user, encoding="utf-8")
    if project is not None:
        (root / ".periplus" / "settings.yml").write_text(project, encoding="utf-8")
    return user_dir, root


def _resolve(
    tmp_path: Path, *, user: str | None = None, project: str | None = None
) -> tuple[ResolvedSettings, tuple[SettingsSource, ...]]:
    """Run the whole pipeline over a real tree: locate, load what exists, merge."""
    user_dir, root = _tree(tmp_path, user=user, project=project)
    sources = locate_settings(find_project_root(root), user_dir)
    documents = {
        source.kind: load_settings_document(source.path) if source.status == "used" else None
        for source in sources
    }
    return resolve_settings(documents["user"], documents["project"], sources), sources


# --------------------------------------------------------------------------------------------
# Locating
# --------------------------------------------------------------------------------------------


def test_the_project_root_is_the_nearest_directory_holding_a_periplus_directory(
    tmp_path: Path,
) -> None:
    """The walk goes up until it finds ``.periplus/``, and a file of that name is not a marker.

    A directory is the marker for the reason ``git`` looks for ``.git``: the same directory holds
    the settings file and the project's own packs, so one marker answers both questions. A file
    named ``.periplus`` is somebody's note, and treating it as a root would anchor every relative
    path in the run to a directory that holds nothing.

    The walk is lexical, so a symlinked parent gives back the symlinked path rather than the
    directory behind it. ``Path.resolve()`` would answer with the real directory, which is a path
    the person never wrote and never navigated through. Every relative path in the run anchors to
    whatever this returns, so resolving here would silently move the whole project root to a second
    location on disk.
    """
    deep = tmp_path / "repo" / "sub" / "deeper"
    deep.mkdir(parents=True)
    (tmp_path / "repo" / ".periplus").mkdir()

    assert find_project_root(deep) == tmp_path / "repo"
    assert find_project_root(tmp_path / "repo") == tmp_path / "repo"

    unmarked = tmp_path / "elsewhere"
    unmarked.mkdir()
    assert find_project_root(unmarked) is None

    (unmarked / ".periplus").write_text("not a directory\n", encoding="utf-8")
    assert find_project_root(unmarked) is None

    real = tmp_path / "real"
    (real / ".periplus").mkdir(parents=True)
    (real / "sub").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    assert find_project_root(link / "sub") == link
    assert find_project_root(link / "sub") != real


def test_the_user_config_dir_reads_the_mapping_it_is_given_and_not_the_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``PERIPLUS_CONFIG_DIR`` decides only when it is in the mapping that was passed in.

    The environment being an argument is what lets a test move the user layer with no monkeypatching
    of this module, and the assertion that keeps that honest is the second one: the variable is put
    into the *process* environment and left out of the mapping, and the mapping still wins. Without
    it, a function reading ``os.environ`` would pass the first assertion in any real shell.

    The other branch returns ``~/.config/periplus``, with exactly one ``periplus`` segment and none
    added by us. A variable named ``PERIPLUS_CONFIG_DIR`` cannot sensibly point at the directory
    holding every tool's configuration, so one function returns one level whichever branch fired.
    Appending a ``periplus`` segment to what this returns would put the file at
    ``~/.config/periplus/periplus/settings.yml``.

    What this cannot check: ``appauthor=False``, which is inert on Linux and macOS and is what stops
    Windows returning ``%APPDATA%\\periplus\\periplus``. That was read out of platformdirs' source
    rather than run.
    """
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "from-the-process"))

    assert user_config_dir({"PERIPLUS_CONFIG_DIR": str(tmp_path / "given")}) == tmp_path / "given"
    assert user_config_dir({}) != tmp_path / "from-the-process"

    resolved = user_config_dir({})

    assert resolved.name == "periplus"
    assert resolved.parent == Path(platformdirs.user_config_dir())
    assert resolved.parent.name != "periplus", "the periplus segment is doubled"


def test_both_layers_are_reported_in_cascade_order_with_a_missing_file_absent(
    tmp_path: Path,
) -> None:
    """User first, project second, and a file that is not there is ``absent`` rather than omitted.

    With a project file, a user file, and neither, the report names
    the file actually used in each case. Naming the one that was not found is the half that makes
    the third case readable — a layer left out of the list looks like a layer that does not exist.
    """
    user_dir, root = _tree(tmp_path, project="periplus_version: 0\n")

    sources = locate_settings(root, user_dir)

    assert [(source.kind, source.status) for source in sources] == [
        ("user", "absent"),
        ("project", "used"),
    ]
    assert sources[0].path == user_dir / "settings.yml"
    assert sources[1].path == root / ".periplus" / "settings.yml"
    assert all(source.reason is None for source in sources)

    # The third case. With no file at either level both layers are still named, which is
    # what lets the report say where it looked rather than printing nothing.
    bare = tmp_path / "bare"
    (bare / "repo" / ".periplus").mkdir(parents=True)
    (bare / "userconf").mkdir()
    assert [(s.kind, s.status) for s in locate_settings(bare / "repo", bare / "userconf")] == [
        ("user", "absent"),
        ("project", "absent"),
    ]


def test_each_source_carries_the_anchor_a_relative_path_in_it_resolves_against(
    tmp_path: Path,
) -> None:
    """The project file anchors to its grandparent and the user file to its parent.

    Two layers, two derivations, and carrying the answer on the record is what stops the merge
    having to remember which is which. The project file is ``<root>/.periplus/settings.yml``, so its
    root is two levels up; the user file sits directly in the configuration directory.

    ``--settings PATH`` breaks both derivations, so there the file's own position decides. A file at
    ``X/.periplus/settings.yml`` anchors to ``X``, which is how pointing at a real project's file
    gets that project's root and the two can never disagree. Any other file anchors to its own
    directory, which keeps a relative ``pack_paths`` entry beside the file that wrote it. An
    explicit root, when the caller has one, wins over both.
    """
    user_dir, root = _tree(tmp_path)

    sources = {source.kind: source for source in locate_settings(root, user_dir)}

    assert sources["project"].root == root
    assert sources["project"].root == sources["project"].path.parent.parent
    assert sources["user"].root == user_dir
    assert sources["user"].root == sources["user"].path.parent

    # The explicitly named file, whose anchor is derived from neither layer.
    inside = root / ".periplus" / "settings.yml"
    inside.write_text("periplus_version: 0\n", encoding="utf-8")
    loose = tmp_path / "elsewhere" / "periplus.yml"
    loose.parent.mkdir()
    loose.write_text("periplus_version: 0\n", encoding="utf-8")

    def _project(settings_path: Path, project_root: Path | None = None) -> SettingsSource:
        (source,) = locate_settings(project_root, None, settings_path)
        return source

    assert _project(inside).root == root
    assert _project(loose).root == tmp_path / "elsewhere"
    assert _project(loose, tmp_path / "override").root == tmp_path / "override"


def test_a_layer_with_no_locatable_file_produces_no_record_at_all(tmp_path: Path) -> None:
    """``absent`` is for a file that has a name and is not there, which is not the same as no layer.

    The user layer is not consulted at all when there is no configuration directory, and a project
    with no ``.periplus/`` anywhere above it has no project settings path to report as missing.
    Reporting a path in either case would name a file nothing ever intended to read.
    """
    assert locate_settings(None, None) == ()
    assert [source.kind for source in locate_settings(tmp_path, None)] == ["project"]
    assert [source.kind for source in locate_settings(None, tmp_path)] == ["user"]


# --------------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------------


def test_the_parser_refuses_to_construct_an_arbitrary_object(tmp_path: Path) -> None:
    """A ``!!python/object/apply:`` tag is exit 4, not a call.

    ``typ='safe'`` is chosen for two reasons, and this test covers the one nothing else in this
    file reaches: the loader has no constructor for a Python tag, so a settings file cannot reach
    ``os.system`` through the parser. The other reason is YAML 1.2 scalar rules, which ``rt``
    satisfies as well — so a ``typ`` changed to ``rt`` would leave the rest of this file passing
    and open exactly this.
    """
    path = tmp_path / "settings.yml"
    path.write_text('packs: !!python/object/apply:os.system ["echo pwned"]\n', encoding="utf-8")

    with pytest.raises(SettingsUnreadable) as raised:
        load_settings_document(path)

    assert raised.value.problem().code is ExitCode.UNREADABLE_SETTINGS
    assert "constructor" in raised.value.problem().detail["detail"]


@pytest.mark.parametrize(
    ("label", "text", "cause"),
    [
        ("malformed", "packs: [php@0.1.0,\n", "parser"),
        ("a duplicate key", "packs: [php@0.1.0]\npacks: [go@0.0.2]\n", "parser"),
        ("a bare scalar", "just a string\n", "shape"),
        ("a list", "- php@0.1.0\n- go@0.0.2\n", "shape"),
        ("empty", "", "shape"),
    ],
)
def test_a_file_that_is_not_a_settings_mapping_is_exit_four_naming_the_file(
    tmp_path: Path, label: str, text: str, cause: str
) -> None:
    """Malformed YAML, a repeated key, and valid YAML that is not a mapping are one failure.

    An empty file loads as ``None`` and a scalar or a list document loads as a ``str`` or a
    ``list``. All three parse without complaint, so the parser has no opinion about them and the
    check has to be here. Two ``packs:`` blocks in one file are the parser's own refusal reaching
    the exit table: PyYAML keeps one value and says nothing, so a person editing a long settings
    file would get a run that ignored half their edit with no output to explain it. All five reach
    a person as a named line rather than a traceback.
    """
    path = tmp_path / "settings.yml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(SettingsUnreadable) as raised:
        load_settings_document(path)

    problem = raised.value.problem()
    assert problem.code is ExitCode.UNREADABLE_SETTINGS, label
    assert str(path) in problem.message
    assert problem.detail["path"] == str(path), label
    assert problem.detail["cause"] == cause


def test_a_file_that_cannot_be_read_or_decoded_is_the_same_named_failure(tmp_path: Path) -> None:
    """Exit 4 is "could not be read **or** parsed", and both halves reach a person as a line.

    A directory where the settings file should be, and a file holding bytes that are not UTF-8, both
    fail before the parser sees anything. Left uncaught they are an ``IsADirectoryError`` and a
    ``UnicodeDecodeError`` traceback, which is what this must not be.
    """
    directory = tmp_path / "as-a-directory"
    (directory / "settings.yml").mkdir(parents=True)
    undecodable = tmp_path / "binary.yml"
    undecodable.write_bytes(b"packs: \xff\xfe\x00\n")

    for path, cause in ((directory / "settings.yml", "read"), (undecodable, "encoding")):
        with pytest.raises(SettingsUnreadable) as raised:
            load_settings_document(path)
        problem = raised.value.problem()
        assert problem.code is ExitCode.UNREADABLE_SETTINGS
        assert problem.detail["cause"] == cause
        assert str(path) in problem.message


# --------------------------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------------------------


def test_the_merge_table_names_exactly_the_keys_the_settings_schema_declares() -> None:
    """A key in the schema and nowhere else fails the suite, in this line.

    A new settings key is a row in a table and a field on the record,
    never a branch in the merge. That only holds while the table and the record agree, and a key
    with a field and no row would resolve to ``None`` in every run while looking supported.

    The expectation is read out of ``project-settings.schema.json``, which is the whole of the
    point: editing the schema alone fails here, and editing ``settings.py`` alone fails here.
    Against a hand-written set of names, planting a key in the schema failed nothing at all.

    **This is a sensitivity test and not a red.** It passes the moment it is written, because the
    schema and the merge table already agree on the same nine names. Its value is entirely in what
    it does when one of them changes.
    """
    declared = _declared_settings_keys()
    fields = {field.name for field in dataclasses.fields(ResolvedSettings)}

    assert set(MERGE_RULES) == declared
    assert fields == declared


def test_the_shipped_stub_names_every_key_the_settings_schema_declares() -> None:
    """The stub `init` writes names every key the schema declares, and declares exactly one.

    Two assertions, because either alone is satisfiable by a file that is wrong. The first reads
    the key names out of the text, so a key that was dropped from the stub fails even though the
    document still parses. The second loads the stub the way the tool loads a real settings file,
    so a key left uncommented by accident fails even though its name is present.

    The expectation now comes from the schema, which is what this test's own name has claimed since
    it was written — it said "every key the settings schema declares" while comparing against a set
    of names typed a few lines above it. Reading the schema makes the test do what it says.
    """
    text = STUB_PATH.read_text(encoding="utf-8")
    # Two forms, and both are exact. A commented key sits alone on its line -- `# packs:` or
    # `#packs:`, with only whitespace after the colon; a declared key carries its value,
    # `periplus_version: 0`. Anchoring at column zero keeps a nested key inside a commented block
    # -- `include:` under `first_party:` -- out of the count.
    #
    # The looser `^(?:#\s?)?([a-z_][a-z0-9_]*):` this replaced also matched a wrapped prose line
    # beginning `# searches: ...`, so it counted lines that look like keys rather than keys, and
    # the stub's comments could break the test by being reworded. Requiring the line to end after
    # the colon is what separates the two; the optional space and the trailing whitespace are
    # tolerated because a stub that is right should not fail over either.
    named = {
        declared or commented
        for commented, declared in re.findall(
            r"^(?:#\s?([a-z_][a-z0-9_]*):[ \t]*$|([a-z_][a-z0-9_]*): \S)", text, re.MULTILINE
        )
    }

    assert named == _declared_settings_keys()

    document = load_settings_document(STUB_PATH)

    assert dict(document) == {"periplus_version": 0}


# --------------------------------------------------------------------------------------------
# The file `init` writes is valid against the schema it is supposed to follow
# --------------------------------------------------------------------------------------------


def test_the_file_init_writes_into_an_empty_directory_validates_against_the_schema(
    tmp_path: Path,
) -> None:
    """Run as a person would: init, then validate.

    The file is produced by running ``init`` rather than read out of ``settings.stub.yml``,
    because what matters is the file the command writes and the stub is only one of its two
    outputs. With ``packs`` required, this reports ``'packs' is a required property``.

    **The schema is what is wrong here, not the stub.** An unconfigured project is a state this
    tool already supports on purpose: ``status`` exits 0 on an unconfigured machine, and
    ``errors.py`` records the reason beside ``NO_SETTINGS`` — for a command whose job is to
    describe a state, an empty one is the state. A schema that calls that file invalid contradicts
    a decision already shipped, so ``packs`` comes out of ``required``.
    """
    report = initialise_project(tmp_path)
    document = load_settings_document(report.settings)

    errors = sorted(
        error.message
        for error in Draft202012Validator(_settings_schema()).iter_errors(dict(document))
    )

    assert errors == []


def test_the_file_init_writes_with_a_prefilled_pin_validates_against_the_schema(
    tmp_path: Path,
) -> None:
    """The other output of ``init``, which the stub tests do not reach.

    ``init`` writes the bare stub, or the stub plus an uncommented ``packs:`` block when detection
    matched. Both are "the settings file ``periplus init`` writes", and only asserting the first
    would leave the shipped prefill unchecked against the schema it has to satisfy.

    **This one passes on arrival** — the prefilled form already validates, because it declares both
    keys the schema requires. It is here so that dropping ``packs`` from ``required`` cannot
    silently take ``minItems`` or the pin pattern with it.
    """
    report = initialise_project(tmp_path, packs=("drupal@0.1.0",))
    document = load_settings_document(report.settings)

    assert dict(document)["packs"] == ["drupal@0.1.0"]
    errors = sorted(
        error.message
        for error in Draft202012Validator(_settings_schema()).iter_errors(dict(document))
    )

    assert errors == []


def test_a_settings_file_declaring_an_empty_pack_list_is_still_refused() -> None:
    """``minItems: 1`` stays when ``packs`` leaves ``required``, and they are different facts.

    A key that is absent is a project nobody has configured. A key present and empty is a claim
    that no pack applies to this repository, which is a different statement and one no run should
    accept quietly — ``init`` itself refuses to write ``packs: []`` for exactly this reason.
    Dropping ``required`` is the fix the file ``init`` writes needs; dropping ``minItems`` with it
    would turn the two states back into one.

    A sensitivity test: it passes today, and it is what fails if the two are collapsed.
    """
    errors = [
        error.message
        for error in Draft202012Validator(_settings_schema()).iter_errors(
            {"periplus_version": 0, "packs": []}
        )
    ]

    assert errors != [], "an empty `packs` list is now accepted, and it says something different"


def test_a_pin_list_replaces_rather_than_merging(tmp_path: Path) -> None:
    """``packs`` takes the last file that declared it, whole. A merged lockfile is not a lockfile.

    A pin is matched against directory names, so the list has to be the set of pins one
    file chose. A user-level pin surviving into a project's run would add a pack the repository
    never asked for and never committed.
    """
    resolved, _ = _resolve(
        tmp_path,
        user="packs: [go@0.0.2]\n",
        project="packs: [php@0.1.0, drupal@0.1.0]\n",
    )

    assert resolved.packs is not None
    assert resolved.packs.value == ("php@0.1.0", "drupal@0.1.0")
    assert [source.kind for source in resolved.packs.sources] == ["project"]


def test_a_folder_the_project_does_not_mention_keeps_the_user_file_as_its_source(
    tmp_path: Path,
) -> None:
    """``folders`` merges name by name, so one file can override one name and leave the rest.

    The fell-through name is what this shape exists to make visible. ``shared`` reaches the result
    from the user file alone and says so; ``config`` is overridden and names the project file. A
    mapping merged whole would have deleted ``shared`` without a word.

    Every value survives as the template it was written as, braces intact and nothing joined to a
    root. Substitution, the unknown-name failure, the cycle failure and the join to the project root
    are all ``resolve_folders``' work, and this mapping is already that function's declared input. A
    folder value that came back absolute would mean this module had grown the half of the seam it
    does not own.
    """
    resolved, _ = _resolve(
        tmp_path,
        user="folders: {config: ./user-config, shared: ./everywhere}\n",
        project=(
            "folders:\n"
            '  config: "./drupal-app/config/default"\n'
            '  module_config: "{config}/*/config/install"\n'
        ),
    )

    assert set(resolved.folders) == {"config", "module_config", "shared"}
    assert resolved.folders["config"].value == "./drupal-app/config/default"
    assert [s.kind for s in resolved.folders["config"].sources] == ["project"]
    assert resolved.folders["shared"].value == "./everywhere"
    assert [s.kind for s in resolved.folders["shared"].sources] == ["user"]
    assert resolved.folders["module_config"].value == "{config}/*/config/install"


def test_values_merge_name_by_name_and_drop_a_value_that_is_not_text(tmp_path: Path) -> None:
    """``values`` merges as ``extensions`` does, each name carrying the file that won it, and a
    mapping holding a value that is not text contributes nothing."""
    resolved, _ = _resolve(
        tmp_path,
        user="values: {module: example.com/user, owner: ops}\n",
        project="values: {module: example.com/app}\n",
    )

    assert {name: s.value for name, s in resolved.values.items()} == {
        "module": "example.com/app",
        "owner": "ops",
    }
    assert [s.kind for s in resolved.values["module"].sources] == ["project"]
    assert [s.kind for s in resolved.values["owner"].sources] == ["user"]
    numbers, _ = _resolve(tmp_path / "numbers", project="values: {module: 1}\n")
    assert numbers.values == {}


def test_a_key_no_file_declares_is_absent_rather_than_a_fabricated_default(
    tmp_path: Path,
) -> None:
    """A key that fell through to nothing is ``None``, and nothing invents a value for it.

    The cascade deliberately permits a key nobody set, so the record has to be able to say so. An
    empty tuple with no sources would print as a value somebody had chosen, which is the one thing
    the source-carrying shape exists to prevent.
    """
    resolved, _ = _resolve(tmp_path, project="packs: [php@0.1.0]\n")

    assert resolved.packs is not None
    assert resolved.pack_paths is None
    assert resolved.exclude is None
    assert resolved.first_party is None
    assert resolved.folders == {}
    assert resolved.extensions == {}


def test_first_party_accumulates_both_of_its_lists(tmp_path: Path) -> None:
    """``include`` and ``exclude`` each accumulate, and the pair is one setting with one source
    list.

    This is where a dependency is deliberately promoted to first-party, so a machine-level rule and
    a project-level one have to be able to coexist rather than one silently replacing the other.
    """
    resolved, _ = _resolve(
        tmp_path,
        user='first_party:\n  exclude: ["**/vendor/**"]\n',
        project='first_party:\n  include: ["drupal-app/web/modules/custom/**"]\n',
    )

    assert resolved.first_party is not None
    assert resolved.first_party.value == FirstParty(
        include=("drupal-app/web/modules/custom/**",),
        exclude=("**/vendor/**",),
    )
    assert [source.kind for source in resolved.first_party.sources] == ["user", "project"]


def test_a_value_of_the_wrong_shape_is_dropped_rather_than_coerced(tmp_path: Path) -> None:
    """A list-valued key written as a string contributes nothing, instead of a tuple of characters.

    Nothing here validates, by design — but nothing here may lie about
    a type either. ``tuple("ops/x.php")`` is nine one-character exclusion patterns, and it would
    reach a report as though somebody had written them.

    The consequence is named rather than hidden: a malformed ``packs:`` in the project file leaves
    the user layer's list winning, because a contribution that is dropped is a contribution that
    never happened. The validator is what turns that into a message.

    The other half of the same question is what is *not* dropped. An ``accepted_unknowns`` entry
    whose ``accepted_on`` is an unquoted date is kept, date object and all — measured on ruamel
    0.19.1 under ``typ='safe'``, ``2026-08-28`` loads as a ``datetime.date``. A merge
    that typed this key's entries as ``Mapping[str, str]`` and enforced it would delete a
    legitimate entry from a person's file to satisfy an annotation — silently, since nothing reads
    this key back yet.
    """
    resolved, _ = _resolve(
        tmp_path,
        user="packs: [go@0.0.2]\n",
        project=(
            'packs: php@0.1.0\nexclude: "ops/settings.production.php"\nperiplus_version: true\n'
            "accepted_unknowns:\n"
            "  - id: drupal-dynamic-service\n"
            "    rule: drupal.service_call\n"
            "    reason: the id is assembled at runtime\n"
            "    accepted_by: camoa\n"
            "    accepted_on: 2026-08-28\n"
        ),
    )

    assert resolved.exclude is None
    assert resolved.periplus_version is None
    assert resolved.packs is not None
    assert resolved.packs.value == ("go@0.0.2",)
    assert resolved.accepted_unknowns is not None
    (entry,) = resolved.accepted_unknowns.value
    assert entry["id"] == "drupal-dynamic-service"
    assert str(entry["accepted_on"]) == "2026-08-28"

    # A list of the right shape holding one item of the wrong type is the same refusal. Checking the
    # container and not its items would put an `int` into a `tuple[str, ...]` and let it reach a
    # report as a pin.
    numbers, _ = _resolve(tmp_path / "numbers", project="packs: [1, 2]\n")
    assert numbers.packs is None


def test_a_key_the_settings_schema_does_not_name_changes_nothing(tmp_path: Path) -> None:
    """An unrecognised key is ignored without comment, whatever it holds.

    The merge walks its own table, never the document's keys, so a key nobody declared has nowhere
    to land. Refusing it would be validation, and validation is the next task's.

    One tree, rewritten between the two resolutions, so the two records differ in the settings file
    and in nothing else. Two trees would differ in the paths their sources name and the comparison
    would pass for the wrong reason.
    """
    user_dir, root = _tree(
        tmp_path, project="packs: [php@0.1.0]\nnonsense: {deeply: [nested, 1, true]}\n"
    )
    sources = locate_settings(root, user_dir)
    project = sources[1].path

    with_extra = resolve_settings(None, load_settings_document(project), sources)
    project.write_text("packs: [php@0.1.0]\n", encoding="utf-8")
    without = resolve_settings(None, load_settings_document(project), sources)

    assert with_extra == without


# --------------------------------------------------------------------------------------------
# Anchoring
# --------------------------------------------------------------------------------------------


def test_the_same_relative_pack_path_anchors_to_the_file_that_declared_it(
    tmp_path: Path,
) -> None:
    """``./packs`` in both files is two different directories, each beside its own file.

    This is what keeps a committed ``./packs`` portable: the project's entry follows the repository
    wherever it is checked out, and the machine's entry stays in the person's configuration
    directory. Anchoring both to one root would make a committed settings file mean something
    different on every machine.

    Both files write the *same string*, so only the anchor distinguishes the two resulting paths,
    and each is attributed to its own file. An implementation that attributed both to one file would
    name the wrong settings file for a directory that really exists.
    """
    resolved, sources = _resolve(
        tmp_path,
        user="pack_paths: [./packs]\n",
        project="pack_paths: [./packs]\n",
    )

    assert resolved.pack_paths is not None
    assert resolved.pack_paths.value == (
        tmp_path / "userconf" / "packs",
        tmp_path / "repo" / "packs",
    )
    assert [source.kind for source in resolved.pack_paths.sources] == ["user", "project"]
    assert dict(
        zip(resolved.pack_paths.value, resolved.pack_paths.entry_sources or (), strict=True)
    ) == {
        tmp_path / "userconf" / "packs": SourceRef(kind="user", name=str(sources[0].path)),
        tmp_path / "repo" / "packs": SourceRef(kind="project", name=str(sources[1].path)),
    }


def test_each_pack_path_names_the_file_that_actually_added_it(tmp_path: Path) -> None:
    """Per-entry attribution, which ``sources`` alone cannot give and ``packs.py`` needs.

    ``sources`` attributes the key: two files contributed, in this order. That is not the same fact
    as which file added which path, and ``packs.py``'s ``PackRoot.source`` — "which settings file
    added a configured root" — needs the second one. Given ``(pathA, pathB)`` and
    ``(user, project)`` there is nothing connecting them, so a ``packs.py`` written against the
    older shape would populate that field with the first source, or the last, and type-check either
    way.

    **The counts are deliberately unequal, and that is the whole test.** The user file contributes
    two paths and the project file one, so ``entry_sources`` is three long where ``sources`` is two.
    An earlier version of this test gave each file one path, which made the two tuples
    byte-identical: ``entry_sources = sources`` — one reference per *file*, in cascade order, which
    is the likeliest real bug here — passed it and the whole suite. Measured, not reasoned about.
    Unequal counts are what separate "one per entry" from "one per file that happened to line up".

    Two of the three paths are also written as different strings and one as a path both files could
    have named, so the assertion below is a mapping from each resolved directory to the file that
    added it, not an ordering that could be right by accident.
    """
    resolved, sources = _resolve(
        tmp_path,
        user="pack_paths: [./user-only, /opt/shared-packs]\n",
        project="pack_paths: [./project-only]\n",
    )
    user_ref = SourceRef(kind="user", name=str(sources[0].path))
    project_ref = SourceRef(kind="project", name=str(sources[1].path))

    assert resolved.pack_paths is not None
    assert resolved.pack_paths.sources == (user_ref, project_ref)
    assert resolved.pack_paths.entry_sources == (user_ref, user_ref, project_ref)
    assert dict(zip(resolved.pack_paths.value, resolved.pack_paths.entry_sources, strict=True)) == {
        tmp_path / "userconf" / "user-only": user_ref,
        Path("/opt/shared-packs"): user_ref,
        tmp_path / "repo" / "project-only": project_ref,
    }


def test_an_accumulating_key_that_is_not_pack_paths_attributes_per_entry_too(
    tmp_path: Path,
) -> None:
    """``exclude`` carries the same per-entry attribution, so this is the mechanism, not one key.

    The counts are unequal in the opposite direction to the ``pack_paths`` test — one pattern from
    the user file and two from the project file — so an implementation that padded or truncated in
    one direction is caught by the other.

    **Both files declare ``**/vendor/**``, and that repeat is the whole reason ``accumulate`` is a
    different rule from ``union``.** ``accumulate`` keeps both copies, so the project file's copy is
    the project file's and must say so. An earlier version of this test used three distinct
    patterns, and under it an implementation that attributed each entry to whoever declared that
    *value* first — reporting the project file's own copy as the user file's — passed. A rule about
    what happens when two layers say the same thing needs a fixture where two layers say the same
    thing.

    The assertion is a list of pairs rather than a mapping for the same reason. ``dict(zip(...))``
    collapses the two ``**/vendor/**`` entries into one key and silently discards the first entry's
    attribution, which is exactly the fact under test.
    """
    resolved, sources = _resolve(
        tmp_path,
        user='exclude: ["**/vendor/**"]\n',
        project='exclude: ["**/vendor/**", "ops/secrets/**"]\n',
    )
    user_ref = SourceRef(kind="user", name=str(sources[0].path))
    project_ref = SourceRef(kind="project", name=str(sources[1].path))

    assert resolved.exclude is not None
    assert resolved.exclude.sources == (user_ref, project_ref)
    assert resolved.exclude.value == ("**/vendor/**", "**/vendor/**", "ops/secrets/**")
    assert resolved.exclude.entry_sources == (user_ref, project_ref, project_ref)
    assert list(zip(resolved.exclude.value, resolved.exclude.entry_sources, strict=True)) == [
        ("**/vendor/**", user_ref),
        ("**/vendor/**", project_ref),
        ("ops/secrets/**", project_ref),
    ]


def test_a_directory_both_files_name_is_attributed_to_the_one_that_added_it_first(
    tmp_path: Path,
) -> None:
    """The union keeps the first occurrence, so the earlier layer is the one that added it.

    The later file changed nothing — the directory was already going to be searched, in that
    position — so attributing the surviving entry to it would say something untrue. Both files stay
    in ``sources``, which is where "both declared it" is recorded.

    **Both files declare that one directory and nothing else, so ``sources`` is longer than
    ``entry_sources``.** That gap is the test. It is the only fixture in which the two tuples have
    different lengths *because of the merge rule* rather than because the files listed different
    things, and it is what pins ``sources`` to "every file that declared this key" rather than to
    "the files that survived de-duplication". An earlier version had the project file also declare
    ``./packs``, which survived and put the project file back into a derived ``sources`` — so
    ``sources = tuple(dict.fromkeys(entry_sources))`` passed, dropping a settings file that had
    named that very directory from the record of who had a say.
    """
    shared = tmp_path / "shared-packs"
    resolved, sources = _resolve(
        tmp_path,
        user=f"pack_paths: [{shared}]\n",
        project=f"pack_paths: [{shared}]\n",
    )
    user_ref = SourceRef(kind="user", name=str(sources[0].path))
    project_ref = SourceRef(kind="project", name=str(sources[1].path))

    assert resolved.pack_paths is not None
    assert resolved.pack_paths.value == (shared,)
    assert resolved.pack_paths.entry_sources == (user_ref,)
    assert resolved.pack_paths.sources == (user_ref, project_ref)


def test_per_entry_attribution_is_carried_only_where_there_is_something_to_say(
    tmp_path: Path,
) -> None:
    """Every accumulating key carries it, one reference per entry; every other key carries ``None``.

    ``None`` is not "unknown". A replace key's entries all came from the one file ``sources``
    already names, so repeating that file once per entry would add a second place for the same fact
    to be wrong. ``folders`` needs none of it: each name is its own ``ResolvedSetting`` with its own
    source, which is per-entry attribution already.

    ``first_party`` is the one accumulating key that carries ``None``, because its value is two
    lists inside one object and a flat tuple cannot line up with it. Asserted so the gap is a
    recorded fact rather than an oversight discovered later.
    """
    resolved, _ = _resolve(
        tmp_path,
        user='exclude: ["**/user-junk/**"]\n',
        project=(
            "periplus_version: 0\n"
            "packs: [php@0.1.0, drupal@0.1.0]\n"
            "pack_paths: [./packs]\n"
            'exclude: ["ops/settings.production.php"]\n'
            'first_party:\n  include: ["src/**"]\n'
        ),
    )

    for name in ("exclude", "pack_paths"):
        setting = getattr(resolved, name)
        assert setting.entry_sources is not None, name
        assert len(setting.entry_sources) == len(setting.value), name

    assert resolved.packs is not None
    assert resolved.packs.entry_sources is None
    assert resolved.periplus_version is not None
    assert resolved.periplus_version.entry_sources is None
    assert resolved.first_party is not None
    assert resolved.first_party.entry_sources is None


def test_a_pack_path_is_normalised_lexically_and_never_resolved(tmp_path: Path) -> None:
    """``..`` collapses textually, and a symlinked root stays the path the person wrote.

    ``Path.resolve()`` would print a directory nobody named, which is the opposite of what a report
    whose whole job is to say where it looked should do. Lexical normalisation still makes two
    spellings of one directory a single entry, which is what the union needs.
    """
    real = tmp_path / "real"
    (real / ".periplus").mkdir(parents=True)
    (real / "packs").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    (real / ".periplus" / "settings.yml").write_text(
        "pack_paths: [./packs, ./vendor/../packs]\n", encoding="utf-8"
    )

    sources = locate_settings(find_project_root(link), None)
    resolved = resolve_settings(None, load_settings_document(sources[0].path), sources)

    assert resolved.pack_paths is not None
    assert resolved.pack_paths.value == (link / "packs",)
    assert resolved.pack_paths.value != (real / "packs",)
