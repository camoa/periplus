"""compile_pattern: the named-group rewrite counts the backslashes before the group."""

import re
from pathlib import Path

import pytest
from test_demo_a_support import mapped, nodes, pin, plant, rutter

from periplus.cli import main
from periplus.engine.pattern import compile_pattern

MANIFEST = """\
pack: slashes
version: 0.0.1
depends: []
folders:
  scrolls: ./scrolls
files:
  types:
    scroll:
      endings: [scroll]
      reader: text
"""

# Two literal backslashes sit before the named group in the YAML text.
RULES = r"""
node_types:
- {name: slashes.item, id_namespace: slashes.item}
rules:
- {rule: item, reads: file, in: [scrolls],
   match: {file: '*', filetype: scroll, text: 'item \\(?<name>\w+)'},
   id: {from: {capture: name}}, emits: [{node: {type: slashes.item}}], confidence: declared}
"""


def test_two_backslashes_before_named_group_keep_the_group_c1() -> None:
    try:
        pattern = compile_pattern("a\\\\(?<ns>\\w+)")
    except re.error as error:
        pytest.fail(f"pattern did not compile: {error}")
    assert "ns" in pattern.groupindex
    match = pattern.search("a\\bc")
    assert match is not None
    assert match.group("ns") == "bc"


def test_lookbehinds_are_not_rewritten_c1() -> None:
    positive = compile_pattern("(?<=x)y")
    negative = compile_pattern("(?<!x)y")
    plain = compile_pattern("\\\\(?<=x)y")
    assert positive.pattern == "(?<=x)y"
    assert negative.pattern == "(?<!x)y"
    assert plain.pattern == "\\\\(?<=x)y"
    assert positive.search("xy") is not None
    assert negative.search("xy") is None


def test_single_backslash_leaves_the_paren_literal_c1() -> None:
    # \(?<n> is a literal paren, an optional "<", then the text n>.
    pattern = compile_pattern("\\(?<n>")
    assert pattern.groupindex == {}
    assert pattern.search("(<n>") is not None
    assert pattern.search("<n>") is not None


def test_pack_with_escaped_backslash_before_group_validates_and_fires_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rutter(tmp_path, "slashes", MANIFEST, {"slashes.yaml": RULES})
    pin(tmp_path, "slashes@0.0.1")
    plant(tmp_path, {"scrolls/one.scroll": "item \\alpha\n"})
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "slashes"]) == 0
    document = mapped(tmp_path)
    items = [n for n in nodes(document).values() if n["type"] == "slashes.item"]
    values = {n["id"].split("::")[1] for n in items}
    assert values == {"alpha"}
