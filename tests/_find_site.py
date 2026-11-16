"""A tiny site for ``find``: a module of two classes, their methods, call sites and a parameter,
a test class, a name with no place, two calls between methods and the descriptions file."""

from __future__ import annotations

import json
from pathlib import Path

from _navigate import _document, _edge, _node

LOGIN = "cls::Login"
SUBMIT = "meth::Login::submit"
FORM = "meth::Login::form"
RECORD = "meth::Audit::record"

NODES = [
    _node("mod::shop", "t.module", line=1, file="shop/shop.info"),
    _node(LOGIN, "t.class", line=3, file="shop/Login.php"),
    _node(SUBMIT, "t.method", line=5, file="shop/Login.php"),
    _node("par::Login::submit::$name", "t.param", line=5, file="shop/Login.php"),
    _node("call::Login::submit::lock", "t.call", line=8, file="shop/Login.php"),
    _node(FORM, "t.method", line=20, file="shop/Login.php"),
    _node("call::Login::form::render", "t.call", line=22, file="shop/Login.php"),
    _node("cls::Audit", "t.class", line=1, file="shop/Audit.php"),
    _node(RECORD, "t.method", line=3, file="shop/Audit.php"),
    _node("call::Audit::record::write", "t.call", line=4, file="shop/Audit.php"),
    _node("cls::LoginTest", "t.class", line=1, file="tests/LoginTest.php"),
    _node("fn::login_check", "t.function", "unresolved"),
]
EDGES = [
    _edge("in_module", LOGIN, "mod::shop", 3, file="shop/Login.php"),
    _edge("in_module", "cls::Audit", "mod::shop", 1, file="shop/Audit.php"),
    _edge("calls", SUBMIT, RECORD, 9, file="shop/Login.php"),
    _edge("calls", FORM, RECORD, 23, file="shop/Login.php"),
]
LEGEND = {
    "edge_kinds": {
        "calls": "One method calls another, such as an audit write.",
        "in_module": "A class belongs to its module.",
    },
    "node_types": {},
}
DESCRIBED = """\
nodes:
  meth::Login::submit:
    text: Checks the password; blocks the account after five failures.
    file: shop/Login.php
    line: 5
  meth::Audit::record:
    text: Writes a login attempt to the log.
    file: shop/Audit.php
    line: 3
edges:
- from: meth::Login::submit
  kind: calls
  to: meth::Audit::record
  text: Records the failed attempt for the lockout count.
  file: shop/Login.php
  line: 9
"""
LOGIN_PHP = [""] * 25
LOGIN_PHP[8] = "        $this->audit->record($name);"
LOGIN_PHP[22] = "        $this->audit->record('blocked_admin');"


def site(root: Path, described: str = DESCRIBED) -> Path:
    """Write the map, the descriptions file and the one source file under ``root``; return the
    map's path."""
    document = _document(
        NODES[::-1],
        EDGES,
        grouping_kinds=["in_module"],
        supporting_paths=["tests/**"],
        legend=LEGEND,
    )
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    (root / "descriptions.yaml").write_text(described, encoding="utf-8")
    (root / "shop").mkdir()
    (root / "shop" / "Login.php").write_text("\n".join(LOGIN_PHP), encoding="utf-8")
    return path
