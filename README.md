# Periplus

> *periplus* (n.): an ancient coastal record of the ports and the distances between them.

Periplus makes a map of a code base: a JSON file of nodes and edges. Configuration files called
rutters tell it what to find. The same input always gives the same map, byte for byte. Periplus
never guesses. A thing that no rutter explains appears in the map as a marked unknown.

A **rutter** is a folder of YAML files for one stack, such as PHP, Drupal or Python. It declares
node types and edge kinds. It also says where to look, which files to read and how to name what it
finds. A new stack needs a new rutter, never a change to the engine. File names and settings call
a rutter a *pack*: a rutter lives in a folder named `<pack>@<version>`.

Status: **pre-release**, version 0.1.0. Nothing is published yet.

How it is meant to work: a person writes a rutter, often with help from an AI. Periplus then runs
it with no AI. A person or an AI reads the map, where every node and edge carries its file and
line. To improve a map, improve the rutters. The engine stays the same.

[`docs/principles.md`](docs/principles.md) gives the reasons for this design: why a new mapper,
and why rutters and not built-in support for each stack.

## Install

Periplus needs Python 3.11 or later. It declares support for 3.11 to 3.14. The CI workflow
runs the test suite on 3.11, 3.12, 3.13 and 3.14, and the static checks on 3.11.

Periplus is not on PyPI yet. Install it from a local copy of this repository:

```
uv tool install /path/to/periplus           # or: pip install /path/to/periplus
uv tool install '/path/to/periplus[go]'     # adds the Go grammar that go_basic needs
uv tool install '/path/to/periplus[js]'     # adds the JavaScript grammar that js_basic needs
periplus --version
```

To update an install, pull the repository and run `uv tool install /path/to/periplus` again. A
local directory is rebuilt when `pyproject.toml` changes or a file under `src/periplus` does. Run
`uv tool install --reinstall /path/to/periplus` for the form that always rebuilds. The command
`periplus status` prints a `rutters:` digest of the bundled rutters, so you can compare two installs.

The distribution name is `periplus-map`. Its five runtime dependencies are pinned exactly. One
package that `jsonschema` brings is compiled, so your platform needs a prebuilt wheel or Rust.

To work on Periplus itself, run `uv sync --frozen --all-extras` in the repository. This installs
the development tools and the Go grammar into `.venv`.

## Commands

Run each command in the project folder.

| Command | What it does |
|---|---|
| `periplus init` | Creates `.periplus/`, a pack folder and a commented settings file. It pins a rutter when it recognises the stack. |
| `periplus status` | Shows the settings, where each value came from, and the pack search path. |
| `periplus spec drupal_basic --summary` | Prints the rutter contract and what one rutter declares and inherits. |
| `periplus validate drupal_basic` | Checks one rutter's files against the shipped schemas and names each disagreement. Give a bare `name`, or `name@version` to pick one of several copies. |
| `periplus update` | Moves each pin to the installed version of that rutter. It leaves project-local and unknown pins as they are. |
| `periplus map --output map.json` | Runs the loaded rutters over the project and writes the map. |

`status`, `spec`, `validate`, `update` and `map` also take `--format json`. The settings file,
`.periplus/settings.yml`, names the rutters to load, each pinned to an exact version. After you
update Periplus, run `periplus update` to bring the pins to the installed versions:

```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
folders:
  config: ./config/default
```

The `folders` line moves the config folder from `drupal_basic`'s default, `./config/sync`. Leave
it out when your site uses the default.

In a Drupal project, `periplus init` writes the `drupal_basic@0.3.0` pin for you. It looks for
`drupal/core` in `composer.json`, or for `web/core/lib/Drupal.php`. The rutters that
`drupal_basic` depends on load without a pin of their own.

`periplus map` also prints a run report. It names each rule and how often it fired, and the files
no rule read. It also names folders it could not list, files that did not parse, and rules it
could not run.

## Write a rutter

A rutter for a new stack is a folder of YAML files in the project. You write it, map the
project, read what the map cannot explain, and write the next rule.

### The loop

1. Run `periplus init` in the project folder. It creates `.periplus/packs/` and the settings file
   `.periplus/settings.yml`. It pins a bundled rutter when it recognises the stack. For a new
   stack, write a first rutter and pin it, as in the example below.
2. Run `periplus map --output map.json --format json >report.json`. A map needs at least one
   pinned rutter, and with none it stops at exit 17.
3. Read the unknowns. In the report, `unread` lists the files in the rules' folders that no rule
   read. `skipped` lists each match whose rule could not build a node or edge it emits, with the
   reason. `not_executed` lists the rules the engine cannot run, and why. In the map,
   `counts.nodes_by_state` counts the `referenced` nodes, which a file names but no rule maps. It
   also counts the `unresolved` nodes, which a rule looked for and did not find.
4. Write a rule for those names in a rutter under `.periplus/packs/`. Pin a new rutter under
   `packs` in the settings. To build on a bundled rutter, name it in `depends`, as
   `depends: [php_basic]`. Your rutter may then use its folders, file types and types, and add
   rules. The bundled rutter's own files stay as installed.
5. Run `periplus validate <pack>`. It names each file and place that disagrees with the schemas. A
   rutter that does not validate stops the map.
6. Map again. The unknowns you covered disappear. Go back to step 3.

### Where a rutter and its settings live

A project's own rutters sit in `.periplus/packs/`, one folder per rutter, named
`<pack>@<version>`. Each holds a manifest, `pack.yaml`, and pack files: every other `.yaml` or
`.yml` file, in any subfolder.

The settings file, `.periplus/settings.yml`, names:

- `packs`: the rutters to load, each pinned as `<pack>@<version>`. A pinned rutter's dependencies
  load without a pin of their own.
- `folders`: a new place for a folder that a rutter names. A project that keeps the example's
  lists in `todo` sets `folders: {lists: ./todo/**}`. The rules then read `todo` and every folder
  below it.
- `values`: named text values that any template of any rutter may name, such as `{module}`.
- `pack_paths`: more folders to find rutters in, relative to the project folder.
- `re_include`: globs that take back the files a rutter's `files.exclude` leaves out.

`periplus status` lists where Periplus looks for a pinned rutter: the project's
`.periplus/packs`, the user's configuration folder, the bundled rutters and each `pack_paths`
folder. A bundled rutter, such as `php_basic`, loads by its pin alone.

### A complete small rutter

This rutter reads a line format invented for this example, a list of chores. A line
`chore <name>` declares a chore. `after <name>` at its end names the chore it waits for. Write
these four files in an empty folder.

<!-- example: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - chores@0.0.1
```

<!-- example: .periplus/packs/chores@0.0.1/pack.yaml -->
```yaml
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
```

<!-- example: .periplus/packs/chores@0.0.1/rules/chores.yaml -->
```yaml
node_types:
- name: chores.chore
  id_namespace: chores.chore
edge_kinds:
- kind: waits_for
  from: chores.chore
  to: chores.chore
rules:
- rule: chore
  reads: file
  in: [lists]
  match: {file: '*', filetype: chores, text: '(?m)^chore (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: chores.chore}}]
  confidence: declared
- rule: chore_waits
  reads: file
  in: [lists]
  match: {file: '*', filetype: chores, text: '(?m)^chore (?<name>\w+) after (?<after>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: waits_for, from: this_node, to: {from: {capture: after}}}}]
  confidence: declared
```

<!-- example: lists/home.chores -->
```text
# the week
chore dishes
chore laundry after dishes
chore floors after sweeping
```

`pack.yaml` gives the rutter's name and version, a folder `lists`, and a file type `chores` for
files ending in `.chores`, read as text. The pack file declares the node type `chores.chore` and
the edge kind `waits_for`. The rule `chore` fires once per match of its `text` pattern, and the
capture `name` gives the node's id. The rule `chore_waits` adds a `waits_for` edge from that node
to the name after `after`. `periplus validate` refuses one rule that emits both the node and the
edge, so the edge has its own rule. `confidence: declared` says the file states the thing.

Run `periplus validate chores`, then `periplus map --output map.json`. The map holds exactly these
nodes and edges, each with its state or kind and its file and line:

<!-- example-map -->
```text
node chores.chore::dishes   mapped      lists/home.chores:2
node chores.chore::laundry  mapped      lists/home.chores:3
node chores.chore::floors   mapped      lists/home.chores:4
node chores.chore::sweeping referenced
edge chores.chore::laundry  waits_for  chores.chore::dishes    lists/home.chores:3
edge chores.chore::floors   waits_for  chores.chore::sweeping  lists/home.chores:4
```

`sweeping` is `referenced`: line 4 names it, and no rule maps it. That is the kind of unknown
that step 3 of the loop finds. The check `scripts/demo.d/99j-readme-example.sh` runs this example
from this file and compares the map with the lines above.

### What to read next

| Read | For |
|---|---|
| `periplus spec` | The contract: the schemas, the rule format, the engine, and what the format cannot say yet. `periplus spec <pack>` adds what one rutter declares and inherits. |
| [`docs/rutter-author-guide.md`](docs/rutter-author-guide.md) | Start here: the files of a rutter, one rule of each shape, and how to check a rutter. |
| [`docs/rutter-author-guide-text.md`](docs/rutter-author-guide-text.md) | Text files: spans, values from enclosing spans, the line of a node, and a path below a folder. |
| [`docs/rutter-author-guide-drupal.md`](docs/rutter-author-guide-drupal.md) | Parse-tree rules, read through the PHP and Drupal rutters. |
| [`docs/rutter-author-guide-references.md`](docs/rutter-author-guide-references.md) | Calls read from a parse tree, and every key the schemas accept that the engine does not run. |
| [`docs/rutter-author-guide-imports.md`](docs/rutter-author-guide-imports.md) | Import paths and a call's arguments. |
| `examples/second-stack/packs` | Three working text rutters to copy: `python_text`, `typer_text` and `speckitty`. |
| `periplus validate <pack>` | Checks one rutter's files. It names each disagreement with the schemas, by file and place. |

A parse-tree rutter pins its grammar under `grammar` in `pack.yaml`, as `php_basic` does.
Periplus installs the PHP grammar, and the Go grammar with the `go` extra. Another language needs
its `tree-sitter-<language>` package installed beside Periplus, or the map stops at exit 28.

An AI that writes a rutter reads `periplus spec` first, then the guide pages in the order above.
Then it runs the loop. The map's `referenced` and `unresolved` nodes say which rule to write next.

## What the map holds

The map is one JSON file. It holds the nodes, the edges, counts by type and by kind, the packs
loaded and the settings file used. Each node has an `id`, a `type`, a `state` and its `locations`
(file and line). Its `provenance` names the pack, the rule and the rule's declared confidence.

The engine writes three states today:

- `mapped`: a rule found the thing in a file the project holds.
- `referenced`: a file names the thing, but no rule read where it is defined. Drupal core is an
  example when only custom code is mapped.
- `unresolved`: a rule looked for a name and no rule maps it. The node records what was searched.

An unresolved node from a map of a Drupal site, shortened:

```json
{"id": "php.function::Drupal\\my_module\\Plugin\\Action\\json_decode",
 "state": "unresolved", "type": "php.function",
 "unresolved_detail": {"rule": "php_basic/calls_function", "found": "no mapped node of this name",
   "searched_for": "Drupal\\my_module\\Plugin\\Action\\json_decode",
   "types_tried": ["php.function"]}}
```

Each edge has `from`, `to`, `kind`, its locations, an `occurrences` count and its provenance.

**Determinism.** The check `scripts/demo.d/99j-readme-example.sh` maps the example above twice in
one folder, and the two maps are byte-identical. This ran on one Linux machine. The design aims for identical maps across machines, but no test has
compared two machines or two operating systems yet.

## The rutters provided

Bundled rutters load by name. Example rutters are copied into a project's `.periplus/packs`.
The tables group them by language and by framework.

### Languages and file types

| Rutter | Version | What it finds |
|---|---|---|
| `php_basic` | 0.2.0 | PHP classes, interfaces, traits, enums, functions and methods. Inheritance, interfaces, traits, containment, and plain and static calls; a call to a PHP builtin function makes nothing. Reads a parse tree. |
| `js_basic` | 0.0.1 | JavaScript functions that have a name of their own, each under its script's path. Reads a parse tree. Needs the `js` extra. |
| `go_basic` | 0.0.3 | Go functions, methods, structs and interfaces, each under its package's import path. Calls written `f(x)` inside one package, and `pkg.F(x)` through an import, to another package of the module or to an unresolved function outside it. Reads a parse tree. Needs the `go` extra. |
| `yaml_basic` | 0.1.0 | Claims `.yml` and `.yaml` files for rutters that depend on it. No rules of its own. |
| `twig_basic` | 0.1.0 | Claims `.twig` files for rutters that depend on it. No rules of its own. |

### Drupal

The two core rutters come first. Each contributed module has a rutter of its own, pinned
beside `drupal_basic` when the site uses that module.

| Rutter | Version | What it finds |
|---|---|---|
| `drupal_basic` | 0.3.0 | Configuration, modules, themes, services, routes, permissions, libraries, templates, hooks, entity types, fields, displays and plugins. The services and entity types that `\Drupal::service('x')`, `$container->get('x')`, `\Drupal::entityQuery('x')` and an entity type manager's `getStorage('x')` name in PHP functions and methods. Hooks from `Hook` attribute methods, and from procedural functions named by their file's name, such as `mymod_cron` in `mymod.module`. Depends on `php_basic`, `yaml_basic` and `twig_basic`. |
| `drupal_js_basic` | 0.0.1 | Drupal behaviors and the behaviors they attach, `drupalSettings` keys that PHP attaches and behaviors read, and the libraries that PHP and templates attach. Depends on `js_basic` and `drupal_basic`. |
| `ai_basic` | 0.0.1 | The AI module's agent plugins and function call plugins, by attribute, each joined to its class. |
| `advancedqueue_basic` | 0.0.1 | The Advanced Queue module's job type plugins, by attribute or annotation, each joined to its class. |
| `config_pages_basic` | 0.0.1 | Each Config Pages type, from its config file, as a bundle of the entity type `config_pages`. |
| `crop_basic` | 0.0.1 | Each Crop API crop type, from its config file, as a bundle of the entity type `crop`. |
| `drush_basic` | 0.0.1 | Drush commands in the custom modules, from the `Command` attribute or the `@command` tag, each joined to its method and class. |
| `eck_basic` | 0.0.1 | Each Entity Construction Kit entity type, and each of its bundles, from their config files. |
| `paragraphs_basic` | 0.0.1 | Each paragraph type, from its config file, as a bundle of the entity type `paragraph`. |
| `profile_basic` | 0.0.1 | Each Profile type, from its config file, as a bundle of the entity type `profile`. |
| `salesforce_basic` | 0.0.1 | Salesforce mapping field plugins; each mapping with its Salesforce object and its edges to the bundle, entity type and fields it maps; the Salesforce events that subscribers name. |
| `twig_tweak_basic` | 0.0.1 | The block plugins, menus, entity types and field storages that Twig Tweak functions such as `drupal_block('x')` name in templates. |
| `webform_basic` | 0.0.1 | Webform handler plugins, by annotation, and each webform, from its config file, as a bundle of `webform_submission`. |

### Laravel

| Rutter | Version | What it finds |
|---|---|---|
| `laravel_basic` | 0.0.5 | Laravel routes with the prefixes and names of `Route::prefix()->name()->group()` groups, their controller methods, controllers, models, migrations, Blade views with their includes and component tags, and configuration files with the text keys of the array each returns. The views and keys that `view('x')` and `config('x.y')` calls name in PHP functions and methods. Depends on `php_basic`. Reads text, and a parse tree for the calls. |

### Examples

| Rutter | Version | What it finds |
|---|---|---|
| `python_text` | 0.1.0 | Python modules, top-level classes and functions, imports and calls. Reads text. |
| `typer_text` | 0.1.0 | Typer apps, commands and mounts. Depends on `python_text`. |
| `speckitty` | 0.1.0 | spec-kitty missions and their templates. |

The bundled rutters are in `src/periplus/packs`. The examples are in
`examples/second-stack/packs`. The manifest of every rutter in the tables above, except
`yaml_basic`, `twig_basic` and the examples, opens with a list of its known gaps.

To map a Go module, install the `go` extra and run Periplus at the module's root. Give the module
path in the settings, because Periplus does not read `go.mod`:

```yaml
periplus_version: 0
packs:
  - go_basic@0.0.3
values:
  module: example.com/app
```

To map a Laravel application, pin `php_basic@0.2.0` and `laravel_basic@0.0.5` and run Periplus
at the application's root. The default Laravel folders need no settings. To move the templates,
set `views_root` under `folders`; a template is named by its path below `views_root`.

The bundle also holds five older reference packs, `php`, `drupal`, `yaml`, `twig` and `go`. They
pass `periplus validate`, but they hold vocabulary only and cannot make a map.

New in this release: `drupal_basic` 0.3.0, the eleven rutters for contributed Drupal modules,
listed after it in the Drupal table, and the two JavaScript rutters, `js_basic` and
`drupal_js_basic`. The AI and Advanced Queue plugins moved out of `drupal_basic` into their own
rutters. Three new rutter shapes: a resolution step that looks a written name up in a table the
rutter declares under `tables`, a call argument written as a class constant read through the
grammar's `constant_access` and `constant_declaration` keys, and a rule narrowed to one file
ending by `match.ending`. A rutter's `boundary` lists the framework classes the map never reads.
Each one an edge reaches becomes a `declared` node, and a class that descends from one may take
the type the list gives it.
Settings `values` pass project facts, such as a Go module path, to a rutter.

## Tests and checks

The pytest suite holds 288 tests. `scripts/demo.sh` runs the 53 end-to-end checks in
`scripts/demo.d` and stops at the first failure. Each check maps a small project and compares the
result with what it expects.

The CI workflow, `.github/workflows/checks.yml`, installs the package with its `dev` extra only.
It runs pytest on Python 3.11 to 3.14, ruff and mypy, and validates every bundled pack. It
does not run the end-to-end checks, and it never maps a Go project. The workflow has not run yet.

To propose a change, read [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Known limitations

These are the limits a new user meets first. [`docs/known-limitations.md`](docs/known-limitations.md)
lists the rest, each rutter's among them.

- **Keys accepted but not executed.** The schemas accept more than the engine runs, for example
  `resolution` and `excluded_tokens`. A rule with such a key does
  not run. Such a key outside a rule stops the map. `rutter-author-guide-references.md` lists every key.
- **No order among rutters.** Two rules in one rutter on one parse-tree node: the last one wins.
  Nothing settles two rutters that give one attribute two values.
- **One edge kind name for all rutters.** `php_basic`, `go_basic` and `python_text` each declare
  `calls` with different ends. So one project cannot load `php_basic` beside either of the others.
- **Patterns run on Python's `re`, not RE2.** Nothing checks for the RE2 subset, and
  `laravel_basic` uses backreferences and lookarounds. Python `re` refuses only what it cannot
  compile, such as a variable-width lookbehind.
- **An unresolved end takes its first candidate type.** For example, `pathlib.Path` becomes a
  `python.function`. The map states a type it cannot know.
- **One JSON file, and every run is a full run.** There is no split map and no incremental run.
- **No query commands and no export.** There is no `find`, `show` or `path` command, and no
  GraphML, Mermaid or DOT output yet.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

Built with AI assistance. Periplus uses no AI to make a map.
