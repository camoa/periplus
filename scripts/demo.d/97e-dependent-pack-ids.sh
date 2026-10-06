#!/usr/bin/env bash
# A dependent pack's declaration rules on php_basic's class node. A planted pack depending on
# php_basic matches class_declaration with body_child: declaration_list twice, once emitting its own
# node type and once, as the twin, an edge from it to the class. Mapped with and without that pack,
# php_basic's class and method ids and the ends of every php_basic edge are identical, and no id
# starts with None::. A map file holding a None::X node fails the shipped map schema.
# No pack can now make the engine build a None:: id, since the packs refuse every such shape at
# load, so the last part drives periplus map in process with build_document wrapped to add one:
# the write guard refuses it with exit 17 and UNDECLARED_ID_NAMESPACE, and writes no file.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"

site="$work/site"
pack="$site/.periplus/packs/models@0.0.1"
mkdir -p "$pack/rules" "$site/src/Models"
cat >"$pack/pack.yaml" <<'YAML'
pack: models
version: 0.0.1
depends: [php_basic]
folders:
  models: ./src/Models/**
YAML
cat >"$pack/rules/models.yaml" <<'YAML'
node_types:
- name: models.model
  id_namespace: models.model
edge_kinds:
- kind: implemented_by
  from: models.model
  to: php.class
rules:
- rule: model_class
  reads: file
  in: [models]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: models.model}}]
  confidence: inferred
- rule: model_is_class
  reads: file
  in: [models]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{edge: {kind: implemented_by, from: this_node, to: {from: qualified_name}}}]
  confidence: inferred
YAML
cat >"$site/src/Models/User.php" <<'PHP'
<?php

namespace App\Models;

class Base
{
}

class User extends Base implements Shown
{
    use Named;

    public function save()
    {
    }
}
PHP

printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/alone.json" >/dev/null)
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n  - models@0.0.1\n' \
    >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/both.json" >/dev/null)

python3 - "$work/alone.json" "$work/both.json" <<'PY'
import json
import sys

alone, both = (json.load(open(path)) for path in sys.argv[1:3])


def basic(document):
    """php_basic's node ids and the kind and ends of each edge it states."""
    ids = {n["id"] for n in document["nodes"] if n["type"].startswith("php.")}
    edges = {
        (e["kind"], e["from"], e["to"])
        for e in document["edges"]
        if any(p["pack"] == "php_basic" for p in e["provenance"])
    }
    return ids, edges


ids, edges = basic(alone)
assert {"php.type::App\\Models\\User", "php.method::App\\Models\\User::save"} <= ids, ids
assert ("contains", "php.type::App\\Models\\User", "php.method::App\\Models\\User::save") in edges
assert ("inherits", "php.type::App\\Models\\User", "php.type::App\\Models\\Base") in edges, edges
assert basic(both) == (ids, edges), (basic(both)[0] ^ ids, basic(both)[1] ^ edges)
model = "models.model::App\\Models\\User"
assert ("implemented_by", model, "php.type::App\\Models\\User") in {
    (e["kind"], e["from"], e["to"]) for e in both["edges"]
}
for document in (alone, both):
    named = [n["id"] for n in document["nodes"]]
    named += [end for e in document["edges"] for end in (e["from"], e["to"])]
    assert not [i for i in named if i.startswith("None::")], named
PY

"$python" - "$work/both.json" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import copy
import json
import sys

from jsonschema import Draft202012Validator

document = json.load(open(sys.argv[1]))
validator = Draft202012Validator(json.load(open(sys.argv[2])))
validator.validate(document)
for bad in ("None::X", "::X"):
    planted = copy.deepcopy(document)
    planted["nodes"].append({**planted["nodes"][0], "id": bad})
    errors = [e for e in validator.iter_errors(planted) if list(e.absolute_path)[-1:] == ["id"]]
    assert errors, bad
PY
(cd "$site" && "$python" - "$work/guarded.json" <<'PY'
import contextlib
import io
import json
import sys
from pathlib import Path

import periplus.map
from periplus.cli import main

built = periplus.map.build_document


def planted(*args, **kwargs):
    """The engine's document, with one node whose namespace no pack declares."""
    document = built(*args, **kwargs)
    document["nodes"].append({**document["nodes"][0], "id": "None::X"})
    return document


periplus.map.build_document = planted
target, captured = Path(sys.argv[1]), io.StringIO()
with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
    code = main(["map", "--output", str(target), "--format", "json"])
assert code == 17, (code, captured.getvalue())
problems = json.loads(captured.getvalue())["problems"]
assert [p["detail"] for p in problems] == [
    {"problem": "UNDECLARED_ID_NAMESPACE", "id": "None::X"}
], problems
assert "UNDECLARED_ID_NAMESPACE" in problems[0]["message"], problems
assert "None::X" in problems[0]["message"], problems
assert not target.exists()
PY
)
echo "dependent pack ids ok"
