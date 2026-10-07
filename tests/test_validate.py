"""``periplus validate``, as tests: it names what failed, every bundled pack passes it, and the
determinism that binds both.

Every test that asserts a status or an output runs the console script in a **subprocess**. That is
not caution about global state: the requirement is "run validate, it exits non-zero", and a
process status is the thing a person and a CI step both read. Calling ``validate()`` in process
would assert on a return value that no shell ever sees.

**What is deliberately not tested here: CI.** "Break one pack and watch CI reject it" needs a
push, and a test pushes nothing. A test asserting that a workflow YAML file contains a
string would assert a proxy for a rejection that never happened, so there is no such test. What is
tested is the thing that can fire: the command the workflow runs, against a deliberately broken
pack, exiting non-zero. The gap between those two is real and stays open.

The broken packs are built from the bundled ``go`` pack's own bytes, copied and renamed, never
invented. ``go`` because it declares ``depends: []``, so a run against it produces schema findings
and no dependency-resolution noise; renamed because a second copy under the pack's own name would
resolve to two directories and report a duplicate before it read a single rule.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from ruamel.yaml import YAML

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
BUNDLED_PACKS = SRC / "periplus" / "packs"
SCHEMA_DIRECTORY = SRC / "periplus" / "contract" / "schema"

#: The bundled pack the fixtures are cut from, and the name every copy is renamed to. The version
#: half is kept as it ships, so the copy is the real pack with one word changed.
SOURCE_PACK = "go@0.0.2"
FIXTURE_PACK = "gofixture"
FIXTURE_DIRECTORY = f"{FIXTURE_PACK}@0.0.2"

#: The packs the wheel carries, by name. Restated here rather than read off the directory
#: listing, for the reason ``test_packaging.BUNDLED_PACKS`` gives: a test that reads the same
#: directory it is checking passes against an empty one.
BUNDLED_PACK_NAMES = (
    "advancedqueue_basic",
    "ai_basic",
    "config_pages_basic",
    "crop_basic",
    "drupal",
    "drupal_basic",
    "drupal_js_basic",
    "drush_basic",
    "eck_basic",
    "go",
    "go_basic",
    "js_basic",
    "laravel_basic",
    "paragraphs_basic",
    "php",
    "php_basic",
    "profile_basic",
    "salesforce_basic",
    "twig",
    "twig_basic",
    "twig_tweak_basic",
    "webform_basic",
    "yaml",
    "yaml_basic",
)

#: The console script, run for real. ``main`` is called rather than the installed binary so the
#: test exercises this checkout rather than whatever is on PATH, and the status still travels
#: through ``SystemExit`` the way ``[project.scripts]`` sends it.
_CHILD = """
import sys

from periplus.cli import main

raise SystemExit(main(sys.argv[1:]))
"""

#: Two properties of the console script's own import graph, read in a child because both are
#: about what a *first* import pulls in and this process has already imported half the package.
_IMPORT_GRAPH = """
import json
import sys

import periplus.cli

json.dump(
    {"validate": "periplus.validate" in sys.modules, "jsonschema": "jsonschema" in sys.modules},
    sys.stdout,
)
"""


def _yaml() -> YAML:
    """A safe loader, as ``settings.py`` and ``manifest.py`` build one."""
    return YAML(typ="safe")


@dataclass(frozen=True)
class Project:
    """A project root with a pack directory, and the user configuration directory beside it."""

    root: Path
    config: Path
    packs: Path


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    """A real project tree: ``.periplus/`` with a settings file and an empty pack directory.

    A file rather than a bare directory, because ``.periplus/settings.yml`` is what several of
    these tests then edit to add a pin, and a test that created it only sometimes would have two
    shapes of project to reason about.
    """
    root = tmp_path / "repo"
    packs = root / ".periplus" / "packs"
    packs.mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\n", encoding="utf-8")
    config = tmp_path / "userconf"
    config.mkdir()
    yield Project(root=root, config=config, packs=packs)


@pytest.fixture
def elsewhere(tmp_path: Path) -> Iterator[Project]:
    """A directory that is not a project, with an empty user configuration directory.

    The bundled pack root is searched from anywhere, so this is where a run against a shipped pack
    happens with nothing of a project's making in the way.
    """
    root = tmp_path / "elsewhere"
    root.mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    yield Project(root=root, config=config, packs=root)


def _run(
    args: Sequence[str], *, cwd: Path, config: Path, **overrides: str
) -> subprocess.CompletedProcess[str]:
    """Run the console script in a fresh interpreter, with the environment built rather than
    inherited.

    Built, so an inherited ``PERIPLUS_CONFIG_DIR`` or ``PYTHONPATH`` cannot put a second settings
    layer or a second copy of the package into a run that is asserting on paths.
    """
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PERIPLUS_CONFIG_DIR": str(config),
        **overrides,
    }
    return subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _CHILD, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        check=False,
    )


def _copy_pack(destination: Path) -> Path:
    """The bundled ``go`` pack, copied under a name nothing else on the search path carries.

    Only the manifest's ``pack:`` line changes. Every rule file arrives byte for byte, which is
    what makes a break below a break in real shipped content rather than in a file written to fail.
    """
    target = destination / FIXTURE_DIRECTORY
    shutil.copytree(BUNDLED_PACKS / SOURCE_PACK, target)
    manifest = target / "pack.yaml"
    text = manifest.read_text(encoding="utf-8")
    assert "\npack: go\n" in text, "the bundled go manifest no longer declares `pack: go`"
    manifest.write_text(text.replace("\npack: go\n", f"\npack: {FIXTURE_PACK}\n"), encoding="utf-8")
    return target


def _drop_confidence(pack: Path) -> None:
    """Remove ``confidence`` from the first rule of the pack's declaration file.

    ``confidence`` is one of the five keys ``pack-file.schema.json`` requires of a rule, and it
    yields ``$.rules[0]: 'confidence' is a required property``, which names the key and its path.
    """
    rules = pack / "types" / "find_declarations.yaml"
    text = rules.read_text(encoding="utf-8")
    assert "\n  confidence: declared\n" in text, "the go pack's first rule no longer declares one"
    rules.write_text(text.replace("\n  confidence: declared\n", "\n", 1), encoding="utf-8")


def _break_the_match_branch(pack: Path) -> None:
    """Leave the first rule's ``match`` block with none of the ten keys ``oneOf`` requires.

    This is the failure that names nothing on its own. ``$defs/match`` is a ``oneOf`` over ten
    ``required`` branches, so a block matching none of them yields a parent error reading "is not
    valid under any of the given schemas" — no key, no remedy — and carries the ten sub-errors that
    do name keys in ``.context``.
    """
    rules = pack / "types" / "find_declarations.yaml"
    document = _yaml().load(rules.read_text(encoding="utf-8"))
    assert "declaration" in document["rules"][0]["match"], "the go pack's first rule changed shape"
    document["rules"][0]["match"] = {"name_child": "package_identifier"}
    with rules.open("w", encoding="utf-8") as handle:
        _yaml().dump(document, handle)


def _add_an_out_of_order_file(pack: Path) -> Path:
    """Add one file whose two errors come out of ``iter_errors`` in the opposite of sorted order.

    ``pack-file.schema.json`` declares ``needs`` third from the top and ``edge_kinds`` fifth, so
    ``iter_errors`` reports ``$.needs`` before ``$.edge_kinds``; sorting by pointer puts
    ``$.edge_kinds`` first. That inversion is a property of the shipped schema's own key order, so
    it holds on every machine and every filesystem — which is what a determinism check across two
    processes on one machine cannot give.
    """
    path = pack / "ordering.yaml"
    path.write_text("needs: not-a-mapping\nedge_kinds: not-a-list\n", encoding="utf-8")
    return path


def _add_files_that_parse_to_nothing(pack: Path) -> tuple[str, ...]:
    """Add three files that parse cleanly and carry no document, by three different routes.

    A zero-byte file, a file holding one comment, and a file holding ``--- null``. All three load
    to ``None`` under a safe loader, and none of them is a parse failure — which is the distinction
    the run has to make, because a file that will not parse and a file that parses to nothing are
    the same value and different faults.

    Three and not one because they reach ``None`` differently — no bytes, no document node, and an
    explicit null node — and a repair that special-cased any one of them would leave the others
    invisible.
    """
    (pack / "empty.yaml").write_text("", encoding="utf-8")
    (pack / "commentonly.yaml").write_text("# nothing but a comment\n", encoding="utf-8")
    (pack / "explicitnull.yaml").write_text("--- null\n", encoding="utf-8")
    return ("commentonly.yaml", "empty.yaml", "explicitnull.yaml")


def _sort_key(error: dict[str, object]) -> tuple[str, str, str, str]:
    """The order every error in the report comes out in: file, pointer, message, then keyword.

    The keyword is the fourth component and not an afterthought: path, pointer and message
    together do not order two errors that differ only in which keyword failed, and falling back to
    ``iter_errors`` order there is the guarantee jsonschema does not give.
    """
    return (
        str(error["file"]),
        str(error["pointer"]),
        str(error["message"]),
        str(error["keyword"]),
    )


def _schema_id(name: str) -> str:
    """The ``$id`` of one shipped schema, read off the shipped file rather than written out here.

    A literal URL in this file would be a fourth copy of a string that already exists in the
    schema, in the pack files, and in whatever an editor resolves. Reading it means a change to the
    schema's identity has one place to be made.
    """
    return str(json.loads((SCHEMA_DIRECTORY / name).read_text(encoding="utf-8"))["$id"])


def _bundled_pack_files() -> list[Path]:
    """Every YAML file the bundled packs carry, sorted."""
    return sorted(BUNDLED_PACKS.rglob("*.yaml")) + sorted(BUNDLED_PACKS.rglob("*.yml"))


# ---------------------------------------------------------------------------------------------
# Validate names what failed
# ---------------------------------------------------------------------------------------------


def test_an_unmodified_bundled_pack_validates_clean_and_says_what_it_opened(
    elsewhere: Project,
) -> None:
    """An unmodified bundled pack exits 0.

    The ``checked`` assertion is what stops this passing vacuously, and it is the whole reason the
    report carries that field. A ``validate`` that resolved the pack, opened nothing and reported
    no errors would exit 0 and satisfy the requirement's words exactly; the set of files it says it
    opened is the only thing that separates "found nothing wrong" from "looked at nothing". The
    expected set is read off the source tree, so a pack file added to ``go`` fails here until it
    has been validated too.
    """
    expected = {
        path.relative_to(BUNDLED_PACKS / SOURCE_PACK).as_posix()
        for path in (BUNDLED_PACKS / SOURCE_PACK).rglob("*.yaml")
    }

    result = _run(
        ["validate", "go", "--format", "json"], cwd=elsewhere.root, config=elsewhere.config
    )

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["errors"] == []
    assert set(payload["checked"]) == expected
    assert payload["pack"] == "go"


def test_a_missing_required_key_exits_sixteen_naming_the_key_and_its_path(
    project: Project,
) -> None:
    """A broken pack, from real shipped bytes with one required key removed.

    Three separate facts are asserted: the status is non-zero, the
    file is named, and the key and its position inside that file are named. A report giving only
    the first tells a person their pack is broken and nothing about where.

    16 rather than "non-zero" because this command has its own code and its own
    aggregation. Any non-zero status would name a failure; asserting the number is what makes
    a later change to the table visible instead of silent.
    """
    _drop_confidence(_copy_pack(project.packs))

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert [
        (error["file"], error["pointer"], error["message"]) for error in payload["errors"]
    ] == [
        (
            "types/find_declarations.yaml",
            "$.rules[0]",
            "'confidence' is a required property",
        )
    ]


def test_a_pack_file_that_parses_to_nothing_is_checked_and_refused_rather_than_skipped(
    project: Project,
) -> None:
    """A file holding no document is a schema error, not a file the run may quietly pass over.

    **This is a regression test for a false clean.** A zero-byte file, a
    comment-only file and one holding ``--- null`` could be dropped from a run with no record:
    absent from ``checked``, absent from ``errors``, absent from ``problems``, and the command
    exiting 0. The cause is one branch — a loader returning ``None`` both for a file it could not
    parse and for a file that parsed to nothing, and the caller reading the second as the first. A
    pack could then ship files ``validate`` never opened while the command said it was clean, and
    ``checked`` — the field the whole design leans on to tell "found nothing wrong" from "looked at
    nothing" — did not reveal it.

    Three assertions, because a repair can satisfy any two and still be wrong.

    ``checked`` has to name all three, or the command is still not saying what it opened. The
    errors have to be exactly ``$`` / ``None is not of type 'object'`` — the message the shipped
    ``pack-file.schema.json`` already produces from its top-level ``"type": "object"``, so this is
    the schema doing the refusing and not a rule written into the engine beside it. And
    ``problems`` has to stay empty, which is the assertion that separates this fault from the one
    next to it: a file that parses to nothing is not a file that could not be read, and routing it
    to ``UNREADABLE_MANIFEST`` would report the wrong fault about the right file.
    """
    pack = _copy_pack(project.packs)
    added = _add_files_that_parse_to_nothing(pack)

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert set(added) <= set(payload["checked"]), (
        f"{sorted(set(added) - set(payload['checked']))} were never opened, and the run said clean "
        f"about them"
    )
    assert [
        (error["file"], error["pointer"], error["message"])
        for error in payload["errors"]
        if error["file"] in added
    ] == [(name, "$", "None is not of type 'object'") for name in added]
    assert payload["problems"] == [], (
        "a file that parses to nothing was reported as a file that could not be read"
    )


def test_the_text_form_names_the_file_the_pointer_and_the_message(project: Project) -> None:
    """The default form is the one a person reads, and it carries the same three facts.

    Validate "names what failed". A JSON document a consumer parses satisfies that
    for a program; the text form is what satisfies it for the person who ran the command, and the
    two forms drifting is how the second becomes a status code and a shrug.
    """
    _drop_confidence(_copy_pack(project.packs))

    result = _run(["validate", FIXTURE_PACK], cwd=project.root, config=project.config)

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    assert "types/find_declarations.yaml" in result.stdout
    assert "$.rules[0]" in result.stdout
    assert "'confidence' is a required property" in result.stdout


def test_a_branch_failure_names_the_keys_beneath_it_and_not_only_the_branch(
    project: Project,
) -> None:
    """A ``oneOf`` failure names no key, so its sub-errors are rendered or validate names nothing.

    The first assertion after the status is the one that matters and it is deliberately negative:
    the parent's own message must **not** name ``declaration``, because it genuinely does not — it
    reads "is not valid under any of the given schemas". That is the whole reason ``context`` has
    to be rendered, and asserting it here stops a later reading of "names what failed" that is
    satisfied by the branch line alone.
    """
    _break_the_match_branch(_copy_pack(project.packs))

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    branch = next(error for error in payload["errors"] if error["keyword"] == "oneOf")
    assert branch["pointer"] == "$.rules[0].match"
    assert "declaration" not in branch["message"]
    assert "declaration" in {
        sub["message"].split("'")[1] for sub in branch["context"] if sub["keyword"] == "required"
    }


def test_the_text_form_prints_the_sub_errors_beneath_a_branch_and_not_only_the_branch(
    project: Project,
) -> None:
    """The same clause in the form a person reads.

    The test above reads ``context`` out of the **JSON** document, and the other text-form test
    uses ``_drop_confidence`` — a bare ``required`` error whose ``context`` is empty. So the text
    renderer's recursion over sub-errors is covered by neither: replacing the recursive call in
    ``_error_lines`` with ``pass`` deletes every indented line from the default output, and without
    this test the whole suite stays green. Validate has to name what failed, and in the format a
    person actually sees, a branch line names a branch.

    Five assertions and each closes a different way of passing while saying nothing.

    The branch line's **message** must not name ``declaration``, which is the negative the whole
    test rests on: the parent genuinely reads "is not valid under any of the given schemas", so if
    that line were enough there would be nothing to render beneath it. The message and
    not the whole line, because the line also names the file — ``find_declarations.yaml`` carries
    the word, and asserting against the line fails on that.

    More than one line must sit beneath it, because a single sub-error cannot show that a
    recursion runs rather than that one value was interpolated.

    Those lines must be indented further than the branch, because sub-errors printed flat would
    read as separate faults at the same level rather than as the detail of one.

    Their count must equal the JSON form's ``context`` length. That is the tie: a renderer that
    printed the first sub-error, or every other one, satisfies the three assertions above and
    hands a person a different set of facts from the one a consumer parses.

    And the **keys** they name must be the same set the JSON form carries, because count is not
    content. Ten lines that are all the ``declaration`` sub-error satisfy every assertion above —
    right count, more than one line, correctly indented, ``declaration`` present — while a person
    reads one fact ten times and the nine other keys the branch was refusing are gone. This is the
    assertion that stops it.
    """
    _break_the_match_branch(_copy_pack(project.packs))

    text = _run(["validate", FIXTURE_PACK], cwd=project.root, config=project.config)
    document = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert text.returncode == 16, f"{text.stdout}{text.stderr}"
    lines = text.stdout.splitlines()
    branches = [index for index, line in enumerate(lines) if "  oneOf  " in line]
    assert len(branches) == 1, f"expected one branch line, found {len(branches)}:\n{text.stdout}"
    branch = branches[0]
    # Four fields joined by two spaces: file, pointer, keyword, message. Split rather than
    # searched, so this also pins the line's shape and reads the message on its own.
    fields = lines[branch].strip().split("  ", 3)
    assert len(fields) == 4, f"the branch line is not four fields: {lines[branch]!r}"
    assert "declaration" not in fields[3]

    # Every line indented further than the branch, which is the branch's whole subtree flattened.
    # `context` below is only the top level of it, so the two compare like with like exactly while
    # every sub-error carries an empty context — which all ten do today. A schema change that gave
    # one of them a context of its own would fail this test for a reason that has nothing to do
    # with the property it is about. Recorded, not solved: the fixture is the shipped
    # `$defs/match`, and a nested branch is not reachable through it.
    indent = len(lines[branch]) - len(lines[branch].lstrip())
    beneath: list[str] = []
    for line in lines[branch + 1 :]:
        if len(line) - len(line.lstrip()) <= indent or not line.strip():
            break
        beneath.append(line)

    assert len(beneath) > 1, (
        f"{len(beneath)} lines were printed beneath the branch line, and one cannot show "
        f"that a recursion ran:\n{text.stdout}"
    )
    context = next(
        error for error in json.loads(document.stdout)["errors"] if error["keyword"] == "oneOf"
    )["context"]
    # The key each line names, quoted in both forms because every sub-error here is `required`.
    printed = {line.split("'")[1] for line in beneath}
    carried = {sub["message"].split("'")[1] for sub in context}

    assert "declaration" in printed, (
        f"the branch refused `declaration` and the text form never named it: {sorted(printed)}"
    )
    assert len(beneath) == len(context), (
        f"the text form printed {len(beneath)} sub-errors and the JSON form carries "
        f"{len(context)}, so the two forms give a reader different facts"
    )
    # Count is not content. Ten lines that are all one sub-error satisfy every assertion above:
    # more than one line, correctly indented, `declaration` present, ten of ten. A person is then
    # handed ten copies of one fact and the nine keys the branch was refusing are hidden. Without
    # this line, planting exactly that passes.
    assert printed == carried, (
        f"the text form named {sorted(printed)} and the JSON form carries {sorted(carried)}; the "
        f"two forms are refusing different keys"
    )


def test_a_pack_name_no_directory_carries_exits_fifteen_and_names_what_is_there(
    elsewhere: Project,
) -> None:
    """A misspelled pack is ``PACK_UNKNOWN``, the code that already means exactly that.

    Its own code and not a schema error: nothing was validated, so calling it a schema failure
    would name the wrong file and send a person to fix a pack that is not there. ``spec`` returns
    15 for the same argument, and one number for one meaning is the point of the table.
    """
    result = _run(
        ["validate", "twigg", "--format", "json"], cwd=elsewhere.root, config=elsewhere.config
    )

    assert result.returncode == 15, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert [problem["code"] for problem in payload["problems"]] == [15]
    assert payload["errors"] == []


def test_a_schema_error_takes_the_status_from_a_lower_resolution_code(project: Project) -> None:
    """The departure from ``min()``, asserted where it is observable.

    Every other report in this package takes the lowest code among its problems, and
    ``SCHEMA_INVALID`` is the highest number in the table — so under that rule a ``validate`` run
    in a project with an unresolvable pin would exit 5 and answer a question about a pack with a
    fault in a settings file. Here both faults are real at once: the pin matches nothing, and the
    pack disagrees with the schema.

    The second assertion is what keeps the first honest. A status of 16 could also be reached by
    dropping the resolution problem on the floor, which would be a worse bug than the one this
    test exists to prevent, so the problem has to still be in the report.
    """
    _drop_confidence(_copy_pack(project.packs))
    settings = project.root / ".periplus" / "settings.yml"
    settings.write_text("periplus_version: 0\npacks:\n  - nosuch@1.0.0\n", encoding="utf-8")

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert 5 in {problem["code"] for problem in payload["problems"]}


def test_with_nothing_wrong_in_the_pack_a_resolution_problem_still_takes_the_status(
    project: Project,
) -> None:
    """The other half of the aggregation rule, and the one a single test could not show.

    The same project and the same unresolvable pin as above, with the pack left as it ships. A
    ``validate`` that simply returned 16 whenever anything at all went wrong would pass the test
    above and fail this one; a ``validate`` that kept ``min()`` would fail the one above and pass
    this. Only the pair pins the rule the design states.
    """
    _copy_pack(project.packs)
    settings = project.root / ".periplus" / "settings.yml"
    settings.write_text("periplus_version: 0\npacks:\n  - nosuch@1.0.0\n", encoding="utf-8")

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 5, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["errors"] == []


# ---------------------------------------------------------------------------------------------
# Determinism — the same bytes, whatever ran the command
# ---------------------------------------------------------------------------------------------


def test_the_errors_come_out_sorted_rather_than_in_the_order_they_were_found(
    project: Project,
) -> None:
    """Sortedness, checked against a fixture where the unsorted order is provably different.

    A determinism check that runs the same command twice on one machine cannot catch a missing
    sort: ``Path.rglob`` and ``iter_errors`` both return the same wrong order twice, and the two
    outputs match. So this test does not compare two runs. It compares one run against the order
    the design declares, on a pack built so that the order errors are *found* in is the reverse of
    the order they must be *printed* in.

    The inversion comes from the shipped schema's own key order rather than from the filesystem:
    ``needs`` is declared above ``edge_kinds``, so ``iter_errors`` finds ``$.needs`` first, and
    sorting by pointer puts ``$.edge_kinds`` first. The assertion before the run states that
    inversion, so if the schema is ever reordered this test says the lever is gone instead of
    passing while asserting nothing.
    """
    pack = _copy_pack(project.packs)
    _drop_confidence(pack)
    _add_an_out_of_order_file(pack)

    schema = json.loads(
        (SCHEMA_DIRECTORY / "pack-file.schema.json").read_text(encoding="utf-8")
    )
    declared = list(schema["properties"])
    assert declared.index("needs") < declared.index("edge_kinds"), (
        "the schema no longer declares `needs` above `edge_kinds`, so the found order and the "
        "sorted order may now agree and the assertion below can no longer fail"
    )

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    errors = json.loads(result.stdout)["errors"]
    assert [error["pointer"] for error in errors if error["file"] == "ordering.yaml"] == [
        "$.edge_kinds",
        "$.needs",
    ]
    assert errors == sorted(errors, key=_sort_key)


def test_the_sub_errors_of_a_branch_are_sorted_too(project: Project) -> None:
    """The same rule one level down, where the found order is also not the printed order.

    ``$defs/match``'s ten branches are declared ``file``, ``attribute``, ``annotation`` first, so
    the sub-errors arrive in that order and must be printed in ``annotation``, ``array_entry``,
    ``attribute`` order. Ten sub-errors sharing one file and one pointer is also the case the sort
    key's first three components cannot order at all, which is why the message is in it.
    """
    _break_the_match_branch(_copy_pack(project.packs))

    result = _run(
        ["validate", FIXTURE_PACK, "--format", "json"], cwd=project.root, config=project.config
    )

    assert result.returncode == 16, f"{result.stdout}{result.stderr}"
    branch = next(
        error for error in json.loads(result.stdout)["errors"] if error["keyword"] == "oneOf"
    )
    assert len(branch["context"]) > 1, "a branch with one sub-error cannot show an ordering fault"
    assert branch["context"] == sorted(branch["context"], key=_sort_key)


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_two_processes_from_two_directories_under_two_locales_emit_the_same_bytes(
    project: Project, fmt: str
) -> None:
    """Determinism, in the shape ``test_spec.py`` already uses for ``spec``.

    Two operating-system processes, because two calls inside one pytest process share one hash
    seed, one locale and one dict ordering by construction, and a byte comparison of those cannot
    fail for the reason its name gives.

    The pack is broken in three places across three files on purpose. One error cannot show an
    ordering fault, and errors within a single file cannot show a fault in the order the files
    themselves were walked.

    What this does **not** catch is a missing sort, and that limit is why the test above exists:
    on one machine ``rglob`` returns one order twice. This catches what varies between processes —
    the hash seed and the locale — and the test above catches what does not vary at all.
    """
    pack = _copy_pack(project.packs)
    _drop_confidence(pack)
    _break_the_match_branch(pack)
    _add_an_out_of_order_file(pack)
    deeper = project.root / "src" / "nested"
    deeper.mkdir(parents=True)

    args = ["validate", FIXTURE_PACK, "--format", fmt]
    first = _run(args, cwd=project.root, config=project.config, PYTHONHASHSEED="0", LC_ALL="C")
    second = _run(args, cwd=deeper, config=project.config, PYTHONHASHSEED="2", LC_ALL="C")
    third = _run(
        args, cwd=deeper, config=project.config, PYTHONHASHSEED="0", LC_ALL="es_ES.utf8"
    )

    assert first.returncode == 16, f"{first.stdout}{first.stderr}"
    # Three empty strings compare equal. Without this the byte comparison below would ratify a
    # command that printed nothing at all, which is the one way it can pass while saying nothing.
    assert "find_declarations.yaml" in first.stdout and "ordering.yaml" in first.stdout
    assert first.stdout == second.stdout
    assert first.stdout == third.stdout


# ---------------------------------------------------------------------------------------------
# Every bundled pack declares $schema, and every bundled pack validates
# ---------------------------------------------------------------------------------------------


def test_every_bundled_pack_file_declares_the_schema_it_is_written_against() -> None:
    """Every pack file declares its schema, on all 216 files rather than the 24 manifests.

    That is wider than "a pack declares X", which means the manifest declares it everywhere else
    in this project; the wider check buys what matters, because the rules live in
    ``service/service_autowire.yaml`` and not in ``pack.yaml``, and 24 of 216 covers the files
    nobody edits.

    **What is claimed is that each file states which contract it is written against. Not that any
    editor validates it** — ``periplus.dev`` has no DNS record, so nothing resolves the URL today.

    The expected value is read off each schema's own ``$id``, so the two cannot drift, and a
    manifest pointing at the pack-file schema fails here rather than passing as "declares one".
    """
    manifest_id = _schema_id("pack-manifest.schema.json")
    pack_file_id = _schema_id("pack-file.schema.json")
    loader = _yaml()

    wrong: list[str] = []
    for path in _bundled_pack_files():
        document = loader.load(path.read_text(encoding="utf-8"))
        expected = manifest_id if path.name == "pack.yaml" else pack_file_id
        declared = document.get("$schema") if isinstance(document, dict) else None
        if declared != expected:
            wrong.append(f"{path.relative_to(BUNDLED_PACKS)}: declares {declared!r}")

    assert wrong == [], "\n".join(wrong)
    assert len(_bundled_pack_files()) == 217, "the bundled pack file count changed"


@pytest.mark.parametrize("pack", BUNDLED_PACK_NAMES)
def test_every_bundled_pack_validates_against_the_shipped_schemas(
    elsewhere: Project, pack: str
) -> None:
    """Every bundled pack validates, run locally, as a substitute for watching CI reject one.

    **Asserted:** the exact command a CI step would run exits 0 for each bundled pack,
    on this machine, now.

    **Not asserted:** that CI rejects a broken pack. Nothing is pushed, and no test in this file can
    observe a workflow run. A test reading a workflow YAML file and asserting it
    contains this command would assert that a file says something, which is not that a CI check
    fired.

    Parametrized per pack rather than looped, so a failure names which pack rather than which
    iteration, and so ``drupal`` — the only one resolving a ``depends`` chain — is visibly covered.
    """
    result = _run(
        ["validate", pack, "--format", "json"], cwd=elsewhere.root, config=elsewhere.config
    )

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["errors"] == []
    assert payload["checked"], f"{pack} validated clean because nothing was opened"


def test_a_deliberately_broken_pack_is_rejected_by_the_command_ci_would_run(
    project: Project,
) -> None:
    """"Break one pack and watch it be rejected", with the local run standing in for CI.

    The same command as the test above and the opposite verdict, which is the pair that says the
    check can fire at all. Without this, five packs exiting 0 is equally consistent with a
    ``validate`` that exits 0 for everything.
    """
    _drop_confidence(_copy_pack(project.packs))

    result = _run(["validate", FIXTURE_PACK], cwd=project.root, config=project.config)

    # 16 and not merely "non-zero". An earlier draft asserted both, and the non-zero half passed
    # today for the wrong reason: with no `validate` subcommand the run exits 2 on a usage error,
    # which is a rejection of the invocation and not of the pack.
    assert result.returncode == 16, f"{result.stdout}{result.stderr}"


# ---------------------------------------------------------------------------------------------
# The wiring: the import graph the whole package is arranged around, and the format table
# ---------------------------------------------------------------------------------------------


def test_importing_the_console_script_reaches_neither_the_validator_nor_jsonschema(
    tmp_path: Path,
) -> None:
    """``cli`` imports ``validate`` inside ``main()``, the way it already imports ``init``.

    ``errors.py`` states the property this holds up: nothing on ``cli``'s module-level import path
    imports a runtime distribution, because the dependency check has not run yet and a missing one
    would raise ``ImportError`` instead of exiting 9 naming it. ``validate`` reaches ``jsonschema``,
    so a module-level import of it in ``cli.py`` breaks that for the third distribution exactly as
    a module-level ``import periplus.init`` breaks it for the first two — measured.

    A sensitivity test: it fails the moment the wiring is added at the wrong level.
    """
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _IMPORT_GRAPH],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"validate": False, "jsonschema": False}


def test_the_format_choices_are_exactly_the_renderers_the_validator_offers() -> None:
    """``validate --format``'s choices and ``validate.RENDERERS`` name the same two, in order.

    Two constants on purpose, for the reason ``cli.py`` records for ``status`` and ``spec``: the
    console script may not import a module that reaches a runtime distribution, so the choices are
    written as a literal there and this is the tie that stops the two drifting.
    """
    from periplus.cli import build_parser
    from periplus.validate import RENDERERS

    parser = build_parser()
    subcommands = next(
        action
        for action in parser._actions
        if action.__class__.__name__ == "_SubParsersAction"
    )
    assert "validate" in subcommands.choices, "the console script has no `validate` subcommand"
    validate_parser = subcommands.choices["validate"]
    fmt = next(action for action in validate_parser._actions if action.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(RENDERERS) == ("text", "json")
    assert fmt.default == next(iter(RENDERERS))
