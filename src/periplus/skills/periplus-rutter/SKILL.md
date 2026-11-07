---
name: periplus-rutter
description: Writes or changes a Periplus rutter, the pack of data that tells Periplus how to find one stack's things in real files. Use when the user says the map misses something, add a rule, support this framework, or map this stack, to start a rutter for a new stack, or to make a custom rutter in a project's .periplus/packs that extends a bundled one. Each task ends with periplus validate and periplus map.
---

# Writing a Periplus rutter

## Standing rules

1. Rules are small and add to each other: one rule solves one case, and several cases are several rules. Split by rule file inside one rutter, never by adding rutters for one stack; a new rutter repeats the file types and folders the covering one already holds, and a small rule can be read, tested and removed alone.
2. A rutter reads in passes by depth: order 1 is the structure, order 2 one layer inside each class as nodes at their lines, order 3 joins in the map with map rules. Each pass reads what the one before it found, so no rule has to look a thing up itself.
3. There is no stack knowledge in the engine: a new stack is a rutter, never engine code, even where a request seems to ask for engine code. The engine then stays the same for every stack, and a third-party rutter can do all a built-in one does.
4. Probe before saying a rutter cannot do something: write the rule, run it, and quote the engine's message before you call it an engine gap. A guess about the format's limits has been wrong before; the message is the evidence.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose. The name leaks the project and ties the rule to one site.

## Where the detail lives

This skill gives the steps. Each rule shape, and what the format cannot say, is in the rutter
author guides; read the section the step names instead of guessing a key:

- [Rutter author guide](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide.md): the files of a rutter, one rule of each shape, how to check a rutter.
- [Rutter author guide: text](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-text.md): text spans, nested regions of a text file.
- [Rutter author guide: abilities](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-abilities.md): a call's class and method in one rule, id patterns.
- [Rutter author guide: references](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-references.md): reference rules on a parse tree, and the keys the engine does not run.
- [Rutter author guide: imports](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-imports.md): imports and bindings.
- [Rutter author guide: map rules](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-map-rules.md): map rules, which join what earlier passes found. Its follow steps are `edge`, `ancestors`, `node`, `id_matches` and `try`: the steps inside a `try` run from the current node, and when they reach nothing the walk goes on from that node with the captures it had, so a lookup that may fail (a method on an ancestor the map does not hold) leaves the end to `on_miss`.
- [Rutter author guide: Drupal](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutter-author-guide-drupal.md): the PHP and Drupal rutters, read as worked examples.

[Bundled rutters](https://github.com/camoa/periplus/blob/v0.4.2/docs/rutters.md) lists every rutter that ships with Periplus.

The [README](https://github.com/camoa/periplus/blob/v0.4.2/README.md) section "Write a rutter" and [CONTRIBUTING](https://github.com/camoa/periplus/blob/v0.4.2/CONTRIBUTING.md) give the loop: write the rutter in the
project's own `.periplus/packs` first, and map that project until the map holds what the code holds.

## Write a rule

1. Find the rutter that already covers the stack. Put the new rule in a rule file of that rutter,
   not in a new rutter: a new rule file inside the covering rutter adds to its rules and keeps one
   set of file types and folders.
2. Write one rule for one case. When a request holds several cases, write several rules, even where
   they emit the same type: in `php_basic`, `find_declarations.yaml` and `find_runtime_calls.yaml`
   each find `php.call_site` in their own way, and neither file's rules are stretched over the other's case.
3. Declare each node type and edge kind the rule emits, in that rule file or in a pack the rutter
   depends on. A rule may name only those types.
4. Pick the shape from the guide: a whole-file rule, a text rule, a binding rule, a reference rule
   or a map rule.
5. Set the confidence. Confidence is declared on the rule, not decided at runtime. A rule firing on
   an explicit declaration and a rule firing on a naming convention cannot emit the same
   confidence: the first is `declared`, the second `inferred`.

The example adds a rule file to `python_text` in a project that already holds the
[second-stack example](https://github.com/camoa/periplus/blob/v0.4.2/examples/second-stack) rutters. A module-level name in capitals is a constant only by convention,
so the rule is `inferred`:

<!-- example write-rule: .periplus/packs/python_text@0.1.0/rules/constants.yaml -->
```yaml
node_types:
- name: python.constant
  id_namespace: python.constant
rules:
- rule: constant
  reads: file
  in: [python]
  match: {file: '**', filetype: python, text: '(?m)^(?<name>[A-Z][A-Z0-9_]*)[ \t]*='}
  id: {template: '{module}.{name}'}
  emits: [{node: {type: python.constant}}]
  confidence: inferred
```

<!-- example write-rule: shop/limits.py -->
```python
RETRIES = 3
```

Check the rutter, then map the project; the map report's `not_executed` and `problems` should be empty:

<!-- nav-run -->
```console
$ periplus validate python_text
$ periplus map
```

## Start a rutter

Start a rutter only for a stack no rutter covers. For more rules on a covered stack, write a rule
file in its rutter instead.

1. Make the folder `.periplus/packs/<pack>@<version>` in the project, with a `pack.yaml` naming the
   pack, its version, its dependencies, its folders and its file types.
2. Add one rule file with the node types and the first rule. Start with order 1, the structure.
3. Pin `<pack>@<version>` in `.periplus/settings.yml`, beside the rutters the project already uses.

The example maps each reStructuredText page under `docs` as one node:

<!-- example new-rutter: .periplus/packs/rst_pages@0.1.0/pack.yaml -->
```yaml
pack: rst_pages
version: 0.1.0
depends: []
folders:
  pages: ./docs/**
files:
  types:
    rst:
      endings: [rst]
      reader: text
      path_values:
        page:
          pattern: '^(?<path>.+)\.rst$'
          template: '{path}'
```

<!-- example new-rutter: .periplus/packs/rst_pages@0.1.0/rules/pages.yaml -->
```yaml
node_types:
- name: rst.page
  id_namespace: rst.page
rules:
- rule: page
  reads: file
  in: [pages]
  match: {file: '**', filetype: rst}
  id: {template: '{page}'}
  emits: [{node: {type: rst.page}}]
  confidence: declared
```

<!-- example new-rutter: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - python_text@0.1.0
  - typer_text@0.1.0
  - speckitty@0.1.0
  - rst_pages@0.1.0
```

<!-- example new-rutter: docs/intro.rst -->
```rst
Introduction
============
```

Check the new rutter, then map; `periplus status` shows which rutters the project matched:

<!-- nav-run -->
```console
$ periplus validate rst_pages@0.1.0
$ periplus map
```

## Make a custom rutter

A custom rutter is a project's own rutter that extends a bundled one. It lives in the project's
`.periplus/packs`, the first folder Periplus searches for rutters, so it ships with the project and
needs no change to Periplus.

1. Pick the bundled rutter to extend; `periplus spec <pack>` prints what it declares.
2. Make `.periplus/packs/<pack>@<version>/pack.yaml` with `depends: [<bundled rutter>]`, without a
   version. The custom rutter may then use the bundled rutter's file types, folders and node types.
3. Write its rules in rule files, as in "Write a rule".
4. Pin both rutters in `.periplus/settings.yml`.

The example extends `yaml_basic`, which claims the YAML file endings, to map a service file:

<!-- example custom-rutter: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - yaml_basic@0.1.0
  - app_config@0.1.0
```

<!-- example custom-rutter: config/services.yml -->
```yaml
name: billing
image: billing:1.4
stack: shop
```

<!-- example custom-rutter: .periplus/packs/app_config@0.1.0/pack.yaml -->
```yaml
pack: app_config
version: 0.1.0
depends: [yaml_basic]
folders:
  app_config: ./config
```

<!-- example custom-rutter: .periplus/packs/app_config@0.1.0/rules/services.yaml -->
```yaml
node_types:
- name: app.service
  id_namespace: app.service
edge_kinds:
- kind: part_of
  from: app.service
  to: app.service
rules:
- rule: service
  reads: file
  in: [app_config]
  match: {file: services, filetype: yaml}
  id: {from: file_stem}
  emits:
  - node: {type: app.service}
  - attribute: {name: image, from: {key: image}}
  confidence: declared
- rule: service_in_stack
  reads: file
  in: [app_config]
  match: {file: services, filetype: yaml}
  id: {from: file_stem}
  emits: [{edge: {kind: part_of, from: this_node, to: {from: {key: stack}}}}]
  confidence: declared
```

Check the custom rutter, then map; the node's provenance names `app_config`:

<!-- nav-run -->
```console
$ periplus validate app_config
$ periplus map
```

## Measure what the rule added

Report what a rule added as numbers read from two maps, never as a number predicted from the rows
the rule would match. A prediction counts every row the rule fires on; a correct edge may already
sit beside each false one, so the map can gain far fewer edges than the rule fires on.

1. Keep a copy of the map before the rule. Copy `.periplus/map.json` to a path outside the project:
   the folder you name or, by default, the system temp folder under a `periplus` subfolder named
   after the project folder. Say the path after you write it.

   ```console
   $ mkdir -p /tmp/periplus/<project-folder> && cp .periplus/map.json /tmp/periplus/<project-folder>/before.json
   ```
2. Write or change the rule, check it with `periplus validate`, and run `periplus map`.
3. Run the block with the copy as `sys.argv[1]`, the live `.periplus/map.json` as `sys.argv[2]`
   and, to list what one rule made, `<pack>/<rule>` as `sys.argv[3]`. It prints `Measured`, one
   line per changed count of `counts.nodes_by_state`, `counts.nodes_by_type` and
   `counts.edges_by_kind`, the nodes and edges added, and with a rule the nodes and edges whose
   provenance names it.

   Save the gap-read block below to a file, such as `/tmp/periplus/<project-folder>/gap_read.py`,
   then run it with the two map paths and the optional rule:

   ```console
   $ python3 /tmp/periplus/<project-folder>/gap_read.py /tmp/periplus/<project-folder>/before.json .periplus/map.json [<pack>/<rule>]
   ```

Read bundled rules through `periplus status` (the pack roots and the matched rutters with paths)
and `periplus spec <pack>`, never through a repository path.
The block below does not copy the map: make the step 1 copy first, or `periplus map` overwrites
the before map.

<!-- nav-run -->
```console
$ periplus status
$ periplus spec python_text
$ periplus map
```

<!-- gap-read -->
```python
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


before, after = load(sys.argv[1]), load(sys.argv[2])
rule = sys.argv[3] if len(sys.argv) > 3 else None
print("Measured")
for group, key in (
    ("state", "nodes_by_state"),
    ("type", "nodes_by_type"),
    ("kind", "edges_by_kind"),
):
    was, now = before["counts"].get(key, {}), after["counts"].get(key, {})
    for name in sorted(set(was) | set(now)):
        a, b = was.get(name, 0), now.get(name, 0)
        if a != b:
            print(f"{group}  {name}  {a}  {b}  {b - a:+d}")
old_nodes = {n["id"] for n in before["nodes"]}
old_edges = {(e["from"], e["kind"], e["to"]) for e in before["edges"]}
print("added nodes ", len([n for n in after["nodes"] if n["id"] not in old_nodes]))
print("added edges ", len([e for e in after["edges"] if (e["from"], e["kind"], e["to"]) not in old_edges]))
if rule:
    pack, _, name = rule.partition("/")

    def named(item):
        return any(p.get("pack") == pack and p.get("rule") == name for p in item["provenance"])

    for node_id in sorted(n["id"] for n in after["nodes"] if named(n)):
        print(f"node  {node_id}")
    for row in sorted((e["from"], e["kind"], e["to"]) for e in after["edges"] if named(e)):
        print("edge  " + "  ".join(row))
```

## Offer the next rule

After the measurement, read what is left and offer one rule per turn until the person says stop or
the gap is accepted.

1. Run `periplus map --format json` and read `skipped` for the rows whose `rule` names the new
   rule: each is a match the rule could not turn into a node or edge, with its reason.
2. Read the `edge  <from>  <kind>  <to>` lines of the measurement. Run
   `periplus find :: --limit 0 --format json` and look up the `to` ids there: the referenced and
   unresolved nodes the new edges end on are what the next rule has to define.
   An end that misses only because the stack tries a second name can list that second resolution
   in `fallback`, run on the name as written after the first name is settled: under `php_basic`,
   whose identity resolves `helper()` in namespace `App` to `App\helper`, `fallback: [as_written]`
   alone lands the call on `App\helper`, else on `helper`, and `on_miss` applies under `App\helper`
   when neither is mapped. A pack whose identity does not prefix the namespace writes
   `resolve: [prefix_with: namespace]` beside it.
3. Offer one next rule from those rows, in plain words, and write it only when the person agrees.

<!-- nav-run -->
```console
$ periplus map --format json
$ periplus find :: --limit 0 --format json
```

## Stop with an accepted unknown

The loop stops on the person's word, or on an entry under `accepted_unknowns` in
`.periplus/settings.yml`. An entry holds `id`, `rule`, `reason`, `accepted_by` and `accepted_on`;
the commented stub in the settings file shows the shape. Name the entry as the stop, add it only
when the person accepts the gap, and offer no further rule for it.

## Draft the upstream issue

When `periplus validate` or `periplus map` refuses a shape with a message, or a bundled rule made a
wrong node or edge (its provenance names the bundled rutter), the fix belongs in the bundled
rutter, not in the project's rutter. Never work around a bundled rule's defect inside the project
rutter. The same draft serves a rule any project on the stack could use, as a contribution.

Write the draft to a file outside the project, in the scratch folder from the measurement, and
say the path. Never file the issue. Five parts, in this order:

1. The rule name and the rutter version, from the `packs` list of the map file.
2. One minimal example of the shape, written fresh. Quote no site file.
3. The measured counts, from the measurement.
4. The engine message, verbatim.
5. A link to [When a gap is the engine's](https://github.com/camoa/periplus/blob/v0.4.2/docs/map-report-guide.md#when-a-gap-is-the-engines).
