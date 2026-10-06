"""The pack contract, as tests.

Four JSON Schemas and two prose specs are what a Periplus pack is defined against. What this file
specifies is that they are the documents they claim to be, and that they survive the trip into an
installed wheel. Whether a *pack* agrees with them is ``tests/test_validate.py``'s question, and
the header here said "nothing in this package reads them yet" until ``periplus validate`` was
written.

Two tiers, because those are two behaviours and each has a smallest tier that answers it.
Whether a schema document is well formed is a question about a file's bytes, answered by reading
the file. Whether those bytes reach a user is a question about packaging, answerable only after
an install. The install test ties the two together by comparing the installed text against the
source text byte for byte, so the validity established at the cheap tier is validity of the thing
that actually ships — and a truncation present in both copies still fails, at the cheap tier.

``EXPECTED_CONTRACT_FILES`` is imported from ``test_packaging`` rather than restated. That file
uses it to bound what the wheel and sdist archives may carry; this one uses it to bound what an
install exposes. One declaration means the two bounds cannot drift apart, and a seventh contract
file has to be admitted in one place before either will pass.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from test_packaging import (
    EXPECTED_CONTRACT_FILES,
    PROJECT_ROOT,
    UV,
    _run_or_fail,
    _scripts_dir,
)

#: The seven type names JSON Schema defines. Anything else in a ``type`` position is a word the
#: author meant as vocabulary and a validator will read as a type name.
PRIMITIVE_TYPES = frozenset({"array", "boolean", "integer", "null", "number", "object", "string"})

#: The dialects a shipped schema may declare. One entry, and pinned rather than "any string",
#: because ``$schema`` is how a document says which dialect its keywords belong to — a typo there
#: silently changes the answer to every other question about the document.
KNOWN_DIALECTS = frozenset({"https://json-schema.org/draft/2020-12/schema"})

# The three shapes a schema hides inside another schema. Every keyword below holds a subschema, a
# name-to-subschema map, or an array of subschemas, and the walk recurses through exactly these.
# Nothing else is treated as a schema position, which is what keeps a property genuinely named
# `type` or `contains` — the pack vocabulary has both — from being read as a keyword.
_SCHEMA_VALUED = (
    "additionalProperties",
    "contains",
    "else",
    "if",
    "items",
    "not",
    "propertyNames",
    "then",
    "unevaluatedItems",
    "unevaluatedProperties",
)
_SCHEMA_MAP_VALUED = ("$defs", "dependentSchemas", "patternProperties", "properties")
_SCHEMA_LIST_VALUED = ("allOf", "anyOf", "oneOf", "prefixItems")

# Read from the installed package, never from a path this test constructs. `importlib.resources`
# is how the validator will reach these files at runtime, so it is what the test has to exercise;
# opening `<venv>/lib/.../periplus/contract/...` by hand would prove a file is at a path we built
# and would say nothing about whether the package can find it.
#
# The walk is recursive and unconditional rather than a lookup of the six expected names. A
# lookup reports a missing file and is blind to an extra one, and the caller asserts set equality
# precisely so that a seventh file shipped under contract/ is a failure here too.
READ_INSTALLED_CONTRACT = '''
import importlib.resources
import json
import sys

import periplus

found = {}


def visit(node, path):
    if node.is_dir():
        for child in sorted(node.iterdir(), key=lambda entry: entry.name):
            visit(child, path + "/" + child.name)
    else:
        found[path] = node.read_text(encoding="utf-8")


visit(importlib.resources.files("periplus") / "contract", "periplus/contract")
json.dump({"package_file": periplus.__file__, "files": found}, sys.stdout)
'''


def _source_text(shipped: str) -> str:
    """The working tree's copy of a file, named by the path it takes inside the package."""
    return (PROJECT_ROOT / "src" / shipped).read_text(encoding="utf-8")


def _compiles(pattern: object, where: str, problems: list[str]) -> None:
    """Record a problem unless ``pattern`` is a string a regex engine will accept."""
    if not isinstance(pattern, str):
        problems.append(f"{where}: {pattern!r} is not a string")
        return
    try:
        re.compile(pattern)
    except re.error as error:
        problems.append(f"{where}: {pattern!r} is not a usable regular expression ({error})")


def _check_keywords(
    node: dict[str, Any], where: str, root: dict[str, Any], problems: list[str]
) -> None:
    """Check the keywords at one schema position that constrain the shape of their own value."""
    if "type" in node:
        declared = node["type"]
        names = declared if isinstance(declared, list) else [declared]
        named = all(isinstance(name, str) and name in PRIMITIVE_TYPES for name in names)
        if not names or not named:
            problems.append(
                f"{where}/type: {declared!r} is not a JSON Schema type name or an array of them"
            )
        elif len(set(names)) != len(names):
            problems.append(f"{where}/type: {declared!r} names the same type twice")

    if "required" in node:
        required = node["required"]
        if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
            problems.append(f"{where}/required: {required!r} is not an array of property names")
        elif len(set(required)) != len(required):
            problems.append(f"{where}/required: {required!r} names the same property twice")

    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        problems.append(f"{where}/enum: {node['enum']!r} is not a non-empty array")

    if "pattern" in node:
        _compiles(node["pattern"], f"{where}/pattern", problems)

    for keyword in ("title", "description", "$comment"):
        if keyword in node and not isinstance(node[keyword], str):
            problems.append(f"{where}/{keyword}: {node[keyword]!r} is not a string")

    # `isinstance(True, int)` is true, so a bool has to be excluded explicitly or `minItems: true`
    # reads as the integer 1.
    for keyword in ("maxItems", "maxLength", "minItems", "minLength", "minProperties",
                    "maxProperties"):
        if keyword in node and (
            isinstance(node[keyword], bool) or not isinstance(node[keyword], int)
        ):
            problems.append(f"{where}/{keyword}: {node[keyword]!r} is not an integer")

    for keyword in ("exclusiveMaximum", "exclusiveMinimum", "maximum", "minimum"):
        if keyword in node and (
            isinstance(node[keyword], bool) or not isinstance(node[keyword], (int, float))
        ):
            problems.append(f"{where}/{keyword}: {node[keyword]!r} is not a number")

    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str):
            problems.append(f"{where}/$ref: {ref!r} is not a string")
        elif not ref.startswith("#/$defs/"):
            # Every reference in these four documents is local, which is what lets a reader open
            # one and understand it without fetching anything. A reference that leaves the file
            # would break that, so it is a failure rather than an unchecked case.
            problems.append(f"{where}/$ref: {ref!r} is not a local #/$defs/ reference")
        else:
            defs = root.get("$defs")
            name = ref.removeprefix("#/$defs/")
            if not isinstance(defs, dict) or name not in defs:
                problems.append(f"{where}/$ref: {ref!r} names a $defs entry the document lacks")


def _walk(node: object, where: str, root: dict[str, Any], problems: list[str]) -> None:
    """Check one schema position, then recurse into every schema position inside it."""
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        problems.append(f"{where}: a schema is an object or a boolean, not {type(node).__name__}")
        return

    _check_keywords(node, where, root, problems)

    for keyword in _SCHEMA_VALUED:
        if keyword not in node:
            continue
        child = node[keyword]
        if keyword == "items" and isinstance(child, list):
            for index, element in enumerate(child):
                _walk(element, f"{where}/{keyword}[{index}]", root, problems)
        else:
            _walk(child, f"{where}/{keyword}", root, problems)

    for keyword in _SCHEMA_MAP_VALUED:
        if keyword not in node:
            continue
        block = node[keyword]
        if not isinstance(block, dict):
            problems.append(f"{where}/{keyword}: is not an object mapping names to schemas")
            continue
        for name, child in block.items():
            if keyword == "patternProperties":
                _compiles(name, f"{where}/{keyword} key", problems)
            _walk(child, f"{where}/{keyword}/{name}", root, problems)

    for keyword in _SCHEMA_LIST_VALUED:
        if keyword not in node:
            continue
        block = node[keyword]
        if not isinstance(block, list) or not block:
            problems.append(f"{where}/{keyword}: is not a non-empty array of schemas")
            continue
        for index, child in enumerate(block):
            _walk(child, f"{where}/{keyword}[{index}]", root, problems)


def _schema_problems(document: object, source: str) -> list[str]:
    """Everything wrong with one parsed document, read as a JSON Schema.

    A list rather than a raise, so one run names every fault in all four files instead of the
    first one it meets.
    """
    if not isinstance(document, dict):
        return [f"{source}: the document is {type(document).__name__}, and a schema is an object"]

    problems: list[str] = []
    if document.get("$schema") not in KNOWN_DIALECTS:
        problems.append(
            f"{source}: $schema is {document.get('$schema')!r}, not one of {sorted(KNOWN_DIALECTS)}"
        )
    if not isinstance(document.get("$id"), str):
        problems.append(f"{source}: $id is {document.get('$id')!r}, and must be a string")
    _walk(document, source, document, problems)
    return problems


def test_every_shipped_schema_is_parseable_json_and_a_json_schema_document() -> None:
    """The four schemas parse, and every schema position in them holds a well-formed schema.

    Parsing is the cheap half and catches a copy truncated in transit. The walk is the half that
    matters: it recurses through ``$defs``, ``properties``, ``items``, ``allOf`` and the rest,
    checks that each keyword whose value has a defined shape has that shape, compiles every
    ``pattern``, and resolves every ``$ref`` against the document's own ``$defs``. A dangling
    reference is the fault this catches that reading the file cannot — the JSON is perfectly
    valid and the schema is unusable.

    ``jsonschema`` is a runtime dependency, and ``Draft202012Validator.check_schema`` runs in the
    test below. The walk stays anyway, and that was decided by planting rather than by arguing.
    Thirteen defects were planted in ``pack-manifest.schema.json`` and each was offered to both
    checks.
    Five that this walk catches, ``check_schema`` does not: a ``$ref`` naming a ``$defs`` entry the
    document lacks, a ``$ref`` that leaves the file, an empty ``enum``, a ``$schema`` naming a
    dialect other than 2020-12, and a missing ``$id``. The first two are the fault this walk exists
    for — the JSON is valid, the meta-schema is satisfied, and the schema is unusable.

    Six that ``check_schema`` catches, this walk does not: ``multipleOf``, ``uniqueItems``,
    ``dependentRequired``, ``format``, ``deprecated`` and ``examples`` given values of the wrong
    type. Every one is a keyword these documents do not use today, which is exactly the bound the
    paragraph below has always stated — and it is now covered rather than merely admitted.

    So the guarantee is bounded and worth stating plainly: every keyword these four documents
    actually use is checked here, and the ones none of them uses are checked next door.
    """
    problems: list[str] = []
    for shipped in sorted(name for name in EXPECTED_CONTRACT_FILES if name.endswith(".json")):
        text = _source_text(shipped)
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            problems.append(f"{shipped}: is not parseable JSON ({error})")
            continue
        problems += _schema_problems(document, shipped)

    assert problems == [], "\n".join(problems)


def test_every_shipped_schema_is_valid_under_the_2020_12_meta_schema() -> None:
    """The four schemas are schemas by the dialect's own definition, not by our reading of it.

    This is what the hand-rolled walk above could never be: the reference implementation's verdict
    on the same four documents, so a keyword none of them uses today is still checked the day one
    of them uses it. ``check_schema`` raises on the first fault, so each document is offered
    separately and the failures are collected — one run names every broken file rather than the
    first.

    **A sensitivity test, not a red.** All four documents are valid today and this passes the
    moment it is written. It was verified by planting: thirteen defects in a copy of
    ``pack-manifest.schema.json``, of which this caught eight, including six the walk above misses.
    The two are complementary, which is why both run and neither was deleted.
    """
    problems: list[str] = []
    for shipped in sorted(name for name in EXPECTED_CONTRACT_FILES if name.endswith(".json")):
        document = json.loads(_source_text(shipped))
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError as error:
            problems.append(f"{shipped}: {error.json_path}: {error.message}")

    assert problems == [], "\n".join(problems)


def test_both_shipped_specs_carry_every_numbered_section() -> None:
    """``rules.md`` holds sixteen numbered rules and ``engine.md`` seven numbered steps, in order.

    The numbering is the structure of both documents rather than a count someone chose, so this
    is what a truncated, reordered or half-copied spec fails. Nothing here asserts wording: the
    prose is free to be rewritten, and rule 9 is not free to go missing or to become rule 10.
    """
    numbered = re.findall(r"^## (\d+)\. ", _source_text("periplus/contract/spec/rules.md"), re.M)
    assert numbered == [str(n) for n in range(1, 17)], (
        f"rules.md numbers its rules {numbered}, and the format is defined by sixteen of them"
    )

    steps = re.findall(r"^### (\d+)\. ", _source_text("periplus/contract/spec/engine.md"), re.M)
    assert steps == [str(n) for n in range(1, 8)], (
        f"engine.md numbers its run {steps}, and the run is seven steps in a fixed order"
    )


@pytest.mark.slow
def test_the_contract_is_readable_out_of_an_installed_wheel(tmp_path: Path) -> None:
    """An install of this project exposes the whole contract through ``importlib.resources``.

    This is the property, and it is not "the files are in the source tree" — that became true the
    moment they were copied there and no test can un-know it. Three things make this an assertion
    about an install and not about the checkout:

    The install is **not** editable. ``uv pip install -e .`` would leave the package pointing at
    ``src/periplus``, every read below would come straight back out of the working tree, and the
    test would pass just as green with the contract excluded from the wheel. So the project is
    built and installed for real.

    The reader runs with ``tmp_path`` as its working directory, so the project's ``src/`` is
    nowhere near that interpreter's ``sys.path``, and it reaches the files through
    ``importlib.resources.files("periplus")`` — the same route the validator will use — rather
    than through a path this test assembles.

    And ``periplus.__file__`` is asserted to be inside the venv and outside the project. That is
    the assertion that fails loudest if any of the above is ever weakened back into a source-tree
    read.

    What comes back is compared to the working tree byte for byte. That is what makes the two
    cheap tests above tests of the shipped bytes: they check the source text, and this checks
    that the installed text is the same text.
    """
    if UV is None:
        pytest.fail("uv is not on PATH, so the contract cannot be read out of a real install")

    venv = tmp_path / "venv"
    _run_or_fail([UV, "venv", str(venv)], "uv venv")
    python = _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")
    _run_or_fail(
        [UV, "pip", "install", "--python", str(python), str(PROJECT_ROOT)],
        "uv pip install . (not -e)",
    )

    reader = tmp_path / "read_contract.py"
    reader.write_text(READ_INSTALLED_CONTRACT, encoding="utf-8")
    result = _run_or_fail(
        [str(python), str(reader)],
        "reading the contract out of the install",
        cwd=str(tmp_path),
    )
    report = json.loads(result.stdout)

    installed = Path(report["package_file"]).resolve()
    assert venv.resolve() in installed.parents, (
        f"the reader imported periplus from {installed}, which is not inside {venv}; "
        "this test only means anything against an installed copy"
    )
    assert PROJECT_ROOT not in installed.parents, (
        f"the reader imported periplus from {installed}, inside the project at {PROJECT_ROOT}; "
        "that is the source tree, and the source tree is not what ships"
    )

    files = report["files"]
    assert set(files) == EXPECTED_CONTRACT_FILES, (
        f"the install exposes {sorted(set(files) - EXPECTED_CONTRACT_FILES)} beyond the declared "
        f"contract, and is missing {sorted(EXPECTED_CONTRACT_FILES - set(files))}"
    )

    differing = sorted(
        shipped for shipped in EXPECTED_CONTRACT_FILES if files[shipped] != _source_text(shipped)
    )
    assert differing == [], f"the install's copy of {differing} differs from the working tree's"
