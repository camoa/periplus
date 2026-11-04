"""The three map writers behind ``periplus export``: GraphML, DOT and Mermaid.

Each test hands a planted map document to a writer in ``WRITERS`` and reads what comes back:
the text and the warnings. No file is read and no process is started.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import pytest

# Ids built to break a careless writer: the namespace separator, a dollar sign, an arrow, quotes.
NASTY_IDS = (
    "py.module::a$b",
    "x->y::z",
    'say "hi"::q',
    "plain::one",
)
GRAPHML_NS = "{http://graphml.graphdrawing.org/xmlns}"


def _node(
    node_id: str, node_type: str, state: str, locations: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "state": state,
        "locations": locations,
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }


def _edge(kind: str, source: str, target: str, locations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": locations,
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }


def _document(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "periplus_map_version": 0,
        "packs": [{"pack": "core", "version": "1"}],
        "roots": ["."],
        "nodes": nodes,
        "edges": edges,
    }


def _nasty_map() -> dict[str, Any]:
    types = ("t.alpha", "t.beta", "t.gamma", "t.delta")
    nodes = [
        _node(NASTY_IDS[i], types[i], "mapped", [{"file": f"src/f{i}.py", "line": i + 1}])
        for i in range(4)
    ]
    edges = [
        _edge("calls", NASTY_IDS[0], NASTY_IDS[1], [{"file": "src/f0.py", "line": 7}]),
        _edge("imports", NASTY_IDS[1], NASTY_IDS[2], []),
        _edge("extends", NASTY_IDS[3], NASTY_IDS[2], [{"file": "src/f3.py", "line": 2}]),
    ]
    return _document(nodes, edges)


QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


def _unescape_dot(quoted: str) -> str:
    return quoted[1:-1].replace('\\"', '"').replace("\\\\", "\\")


@pytest.mark.criterion(id="c4")
def test_dot_quotes_every_id_and_labels_nodes_with_id_and_type_and_edges_with_kind_c4() -> None:
    from periplus.navigate.export import WRITERS

    document = _nasty_map()
    text, warnings = WRITERS["dot"](document)
    again, _ = WRITERS["dot"](document)

    assert text == again
    assert text.lstrip().startswith("digraph")
    assert warnings == ()

    node_lines: list[list[str]] = []
    edge_lines: list[list[str]] = []
    for line in text.splitlines():
        quoted = [_unescape_dot(q) for q in QUOTED.findall(line)]
        outside = QUOTED.sub("", line)
        # Nothing odd may sit outside a quoted string: the id characters are all inside quotes.
        assert "::" not in outside and "$" not in outside, line
        assert '"' not in outside, line
        words = outside.split()
        if not quoted or (words and words[0] in {"node", "edge", "graph"}):
            continue
        (edge_lines if "->" in outside else node_lines).append(quoted)

    assert len(node_lines) == len(document["nodes"])
    assert len(edge_lines) == len(document["edges"])

    by_id = {quoted[0]: quoted for quoted in node_lines}
    assert set(by_id) == set(NASTY_IDS)
    for node in document["nodes"]:
        label = " ".join(by_id[node["id"]][1:])
        assert node["id"] in label
        assert node["type"] in label

    got = sorted((quoted[0], quoted[1], quoted[2]) for quoted in edge_lines if len(quoted) >= 3)
    want = sorted((e["from"], e["to"], e["kind"]) for e in document["edges"])
    assert [(a, b, k) for a, b, k in got] == want


def _mermaid_parts(text: str) -> tuple[dict[str, str], list[str]]:
    """Return token -> label for each node line, and the edge lines, with the head line removed."""
    nodes: dict[str, str] = {}
    edges: list[str] = []
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[1:]:
        found = re.match(r'^\s*(\w+)\["(.*)"\]\s*$', line)
        if found:
            nodes[found.group(1)] = found.group(2)
        else:
            edges.append(line)
    return nodes, edges


@pytest.mark.criterion(id="c4")
def test_mermaid_uses_generated_node_tokens_with_quoted_id_and_type_labels_c4() -> None:
    from periplus.navigate.export import WRITERS

    document = _nasty_map()
    text, warnings = WRITERS["mermaid"](document)
    again, _ = WRITERS["mermaid"](document)

    assert text == again
    assert text.lstrip().startswith("flowchart")
    assert warnings == ()

    nodes, edge_lines = _mermaid_parts(text)
    assert len(nodes) == len(document["nodes"])
    assert len(edge_lines) == len(document["edges"])

    for token in nodes:
        assert not any(piece in token for node in document["nodes"] for piece in (node["id"],))
    token_of: dict[str, str] = {}
    for node in document["nodes"]:
        matches = [
            token
            for token, label in nodes.items()
            if all(piece in label for piece in node["id"].split('"')) and node["type"] in label
        ]
        assert len(matches) == 1, node["id"]
        token_of[node["id"]] = matches[0]
    assert len(set(token_of.values())) == len(document["nodes"])

    # Outside the quoted labels there is no raw id character.
    outside = re.sub(r'"[^"]*"', "", text)
    assert "::" not in outside and "$" not in outside

    got = []
    for line in edge_lines:
        words = re.findall(r"\w+", line)
        kinds = [e["kind"] for e in document["edges"] if e["kind"] in words]
        assert len(kinds) == 1, line
        got.append((words[0], words[-1], kinds[0]))
    inverse = {token: node_id for node_id, token in token_of.items()}
    assert sorted((inverse[a], inverse[b], k) for a, b, k in got) == sorted(
        (e["from"], e["to"], e["kind"]) for e in document["edges"]
    )


@pytest.mark.criterion(id="c4")
def test_mermaid_above_500_edges_carries_a_warning_naming_the_limit_c4() -> None:
    from periplus.navigate.export import WRITERS

    nodes = [_node("m::a", "t.x", "mapped", []), _node("m::b", "t.x", "mapped", [])]
    edges = [_edge("calls", "m::a", "m::b", []) for _ in range(501)]
    text, warnings = WRITERS["mermaid"](_document(nodes, edges))

    assert text.lstrip().startswith("flowchart")
    assert len(warnings) >= 1
    assert any("500" in warning for warning in warnings)

    few, none = WRITERS["mermaid"](_document(nodes, edges[:500]))
    assert none == ()


@pytest.mark.criterion(id="c4")
def test_mermaid_above_50000_characters_carries_a_warning_naming_the_limit_c4() -> None:
    from periplus.navigate.export import WRITERS

    long_id = "m::" + "x" * 2000
    nodes = [_node(f"{long_id}{i}", "t.x", "mapped", []) for i in range(30)]
    edges = [_edge("calls", nodes[0]["id"], nodes[1]["id"], [])]
    text, warnings = WRITERS["mermaid"](_document(nodes, edges))

    assert len(text) > 50000
    assert any("50,000" in warning or "50000" in warning for warning in warnings)


def _graphml_keys(root: ET.Element) -> dict[str, tuple[str, str, str]]:
    return {
        key.attrib["id"]: (key.attrib["for"], key.attrib["attr.name"], key.attrib["attr.type"])
        for key in root.findall(f"{GRAPHML_NS}key")
    }


def _data(element: ET.Element, keys: dict[str, tuple[str, str, str]]) -> dict[str, str]:
    return {
        keys[data.attrib["key"]][1]: data.text or ""
        for data in element.findall(f"{GRAPHML_NS}data")
    }


@pytest.mark.criterion(id="c3")
def test_graphml_holds_seven_keys_and_locations_only_where_present_c3() -> None:
    from periplus.navigate.export import WRITERS

    nodes = [
        _node(
            "py.module::a$b",
            "py.module",
            "mapped",
            [{"file": "src/a.py", "line": 3}, {"file": "src/second.py", "line": 9}],
        ),
        _node("x->y::z", "py.func", "referenced", []),
        _node('say "hi"::q', "py.func", "declared", [{"file": "src/q.py", "line": 12}]),
    ]
    edges = [
        _edge("calls", "py.module::a$b", "x->y::z", [{"file": "src/a.py", "line": 5}]),
        _edge("imports", "x->y::z", 'say "hi"::q', []),
    ]
    document = _document(nodes, edges)
    text, warnings = WRITERS["graphml"](document)
    again, _ = WRITERS["graphml"](document)

    assert text == again
    assert warnings == ()

    root = ET.fromstring(text)  # noqa: S314 -- the text is this test's own writer output
    assert root.tag == f"{GRAPHML_NS}graphml"
    keys = _graphml_keys(root)
    assert sorted(keys.values()) == sorted(
        [
            ("node", "type", "string"),
            ("node", "state", "string"),
            ("node", "file", "string"),
            ("node", "line", "int"),
            ("edge", "kind", "string"),
            ("edge", "file", "string"),
            ("edge", "line", "int"),
        ]
    )
    assert len(keys) == 7

    graphs = root.findall(f"{GRAPHML_NS}graph")
    assert len(graphs) == 1
    graph = graphs[0]
    assert graph.attrib["edgedefault"] == "directed"

    node_elements = graph.findall(f"{GRAPHML_NS}node")
    edge_elements = graph.findall(f"{GRAPHML_NS}edge")
    assert len(node_elements) == 3
    assert len(edge_elements) == 2

    by_id = {element.attrib["id"]: _data(element, keys) for element in node_elements}
    assert by_id["py.module::a$b"] == {
        "type": "py.module",
        "state": "mapped",
        "file": "src/a.py",
        "line": "3",
    }
    assert by_id["x->y::z"] == {"type": "py.func", "state": "referenced"}
    assert by_id['say "hi"::q'] == {
        "type": "py.func",
        "state": "declared",
        "file": "src/q.py",
        "line": "12",
    }

    got = sorted(
        (
            element.attrib["source"],
            element.attrib["target"],
            tuple(sorted(_data(element, keys).items())),
        )
        for element in edge_elements
    )
    assert got == [
        (
            "py.module::a$b",
            "x->y::z",
            (("file", "src/a.py"), ("kind", "calls"), ("line", "5")),
        ),
        ("x->y::z", 'say "hi"::q', (("kind", "imports"),)),
    ]


@pytest.mark.criterion(id="wo2")
def test_graphml_writes_each_elements_data_in_one_fixed_order_wo2() -> None:
    from periplus.navigate.export import WRITERS

    ids = ("c::three", "a::one", "b::two")
    nodes = [
        _node(i, "t.x", "mapped", [{"file": f"src/{n}.py", "line": n + 1}])
        for n, i in enumerate(ids)
    ]
    edges = [_edge("calls", ids[0], ids[1], [{"file": "src/e.py", "line": 4}])]
    document = _document(nodes, edges)

    root = ET.fromstring(WRITERS["graphml"](document)[0])  # noqa: S314 -- own writer output
    keys = _graphml_keys(root)
    key_order = [
        (keys[key.attrib["id"]][0], keys[key.attrib["id"]][1])
        for key in root.findall(f"{GRAPHML_NS}key")
    ]
    assert key_order == [
        ("node", "type"),
        ("node", "state"),
        ("node", "file"),
        ("node", "line"),
        ("edge", "kind"),
        ("edge", "file"),
        ("edge", "line"),
    ]

    graph = root.findall(f"{GRAPHML_NS}graph")[0]
    for element in graph.findall(f"{GRAPHML_NS}node"):
        order = [keys[d.attrib["key"]][1] for d in element.findall(f"{GRAPHML_NS}data")]
        assert order == ["type", "state", "file", "line"]
    for element in graph.findall(f"{GRAPHML_NS}edge"):
        order = [keys[d.attrib["key"]][1] for d in element.findall(f"{GRAPHML_NS}data")]
        assert order == ["kind", "file", "line"]

    dot = WRITERS["dot"](document)[0]
    dot_nodes = []
    for line in dot.splitlines():
        outside = QUOTED.sub("", line)
        words = outside.split()
        if "->" in outside or "[" not in outside or words[0] in {"node", "edge", "graph"}:
            continue
        dot_nodes.append(_unescape_dot(QUOTED.findall(line)[0]))
    assert dot_nodes == list(ids)

    mermaid_nodes, _ = _mermaid_parts(WRITERS["mermaid"](document)[0])
    labels = list(mermaid_nodes.values())
    assert [next(i for i in ids if i in label) for label in labels] == list(ids)
