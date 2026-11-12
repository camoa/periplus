"""Print the gap report of a Periplus map. Run it from the project root on .periplus/map.json."""

from __future__ import annotations

import io
import json
import re
import string
import sys
from pathlib import Path
from typing import TypedDict, cast


class Location(TypedDict):
    file: str
    line: int


class RuleName(TypedDict):
    pack: str
    rule: str


class Provenance(RuleName, total=False):
    confidence: str
    sets: list[str]


class NodeKeys(TypedDict):
    id: str
    type: str
    state: str
    locations: list[Location]
    provenance: list[Provenance]


class Node(NodeKeys, total=False):
    attributes: dict[str, object]


# `from` is a keyword, so this type cannot use the class form.
Edge = TypedDict(
    "Edge",
    {
        "kind": str,
        "from": str,
        "to": str,
        "locations": list[Location],
        "provenance": list[Provenance],
    },
)


class Pack(TypedDict):
    pack: str


class TypeRow(TypedDict):
    type: str
    parent: str | None


class MapFile(TypedDict):
    nodes: list[Node]
    edges: list[Edge]
    packs: list[Pack]
    type_hierarchy: list[TypeRow]


NOWHERE: Location = {"file": "-", "line": 0}
MAP_KEYS = {"nodes", "edges", "packs", "type_hierarchy"}
CHAIN_KINDS = ("inherits", "mixes_in", "implements")
ROLE_KINDS = ("inherits", "implements")
MAGIC_CALLS = ("__call", "__callStatic")
# PHP ignores the case of a method name, for ASCII letters only.
METHOD_CASE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def name(i: str) -> str:
    return i.split("::", 1)[1]


def module_of(ns: str) -> str | None:
    p = ns.split("\\")
    return p[1] if len(p) > 2 and p[0] == "Drupal" else None


def first_party(n: Node) -> bool:
    return n["state"] == "mapped" and bool(n["locations"])


def stack(t: str) -> str:
    return t.split(".")[0]


def split(found: list[Node]) -> str:
    inside = sum(first_party(n) for n in found)
    return f"first-party {inside}  outside {len(found) - inside}"


def group(n: Node) -> str:
    if n["provenance"][0]["rule"] == "any_config_file":
        return name(n["id"]).split(".")[0]
    if n["type"] == "php.class":
        return module_of(name(n["id"])) or "none"
    return "-"


def read_backing(enum: Node) -> bool | None:
    """Whether the declaration at the enum's location has a backing type; None when unreadable."""
    place = (enum["locations"] or [NOWHERE])[0]
    file, line = place["file"], place["line"]
    short = re.escape(name(enum["id"]).rsplit("\\", 1)[-1])
    try:
        source = Path(file).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        source = ""
    span = "\n".join(source.split("\n")[line - 1 :])
    # `#[` opens an attribute, which can share the enum's line, so it is no comment. Strings go
    # first, because a string in that attribute can hold `//`, `#` or a colon.
    strings = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'"""
    code = re.sub(strings + r"|/\*.*?\*/|//[^\n]*|#(?!\[)[^\n]*", "", span, flags=re.DOTALL)
    found = re.search(rf"\benum\s+{short}\b(.*)", code, re.DOTALL)
    if found is None:
        print(f"cannot read the enum backing of {enum['id']} in {file}", file=sys.stderr)
        return None
    return ":" in found.group(1).partition("{")[0]


class GapReport:
    def __init__(self, m: MapFile) -> None:
        self.m = m
        self.nodes: dict[str, Node] = {n["id"]: n for n in m["nodes"]}
        self.edges: list[Edge] = m["edges"]
        self.edges_from: dict[str, list[Edge]] = {}
        self.edges_to: dict[str, list[Edge]] = {}
        for e in self.edges:
            self.edges_from.setdefault(e["from"], []).append(e)
            self.edges_to.setdefault(e["to"], []).append(e)
        self.module_folders = [
            n["locations"][0]["file"].rpartition("/")[0] + "/"
            for n in m["nodes"]
            if n["type"] == "drupal.module" and first_party(n)
        ]
        self.backing: dict[str, bool | None] = {}
        faults = {
            n["id"]: self.fault(n) for n in m["nodes"] if n["state"] in ("referenced", "unresolved")
        }
        self.faults = {i: k for i, k in faults.items() if k}
        self.gaps = [n for n in m["nodes"] if n["id"] not in self.faults]

    def mapped(self, i: str) -> bool:
        return i in self.nodes and self.nodes[i]["state"] == "mapped"

    def chain(self, c: str) -> list[str] | None:
        """The mapped ancestry of `c`, or None when a link that could define a method is outside.

        An enum is concrete, so an outside interface gives it no method: only a trait can.
        """
        enum = self.mapped(c) and self.nodes[c]["type"] == "php.enum"
        seen: list[str] = []
        todo = [c]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            if not self.mapped(x):
                return None
            seen.append(x)
            todo += [
                e["to"]
                for e in self.edges_from.get(x, [])
                if e["kind"] in CHAIN_KINDS
                and (not enum or e["kind"] == "mixes_in" or self.mapped(e["to"]))
            ]
        return seen

    def defines(self, c: str, meth: str) -> bool:
        return any(
            e["kind"] == "contains"
            and name(e["to"]).split("::")[-1].translate(METHOD_CASE) == meth.translate(METHOD_CASE)
            and e["to"] in self.nodes
            and e["to"].startswith("php.method::")
            for e in self.edges_from.get(c, [])
        )

    def enum_gives(self, enum: Node, meth: str) -> bool:
        """Whether PHP builds `meth` into `enum`; an unreadable backing counts as yes."""
        folded = meth.translate(METHOD_CASE)
        if folded == "cases":
            return True
        if folded not in ("from", "tryfrom"):
            return False
        if enum["id"] not in self.backing:
            self.backing[enum["id"]] = read_backing(enum)
        return self.backing[enum["id"]] is not False

    def method_fault(self, c: list[str], meth: str) -> str | None:
        if any(self.defines(x, m) for x in c for m in (meth, *MAGIC_CALLS)):
            return None
        start = self.nodes[c[0]]
        if start["type"] == "php.enum" and self.enum_gives(start, meth):
            return None
        return "method no class defines"

    def fault(self, n: Node) -> str | None:
        t, nm = n["type"], name(n["id"])
        k: str | None
        if t == "php.method" and "::" in nm:
            cls, meth = nm.rsplit("::", 1)
            for c in (self.chain(k + "::" + cls) for k in ("php.type", "php.class")):
                if c is not None:
                    return self.method_fault(c, meth)
            return None
        if t == "drupal.library":
            return self.library_fault(nm)
        if t == "drupal.menu_link":
            # A parent id holding a colon is a derivative, made at run time.
            k = None if ":" in nm else nm.split(".")[0]
            kind = "menu link no links file defines"
        elif t == "drupal.theme_hook":
            return self.theme_hook_fault(n)
        elif n["id"].startswith("php.type::"):
            k, kind = module_of(nm), "class no file holds"
        else:
            return None
        return kind if k and self.mapped("drupal.module::" + k) else None

    def library_fault(self, nm: str) -> str | None:
        """A library of a mapped module or theme that its libraries file does not define."""
        ext = nm.split("/")[0]
        if not any(self.mapped(f"drupal.{e}::{ext}") for e in ("module", "theme")):
            return None
        kind = "library no libraries file defines"
        near = sorted(
            i
            for i, x in self.nodes.items()
            if x["type"] == "drupal.library" and first_party(x) and name(i).lower() == nm.lower()
        )
        return f"{kind}  near {near[0]}" if near else kind

    def theme_hook_fault(self, n: Node) -> str | None:
        """A rendered hook whose template a mapped module holds, so that module should declare it.

        A hook's name says nothing of who declares it; a template a theme holds may override a
        hook core declares, so only a module's template marks the place.
        """
        if not any(e["kind"] == "renders_theme_hook" for e in self.edges_to.get(n["id"], [])):
            return None
        template = self.nodes.get("drupal.template::" + name(n["id"]).replace("_", "-"))
        if template is None or not first_party(template):
            return None
        files = [x["file"] for x in template["locations"]]
        if any(f.startswith(d) for f in files for d in self.module_folders):
            return "theme hook no hook_theme declares"
        return None

    def outside(self, start: str, kinds: tuple[str, ...]) -> list[str]:
        """The ids outside the mapped code that `kinds` edges reach, walking through mapped ids."""
        seen, todo, found = {start}, [start], []
        while todo:
            for e in self.edges_from.get(todo.pop(), []):
                if e["kind"] not in kinds or e["to"] in seen:
                    continue
                seen.add(e["to"])
                (todo if first_party(self.nodes[e["to"]]) else found).append(e["to"])
        return sorted(found)

    def print_plain(self) -> None:
        """Group the class-likes no more specific type claims by what gives them a role.

        The class-like types are those under the roots of the types an inherits or implements edge
        joins. A class is claimed when its type belongs to another stack than its root, or when an
        edge from a node of another stack reaches it.
        """
        print("Plain classes")
        parent_of = {r["type"]: r["parent"] for r in self.m["type_hierarchy"]}

        def root(t: str) -> str:
            while parent_of.get(t):
                t = str(parent_of[t])
            return t

        roots = {
            root(self.nodes[i]["type"])
            for e in self.edges
            if e["kind"] in ROLE_KINDS
            for i in (e["from"], e["to"])
        }
        claimed, plain, none = 0, 0, 0
        roles: dict[tuple[str, str], list[str]] = {}
        for i, n in sorted(self.nodes.items()):
            lang = stack(root(n["type"]))
            if not first_party(n) or root(n["type"]) not in roots:
                continue
            if stack(n["type"]) != lang or any(
                stack(self.nodes[e["from"]]["type"]) != lang for e in self.edges_to.get(i, [])
            ):
                claimed += 1
                continue
            plain += 1
            parents = self.outside(i, ("inherits",))
            ifaces = [x for x in self.outside(i, ROLE_KINDS) if x not in parents]
            attrs = {e["to"] for e in self.edges_from.get(i, []) if e["kind"] == "has_attribute"}
            if parents:
                roles.setdefault(("inherits", parents[0]), []).append(i)
            elif ifaces:
                roles.setdefault(("implements", ifaces[0]), []).append(i)
            for a in sorted(attrs):
                roles.setdefault(("has_attribute", a), []).append(i)
            none += not (parents or ifaces or attrs)
        print(f"claimed  {claimed}")
        print(f"plain  {plain}")
        # The parent and interface groups split the plain classes; attribute groups overlap them.
        for (kind, to), found in sorted(
            roles.items(), key=lambda r: (r[0][0] == "has_attribute", -len(r[1]), r[0])
        ):
            print(f"{kind}  {to}  {len(found)}  {found[0]}")
        print(f"none  {none}")

    def print_resolution(self) -> None:
        reached = {e["to"] for e in self.edges if first_party(self.nodes[e["from"]])}
        print("Resolution gaps")
        lists = {
            "referenced": [n for n in self.gaps if n["state"] == "referenced"],
            "unresolved": [n for n in self.gaps if n["state"] == "unresolved"],
            "inferred": [
                self.nodes[e["from"]]
                for e in self.edges
                if any(p.get("confidence") == "inferred" for p in e["provenance"])
            ],
        }
        for word, found in lists.items():
            print(f"{word}  {len(found)}")
            print(split(found))
            if word != "inferred":
                print(f"reached from first-party {sum(n['id'] in reached for n in found)}")

    def print_detail(self) -> None:
        print("Detail gaps")
        groups: dict[tuple[str, str], list[Node]] = {}
        for n in self.gaps:
            groups.setdefault((n["provenance"][0]["rule"], group(n)), []).append(n)
        for (rule, d), found in sorted(groups.items()):
            print(f"{rule}  {d}  {len(found)}")
            print(split(found))

        present: dict[str, list[Node]] = {}
        for n in self.gaps:
            present.setdefault(n["type"], []).append(n)
        hierarchy = self.m["type_hierarchy"]
        roots = {r["type"] for r in hierarchy if not r["parent"]}
        children: dict[str, list[str]] = {r["type"]: [] for r in hierarchy}
        for r in hierarchy:
            if r["parent"]:
                children.setdefault(r["parent"], []).append(r["type"])
        for parent in sorted(children):
            if parent in roots or children[parent]:
                for child in sorted(children[parent]) or ["none"]:
                    found = present.get(child, [])
                    print(f"{parent}  {child}  {len(found)}")
                    if found:
                        print(split(found))
            own: dict[str, list[Node]] = {}
            for n in present.get(parent, []) if children[parent] else []:
                own.setdefault(group(n), []).append(n)
            for d, found in sorted(own.items()):
                print(f"{parent}  own {d}  {len(found)}")
                print(split(found))

        group_of: dict[str, str | None] = {}
        for n in self.gaps:
            if n["state"] == "referenced" and n["type"] == "drupal.module":
                group_of[n["id"]] = name(n["id"])
            elif n["state"] == "referenced" and n["id"].startswith("php.type::"):
                group_of[n["id"]] = module_of(name(n["id"]))
        leaning: dict[str, set[str]] = {g: set() for g in group_of.values() if g}
        for e in self.edges:
            g = group_of.get(e["to"])
            if g and self.mapped(e["from"]):
                leaning[g].add(e["from"])
        names = [p["pack"] for p in self.m["packs"]]
        for g in sorted(leaning, key=lambda g: (-len(leaning[g]), g)):
            pack = next((p for p in names if p == g or p.startswith(g + "_")), "none")
            print(f"{g}  {len(leaning[g])}  rutter: {pack}")

    def print_site_faults(self) -> None:
        print("Site faults")
        first: dict[str, Location] = {}
        for e in self.edges:
            first.setdefault(e["to"], (e["locations"] or [NOWHERE])[0])
        for i in sorted(self.faults):
            where = first.get(i, NOWHERE)
            print(f"{i}  {where['file']}:{where['line']}  {self.faults[i]}")

    def print_unknown_boundaries(self) -> None:
        print("Unknown boundaries")
        marked = [
            n for n in self.m["nodes"] if (n.get("attributes") or {}).get("resolution") == "runtime"
        ]
        print(f"runtime  {len(marked)}")
        print(split(marked))
        for n in sorted(marked, key=lambda n: n["id"]):
            where = ", ".join(f"{x['file']}:{x['line']}" for x in n["locations"]) or "-"
            rule = next(
                (
                    f"{p['pack']}.{p['rule']}"
                    for p in n["provenance"]
                    if "resolution" in p.get("sets", [])
                ),
                "-",
            )
            print(f"{n['id']}  {where}  {rule}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: gap_read.py MAP_FILE", file=sys.stderr)
        return 2
    try:
        with Path(args[0]).open(encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        print(f"cannot read {args[0]}: {e}", file=sys.stderr)
        return 2
    if not isinstance(m, dict) or not m.keys() >= MAP_KEYS:
        print(f"cannot read {args[0]}: not a Periplus map", file=sys.stderr)
        return 2
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    report = GapReport(cast(MapFile, m))
    report.print_resolution()
    report.print_detail()
    report.print_site_faults()
    report.print_unknown_boundaries()
    report.print_plain()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
