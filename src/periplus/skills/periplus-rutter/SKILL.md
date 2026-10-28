---
name: periplus-rutter
description: Write or change a Periplus rutter, the pack of data that tells Periplus how to find one stack's things in real files. Use to write a rule, to start a rutter for a new stack, or to make a custom rutter in a project's .periplus/packs that extends a bundled one. Each task ends with periplus validate and periplus map.
---

# Writing a Periplus rutter

## Standing rules

1. Rules are small and add to each other: split by rule file inside one rutter, never by adding rutters for one stack.
2. A rutter reads in passes by depth: order 1 is the structure, order 2 one layer inside each class as nodes at their lines, order 3 joins in the map with map rules.
3. There is no stack knowledge in the engine: a new stack is a rutter, never engine code, even where a request seems to ask for engine code.
4. Probe before saying a rutter cannot do something: write the rule, run it, and quote the engine's message before you call it an engine gap.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose.

## Where the detail lives

This skill gives the steps. Each rule shape, and what the format cannot say, is in the rutter
author guides; read the section the step names instead of guessing a key:

- [Rutter author guide](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide.md): the files of a rutter, one rule of each shape, how to check a rutter.
- [Rutter author guide: text](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-text.md): text spans, nested regions of a text file.
- [Rutter author guide: abilities](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-abilities.md): a call's class and method in one rule, id patterns.
- [Rutter author guide: references](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-references.md): reference rules on a parse tree, and the keys the engine does not run.
- [Rutter author guide: imports](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-imports.md): imports and bindings.
- [Rutter author guide: map rules](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-map-rules.md): map rules, which join what earlier passes found.
- [Rutter author guide: Drupal](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide-drupal.md): the PHP and Drupal rutters, read as worked examples.

[Bundled rutters](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutters.md) lists every rutter that ships with Periplus.

The [README](https://github.com/camoa/periplus/blob/v0.3.0/README.md) section "Write a rutter" and [CONTRIBUTING](https://github.com/camoa/periplus/blob/v0.3.0/CONTRIBUTING.md) give the loop: write the rutter in the
project's own `.periplus/packs` first, and map that project until the map holds what the code holds.

## Write a rule

1. Find the rutter that already covers the stack. Put the new rule in a rule file of that rutter,
   not in a new rutter: a new rule file inside the covering rutter adds to its rules and keeps one
   set of file types and folders.
2. Declare each node type and edge kind the rule emits, in that rule file or in a pack the rutter
   depends on. A rule may name only those types.
3. Pick the shape from the guide: a whole-file rule, a text rule, a binding rule, a reference rule
   or a map rule.
4. Set the confidence. Confidence is declared on the rule, not decided at runtime. A rule firing on
   an explicit declaration and a rule firing on a naming convention cannot emit the same
   confidence: the first is `declared`, the second `inferred`.

The example adds a rule file to `python_text` in a project that already holds the
[second-stack example](https://github.com/camoa/periplus/blob/v0.3.0/examples/second-stack) rutters. A module-level name in capitals is a constant only by convention,
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
```

Check the custom rutter, then map; the node's provenance names `app_config`:

<!-- nav-run -->
```console
$ periplus validate app_config
$ periplus map
```
