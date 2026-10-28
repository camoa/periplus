"""Text rules: matches, path values, sections, reshaped values, unresolved ends and bindings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import edges, map_project, mapped, nodes, pin, plant, rutter

from periplus.errors import ExitCode
from periplus.map import MapReport

# --- a line format: one node per match, a captured owner, an edge to a captured name ----------

CHORES = """\
pack: chores
version: 0.0.1
depends: []
folders:
  lists: ./lists
files:
  types:
    chores:
      endings: [chores]
      reader: text
"""

CHORE_LINE = r"'(?m)^chore (?<name>\w+) by (?<who>\w+)(?: after (?<after>\w+))?$'"

CHORES_RULES = f"""\
node_types:
- {{name: chores.chore, id_namespace: chores.chore}}
edge_kinds:
- {{kind: waits_for, from: chores.chore, to: chores.chore}}
rules:
- rule: chore
  reads: file
  in: [lists]
  match: {{file: '*', filetype: chores, text: {CHORE_LINE}}}
  id: {{from: {{capture: name}}}}
  emits:
  - node: {{type: chores.chore}}
  - attribute: {{name: owner, from: {{capture: who}}}}
  confidence: declared
- rule: chore_waits
  reads: file
  in: [lists]
  match: {{file: '*', filetype: chores, text: {CHORE_LINE}}}
  id: {{from: {{capture: name}}}}
  emits:
  - edge: {{kind: waits_for, from: this_node, to: {{from: {{capture: after}}}}}}
  confidence: declared
"""

HOME = (
    "# the week\nchore dishes by ana\nchore laundry by ben after dishes\n\n"
    "chore floors by ana after sweeping\n"
)


def _chores(root: Path) -> None:
    rutter(root, "chores", CHORES, {"chores.yaml": CHORES_RULES})
    pin(root, "chores@0.0.1")
    plant(root, {"lists/home.chores": HOME})


def test_a_text_rule_gives_a_node_per_match_at_its_line_with_an_attribute_and_an_edge(
    tmp_path: Path,
) -> None:
    _chores(tmp_path)
    document = mapped(tmp_path)
    found = nodes(document)
    owners = {
        name: (found[f"chores.chore::{name}"]["attributes"]["owner"],
               [loc["line"] for loc in found[f"chores.chore::{name}"]["locations"]])
        for name in ("dishes", "laundry", "floors")
    }
    assert owners == {"dishes": ("ana", [2]), "laundry": ("ben", [3]), "floors": ("ana", [5])}
    assert edges(document) == {
        ("waits_for", "chores.chore::laundry", "chores.chore::dishes"),
        ("waits_for", "chores.chore::floors", "chores.chore::sweeping"),
    }


def test_a_captured_name_nothing_defines_as_a_node_is_in_state_referenced(tmp_path: Path) -> None:
    _chores(tmp_path)
    found = nodes(mapped(tmp_path))
    assert found["chores.chore::dishes"]["state"] == "mapped"
    assert found["chores.chore::sweeping"]["state"] == "referenced"


def test_a_file_with_carriage_return_line_feed_endings_gives_the_same_map(tmp_path: Path) -> None:
    _chores(tmp_path)
    lf = mapped(tmp_path)
    plant(tmp_path, {"lists/home.chores": HOME.replace("\n", "\r\n").encode()})
    assert mapped(tmp_path) == lf


def test_a_file_that_is_not_utf8_text_is_an_unreadable_source(tmp_path: Path) -> None:
    _chores(tmp_path)
    plant(tmp_path, {"lists/bad.chores": b"chore \xff by ana\n"})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.SOURCE_UNREADABLE
    assert any("bad.chores" in p.message for p in report.problems), report.problems


# --- values from a file's path ----------------------------------------------------------------

DECKS = """\
pack: decks
version: 0.0.1
depends: []
folders:
  shelf: ./shelf/*
files:
  types:
    box:
      endings: [box]
      reader: data
      format: yaml
      path_values:
        place:
          pattern: '^shelf/(?<folder>[^/]+)/[^/]+$'
          template: '{folder}'
        where:
          pattern: '^(?<path>.+)\\.box$'
          template: '{path}'
          normalize: [{replace: '/', with: '.'}]
          case: upper
    cards:
      endings: [cards]
      reader: text
      path_values:
        deck:
          pattern: '/(?<folder>[^/]+)/[^/]+$'
          template: '{folder}'
"""

CARD_LINE = r"'(?m)^card (?<name>\w+)(?: needs (?<needs>\w*))?$'"

DECKS_RULES = f"""\
node_types:
- {{name: decks.box, id_namespace: decks.box}}
- {{name: decks.place, id_namespace: decks.place}}
- {{name: decks.crate, id_namespace: decks.crate}}
- {{name: decks.card, id_namespace: decks.card}}
edge_kinds:
- {{kind: needs, from: decks.card, to: decks.card}}
rules:
- {{rule: box_file, reads: file, in: [shelf], match: {{file: '*', filetype: box}},
   id: {{from: file_stem, template: '{{place}}/{{file_stem}}'}},
   emits: [{{node: {{type: decks.box}}}}], confidence: declared}}
- {{rule: box_place, reads: file, in: [shelf], match: {{file: '*', filetype: box}},
   id: {{template: '{{place}}'}}, emits: [{{node: {{type: decks.place}}}}], confidence: declared}}
- {{rule: box_path, reads: file, in: [shelf], match: {{file: '*', filetype: box}},
   id: {{template: '{{where}}'}}, emits: [{{node: {{type: decks.crate}}}}], confidence: declared}}
- {{rule: card, reads: file, in: [shelf],
   match: {{file: '*', filetype: cards, text: {CARD_LINE}}},
   id: {{template: '{{deck}}.{{name}}'}}, emits: [{{node: {{type: decks.card}}}}],
   confidence: declared}}
- rule: card_needs
  reads: file
  in: [shelf]
  match: {{file: '*', filetype: cards, text: {CARD_LINE}}}
  id: {{template: '{{deck}}.{{name}}'}}
  emits:
  - edge: {{kind: needs, from: this_node, to: {{template: '{{deck}}.{{needs}}'}}}}
  confidence: declared
"""

# The last card's "needs" is empty: a trailing space after it.
CARDS = "card ace\ncard king needs ace\ncard queen needs \n"


def _decks(root: Path, manifest: str = DECKS, rules: str = DECKS_RULES) -> None:
    rutter(root, "decks", manifest, {"decks.yaml": rules})
    pin(root, "decks@0.0.1")
    plant(
        root,
        {
            "shelf/alpha/crate.box": "size: 1\n",
            "shelf/beta/crate.box": "size: 2\n",
            "shelf/alpha/hand.cards": CARDS,
        },
    )


@pytest.fixture(scope="module")
def decks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("decks")
    _decks(root)
    return mapped(root)


def test_two_files_of_one_name_in_two_folders_give_two_nodes_named_by_their_paths(
    decks: dict[str, Any],
) -> None:
    found = nodes(decks)
    assert found["decks.box::alpha/crate"]["locations"] == [
        {"file": "shelf/alpha/crate.box", "line": 1}
    ]
    assert found["decks.box::beta/crate"]["locations"] == [
        {"file": "shelf/beta/crate.box", "line": 1}
    ]
    assert {i for i in found if i.startswith("decks.box::")} == {
        "decks.box::alpha/crate",
        "decks.box::beta/crate",
    }


def test_a_data_file_gives_a_node_named_by_its_parent_folder(decks: dict[str, Any]) -> None:
    found = nodes(decks)
    assert found["decks.place::alpha"]["state"] == "mapped"
    assert found["decks.place::beta"]["state"] == "mapped"


def test_a_path_value_drops_the_ending_replaces_the_separators_and_raises_the_case(
    decks: dict[str, Any],
) -> None:
    assert {i for i in nodes(decks) if i.startswith("decks.crate::")} == {
        "decks.crate::SHELF.ALPHA.CRATE",
        "decks.crate::SHELF.BETA.CRATE",
    }


def test_a_text_match_is_named_by_a_path_value_joined_with_a_capture_and_an_edge_end_reaches_it(
    decks: dict[str, Any],
) -> None:
    found = nodes(decks)
    assert found["decks.card::alpha.king"]["locations"] == [
        {"file": "shelf/alpha/hand.cards", "line": 2}
    ]
    assert edges(decks, "needs") == {("needs", "decks.card::alpha.king", "decks.card::alpha.ace")}
    assert found["decks.card::alpha.ace"]["state"] == "mapped"


def test_a_path_value_named_like_a_value_the_engine_fills_is_a_pack_problem(
    tmp_path: Path,
) -> None:
    _decks(
        tmp_path,
        DECKS.replace("        place:\n", "        file_stem:\n"),
        DECKS_RULES.replace("{place}", "{file_stem}"),
    )
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    assert any(
        dict(p.detail) == {"pack": "decks", "file": "pack.yaml", "name": "file_stem"}
        for p in report.problems
    ), report.problems


# --- sections a text rule does not read ---------------------------------------------------------

SCROLLS = """\
pack: scrolls
version: 0.0.1
depends: []
folders:
  scrolls: ./scrolls
files:
  types:
    scroll:
      endings: [scroll]
      reader: text
      sections:
      - name: remark
        open: '#\\['
        close: '\\]#'
      - name: quote
        open: '(?<mark>["''])'
        close: '{mark}'
"""

SCROLLS_RULES = """\
node_types:
- {name: scrolls.item, id_namespace: scrolls.item}
- {name: scrolls.quoted, id_namespace: scrolls.quoted}
rules:
- {rule: item, reads: file, in: [scrolls],
   match: {file: '*', filetype: scroll, text: 'item (?<name>\\w+)'},
   id: {from: {capture: name}}, emits: [{node: {type: scrolls.item}}], confidence: declared}
- {rule: quoted, reads: file, in: [scrolls],
   match: {file: '*', filetype: scroll, text: 'item (?<name>\\w+)', reads_sections: [quote]},
   id: {from: {capture: name}}, emits: [{node: {type: scrolls.quoted}}], confidence: declared}
"""

SCROLL = """\
item alpha
#[ item remarked ]# item beta
" it's item doubled " item gamma
' say "item singled" ' item delta
#[ item unclosed
item after
"""


@pytest.fixture(scope="module")
def scrolls(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    root = tmp_path_factory.mktemp("scrolls")
    rutter(root, "scrolls", SCROLLS, {"scrolls.yaml": SCROLLS_RULES})
    pin(root, "scrolls@0.0.1")
    plant(root, {"scrolls/one.scroll": SCROLL})
    document = mapped(root)
    return {
        kind: {n["id"].split("::")[1] for n in document["nodes"] if n["type"] == kind}
        for kind in ("scrolls.item", "scrolls.quoted")
    }


def test_a_match_starting_inside_a_section_gives_nothing_and_the_same_words_outside_give_nodes(
    scrolls: dict[str, set[str]],
) -> None:
    assert scrolls["scrolls.item"] == {"alpha", "beta", "gamma", "delta"}


def test_a_section_opened_by_one_of_two_markers_ends_at_the_same_marker_only(
    scrolls: dict[str, set[str]],
) -> None:
    # The apostrophe inside the double quotes, and the double quotes inside the single, end nothing:
    # gamma and delta follow them and are found.
    assert {"gamma", "delta"} <= scrolls["scrolls.item"]
    assert not {"doubled", "singled"} & scrolls["scrolls.item"]


def test_a_section_never_closed_runs_to_the_end_of_the_file(scrolls: dict[str, set[str]]) -> None:
    assert not {"unclosed", "after"} & scrolls["scrolls.item"]


def test_a_rule_naming_a_section_under_reads_sections_matches_inside_it(
    scrolls: dict[str, set[str]],
) -> None:
    # It reads the quote sections as well as the text outside every section, and not the remark
    # or the section never closed.
    assert scrolls["scrolls.quoted"] == scrolls["scrolls.item"] | {"doubled", "singled"}


# --- a captured value reshaped -----------------------------------------------------------------

GRIMOIRE = """\
pack: grimoire
version: 0.0.1
depends: []
folders:
  book: ./book
files:
  types:
    spells:
      endings: [spells]
      reader: text
"""

SPELL_LINE = r"'(?m)^spell (?<name>\w+) from (?<school>\w*)$'"
SLUG = """\
    slug:
      from: {capture: name}
      normalize: [{replace: '_', with: '-'}]
      case: lower
"""

GRIMOIRE_RULES = f"""\
node_types:
- {{name: grimoire.spell, id_namespace: grimoire.spell}}
- {{name: grimoire.school, id_namespace: grimoire.school}}
edge_kinds:
- {{kind: teaches, from: grimoire.school, to: grimoire.spell}}
rules:
- rule: spell
  reads: file
  in: [book]
  match: {{file: '*', filetype: spells, text: {SPELL_LINE}}}
  values:
{SLUG}    label:
      template: '{{slug}}@{{school}}'
  id: {{template: '{{slug}}'}}
  emits:
  - attribute: {{name: slug, from: {{value: slug}}}}
  - attribute: {{name: label, template: '[{{label}}]'}}
  - node: {{type: grimoire.spell}}
  confidence: declared
- rule: school
  reads: file
  in: [book]
  match: {{file: '*', filetype: spells, text: '(?m)^school (?<name>\\w+)$'}}
  id: {{from: {{capture: name}}}}
  emits: [{{node: {{type: grimoire.school}}}}]
  confidence: declared
- rule: school_teaches
  reads: file
  in: [book]
  match: {{file: '*', filetype: spells, text: {SPELL_LINE}}}
  values:
{SLUG}  id: {{template: '{{slug}}'}}
  emits:
  - edge: {{kind: teaches, from: {{from: {{capture: school}}}}, to: this_node}}
  confidence: declared
"""

# The last line's school is empty: a trailing space after "from".
SPELLS = (
    "school Flame\nspell Fire_Ball from Flame\nspell Ice_SHARD from Frost\n"
    "spell Lone_Word from \n"
)


@pytest.fixture(scope="module")
def grimoire(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("grimoire")
    rutter(root, "grimoire", GRIMOIRE, {"grimoire.yaml": GRIMOIRE_RULES})
    pin(root, "grimoire@0.0.1")
    plant(root, {"book/one.spells": SPELLS})
    return mapped(root)


def test_a_captured_name_gives_an_attribute_in_lower_case_with_dashes_and_the_node_id(
    grimoire: dict[str, Any],
) -> None:
    """The attribute rows come before the node row in the rule's emits, and the rule still runs."""
    found = nodes(grimoire)
    assert found["grimoire.spell::fire-ball"]["attributes"] == {
        "slug": "fire-ball",
        "label": "[fire-ball@Flame]",
    }
    assert found["grimoire.spell::ice-shard"]["attributes"]["slug"] == "ice-shard"


def test_an_edge_from_an_end_built_from_a_capture_to_this_node_reaches_the_spell(
    grimoire: dict[str, Any],
) -> None:
    assert edges(grimoire) == {
        ("teaches", "grimoire.school::Flame", "grimoire.spell::fire-ball"),
        ("teaches", "grimoire.school::Frost", "grimoire.spell::ice-shard"),
    }
    assert nodes(grimoire)["grimoire.school::Flame"]["state"] == "mapped"
    assert nodes(grimoire)["grimoire.school::Frost"]["state"] == "referenced"


def test_an_edge_end_whose_capture_is_empty_makes_no_edge_and_no_node(
    grimoire: dict[str, Any],
) -> None:
    assert "grimoire.spell::lone-word" in nodes(grimoire)
    assert not [e for e in grimoire["edges"] if e["to"] == "grimoire.spell::lone-word"]
    assert not [i for i in nodes(grimoire) if i.endswith("::")]


def test_a_value_whose_template_names_a_value_defined_after_it_makes_the_rule_not_executable(
    tmp_path: Path,
) -> None:
    rutter(
        tmp_path,
        "grimoire",
        GRIMOIRE,
        {
            "grimoire.yaml": """\
node_types:
- {name: grimoire.spell, id_namespace: grimoire.spell}
rules:
- rule: spell
  reads: file
  in: [book]
  match: {file: '*', filetype: spells, text: '(?m)^spell (?<name>\\w+)$'}
  values:
    early:
      template: '{tardy}!'
    tardy:
      from: {capture: name}
  id: {template: '{early}'}
  emits: [{node: {type: grimoire.spell}}]
  confidence: declared
"""
        },
    )
    pin(tmp_path, "grimoire@0.0.1")
    plant(tmp_path, {"book/one.spells": "spell Fire\n"})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    messages = [p.message for p in report.problems if p.code == ExitCode.RULE_NOT_EXECUTABLE]
    assert len(messages) == 1 and "early" in messages[0] and "tardy" in messages[0], report.problems


# --- an edge end that names nothing mapped -----------------------------------------------------

BENCH = """\
pack: bench
version: 0.0.1
depends: []
folders:
  plans: ./plans
files:
  types:
    bench:
      endings: [bench]
      reader: text
"""

BENCH_RULES = """\
node_types:
- {name: bench.tool, id_namespace: bench.tool}
- {name: bench.task, id_namespace: bench.task}
- {name: bench.note, id_namespace: bench.note}
edge_kinds:
- {kind: uses, from: bench.task, to: bench.tool}
- {kind: mentions, from: bench.note, to: bench.tool}
rules:
- {rule: tool, reads: file, in: [plans],
   match: {file: '*', filetype: bench, text: '(?m)^tool (?<name>\\w+)$'},
   id: {from: {capture: name}}, emits: [{node: {type: bench.tool}}], confidence: declared}
- {rule: task, reads: file, in: [plans],
   match: {file: '*', filetype: bench, text: '(?m)^task (?<name>\\w+) uses (?<tool>\\w+)$'},
   id: {from: {capture: name}}, emits: [{node: {type: bench.task}}], confidence: declared}
- rule: task_uses
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^task (?<name>\\w+) uses (?<tool>\\w+)$'}
  id: {from: {capture: name}}
  emits:
  - edge: {kind: uses, from: this_node, to: {from: {capture: tool}, on_miss: unresolved}}
  confidence: declared
- {rule: note, reads: file, in: [plans],
   match: {file: '*', filetype: bench, text: '(?m)^note (?<tool>\\w+)$'},
   id: {from: {capture: tool}}, emits: [{node: {type: bench.note}}], confidence: declared}
- rule: note_mentions
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^note (?<tool>\\w+)$'}
  id: {from: {capture: tool}}
  emits:
  - edge: {kind: mentions, from: this_node, to: {from: {capture: tool}}}
  confidence: declared
"""


@pytest.fixture(scope="module")
def bench(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("bench")
    rutter(root, "bench", BENCH, {"bench.yaml": BENCH_RULES})
    pin(root, "bench@0.0.1")
    plant(
        root,
        {
            "plans/shed.bench": "tool hammer\ntask build uses hammer\n"
            "task paint uses brush\nnote brush\nnote chisel\n"
        },
    )
    return mapped(root)


def test_an_end_declared_on_miss_unresolved_is_a_node_in_that_state_recording_what_was_searched(
    bench: dict[str, Any],
) -> None:
    brush = nodes(bench)["bench.tool::brush"]
    assert brush["state"] == "unresolved" and brush["locations"] == []
    assert brush["type"] == "bench.tool"
    detail = brush["unresolved_detail"]
    assert detail["rule"] == "bench/task_uses"
    assert detail["searched_for"] == "brush"
    assert detail["types_tried"] == ["bench.tool"]
    assert bench["counts"]["nodes_by_state"]["unresolved"] == 1


def test_an_end_declared_on_miss_unresolved_that_finds_its_node_is_an_ordinary_edge(
    bench: dict[str, Any],
) -> None:
    assert ("uses", "bench.task::build", "bench.tool::hammer") in edges(bench)
    hammer = nodes(bench)["bench.tool::hammer"]
    assert hammer["state"] == "mapped" and "unresolved_detail" not in hammer


def test_an_end_without_on_miss_that_names_nothing_mapped_is_a_node_in_state_referenced(
    bench: dict[str, Any],
) -> None:
    chisel = nodes(bench)["bench.tool::chisel"]
    assert chisel["state"] == "referenced" and "unresolved_detail" not in chisel


def test_an_unresolved_node_reached_also_by_an_edge_without_on_miss_stays_unresolved(
    bench: dict[str, Any],
) -> None:
    assert ("mentions", "bench.note::brush", "bench.tool::brush") in edges(bench)
    assert nodes(bench)["bench.tool::brush"]["state"] == "unresolved"


# --- names bound by a text rule and resolved by declared steps ---------------------------------

MODS = """\
pack: mods
version: 0.0.1
depends: []
folders:
  src: ./src/**
files:
  types:
    mod:
      endings: [mod]
      reader: text
      path_values:
        module:
          pattern: '(?<package>\\w+)/(?<file>\\w+)\\.mod$'
          template: '{package}.{file}'
      resolve:
      - full_if_prefixed: '~'
      - bound_first_segment
      - prefix_with: module
      separator: '.'
"""

MODS_RULES = """\
node_types:
- {name: mods.module, id_namespace: mods.module}
- {name: mods.function, id_namespace: mods.function}
edge_kinds:
- {kind: calls, from: mods.module, to: mods.function}
rules:
- {rule: module, reads: file, in: [src], match: {file: '*', filetype: mod, text: '\\A'},
   id: {template: '{module}'}, emits: [{node: {type: mods.module}}], confidence: declared}
- {rule: function, reads: file, in: [src],
   match: {file: '*', filetype: mod, text: '(?m)^def (?<name>\\w+)$'},
   id: {from: {capture: name}, resolve: [{prefix_with: module}], separator: '.'},
   emits: [{node: {type: mods.function}}], confidence: declared}
- rule: call
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^call (?<name>[~\\w.]+)$'}
  id: {template: '{module}'}
  emits:
  - edge: {kind: calls, from: this_node, to: {from: {capture: name}, on_miss: unresolved}}
  confidence: declared
- rule: call_as_written
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^extern (?<name>[\\w.]+)$'}
  id: {template: '{module}'}
  emits:
  - edge: {kind: calls, from: this_node, to: {from: {capture: name}, resolve: [as_written]}}
  confidence: declared
- rule: import_alias
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^import (?<path>[\\w.]+) as (?<alias>\\w+)$'}
  emits: [{binding: {name: '{alias}', target: '{path}'}}]
  confidence: declared
- rule: import_plain
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^import (?<path>(?:\\w+\\.)*(?<last>\\w+))$'}
  emits: [{binding: {name: '{last}', target: '{path}'}}]
  confidence: declared
- rule: import_group
  reads: file
  in: [src]
  match:
    file: '*'
    filetype: mod
    text: '(?m)(?<member>\\b\\w+)(?=(?:, \\w+)*\\} from (?<prefix>[\\w.]+)$)'
  emits: [{binding: {name: '{member}', target: '{prefix}.{member}'}}]
  confidence: declared
"""

SHOP = """\
import tools.hammer as h
import tools.file
import tools.saw
import {brush, roller} from tools.paint
import tools.drill as saw
def local
call h.strike
call file.read
call saw.cut
call brush
call roller.spin
call ~lib.glue
call local
call nowhere.thing
extern h.strike
"""


@pytest.fixture(scope="module")
def shop(tmp_path_factory: pytest.TempPathFactory) -> tuple[MapReport, dict[str, Any]]:
    root = tmp_path_factory.mktemp("mods")
    rutter(root, "mods", MODS, {"mods.yaml": MODS_RULES})
    pin(root, "mods@0.0.1")
    plant(root, {"src/tools/paint.mod": "def brush\ndef roller\n", "src/app/shop.mod": SHOP})
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def _reached(document: dict[str, Any]) -> dict[int, str]:
    """The end of each edge the shop module states, keyed by the line it is written on."""
    return {
        place["line"]: edge["to"]
        for edge in document["edges"]
        if edge["from"] == "mods.module::app.shop"
        for place in edge["locations"]
        if place["file"] == "src/app/shop.mod"
    }


@pytest.mark.parametrize(
    ("written", "full"),
    [
        ("h.strike", "tools.hammer.strike"),
        ("file.read", "tools.file.read"),
        ("saw.cut", "tools.drill.cut"),
        ("brush", "tools.paint.brush"),
        ("roller.spin", "tools.paint.roller.spin"),
        ("~lib.glue", "lib.glue"),
        ("local", "app.shop.local"),
        ("nowhere.thing", "app.shop.nowhere.thing"),
    ],
    ids=[
        "an alias",
        "the last segment of an import",
        "a later binding of a name wins",
        "a member of a grouped import",
        "a grouped member with a rest",
        "a name with the full prefix",
        "a name the module defines",
        "a name nothing binds",
    ],
)
def test_a_call_ends_at_the_meaning_its_written_name_has(
    shop: tuple[MapReport, dict[str, Any]], written: str, full: str
) -> None:
    # Keyed by the line the call is written on, so two ends swapped between lines cannot pass.
    line = SHOP.splitlines().index(f"call {written}") + 1
    assert _reached(shop[1])[line] == f"mods.function::{full}"


def test_a_name_resolved_as_written_is_left_as_written(
    shop: tuple[MapReport, dict[str, Any]],
) -> None:
    line = SHOP.splitlines().index("extern h.strike") + 1
    assert _reached(shop[1])[line] == "mods.function::h.strike"
    assert nodes(shop[1])["mods.function::h.strike"]["state"] == "referenced"


def test_a_resolved_end_is_mapped_when_a_file_defines_it_and_unresolved_when_none_does(
    shop: tuple[MapReport, dict[str, Any]],
) -> None:
    found = nodes(shop[1])
    assert found["mods.function::app.shop.local"]["state"] == "mapped"
    assert found["mods.function::tools.paint.brush"]["state"] == "mapped"
    assert found["mods.function::lib.glue"]["state"] == "unresolved"


def test_a_binding_rules_fires_are_the_bindings_it_gave(
    shop: tuple[MapReport, dict[str, Any]],
) -> None:
    fires = {rule: count for pack, rule, count in shop[0].executed if pack == "mods"}
    assert (fires["import_alias"], fires["import_plain"], fires["import_group"]) == (2, 2, 2)


# --- an edge end that lists two candidate types -------------------------------------------------

LINKS = """\
pack: links
version: 0.0.1
depends: []
folders:
  pages: ./pages/**
files:
  types:
    lnk:
      endings: [lnk]
      reader: text
      path_values:
        page:
          pattern: '(?<page>\\w+)\\.lnk$'
          template: '{page}'
"""

LINKS_RULES = """\
node_types:
- {name: links.page, id_namespace: links.page}
- {name: links.widget, id_namespace: links.widget}
- {name: links.gadget, id_namespace: links.gadget}
edge_kinds:
- {kind: uses, from: links.page, to: [links.widget, links.gadget]}
rules:
- {rule: page, reads: file, in: [pages], match: {file: '*', filetype: lnk, text: '\\A'},
   id: {template: '{page}'}, emits: [{node: {type: links.page}}], confidence: declared}
- {rule: widget, reads: file, in: [pages],
   match: {file: '*', filetype: lnk, text: '(?m)^widget (?<name>\\w+)$'},
   id: {from: {capture: name}}, emits: [{node: {type: links.widget}}], confidence: declared}
- {rule: gadget, reads: file, in: [pages],
   match: {file: '*', filetype: lnk, text: '(?m)^gadget (?<name>\\w+)$'},
   id: {from: {capture: name}}, emits: [{node: {type: links.gadget}}], confidence: declared}
- rule: use
  reads: file
  in: [pages]
  match: {file: '*', filetype: lnk, text: '(?m)^use (?<name>\\w+)$'}
  id: {template: '{page}'}
  emits:
  - edge:
      kind: uses
      from: this_node
      to: {from: {capture: name}, types: [links.widget, links.gadget], on_miss: unresolved}
  confidence: declared
"""


@pytest.fixture(scope="module")
def links(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("links")
    rutter(root, "links", LINKS, {"links.yaml": LINKS_RULES})
    pin(root, "links@0.0.1")
    plant(root, {"pages/home.lnk": "gadget knob\nwidget dial\nuse knob\nuse dial\nuse ghost\n"})
    return mapped(root)


def test_an_end_listing_two_types_lands_on_the_type_the_name_is_mapped_under(
    links: dict[str, Any],
) -> None:
    found = nodes(links)
    reached = {
        (edge["to"], place["line"])
        for edge in links["edges"]
        if edge["from"] == "links.page::home"
        for place in edge["locations"]
    }
    assert reached == {
        ("links.gadget::knob", 3),
        ("links.widget::dial", 4),
        ("links.widget::ghost", 5),
    }
    assert found["links.gadget::knob"]["state"] == "mapped"
    assert found["links.widget::dial"]["state"] == "mapped"
    assert "links.widget::knob" not in found


def test_an_unknown_name_on_an_end_listing_two_types_is_unresolved_in_the_first_listing_both(
    links: dict[str, Any],
) -> None:
    ghost = nodes(links)["links.widget::ghost"]
    assert ghost["state"] == "unresolved" and ghost["type"] == "links.widget"
    assert ghost["unresolved_detail"]["searched_for"] == "ghost"
    assert ghost["unresolved_detail"]["types_tried"] == ["links.widget", "links.gadget"]
    assert "links.gadget::ghost" not in nodes(links)
