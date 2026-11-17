# Reading the map report

`periplus map` writes the map and prints a report on the run. The map says what was found. The
report says how far to trust it: what stopped the run, which files no rule read, and which matches
a rule could not finish. This page lists each part of the report in the order to read it, says what
it means, and says what to do when it is not empty. It runs on a small Drupal module, planted
below, and every command on the page prints what is shown.

The report comes in two forms. `periplus map` prints text for a person; `periplus map --format
json` prints one JSON document for a script. The JSON keys and the text headings differ, so each
section below names both. The README's [loop](../README.md#the-loop) is the short form of this page.

## The planted project

The project pins three bundled rutters, `drupal_basic`, `js_basic` and `drupal_js_basic`, and its
own rutter `myproject`, planted under [Where a rule belongs](#where-a-rule-belongs).

<!-- nav-file: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - drupal_js_basic@0.0.1
  - myproject@0.0.1
```

A module named `greet`:

<!-- nav-file: web/modules/custom/greet/greet.info.yml -->
```yaml
name: Greet
type: module
core_version_requirement: ^10
```

Its libraries file holds two libraries: `banner` lists one script by a path relative to the
module, and `cdn` lists one script by URL only.

<!-- nav-file: web/modules/custom/greet/greet.libraries.yml -->
```yaml
banner:
  js:
    js/banner.js: {}
cdn:
  js:
    https://cdn.example.com/banner.js: {type: external}
```

Its `.module` file attaches the library and one setting, `greetBanner`, with the key `color`
nested below it.

<!-- nav-file: web/modules/custom/greet/greet.module -->
```php
<?php

/**
 * Implements hook_preprocess_page().
 */
function greet_preprocess_page(array &$variables): void {
  $variables['greet'] = [
    '#attached' => [
      'library' => ['greet/banner'],
      'drupalSettings' => [
        'greetBanner' => [
          'color' => 'red',
        ],
      ],
    ],
  ];
}
```

Its script declares one behavior, which reads the setting. It fetches one path written whole and
one joined with `+`.

<!-- nav-file: web/modules/custom/greet/js/banner.js -->
```js
(function (Drupal, drupalSettings) {
  Drupal.behaviors.greetBanner = {
    attach(context) {
      const banner = drupalSettings.greetBanner;
      fetch('/greet/hello');
      fetch('/greet/user/' + banner.color);
    },
  };
})(Drupal, drupalSettings);
```

Its `README.md` says what the module does. No rule of the pinned rutters reads Markdown.

<!-- nav-file: web/modules/custom/greet/README.md -->
```markdown
# Greet

Shows a greeting banner on every page.
```

## Run the map

Run `periplus map` in the project folder. The report is long, because it lists every rule the
pinned rutters and the ones they depend on hold; open it below.

<details>
<summary>The text report</summary>

<!-- nav-run -->
```
$ periplus map
periplus map

Map:
  path    /path/to/project/.periplus/map.json
  nodes   12
  edges   14
  internal: 12 nodes and 10 edges left out

Boundaries:
  total 0

Unknown boundaries:
  total 0

Type conflicts:
  total 0
  edges left out 0

Files:
  selected  5
  excluded  0
  unread    1
  unlisted  0

Files no rule read, by ending:
  md 1

Files no rule read:
  web/modules/custom/greet/README.md

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  myproject 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
...
  drupal_js_basic path_in_script_string fired 1
...

Rules that fired zero times:
...

Map rule passes:
  pass 1: drupal_basic claim_folder_0 fired 1, drupal_basic claim_folder_1 fired 1, drupal_basic claim_folder_2 fired 1, drupal_basic library_in_module fired 2
  pass 2: drupal_basic function_in_module fired 1, drupal_basic template_member_of_module fired 1, drupal_js_basic script_in_module fired 1, drupal_js_basic behavior_in_module fired 1
  pass 3: none

Rules not executed:
  none

Matches skipped:
  web/modules/custom/greet/greet.libraries.yml:4 library_script fired and emitted nothing

Attributes that differ between files:
  none

Problems:
  none
```

</details>

## The report, part by part

Read the parts in this order. The first ones say whether the map can be trusted at all; the later
ones say how the rules spent the run.

### `problems`

Text heading: Problems. Each row is an exit code and a message. A problem stops the run: no map is
written, `map` is `null` (text: `not written`), and the command exits with the lowest code listed.
When it is not empty, fix what the message names first, and run the map again. Nothing else in the
report is worth reading until it is empty.

Exit 33 says no file was selected at all: every pinned rutter looked only in folders that hold
none of its files. No map is written, and a map already at the path is left as it was. Read
`empty_packs`, then declare where the code is under `folders` in `.periplus/settings.yml`.

### `empty_packs`

Text heading: Packs that selected no file, printed first and only when a row exists. Each row is
a pinned rutter whose file rules selected no file. It names each folder those rules reach that
names no other folder, with its value and how many folders it found, or `no such folder`. When a
folder is missing, the row ends by saying where to declare it; when every folder was found, it
says they hold no file the rutter's rules read. A rutter that matches nothing in this project is
not an error, so the run goes on. When the rutter should
have found files, declare the folder it names under `folders` in the settings, and run the map
again.

### `parse_errors`

Text heading: Files that did not parse cleanly. Each row is a file whose parse tree holds an
error, so the rules may have missed part of what it declares. When it is not empty, open the file:
it may hold a syntax error, or a form the grammar does not know.

### `unread`

Text headings: the `unread` count under Files; Files no rule read, by ending; and Files no rule
read, which shows the first 20 and says how many more the JSON report lists. Each row is a file in
the rules' folders that no rule read. The map knows nothing about it. When it is not empty, look at
the endings first: a whole family of files is a rule to write, and a single file may be one to
exclude. Here the `greet` module's `README.md` is listed, since no rule reads Markdown. A file
outside every rule's folder, such as the files under `.periplus`, is not counted.

### `unlisted`

Text headings: the `unlisted` count under Files, and Folders that could not be listed. Each row is
a folder below the rules' folders that the walk for unread files could not list, most often for
want of permission. Its files are neither read nor counted as unread. When it is not empty, fix
the folder's permissions or exclude it.

### `not_executed`

Text heading: Rules not executed. Each row is a pack, a rule and the reason the engine cannot run
it, such as a key the engine does not support. The rule made nothing. When it is not empty, read
the reason: rewrite the rule in a form the engine runs, or accept the gap.

### `skipped`

Text heading: Matches skipped. Each row is a file, a line, a rule and the reason. The rule matched
there but could not build the node or edge it emits, so nothing was made for that match. When it
is not empty, open the file at the line. The shape there is one the rule does not cover.

A map rule also has a row when it would start from, or follow a `node` step to, a node another map
rule made with an id no file rule found. The reason names that node and the map rule that made
it. Such a node is never read, so start the rule from a node a file rule finds.

### `zero_fires`

Text heading: Rules that fired zero times. Each row is a pack and a rule that ran over the project
and matched nothing. Most rules of a broad rutter fire zero times on a small project, as here.
When a rule you expected to fire is listed, the files hold a shape it does not match: plant that
shape alone in a small project to see why.

### `differing`

Text heading: Attributes that differ between files. Each row is a node and an attribute that two
files give different values. The map writes the attribute as `differs` rather than pick one. When
it is not empty, find the files that declare the node and decide which value is right.

### `executed`

Text heading: Rules executed. Each row is a pack, a rule and how many times it fired. It is the
count behind `zero_fires`. When a count is higher or lower than the files suggest, run the
navigation commands on the nodes the rule makes.

### `map_passes`

Text heading: Map rule passes. Map rules join what the file rules found. Each pass lists the map
rules that fired in it; the last pass adds nothing. An empty list means no map rule runs. There is
nothing to fix here; it explains edges no single file holds.

### `packs`

Text heading: Packs. Each row is a rutter and its version: the ones pinned and the ones they
depend on, such as `php_basic` here. When a version is not the one you pinned, run `periplus
status`.

### `selected`

Text: the `selected` count under Files. How many files the rules read. When it is lower than you
expect, compare it with `unread`.

### `opened`

Not in the text report. The JSON list of the files the rules opened, in order. Use it to confirm a
file was read at all.

### `excluded`

Text: the `excluded` count under Files. How many files the exclude patterns in the settings
removed. When it is higher than you expect, check the patterns.

### `nodes`

Text: the `nodes` count under Map. How many nodes the map holds. When it is lower than you
expect, check `unread` for files no rule read and `skipped` for matches that made
nothing.

### `edges`

Text: the `edges` count under Map. How many edges the map holds. With `nodes`, it is the quickest
sign that a change to a rule did something.

### `internal`

Text: the line `internal: N nodes and M edges left out` under Map, printed only when either count
is above zero. JSON: `{"nodes": N, "edges": M}`. How many nodes of a type marked `internal`, or
below one, the written map leaves out, and how many edges with an end on one. Those types serve
the map rules only. There is nothing to fix here; it explains why `nodes` and `edges` are lower
than the rules made. The README's [What the map holds](../README.md#what-the-map-holds) says what
stays in the map, call sites marked `resolution: runtime` among them.

### `boundaries`

Text: the Boundaries section. JSON: `{"total": N, "by_node": [{"node", "edges"}]}`. `total` counts
the nodes in state `boundary`: what a rule identified outside the mapped code. Each row is one such
node and the number of edges into it, most first; the text shows ten. An API node's row counts the
project things and the marked ends that enter it.

### `unknown_boundaries`

Text: the Unknown boundaries section. JSON: `{"total": N, "by_pack": {...}, "by_reason": {...}}`.
`total` counts the nodes in state `unknown_boundary`: what the map could not make known.
`by_pack` names the pack whose rule set the mark. `by_reason` is `no rule`, an end that leaves the
mapped code with no rule identifying it yet, or `run-time`, a call whose target is built at run
time. Each `no rule` node is a rule a rutter still lacks. No navigation command selects nodes by state;
the map's `counts.nodes_by_state` counts them, and each row a command prints names its state.

### `type_conflicts`

Text: the Type conflicts section. JSON: `{"total": N, "edges_left_out": M, "by_node": [{"node",
"candidates"}]}`. `total` counts the nodes that rules typed as types on different branches of one
ancestor, such as two kinds of form for one class. Each such node keeps the nearest type the
candidates share, and its `type_conflict` attribute names each candidate as `<type> by
<pack>/<rule>`. `edges_left_out` counts the edges only a candidate type could carry, which the map
does not write. Each row is one node and its candidates; the text shows ten. Fix the rule that
should not match the node, or declare one candidate below the other. `periplus find --type <type>`
lists the nodes a candidate type names.

### `map`

Text: the `path` row under Map. Where the map was written, or `null` when a problem stopped the
run. Read the map with the navigation commands in [docs/navigation.md](navigation.md).

## Read the map

The setting `greetBanner` is one node. The `.module` file provides it and the behavior reads it.

<!-- nav-run -->
```
$ periplus show drupal.js_setting::greetBanner
periplus show drupal.js_setting::greetBanner
type: drupal.js_setting
state: mapped
location: web/modules/custom/greet/greet.module:11
provenance: drupal_js_basic:setting_attached_in_array  declared
description: none

Outgoing (0):
  none

Incoming (2):
  provides_setting:
    php.function::greet_preprocess_page  php.function  mapped  web/modules/custom/greet/greet.module:11  x1  inferred  drupal_js_basic:setting_attached_in_array_in_function
      | 'greetBanner' => [
  reads_setting:
    drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  web/modules/custom/greet/js/banner.js:4  x1  declared  drupal_js_basic:setting_read_in_behavior
      | const banner = drupalSettings.greetBanner;
```

The script reaches the behavior it declares, the path it fetches whole and the module whose
folder holds it. The function `attach` written in the behavior's object is the behavior's, so it
is no node of its own. `fetch` is a browser global, so its calls make no node. `--raw` follows
every edge leaving the script, whatever its cause:

<!-- nav-run -->
```
$ periplus neighbors js.file::web/modules/custom/greet/js/banner.js --raw
periplus neighbors js.file::web/modules/custom/greet/js/banner.js
3 items
  1  drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  via script_declares_behavior from js.file::web/modules/custom/greet/js/banner.js  web/modules/custom/greet/js/banner.js:2
      | Drupal.behaviors.greetBanner = {
  1  drupal.module::greet  drupal.module  mapped  via script_in_module from js.file::web/modules/custom/greet/js/banner.js  web/modules/custom/greet/js/banner.js:1
      | (function (Drupal, drupalSettings) {
  1  drupal.url_path::/greet/hello  drupal.url_path  referenced  via script_links_to_path from js.file::web/modules/custom/greet/js/banner.js  web/modules/custom/greet/js/banner.js:5
      | fetch('/greet/hello');
```

## A shape the map lacks

The map lacks a node or an edge the code holds. Before you write a rule for it, look for it in the
Not mapped yet comment at the top of the `pack.yaml` of the rutter that maps that part of the stack,
when it has one; not every rutter does.
A shape listed there is a rule not written yet: the rutter's authors saw it and left it out, so it needs a new rule, not a fix.

Do not wait for the report to point at it. A rutter refuses a shape by not matching it, so a
refused shape beside shapes the rule accepts leaves no report row at all: the rule fires on the
accepted ones and is listed under `executed` with its count. The report shows a shape not mapped
yet only in two cases: a rule that matched nothing in the whole project, under `zero_fires`, and a match the
rule found and could not finish, under `skipped`. The three examples below show both rows, and a
shape that leaves none.

A path joined with `+` is a shape `drupal_js_basic` does not map yet. In the planted project its
rule `path_in_script_string` fires once, on the whole path, and the joined path leaves no row. A
second project, `joined-only`, beside the planted one, holds one script with only a joined path.

<!-- nav-file: joined-only/.periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - drupal_js_basic@0.0.1
```

<!-- nav-file: joined-only/web/modules/custom/join/js/join.js -->
```js
const id = 7;
fetch('/join/user/' + id);
```

Mapped there, the report lists `path_in_script_string` under `zero_fires`, in the text heading
Rules that fired zero times.

<details>
<summary>The text report of joined-only</summary>

<!-- nav-run: joined-only -->
```
$ periplus map
periplus map

Packs that selected no file:
  drupal_basic: config = ./config/sync, no such folder; contrib_module = ./web/modules/contrib, no such folder; custom_module = ./web/modules/custom, 1 folder found; custom_theme = ./web/themes/custom, no such folder; if the code is elsewhere, declare the folder under folders in .periplus/settings.yml

Map:
  path    /path/to/project/.periplus/map.json
  nodes   1
  edges   0
  internal: 3 nodes and 2 edges left out

Boundaries:
  total 0

Unknown boundaries:
  total 0

Type conflicts:
  total 0
  edges left out 0

Files:
  selected  1
  excluded  0
  unread    0
  unlisted  0

Files no rule read, by ending:
  none

Files no rule read:
  none

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
...
  drupal_js_basic path_in_script_string fired 0
...

Rules that fired zero times:
...
  drupal_js_basic path_in_script_string
...

Map rule passes:
  pass 1: none

Rules not executed:
  none

Matches skipped:
  none

Attributes that differ between files:
  none

Problems:
  none
```

</details>

A library that lists only a URL is a shape not mapped yet too: the URL names no file to map. The rule
`library_script` matches the entry of the library `cdn` in the planted libraries file and cannot
build an edge from it, so the report of the planted project lists it under `skipped`, in the text
heading Matches skipped, at its libraries file.

<details>
<summary>The text report of the planted project</summary>

<!-- nav-run -->
```
$ periplus map
periplus map

Map:
  path    /path/to/project/.periplus/map.json
  nodes   12
  edges   14
  internal: 12 nodes and 10 edges left out

Boundaries:
  total 0

Unknown boundaries:
  total 0

Type conflicts:
  total 0
  edges left out 0

Files:
  selected  5
  excluded  0
  unread    1
  unlisted  0

Files no rule read, by ending:
  md 1

Files no rule read:
  web/modules/custom/greet/README.md

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  myproject 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
...

Rules that fired zero times:
...

Map rule passes:
  pass 1: drupal_basic claim_folder_0 fired 1, drupal_basic claim_folder_1 fired 1, drupal_basic claim_folder_2 fired 1, drupal_basic library_in_module fired 2
  pass 2: drupal_basic function_in_module fired 1, drupal_basic template_member_of_module fired 1, drupal_js_basic script_in_module fired 1, drupal_js_basic behavior_in_module fired 1
  pass 3: none

Rules not executed:
  none

Matches skipped:
  web/modules/custom/greet/greet.libraries.yml:4 library_script fired and emitted nothing

Attributes that differ between files:
  none

Problems:
  none
```

</details>

A setting key nested below a first-level key is the third. The rule `setting_attached_in_array`
fires on the first-level key `greetBanner` of the planted `.module` file, and the nested key
`color` appears nowhere: no node, no report row.

<!-- nav-run -->
```
$ periplus show drupal.js_setting::greetBanner
periplus show drupal.js_setting::greetBanner
type: drupal.js_setting
state: mapped
location: web/modules/custom/greet/greet.module:11
provenance: drupal_js_basic:setting_attached_in_array  declared
description: none

Outgoing (0):
  none

Incoming (2):
  provides_setting:
    php.function::greet_preprocess_page  php.function  mapped  web/modules/custom/greet/greet.module:11  x1  inferred  drupal_js_basic:setting_attached_in_array_in_function
      | 'greetBanner' => [
  reads_setting:
    drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  web/modules/custom/greet/js/banner.js:4  x1  declared  drupal_js_basic:setting_read_in_behavior
      | const banner = drupalSettings.greetBanner;
```

<!-- nav-run -->
```
$ periplus find color
periplus find: 0 things, 0 edges

no matches
```

## Where a rule belongs

A rule for a convention only this project uses stays in the project's own rutter, a folder under
`.periplus/packs` named `<pack>@<version>` with a `pack.yaml`. A rule for a shape any project on
the stack can hold goes to the bundled rutter for that stack, so every project gets it. Write a
rule in the project first, and move it once a second project needs it. The pins sit in
`.periplus/settings.yml`, and a bundled rutter loads by its pin alone; `periplus status` lists the
search path the pins are found on: the project's packs, the user configuration directory, the bundled
rutters, and any `pack_paths`.

The bundled example is `path_in_script_string` in `drupal_js_basic`: a path written whole in a
script string, `fetch('/greet/hello')`, is plain JavaScript on any Drupal site, so the rule ships
with the rutter.

The project-only example is the rule `event_from_data_track` of the planted project's rutter
`myproject@0.0.1`. The planted templates mark an element to track with a `data-track` attribute, a
convention of this project and no other, so the rule stays in the project. Its `pack.yaml` depends
on `drupal_basic`, whose type `drupal_template_text` the rule reads. Its `event.yaml` declares the
node type `myproject.event` and holds the rule.

<!-- nav-file: .periplus/packs/myproject@0.0.1/pack.yaml -->
```yaml
# What it maps, and what it does not map yet.
# This project's own rutter: its templates mark an element to track with a data-track
# attribute, a convention no other project shares. event.yaml declares the node type
# myproject.event and reads drupal_basic's type drupal_template_text for the attribute.
# - A value written by Twig, data-track="{{ name }}", makes no node.
pack: myproject
version: 0.0.1
depends: [drupal_basic]
```

<!-- nav-file: .periplus/packs/myproject@0.0.1/event.yaml -->
```yaml
node_types:
- name: myproject.event
  id_namespace: myproject.event

rules:
# data-track="name" in a template: the event the element sends.
- rule: event_from_data_track
  reads: file
  in: [module_root, theme_root]
  match:
    file: '*.html'
    filetype: drupal_template_text
    text: 'data-track="(?<event>[\w-]+)"'
  id: {template: '{event}'}
  line: {capture: event}
  emits: [{node: {type: myproject.event}}]
  confidence: declared
```

A template of the `greet` module carries the attribute.

<!-- nav-file: web/modules/custom/greet/templates/card.html.twig -->
```twig
<div class="card" data-track="card-open">{{ title }}</div>
```

The map holds the event.

<!-- nav-run -->
```
$ periplus show myproject.event::card-open
periplus show myproject.event::card-open
type: myproject.event
state: mapped
location: web/modules/custom/greet/templates/card.html.twig:1
provenance: myproject:event_from_data_track  declared
description: none

Outgoing (0):
  none

Incoming (0):
  none
```

## When a gap is the engine's

A gap is the engine's only when no rule can state the shape. The test is to write the rule two
ways: two formulations, each written and run, and each refused by `periplus validate` or by the
map command with an engine message. One refusal shows only that one formulation cannot run; the
other may. Any other gap is a rule not yet written. A gap no rule can state is the only reason to
touch the engine; quote the engine's message for each formulation when you report it.

A third project, `broken`, beside the planted one, pins its own rutter `own@0.0.1`. Its one rule
takes the node's id from a call's argument and also sets `match.body_child`. The run below shows
one refusal; a second formulation of the same shape must be refused as well before the gap is the
engine's.

<!-- nav-file: broken/.periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - own@0.0.1
```

<!-- nav-file: broken/.periplus/packs/own@0.0.1/pack.yaml -->
```yaml
pack: own
version: 0.0.1
depends: [php_basic]
```

<!-- nav-file: broken/.periplus/packs/own@0.0.1/rules/own.yaml -->
```yaml
node_types:
- {name: own.entry, id_namespace: own.entry}

rules:
- rule: group
  reads: file
  in: [source]
  match:
    declaration: scoped_call_expression
    name_child: name
    body_child: arguments
    filetype: php
  id: {from: {argument: 0}}
  emits: [{node: {type: own.entry}}]
  confidence: declared
```

The map command refuses the whole project and writes no map, with the engine's message under
Problems and exit 26.

<!-- nav-run: broken -->
```
$ periplus map
periplus map

Map:
  path    not written
  nodes   0
  edges   0

Boundaries:
  total 0

Unknown boundaries:
  total 0

Type conflicts:
  total 0
  edges left out 0

Files:
  selected  0
  excluded  0
  unread    0
  unlisted  0

Files no rule read, by ending:
  none

Files no rule read:
  none

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  none

Rules executed:
  none

Rules that fired zero times:
  none

Map rule passes:
  none

Rules not executed:
  none

Matches skipped:
  none

Attributes that differ between files:
  none

Problems:
  26 own/rules/own.yaml: the rule group cannot be executed: an id from a call's argument cannot be combined with match.body_child
(exit 26)
```
