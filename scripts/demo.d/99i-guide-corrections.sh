#!/usr/bin/env bash
# The guide corrections the Go and Laravel rutter authors asked for: each guide page holds one
# distinctive phrase per correction, read with its line breaks joined, and no longer holds the
# sentences those corrections replaced, among them the old limits on tree ids, readers, has_child
# and settings values. The references page's list of keys the schemas accept and the engine does not run, each holder line
# expanded over its keys, is exactly the engine's UNEXECUTED_KEYS.
set -euo pipefail
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
"$python" - "$ROOT" <<'PY'
import re
import sys
from pathlib import Path

from periplus.engine.packload import UNEXECUTED_KEYS

root = Path(sys.argv[1])
pages = {
    name: " ".join((root / "docs" / f"rutter-author-guide{name}.md").read_text().split())
    for name in ("", "-drupal", "-references")
}
present = {
    "": [
        "pack files, each other `.yaml` or `.yml` file in any subfolder",
        "`pack_paths` adds rutter folders, relative to the project folder",
        "`re_include` takes back by glob what a rutter's `files.exclude` leaves out",
        "`periplus spec <pack>` prints the schemas",
        "`match.file` globs the file's stem, its name less its type's ending",
        "a folder value needs `/**` to reach those below",
        "declare a second type on that ending under `files.types`, as "
        "`php_notes: {endings: [php], reader: text}`",
        "each rule takes its own type's path values and sections, and two types read alike are refused",
        "`values` names strings, as `values: {module: example.com/app}`, that any template may name",
        "and a path value template naming what neither its pattern nor a setting gives, refuse the map "
        "with exit 19",
        "Give the types at each end of a kind one id namespace",
        "refuse the map with exit 19, naming the kind and both files",
        "a tree rutter, with a [reference rule](rutter-author-guide-references.md)",
        "`unread` lists the files in the rules' folders that no rule read",
        "so it is never empty there",
        "`unlisted` the folders it could not list: each should be empty",
        "[Tree references](rutter-author-guide-references.md) lists the keys",
        "Python's `re`, which loads a lookahead and refuses a lookbehind of varying width",
    ],
    "-drupal": [
        "A text rule on PHP names its own file type, a second one claiming the ending php and read as "
        "text",
        "plain and static calls are stated",
        "Segments split on the `qualified_name` separator only",
        "[`path` and `normalize`](rutter-author-guide-imports.md) bind b",
    ],
    "-references": [
        "Print the tree of a sample file with the pinned grammar",
        "Check 67b-php-calls proves the two rules.",
        "the grammar parses only isset, empty, die and eval as calls",
        "a path value of its file type, a settings value, or a field of the matched node",
        "The engine's names, then path values and settings, shadow a field of the same name",
        "`namespace: {path_value: pkg}` takes the file's namespace from a path value",
        "A field fills with the whole text of that child node",
        "A template needs a `from` listing exactly the names it names",
        "`normalize` on the id, as on a text rule's, cleans the finished id",
        "So normalizing a name another rule uses splits the node",
        "fires a declaration rule only on a node with a direct child of that type",
        "`name_child` takes field names only",
        "still needs the type declared again in full",
        "`skip_names` lists written names that make nothing",
        "the first `name_child` field exactly as written, case and all, before any `resolve` step",
        "An unresolved node's type is the first candidate",
        "`types_tried`, every candidate in the order tried",
        "Both rules state their own node",
        "belongs to the rule's own pack or a pack it depends on",
        "Two such rules in one pack on one tree node do not combine: the enclosing class comes from "
        "the last",
        "the `in` folders and `file` glob of the rule that gives it are not consulted",
        "A reference rule's from end is the other way round: it takes the first declaration rule in "
        "load order, a dependency's before the pack's own",
        "## Keys the schemas accept and the engine does not run",
    ],
}
absent = {
    "": [
        "does not enforce it", "is not executed on a file type that any pack reads as a tree",
        "a tree type declared again as text is not refused",
    ],
    "-drupal": ["is not executed in any pack", "declares PHP again as text"],
    "-references": [
        "has no key that skips a name", "proves each case on this page",
        "a template naming a path value is not executed", "states ids with text rules",
        "a tree declaration's id still cannot name one",
        "of the matched node: `template:",
    ],
}
for name, phrases in present.items():
    for phrase in phrases:
        assert phrase in pages[name], f"rutter-author-guide{name}.md lacks: {phrase}"
for name, phrases in absent.items():
    for phrase in phrases:
        assert phrase not in pages[name], f"rutter-author-guide{name}.md still holds: {phrase}"
# `unread` is in no sentence that says should be empty, nor in the one before it.
for match in re.finditer("should be empty", pages[""], re.I):
    before = " ".join(re.split(r"(?<=\.) ", pages[""][: match.start()])[-2:])
    assert "`unread`" not in before, f"rutter-author-guide.md says `unread` should be empty: {before}"

text = (root / "docs/rutter-author-guide-references.md").read_text()
block = re.search(
    r"^## Keys the schemas accept and the engine does not run\n.*?^```text\n(.*?)^```$",
    text, re.M | re.S,
)
assert block, "the references page has no list of unexecuted keys"
listed, holder = [], None
for line in block[1].splitlines():
    if line.startswith("    "):
        assert holder is not None, line
        keys = line.split()
    else:
        holder, _, rest = line.partition(": ")
        keys = rest.split()
    listed += [f"{holder}.{key}" for key in keys]
assert len(listed) == len(set(listed)), sorted({k for k in listed if listed.count(k) > 1})
assert set(listed) == set(UNEXECUTED_KEYS), (
    sorted(set(listed) - set(UNEXECUTED_KEYS)), sorted(set(UNEXECUTED_KEYS) - set(listed))
)
print(f"guide corrections: {sum(map(len, present.values()))} phrases, {len(listed)} keys")
PY
echo "guide corrections ok"
