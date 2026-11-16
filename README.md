<div align="center">

# Periplus

**A map of a code base in one JSON file · rutters that say what to find · the same map every run**

[![checks](https://img.shields.io/github/actions/workflow/status/camoa/periplus/checks.yml?branch=main)](https://github.com/camoa/periplus/actions/workflows/checks.yml)
[![License](https://img.shields.io/github/license/camoa/periplus)](LICENSE)
[![Latest tag](https://img.shields.io/github/v/tag/camoa/periplus)](https://github.com/camoa/periplus/tags)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
<sub>The CI workflow, `.github/workflows/checks.yml`, installs the package with its `dev`
extra for the tests. It runs pytest on Python 3.11 to 3.14, ruff and mypy, and validates
every bundled pack. It does not run the acceptance scripts, and it never maps a Go project.</sub>

Status: **beta**, version 0.8.0.

</div>

> *periplus* (n.): an ancient coastal record of the ports and the distances between them.
>
> *rutter* (n.): a mariner's book of written sailing directions for one coast, from the French
> *routier*; it told a pilot what to look for before charts did.

Periplus makes a map of a code base: a JSON file of nodes and edges. Configuration files called
rutters tell it what to find. The same input always gives the same map, byte for byte. Periplus
never guesses. A thing that no rutter explains appears in the map as a marked unknown.

A **rutter** is a folder of YAML files for one stack, such as PHP, Drupal or Python. It declares
node types and edge kinds. It also says where to look, which files to read and how to name what it
finds. A new stack needs a new rutter, never a change to the engine. File names and settings call
a rutter a *pack*: a rutter lives in a folder named `<pack>@<version>`.

How it is meant to work: a person writes a rutter, often with help from an AI. Periplus then runs
it with no AI. A person or an AI reads the map, where every node and edge carries its file and
line. To improve a map, improve the rutters. The engine stays the same.

## Contents

- [Get started](#get-started)
- [Why Periplus](#why-periplus)
- [What the map holds](#what-the-map-holds)
- [Write a rutter](#write-a-rutter)
- [Read the map](#read-the-map)
- [CLI reference](#cli-reference)
- [Troubleshooting](#troubleshooting)
- [Tests and checks](#tests-and-checks)
- [How Periplus behaves](#how-periplus-behaves)
- [License](#license)

## Get started

Periplus needs Python 3.11 or later. It declares support for 3.11 to 3.14.

### 1. Install Periplus

Install it from PyPI:

```
uv tool install periplus-map                # or: pip install periplus-map
periplus --version
```

To install a tagged version from the repository:

```
uv tool install git+https://github.com/camoa/periplus@v0.8.0
```

To install from a local copy of this repository:

```
uv tool install /path/to/periplus           # or: pip install /path/to/periplus
```

After any of these installs, run `periplus skills install` to copy the Claude skills Periplus
ships into `~/.claude/skills`. Run it again after an update to replace the older copies.

#### Use the skills with other agents

The skills follow the [Agent Skills](https://agentskills.io) format: a folder with a `SKILL.md`
file. After `periplus skills install`, the folders `periplus-describe`, `periplus-gaps`, `periplus-map` and
`periplus-rutter` are in `~/.claude/skills`. Copy them to the folder the agent reads, and copy them
again after each update. The folder `~/.agents/skills` serves four agents at once:

```
mkdir -p ~/.agents/skills && rsync -a --delete ~/.claude/skills/periplus-* ~/.agents/skills/
```

- [Codex CLI](https://learn.chatgpt.com/docs/build-skills): `~/.agents/skills`, or `.agents/skills` in a repository.
- [Gemini CLI](https://geminicli.com/docs/cli/skills/): `~/.gemini/skills` or `~/.agents/skills`, or `.gemini/skills` or `.agents/skills` in a workspace.
- [GitHub Copilot in VS Code](https://code.visualstudio.com/docs/copilot/customization/agent-skills): `~/.copilot/skills`, `~/.agents/skills` or `~/.claude/skills`, so the Claude install already works. A repository can use `.github/skills`.
- [Cursor](https://cursor.com/docs/context/skills): `~/.cursor/skills` or `~/.agents/skills`, and it also reads `~/.claude/skills`. A repository can use `.cursor/skills`.

To upgrade an install from PyPI, use the tool you installed with:

```
uv tool upgrade periplus-map
pipx upgrade periplus-map
pip install -U periplus-map
```

`uv tool upgrade` leaves an install pinned to an exact version, such as `periplus-map==0.5.1`, where
it is. For that one, run `uv tool install periplus-map@latest`.

Then run `periplus skills install` again, and repeat the copy above for any other agent. Read the
[changelog](CHANGELOG.md) before you upgrade: when a bundled rutter's version changes, update the
pins in your project's settings with `periplus update` and map again.

To update a local install, pull the repository and run `uv tool install /path/to/periplus` again. A
local directory is rebuilt when `pyproject.toml` changes or a file under `src/periplus` does. Run
`uv tool install --reinstall /path/to/periplus` for the form that always rebuilds. The command
`periplus status` prints a `rutters:` digest of the bundled rutters, so you can compare two installs.

The distribution name is `periplus-map`. Its seven runtime dependencies are pinned exactly. One
package that `jsonschema` brings is compiled, so your platform needs a prebuilt wheel or Rust.

To work on Periplus itself, run `uv sync --frozen --all-extras` in the repository. This installs
the development tools into `.venv`.

### 2. Pin a rutter

Run `periplus init` in the project folder. It creates `.periplus/`, a pack folder and a commented
settings file. It pins each bundled rutter whose detector matches the project, and writes the
folders it found where a rutter's default folder does not exist:

```
cd /path/to/project
periplus init
```

The settings file, `.periplus/settings.yml`, names the rutters to load, each pinned to an exact
version:

```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
folders:
  config: ./config/default
```

The `folders` line moves the config folder from `drupal_basic`'s default, `./config/sync`. Leave
it out when your site uses the default.

In a Drupal project, `periplus init` pins `drupal_basic@0.3.0` when `composer.json` names
`drupal/core` or `web/core/lib/Drupal.php` exists. It also pins each contributed-module rutter,
such as `webform_basic`, whose module `core.extension.yml` lists, plus `drush_basic` for Drush
commands and `drupal_js_basic` for scripts in custom modules and themes. It prints one line per
pin with the file that matched. Where `web/modules/custom`, `web/themes/custom` or `config/sync`
do not exist, it looks for the `docroot/` and project-root versions and `config/default`. It
writes each one it finds under `folders` and prints what it chose. A folder it found nowhere is
printed as `unplaced`; declare it under `folders` yourself. The rutters that `drupal_basic`
depends on load without a pin of their own. After you update Periplus, run `periplus update` to
bring the pins to the installed versions.

### 3. Map the project

```
periplus map
```

`periplus map` writes the map to `.periplus/map.json`, where the other commands look for it. It
also prints a run report. It names each rule and how often it fired, and the files
no rule read. A pinned rutter that selected no file is listed first, under `Packs that selected no
file`, with the folders it looked in. Exit 33 means no rutter selected any file: `map` writes no
map, leaves an existing one as it was, and asks you to declare where the code is under `folders`
in `.periplus/settings.yml`. The report also names folders it could not list, files that did not parse, and rules it
could not run. The [map report guide](docs/map-report-guide.md) reads each part in turn.

### 4. Ask the map

```
periplus types
periplus find TEXT
periplus show ID
```

[Read the map](#read-the-map) lists the commands that read the map, grouped by what they are for.

## Why Periplus

**The map is one file you commit, it is the same on every run, and nothing serves it.**

[`docs/principles.md`](docs/principles.md) gives the reasons for this design: why a new mapper,
and why rutters and not built-in support for each stack. The table compares Periplus with the
kinds of tool that page describes.

| | Periplus | A source indexer | A server-backed tool | An AI summary |
|---|---|---|---|---|
| Framework configuration and templates | Read by rutter rules, as the source files are | Little or nothing | Little or nothing | What the model happens to read |
| What you get | One JSON file to commit, compare and review | An index for the tool's own queries | A database behind a server or viewer | Ranked text made for one prompt, never saved |
| What it needs to run | The command line | The tool | A database, a server or a viewer | A model |
| A new stack | A new rutter, with no engine change | Code in the tool | Code in the tool | A new prompt |

## What the map holds

The map is one JSON file. It holds the nodes, the edges, counts by type and by kind, the packs
loaded and the settings file used. When it holds an edge of a kind its rutter declares grouping
(`groups: true`: the edge's `from` end belongs to the container at its `to` end), it lists those
kinds, sorted, under `grouping_kinds`. When its rutters describe a node type or edge kind it holds,
it carries those one-line texts under `legend`, as `edge_kinds` and `node_types` maps from name to
text, keys sorted; a map whose rutters describe none has no `legend`. It lists each edge kind it
holds under its cause, the end that sets off the other: `cause_from_kinds`, `cause_to_kinds`,
`cause_none_kinds` or `cause_touch_kinds`; a kind in none of them is undeclared. When a node holds
an attribute its rutter gives a mark, `marks` names the mark of each such attribute. Each node has an `id`, a `type`, a `state` and its `locations`
(file and line). Its `provenance` names the pack, the rule and the rule's declared confidence: `declared`,
`inferred` or `mentioned`, strongest first. Rules that reach one node or edge at different
confidences each keep their own row.

The engine writes five states:

- `mapped`: a rule found the thing in a file the project holds.
- `boundary`: the thing is outside the mapped code, and a rule says what it is.
- `unknown_boundary`: the thing leaves the mapped code and no rule says what it is, or it is a
  call site whose target is built at run time. The node records why.
- `unresolved`: a rule looked for a name inside the mapped code and no rule maps it. The node
  records what was searched.
- `referenced`: a file names the thing, but no rule read where it is defined. Drupal core is an
  example when only custom code is mapped.

An unresolved node from a map of a Drupal site, shortened: a method calls `my_module_format()`,
which no mapped file declares.

```json
{"id": "php.function::my_module_format",
 "state": "unresolved", "type": "php.function",
 "unresolved_detail": {"rule": "php_basic/calls_function", "found": "no mapped node of this name",
   "searched_for": "my_module_format", "types_tried": ["php.function"]}}
```

Each edge has `from`, `to`, `kind`, its locations, an `occurrences` count and its provenance.

- A call whose target is built at run time, such as `$this->$name()`, is a call-site node, as
  `php.call_site`, whose `attributes` hold `resolution: runtime`. The map keeps the call and draws
  no edge from it, because no rule can name the target. A node of a type a rutter marks
  `internal` serves that rutter's map rules and is left out of the written map, with every edge
  that has an end on it.
- A node that two rules type as two kinds of one type, such as two kinds of form, keeps the type
  both kinds descend from. Its `attributes` hold `type_conflict`, each candidate type with the
  pack and rule that gave it, and the map report lists it under Type conflicts.

**Determinism.** `scripts/demo.d/99s-map-determinism.sh` maps one project in separate processes
under different hash seeds and locales, and the maps are byte-identical. This ran on one Linux
machine. The design aims for identical maps across machines, but no test has
compared two machines or two operating systems yet.

### The rutters provided

What the map holds depends on the rutters loaded. Bundled rutters load by name. Example rutters
are copied into a project's `.periplus/packs`. The tables group them by language and by framework.

[`docs/rutters.md`](docs/rutters.md) lists every bundled rutter with its dependencies.

<details>
<summary><strong>Languages and file types</strong></summary>

| Rutter | Version | What it finds |
|---|---|---|
| `php_basic` | 0.2.0 | PHP classes, interfaces, traits, enums, functions and methods. Inheritance, interfaces, traits, containment, properties and parameters with their types, and call sites. Plain and static calls, calls on `self`, `static`, `parent` and `$this`, and method calls through a typed or assigned property. The classes a `new` creates, as `instantiates`, and a `Foo::class` or `\A\B\Foo::class`, as `references_class`; a call to a PHP builtin function makes nothing. Reads a parse tree. |
| `js_basic` | 0.0.1 | JavaScript scripts, and the functions that have a name of their own, each under its script's path. Functions assigned to a dotted name, `A.b.c = function () {}`, under the dotted name when `A` is a global object such as `window`, else under its script's path, and functions written in an object literal assigned to one, the same way. Calls written `f(x)`, and member calls such as `A.b.c()` to a mapped member function, from the function or the script that holds them, as `js_calls`; a member call on a shared object that is not a browser one, which no script assigns, ends at one unresolved member function. A call to a JavaScript or browser global, such as `parseInt` or `fetch`, makes nothing. It reads `.js` files only. Reads a parse tree. |
| `go_basic` | 0.0.3 | Go functions, methods, structs and interfaces, each under its package's import path. Calls written `f(x)` inside one package, and `pkg.F(x)` through an import, to another package of the module or to an unresolved function outside it. It skips test files and `vendor`, and needs the module path in the settings as `values.module`. Reads a parse tree. |
| `yaml_basic` | 0.1.0 | Claims `.yml` and `.yaml` files for rutters that depend on it. No rules of its own. |
| `twig_basic` | 0.1.0 | Claims `.twig` files for rutters that depend on it. No rules of its own. |
| `typescript` | 0.1.0 | TypeScript modules, imports, packages and functions in `.ts` and `.tsx` files, and calls from one function to a function the file binds by name. It reads the files as text; the project sets the folder the `@/` alias points at as `typescript_alias_root`. |
| `react` | 0.1.0 | React components and hooks, named by convention, the components a function renders, the hooks it uses, and the `use client` or `use server` directive. It reads the files as text. Depends on `typescript`. |
| `nextjs` | 0.2.0 | Next.js App Router pages, layouts, route handlers with their HTTP methods, middleware and special files under `app`. A `fetch` of a route, a link to a page, and a name or prop that holds a route URL. It reads the files as text. Depends on `react`. |

</details>

<details>
<summary><strong>Drupal: 3 core rutters and 14 contributed-module rutters</strong></summary>

The three core rutters come first. Each contributed module has a rutter of its own, pinned
beside `drupal_basic` when the site uses that module.

| Rutter | Version | What it finds |
|---|---|---|
| `drupal_basic` | 0.3.0 | Configuration, modules, themes, services, routes, permissions, libraries, templates, hooks, entity types, fields, displays and plugins. The services and entity types that `\Drupal::service('x')`, `$container->get('x')`, `\Drupal::entityQuery('x')` and an entity type manager's `getStorage('x')` name in PHP functions and methods, with a static `load()` on a module's own entity class. The route and path a method or function links to, and the views plugins a view uses. Plugin types with their plugins and managers, an entity type's handler classes, a constraint's validator, and the service that answers a custom route requirement. Events with their subscribers and dispatchers, custom Twig filters and functions with the templates that call them, the field storages that code and templates name, and the block, theme hook or field a suggestion template's name points to. The roles that `hasRole`, `addRole` and `removeRole` name, the configuration objects that `\Drupal::config('x')` and a config factory name, the queue workers whose queues a queue factory gets, and the forms a `form_<id>_alter` hook alters. The factory a service is built by, local tasks, local actions and contextual links with their routes and classes, entity and confirm forms typed as forms, and the macro files a template imports. Hooks from `Hook` attribute methods, and from procedural functions named by their file's name, such as `mymod_cron` in `mymod.module`. Each PHP attribute with the class, method, function, property or parameter it sits on, each route subscriber as a route alter marked `resolution: runtime`, and the themes `core.extension` installs. The module or theme that holds each route, service, library, class and template, the form class a `getForm(X::class)` builds, and the route a template's path reaches by its shape. Depends on `php_basic`, `yaml_basic` and `twig_basic`. |
| `drupal_js_basic` | 0.0.1 | Drupal behaviors, the behaviors they attach and the calls written in them, `drupalSettings` keys that PHP attaches and behaviors read, the libraries that PHP, templates and components attach, the library scripts and stylesheets, and the paths that script strings, template literals and `Drupal.url()` write, with the route a template literal's path reaches by its shape. A request whose URL is built at run time is a node marked `resolution: runtime`. Depends on `js_basic` and `drupal_basic`. |
| `drupal_more` | 0.1.0 | Base fields an entity class defines and the entity type a reference field targets, the PHP class or trait that reads or writes a field by name, a `has_handler` edge from an entity class to each handler class its annotation names, the storage schema, views data and translation handlers among them, which `drupal_basic` does not read, `Job::create('type')` calls, and `->hasPermission('literal')` checks. Depends on `drupal_basic` and `advancedqueue_basic`. |
| `ai_basic` | 0.0.1 | The AI module's agent plugins and function call plugins, by attribute, each joined to its class. |
| `advancedqueue_basic` | 0.0.1 | The Advanced Queue module's job type plugins, by attribute or annotation, each joined to its class. |
| `config_pages_basic` | 0.0.1 | Each Config Pages type, from its config file, as a bundle of the entity type `config_pages`. |
| `crop_basic` | 0.0.1 | Each Crop API crop type, from its config file, as a bundle of the entity type `crop`. |
| `drupal_next` | 0.1.0 | The next module's sites, per-bundle settings and four plugin kinds, the site's preview and revalidate handlers in the Next.js app, Drupal endpoints with their HTTP methods from routing files and REST resources, the TypeScript calls to an endpoint, JSON:API resources and OAuth scopes. Depends on `drupal_basic`, `php_basic`, `typescript`, `react` and `nextjs`. |
| `drush_basic` | 0.0.1 | Drush commands in the custom modules, from the `Command` attribute or the `@command` tag, each joined to its method and class. |
| `eca_basic` | 0.0.1 | Each ECA model, from its config file, with the event, condition and action plugins it names, a custom module's ECA event and condition plugins, the events its event plugins react to, its entries and the successors between them, and the field storages, roles, bundles and entity types its configuration names. |
| `eck_basic` | 0.0.1 | Each Entity Construction Kit entity type, and each of its bundles, from their config files. The entity type a static `EckEntityType::load()` names. |
| `paragraphs_basic` | 0.0.1 | Each paragraph type, from its config file, as a bundle of the entity type `paragraph`. The entity type a static `load()` on `Paragraph` or `ParagraphsType` names, and the paragraph field storage a template reads as `paragraph.field_x`, or as `content.field_x` in a `paragraph--` template. |
| `profile_basic` | 0.0.1 | Each Profile type, from its config file, as a bundle of the entity type `profile`. The entity type a static `load()` on `Profile` or `ProfileType` names. |
| `salesforce_basic` | 0.0.1 | Salesforce mapping field plugins; each mapping with its Salesforce object and its edges to the bundle, entity type and fields it maps, the field storages its tokens name and the webform elements its webform submission tokens and `WebformElements` rows name; the Salesforce events that subscribers name; the entity type a static `load()` on `MappedObject` or `SalesforceMapping` names. Depends on `webform_basic`. |
| `salesforce_eca_basic` | 0.0.1 | The ECA event plugins of the Salesforce ECA module, added to `eca_basic`'s table of event plugins, so a model that reacts to one links to the Salesforce event a subscriber subscribes to. Depends on `eca_basic` and `salesforce_basic`. |
| `twig_tweak_basic` | 0.0.1 | The block plugins, menus, entity types, entity forms and field storages that Twig Tweak functions such as `drupal_block('x')` name in templates. |
| `webform_basic` | 0.0.1 | Webform handler plugins, by annotation, each joined to its class, and each webform, from its config file, as a bundle of `webform_submission`, with the handlers it runs and its elements. The entity type a static `load()` on `Webform` or `WebformSubmission` names. |

</details>

<details>
<summary><strong>Laravel</strong></summary>

| Rutter | Version | What it finds |
|---|---|---|
| `laravel_basic` | 0.0.5 | Laravel routes with the prefixes and names of `Route::prefix()->name()->group()` groups, each joined to its controller method, its resource controller or the view it renders, controllers, models, migrations, Blade views with their includes, extends and component tags, and configuration files with the text keys of the array each returns. The views and keys that `view('x')` and `config('x.y')` calls name in PHP functions and methods. Depends on `php_basic`. Reads text, and a parse tree for the calls. |

</details>

<details>
<summary><strong>Examples</strong></summary>

| Rutter | Version | What it finds |
|---|---|---|
| `python_text` | 0.1.0 | Python modules, top-level classes and functions, imports and calls. Reads text. |
| `typer_text` | 0.1.0 | Typer apps, commands and mounts. Depends on `python_text`. |
| `speckitty` | 0.1.0 | spec-kitty missions and their templates. |

</details>

<details>
<summary><strong>Reference packs</strong></summary>

The bundle also holds five older reference packs. They hold vocabulary only and cannot make a map:
`periplus validate` finds no schema error in them, and reports the same problems `periplus map`
reports for a project that pins them, such as the rules in them the engine does not execute.

| Pack | Version |
|---|---|
| `php` | 0.1.0 |
| `drupal` | 0.1.0 |
| `yaml` | 0.0.1 |
| `twig` | 0.0.1 |
| `go` | 0.0.2 |

</details>

The bundled rutters are in `src/periplus/packs`. The examples are in
`examples/second-stack/packs`. The manifest of every rutter in the tables above, except
`yaml_basic`, `twig_basic`, `typescript`, `react`, `nextjs`, `drupal_more`, `drupal_next`, the
examples and the reference packs, opens with a list of what it does not map yet.

To map a Go module, run Periplus at the module's root. Give the module
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

New in this release:

- **Marks.** A rutter can declare attributes with a short mark, such as `[not installed]`. Every
  row that names a marked thing prints its mark, and `find --mark` selects by it.
- **Cause.** Each edge kind says which end sets off the other. `neighbors` lists what an item sets
  off and `affected` what sets it off, hop by hop, and stop at hubs.
- **Depth and reach.** `depth` says how far those walks go before you list them. `reach` prints
  `depth`, both walks, `only` and `hubs` in one reply, within a character budget.
- **Sets and pipes.** `only`, `hubs`, `members`, `pieces` and `count` work on a set of ids.
  `--ids` prints ids, and `-` reads them, so one command feeds the next. Map files combine with
  `extract`, `join`, `common`, `minus` and `diff`.
- **Description tools.** `in` and `at` go from a file or a line to the map. `undescribed` counts
  what is left to describe, `order` puts it in reading order, and `stamp` and `stale` keep the
  descriptions in step with the code.
- **First run.** `init` finds the project's folders and pins each bundled rutter it detects.
  `map` exits 33 instead of writing an empty map.
- **find.** It ranks main things first, counts before it lists, keeps to a character budget, and
  finds edges by their description or code line.

Map again after upgrading, so the walks can read each edge kind's cause.

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
5. Run `periplus validate <pack>`. It names each file and place that disagrees with the schemas,
   and reports what `periplus map` refuses the rutter for before it reads a file. A rutter that
   does not validate stops the map.
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
`.periplus/packs`, the user configuration directory, the bundled rutters and each `pack_paths`
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
| [`docs/rutter-author-guide-references.md`](docs/rutter-author-guide-references.md) | Calls read from a parse tree; tables, `add_table_rows` and `in_table`; `encloses_for`; and every key the schemas accept that the engine does not run. |
| [`docs/rutter-author-guide-imports.md`](docs/rutter-author-guide-imports.md) | Import paths and a call's arguments. |
| [`docs/rutter-author-guide-abilities.md`](docs/rutter-author-guide-abilities.md) | A condition on a second child, an id that must fit a pattern, a declared end, and a class constant as a call's argument. |
| [`docs/rutter-author-guide-map-rules.md`](docs/rutter-author-guide-map-rules.md) | Map rules: rules that read the map the file rules made, run in passes, one hop each. |
| `examples/second-stack/packs` | Three working text rutters to copy: `python_text`, `typer_text` and `speckitty`. |
| `periplus validate <pack>` | Checks one rutter's files. It names each disagreement with the schemas, by file and place, and what `periplus map` refuses the rutter for before it reads a file. |
| [`docs/map-report-guide.md`](docs/map-report-guide.md) | Reading the map report: each part in the order to read it, what it means, and what to do when it is not empty. |

A parse-tree rutter pins its grammar under `grammar` in `pack.yaml`, as `php_basic` does.
Periplus installs the PHP, Go and JavaScript grammars. Another language needs its
`tree-sitter-<language>` package installed beside Periplus, or the map stops at exit 28.

An AI that writes a rutter reads `periplus spec` first, then the guide pages in the order above.
Then it runs the loop. The map's `referenced` and `unresolved` nodes say which rule to write next.

## Read the map

Twenty-nine commands read a written map, and stop. They read the map, the descriptions file and
the source line under each row, and nothing more. They come in two layers: small commands that do
one job each, and two macros, `reach` and `slice`, that combine them in one reply.

- **Learn the map's words.** `periplus types` counts the node types and edge kinds. `periplus
  legend` says what each kind and type means and which types a kind joins.
- **Cheap counts, to decide what to read.** `periplus depth ID...` says how far what the ids set
  off, and what sets them off, reaches. `periplus count ID...` counts a set by type and state, with
  the edges among it. `periplus pieces ID...` splits a set into the groups edges join. `periplus
  files ID...` counts a set by file. `periplus hubs ID...` lists the hubs a walk stops at.
- **Fetch things and their links.** `periplus find TEXT` searches node ids, attributes and
  descriptions, then edge descriptions and code lines. `periplus show ID...` prints nodes and their
  edges. `periplus neighbors ID...` and `periplus affected ID...` list what the ids set off and
  what sets them off, hop by hop, by the cause each edge kind declares. `periplus only ID...` lists
  what the ids alone set off. `periplus members ID...` lists what a container holds. `periplus in
  FILE...` lists what the map holds in a file, and `periplus at FILE:LINE...` names the mapped
  thing at a line and what holds it. `periplus path FROM TO` prints the shortest chains between
  two.
- **Macros.** `periplus reach ID...` prints `depth`, `neighbors`, `affected`, `only` and `hubs` for
  the ids in one reply, to a character budget. `periplus slice WORDS` prints the piece of the map
  around the things some words or ids name, in linked pieces grouped by file. Each names the small
  command that prints in full a part it cut.
- **Sets and map files.** `periplus extract`, `join`, `common`, `minus` and `diff` write and compare
  map files. `periplus export` prints the map as GraphML, DOT or Mermaid.
- **Descriptions.** `periplus undescribed` counts the main things with no description yet.
  `periplus order ID...` puts a set in order, each thing after what it uses. `periplus stamp`
  writes into each node entry of the descriptions file a fingerprint of its code, and `periplus
  stale` lists the entries whose code changed since.

A command that lists things takes `--ids` and prints one full id a line; a command that takes ids
reads them from standard input when given `-`, so `periplus neighbors ID --depth all --ids |
periplus count -` joins two. `periplus check-map` runs the full schema check that the other
commands skip. The [navigation guide](docs/navigation.md) gives each command's options, output and
exit codes, with an example you can run.

### Slice, sets and export

`periplus slice` prints a piece of the map, and with `--out FILE` writes it to a map file of its
own. `periplus extract ID... --out FILE` writes exactly the things some ids name and the edges
among them. Map files combine as sets: `periplus join`, `common` and `minus` read two or more and
count, or with `--out` write, what any, every, or only the first of them holds; `periplus diff OLD
NEW` lists the things and edges added, removed and changed. `periplus export` prints the whole map
as GraphML, DOT or Mermaid. To draw a part of the map, slice it to a file, then export the slice.

```
periplus slice [ID ...] [--from ID...] [--path PREFIX]... --out FILE [--direction out|in|both] [--depth N] [--kind K]... [--limit N] [--map PATH]
periplus export --format graphml|dot|mermaid [--map PATH]
```

With `--out`, `slice` starts from the ids you name and from every node whose first file starts with `--path PREFIX`, and follows edges
from them. Repeat `--path` for several prefixes. `--direction out` and `in` follow edges one way; `both` follows an edge either way at every hop (default `both`).
`--depth N` sets how many edges to follow (default 1), and `--kind K` keeps only edges of kind `K`;
repeat it for several. `--limit N` stops the slice when it would hold more than `N` items (default
500, `0` for no limit): the command exits 32 and writes nothing. An unknown id, or a prefix that
matches nothing, exits 31. A slice is a smaller map, so name it so it cannot replace the full
map.

`export` prints to standard output and its warnings to standard error. GraphML names each node by
a generated token, labels it with a short name and carries the map id as its `id` data, with the
node type and state, the edge kind as the edge label, and the file and line where there is one.
DOT and Mermaid label each node with its id and type.

```
periplus slice --path src/Billing/ --out billing.map.json
periplus export --format graphml --map billing.map.json > billing.graphml   # open in Gephi Lite
periplus export --format dot --map billing.map.json > billing.dot           # render with Graphviz
periplus export --format mermaid --map billing.map.json > billing.mmd       # wrap in a mermaid code fence in a pull request
```

Gephi Lite handles light graphs; use Gephi for more than about 10,000 nodes. Mermaid on GitHub may
not draw a graph above 500 edges or 50,000 characters, and the export warns when it passes either.

## CLI reference

Run each command in the project folder.

```
# set up and build
periplus init                      # create .periplus/ and a settings file, pinning the rutters and folders it finds
periplus status                    # report the settings, where each value came from, and the pack search path
periplus spec [PACK] [--summary]   # print the rutter contract, and what one rutter declares and inherits
periplus validate PACK             # check one rutter against the schemas and what map refuses it for
periplus update                    # move each pin to the installed version of that rutter
periplus map                       # map this project and write .periplus/map.json, with a run report
periplus check-map                 # check every node and edge of the map against the map schema
periplus skills install            # copy the Claude skills Periplus ships into ~/.claude/skills

# learn the map's words
periplus types                     # count the node types and edge kinds in the written map
periplus legend                    # say what each edge kind and node type in the map means

# cheap counts
periplus depth ID...               # say how far what an item sets off, and what sets it off, reach
periplus count ID...               # count the things ids name, by type and state, and the edges among them
periplus pieces ID...              # split ids into the groups that edges among them join
periplus files ID...               # list the files that hold a set of things, most first
periplus hubs ID...                # list the hubs the walk by cause from the ids stops at

# fetch things and their links
periplus find TEXT                 # find the things and edges that hold some words, main things first
periplus show ID...                # show nodes and the edges at each
periplus neighbors ID...           # list what an item sets off, hop by hop
periplus affected ID...            # list what sets an item off, hop by hop
periplus only ID...                # list what the ids set off that nothing else sets off
periplus members ID...             # list what a container holds, by the map's grouping kinds
periplus in FILE...                # list the things the map holds in each file, in line order
periplus at FILE:LINE...           # name the mapped thing at a file and line, and what holds it
periplus path FROM TO              # show every shortest chain of edges from one item to another

# macros
periplus reach ID...               # print depth, neighbors, affected, only and hubs in one reply
periplus slice WORDS               # print the piece of the map around some words, ids or a path
periplus slice ID --out FILE       # write the items around some items or a path to a smaller map

# sets and map files
periplus extract ID... --out FILE  # write the things ids name, and the edges among them, to a map file
periplus join MAP MAP...           # count or write (--out) the things and edges in any of the maps
periplus common MAP MAP...         # count or write (--out) the things and edges in every one of the maps
periplus minus MAP MAP...          # count or write (--out) the things in the first map and in no other
periplus diff OLD NEW              # list the things and edges added, removed and changed between two maps
periplus export --format F         # print the map as graphml, dot or mermaid

# descriptions
periplus undescribed [ID...]       # count the main things with no description, by file, type or container
periplus order ID...               # list a set so that each thing comes after what it calls or uses
periplus stamp                     # write a fingerprint of its code into each node entry of the descriptions file
periplus stale                     # list the node entries whose code changed or whose node is gone
```

`periplus validate` takes a bare `name`, or `name@version` to pick one of several copies.
`periplus update` leaves project-local and unknown pins as they are. Every command but `init`, `skills`
and `export` takes `--format json`. The twenty-five commands that read one map take `--map PATH`; the
[navigation guide](docs/navigation.md) gives their other options. `periplus --version` prints the
installed version, and `periplus <command> --help` gives each command's options.

## Troubleshooting

- **`periplus map` stops at exit 17.** The project pins no rutter, so there is nothing to map.
  Run `periplus init`, or pin a rutter under `packs` in `.periplus/settings.yml`. Exit 17 also
  marks a map that fails its own schema, which is an engine defect. Nothing is written in
  either case.
- **`periplus map` stops at exit 28: a grammar mismatch.** A rutter's `grammar` in `pack.yaml`
  pins a parser runtime or a grammar version other than the one installed, or one that is not
  installed. The message names the rutter, the package, the version pinned and the version
  found. For a language other than PHP, Go and JavaScript, install its `tree-sitter-<language>`
  package at the pinned version. The check runs before any
  source file is opened.
- **`periplus map` stops at exit 33: no file was selected.** Every pinned rutter looked only in
  folders that hold none of its files, so no map was written and an existing map was left as it
  was. The report's first section names each rutter and the folders it looked in. Declare where
  the code is under `folders` in `.periplus/settings.yml`.
- **A navigation command stops at exit 29, 30 or 31.** It found no map, the file is not a map,
  or the id names no node. The [navigation guide](docs/navigation.md) gives the remedy for each.

## Tests and checks

The pytest suite tests the engine and the bundled rutters. `scripts/demo.sh` runs the acceptance
scripts in `scripts/demo.d` and stops at the first failure: one for each command, one for each
bundled stack family, and the README and guide examples. Each script maps a small project and
compares the result with what it expects. A person runs them at the end of a task. The CI workflow
behind the checks badge does not run them.

To propose a change, read [`CONTRIBUTING.md`](CONTRIBUTING.md).

## How Periplus behaves

A shape the map does not hold is a rule not written yet. The map marks what it could not resolve:
unresolved names, run-time marks, call sites with no edge, and skipped rows in the map report. Each
rutter's `pack.yaml` header says what it does not map yet, and the `periplus-gaps` skill reads a map
and says which rule is missing.

The engine and the map format work as follows.

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

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Built with AI assistance. Periplus uses no AI to make a map.
