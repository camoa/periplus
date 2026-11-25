# A condition on a second child, an id that must fit a pattern, and a declared end

A tree rule can test the text of any child of its match, not only the name. A tree declaration
rule can also require that its id source fit a pattern, and start or end an edge at the node
another rule declares at the same match. No worked example below is Drupal. `tests/test_demo_b_tree_rules.py`, `tests/test_declared_end.py` and `tests/test_property_type_sources.py` map planted rutters that use these abilities. An annotation rule can fire on every entry of a group nested in a docblock annotation. The last section reads a class constant as a call's argument.

## A call tested on its class and its method

Laravel reads a setting through a facade, as `Config::get('app.name')`. A rule on the method alone
also takes `Cache::get(`; a rule on the class alone also takes `Config::set(`. This rutter depends
on `laravel_basic` and tests both:

<!-- example facade: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - laravel_basic@0.0.5
  - facades@0.0.1
```

<!-- example facade: .periplus/packs/facades@0.0.1/pack.yaml -->
```yaml
pack: facades
version: 0.0.1
depends: [laravel_basic]
```

<!-- example facade: .periplus/packs/facades@0.0.1/rules/config.yaml -->
```yaml
rules:
- rule: config_facade_get
  reads: file
  in: [source]
  match:
    reference: scoped_call_expression
    name_child: name
    filetype: php
    where:
    - {name_matches: {child: scope, pattern: '\\?(?:Illuminate\\Support\\Facades\\)?Config'}}
    - {name_matches: get}
  emits:
  - edge:
      kind: reads_config
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [laravel.config_key], on_miss: unresolved}
  confidence: declared
```

<!-- example facade: config/app.php -->
```php
<?php

return [
    'name' => 'Shop',
];
```

<!-- example facade: app/Http/Controllers/HomeController.php -->
```php
<?php

namespace App\Http\Controllers;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Config;

class HomeController
{
    public function show()
    {
        $name = Config::get('app.name');
        Config::set('app.name', 'Store');
        return Cache::get('app.name');
    }
}
```

The mapping form of `name_matches` names its `child`: a field of the matched node, or else the node
type of its first child of that type. The string form tests the first `name_child`, as before. Each
pattern must match the child's whole text, whatever its node type. A match without that child fails
the condition. A child is one level down; a grandchild cannot be named. A match that fails any
condition makes nothing: no edge, no row under `skipped`, and no fire. The map's `reads_config`
edges and the rule's fires are exactly these:

<!-- example facade map -->
```text
edge php.method::App\Http\Controllers\HomeController::show reads_config laravel.config_key::app.name app/Http/Controllers/HomeController.php:12
fires config_facade_get 1
```

The `to` end takes the keys of any reference rule's end, `fallback` among them, as
[Tree references](rutter-author-guide-references.md) describes.

## An id that must start with a setting

WordPress asks a plugin to prefix its functions with its own name. In the plugin `acme`,
`acme_init` is the plugin's own; `acmeshop_init` and `format_price` are not. The plugin's name is a
settings value, and the id pattern names it in braces:

<!-- example prefix: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - php_basic@0.3.0
  - wp_prefix@0.0.1
values:
  plugin: acme
```

<!-- example prefix: .periplus/packs/wp_prefix@0.0.1/pack.yaml -->
```yaml
pack: wp_prefix
version: 0.0.1
depends: [php_basic]
```

<!-- example prefix: .periplus/packs/wp_prefix@0.0.1/rules/functions.yaml -->
```yaml
node_types:
- name: wp.plugin_function
  id_namespace: wp.plugin_function
rules:
- rule: plugin_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^{plugin}_(?<task>\w+)$', template: '{plugin}:{task}'}
  emits: [{node: {type: wp.plugin_function}}]
  confidence: inferred
```

<!-- example prefix: wp-content/plugins/acme/acme.php -->
```php
<?php
/*
 * Plugin Name: Acme
 */

function acme_init() {
}

function acme_admin_menu() {
}

function acmeshop_init() {
}

function format_price($cents) {
    return number_format($cents / 100, 2);
}
```

The id steps run in order: `from`, `pattern`, `template`, `normalize`. `from` names one source. The
pattern is searched in its text, so `^` and `$` make it test the whole name. Its named captures join
the values the template may name. Without a template the id is the source text, and the pattern
only filters. `{plugin}` must be a path value or a settings value. The engine fills it with the
value as literal text before it compiles the pattern, so a dot in a value matches only a dot. A
source the pattern does not fit makes nothing: no node, no row under `skipped`, and no fire. The
map's `wp.plugin_function` nodes and the rule's fires are exactly these:

<!-- example prefix map -->
```text
node wp.plugin_function::acme:init mapped wp-content/plugins/acme/acme.php:6
node wp.plugin_function::acme:admin_menu mapped wp-content/plugins/acme/acme.php:9
fires plugin_function 2
```

A class rule with a pattern and a `body_child` is still the holder of its members. When the pattern
drops a class, its members get no enclosing type. A rule whose id names `enclosing_type` makes
nothing for them, and no edge reaches `enclosing_class`. No row under `skipped` reports either.

An id that `normalize` empties is still minted. The test for an empty id runs before `normalize`.
So `normalize: [{replace: '^tmp_.*', with: ''}]` turns `tmp_one` into an id with nothing after
the `::`, and the rule counts a fire.

Only a tree declaration rule takes `id.pattern`. The map refuses it with exit 26 on a text rule, an
attribute rule, a data rule, an id from a call's argument, or an id with a list of sources.

## An edge from a node another rule declares

A module names its scheduled tasks by prefix: `mymod_cron` runs the task `cron`. The rutter
`tagger` depends on `php_basic`, whose rule `find_function` declares each function as
`php.function`. Its rule `task` declares `tag.task` from the name. Its rule `runs` joins the two
with the end `{declared: <type>}`:

<!-- example declared: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - tagger@0.0.1
```

<!-- example declared: .periplus/packs/tagger@0.0.1/pack.yaml -->
```yaml
pack: tagger
version: 0.0.1
depends: [php_basic]
folders:
  code: ./**
files:
  extends: php_basic
  add_extensions: [module]
```

<!-- example declared: .periplus/packs/tagger@0.0.1/rules/tag.yaml -->
```yaml
node_types:
- name: tag.task
  id_namespace: tag.task
edge_kinds:
- kind: runs_task
  from: php.function
  to: tag.task
rules:
- rule: task
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^mymod_(?<task>.+)$', template: '{task}'}
  emits: [{node: {type: tag.task}}]
  confidence: declared
- rule: runs
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  emits: [{edge: {kind: runs_task, from: {declared: php.function}, to: {declared: tag.task}}}]
  confidence: declared
```

The project holds one file, `mymod.module`:

<!-- example declared: mymod.module -->
```php
<?php

function mymod_cron()
{
}

function helper()
{
}
```

`{declared: <type>}` is the id of the node of that type that a rule of this rutter, or of one it
depends on, declares at the same match. It may stand at `from` or at `to` of an edge a tree
declaration rule emits. The id is the other rule's whole id, namespace and all. One rutter
declares each type, so the name picks that rutter's rules; when two of them declare the type at
one match, the first that fires there and mints an id gives it. The end does not test the other
rule's `in` folders or excludes. When that rule does not read the file, its node is referenced, of
the named type. The map's `runs_task` edges, the report's skipped rows and
the rules' fires are exactly these:

<!-- example declared map -->
```text
edge php.function::mymod_cron runs_task tag.task::cron mymod.module:3
skipped mymod.module:7 runs edge runs_task: no value for {declared: tag.task}
fires task 1
fires runs 2
```

`helper` does not fit the pattern, so no rule declares a `tag.task` there. The edge is not made,
and the row names the end. The type must be one of the kind's types at that end, or a type below
one; any other refuses the map with exit 22, naming the rule and the type. A type that neither the
rutter nor one it depends on declares refuses the map with exit 23. Only a tree declaration rule
takes this end.

## A field resolved through the imports, and the method around a match

These two blocks are not worked examples; `tests/test_qualified_source.py` and
`tests/test_enclosing_method_end.py` run the same shapes.

A tree declaration rule's id may list `{qualified: <field>}` among its sources. The engine reads
that field of the matched node and takes the first written name inside it: the field itself when
it is one, or, for a nullable type `?Foo`, the `Foo` within. It resolves that name through the
file's imports and namespace, by the rutter's `identity` and `imports` blocks, as it resolves a
written name at a reference rule's end. The template names the result by the field name. A name
that resolves to nothing is used as written. A field that holds no written name makes nothing. A
match without the field makes nothing, and the report lists it once per file under `skipped`:

```yaml
- rule: parameter
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id:
    from: [enclosing_type, declared_name, {qualified: type}]
    template: '{enclosing_type}::{declared_name}:{type}'
  emits: [{node: {type: probe.parameter}}]
  confidence: declared
```

With `use App\Service\Registration;` in `namespace App\Ctl;`, the parameter
`Registration $reg` of class `Thing` gets the id `App\Ctl\Thing::$reg:App\Service\Registration`.
`Helper $help`, not imported, gets `App\Ctl\Thing::$help:App\Ctl\Helper`. A nullable
`?Registration $maybe` gets `App\Ctl\Thing::$maybe:App\Service\Registration`, the name inside the
`?` resolved the same way. An untyped `$loose` gives the row `the id source type is absent`.

`enclosing_method` is the member of the enclosing type that holds the match, at which a rule of
the rutter or of one it depends on mints a node. As an id source it is that member's declared
name. As an edge end it is that node's id, at `from` or at `to`, with `this_node`,
`enclosing_class`, `enclosing_file` or `{declared: <type>}` at the other end:

```yaml
- rule: held_by
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{edge: {kind: probe_held_by, from: this_node, to: enclosing_method}}]
  confidence: declared
```

A match outside any type, or in no member a rule mints, has no enclosing method. An id that names
it makes nothing, and an edge that names it is not made. No row under `skipped` reports either, as
for an id that names `enclosing_type` outside any type.

The member sits in a body of the match's nearest holder, the nearest tree node a rule with a
`body_child` fires on. A function declared inside a method, which such a rule maps, is the nearest
holder of what it holds, so a match there has no enclosing method. As an edge end, the node is the
first that a rule mints at the member of a type the edge kind allows there, or a type below one;
as an id source, the name is the one the first rule minting a type not marked `internal` reads.
`enclosing_class` takes, among the holder rules that fire on the nearest holder, the first of a
type the edge kind allows.

Two `where` conditions of a tree declaration or reference rule read the tree nodes from the match's
parent up to its nearest holder, that holder included; the match's own type is not among them.
`within: [<node type>, ...]` passes a match only when one of those nodes has one of the types;
`not_within: [<node type>, ...]` passes it only when none has. The type names are not checked
against the grammar when the rutter loads, so a misspelt type in `within` never holds, and one in
`not_within` never leaves a match out.
With no holder, the nodes run up to the file's root, or to a node that holds a body no rule fires
on. A holder above the nearest one is never read. Two rules then split one shape, a call in a
method's own body and a call in a closure inside it:

```yaml
match: {declaration: member_call_expression, name_child: object, filetype: php,
  where: [{not_within: [anonymous_function, arrow_function]}]}
```

The twin rule has `within: [anonymous_function, arrow_function]` and its own id. Each `within`
condition must hold. A function declared inside that closure is the nearest holder of its own
calls, so neither rule sees the closure above it.

## A name below the match, and a value from the docblock

These blocks are not worked examples; `tests/test_property_type_sources.py` runs the same shapes.

A tree declaration rule's `name_child` may be a list, a path of one step or more walked from the
matched node. Each step is the child in that field, or else the first named child of that node
type. The declared name is the leaf's text, and the node sits at the leaf's line. In PHP a typed
property's type sits on the `property_declaration`, and its name two levels down:

```yaml
match: {declaration: property_declaration, name_child: [property_element, name], filetype: php}
```

A rule with this match fires once per statement, so `protected $a, $b;` names `$a` only. To read
every element, match the element and walk one step to its name. A string `name_child` names a
field, and a PHP constant's name has none, so the one-step list `[name]` reads it by its node type:

```yaml
match: {declaration: const_element, name_child: [name], filetype: php}
```

This rule fires once per constant, so `const A = 'a', B = 'b';` names `A` and `B`. An empty step,
as `[scope, ""]`, and an empty string `name_child: ""` are refused at load, by `periplus validate`
and `periplus map` alike.

The id may also list one docblock source, `{docblock: <pattern>}`. The engine searches the
pattern in the comment that is the matched node's previous sibling, of the node type the grammar's
`identity.comment` names. The pattern holds exactly one named group, and the template names the
value by that group's name. Wrapped as `{qualified: {docblock: <pattern>}}`, the value resolves
through the file's imports and namespace, as `{qualified: <field>}` resolves a field:

```yaml
- rule: resolved
  reads: file
  in: [source]
  match: {declaration: property_declaration, name_child: [property_element, name], filetype: php}
  id:
    from: [declared_name, {qualified: {docblock: '@var\s+(?<type>[\w\\]+)'}}]
    template: '{declared_name}:{type}'
  emits: [{node: {type: probe.resolved}}]
  confidence: declared
```

With `use App\Service\Registration;` in `namespace App\Ctl;`, `/** @var Registration */` before
`protected $reg;` gives `$reg:App\Service\Registration`. Without `qualified` it gives
`$reg:Registration`. A match with no comment before it, or whose comment the pattern does not fit,
makes nothing, and no row under `skipped` reports it. The template may leave the value out; the
source is then only a condition, and an edge rule can use it to start at the property's own id. An
attribute template may name the value too
([An attribute on a declaration rule's node](rutter-author-guide-references.md#an-attribute-on-a-declaration-rules-node)).

## Every entry of a group in a docblock annotation

This block is not a worked example; `tests/test_annotation_each.py` runs the same shapes.

An annotation rule reads the keys at the top level of the annotation's body. With `match.each`,
it fires once for each entry of a group nested in the body instead. The path is keys joined by
dots that end in a star, as a data rule's `each` does, so `parts.panel.*` is each entry of the
`panel` group inside `parts`. One more star may stand for any group's key: `parts.*.*` is each
entry of every group inside `parts`, and the templates name that group's key `group`. A path part
is any key the annotation may hold, quoted or bare, so `sub-parts.*` reads the quoted key
`"sub-parts"`; a key that itself holds a dot or a star cannot be named in a path. A path without
the last star, with a third star, with an empty part, or with a star inside a part, is refused at
load, and so is a template that names `group` when the path has no second star.

```text
/**
 * @Thing(
 *   id = "invoice",
 *   parts = {
 *     "list" = "Acme\InvoiceList",
 *     "panel" = {
 *       "add" = "Acme\InvoiceAddPanel",
 *       "edit" = "Acme\InvoiceEditPanel",
 *     },
 *   },
 * )
 */
class Invoice {}
```

```yaml
- rule: panel_entry
  reads: file
  in: [source]
  match: {annotation: Thing, each: parts.panel.*, filetype: php, where: [{applies_to: class_declaration}]}
  id: {template: '{enclosing_type}|panel|{key}'}
  emits: [{node: {type: acme.entry}}]
  confidence: declared
- rule: panel_entry_class
  reads: file
  in: [source]
  match: {annotation: Thing, each: parts.panel.*, filetype: php, where: [{applies_to: class_declaration}]}
  id: {template: '{enclosing_type}|panel|{key}'}
  emits: [{edge: {kind: entry_names_class, from: this_node, to: {template: '{value}'}}}]
  confidence: declared
```

Two rules, because a rule that emits an edge emits no node. They make
`acme.entry::Acme\Invoice|panel|add` and `acme.entry::Acme\Invoice|panel|edit`, each at the line
of its own key, and an edge from each to the class its value names. The rule's
templates name `key`, the entry's key without its quotes; `value`, the entry's value;
`enclosing_type`, the full name of the class the annotation sits on; and, with a second star,
`group`. A template that names anything else is refused at load, and so is an empty id template.
The id may also come from `annotation_key` as before, and attributes and edge attributes still read
the keys at the top level of the body. Only an edge's `to` end takes `{template: ...}`; the id of
its node is minted in the namespace of the kind's to types, unless the template starts with a
declared namespace.

Two refusals, each leaving the rule not executed with exit 26 when the map runs:

```
the rule panel_entry cannot be executed: match.each of an annotation rule is keys joined by dots that end in a star, as parts.inner.*, with at most one other star, which stands for any group's key
the rule panel_entry cannot be executed: a template or normalize step of an annotation rule with match.each names group, which is not key, value, enclosing_type, or group with a star before the last one
```

Use `match.each` where a group of an annotation holds one entry per thing. It replaces a rule per
known key, and a rule per position in the group, and reads entries no rule could list ahead.

An edge's `to` end may also be `{from: {annotation_key: <key>}}`, on any annotation rule: the id
the value of that key of the same annotation names, in the namespace of the kind's to types. With
`@Thing(id = "invoice", paths = {"main" = "/invoice/{id}", "make" = "/invoice"})`, a rule over
`paths.*` with id `{template: '{value}'}` and the edge
`{kind: path_of, from: this_node, to: {from: {annotation_key: id}}}` joins each path to
`acme.thing::invoice`:

```yaml
- rule: thing_path
  reads: file
  in: [source]
  match: {annotation: Thing, each: paths.*, filetype: php, where: [{applies_to: class_declaration}]}
  id: {template: '{value}'}
  emits: [{edge: {kind: path_of, from: this_node, to: {from: {annotation_key: id}}}}]
  confidence: declared
```

The key may hold dots to name an entry inside a group, as the paragraph after next says. A key
that is missing, or whose value is
not quoted text, makes no edge for that entry and lists `key id is missing` or
`key id is not quoted text` at the entry's line, also when a twin node rule fires there.

The id and the `to` end take `normalize`, the steps an id's `normalize` takes elsewhere, run in
order on the filled text. A step may name the same values the templates name, and no other.
`to: {template: '{value}', normalize: [{replace: '^\\', with: ''}]}` drops a leading backslash
from a class name, and an id
`{template: '{enclosing_type}|paths|{key}|{key}', normalize: [{replace: '-(?=[^|]*$)', with: _}]}`
turns `edit-page` into `edit_page` in the id's last part alone.

A rule over every group of `parts`, with `{group}`, reads like this:

```yaml
- rule: any_part_entry
  reads: file
  in: [source]
  match: {annotation: Thing, each: parts.*.*, filetype: php, where: [{applies_to: class_declaration}]}
  id: {template: '{enclosing_type}|{group}|{key}', normalize: [{replace: '-', with: _}]}
  emits: [{node: {type: acme.entry}}]
  confidence: declared
```

With `"edit-page" = "Acme\InvoiceEditPanel"` in `panel`, it makes
`acme.entry::Acme\Invoice|panel|edit_page`.

Without `each`, an `annotation_key` with dots reads one entry inside a group, in the id, an
attribute or an edge attribute: `{annotation_key: api_paths.main}` is the `main` entry of the
`api_paths` group. It reads as a key at the top level does: a key the group does not hold is
missing, a value that is not quoted text is not quoted text, and when the key is written twice the
last one counts.

A value is quoted text without its quotes, or the text of a nested annotation that holds one quoted
text. An entry whose value is a group is not an entry of the path and makes nothing: `parts.*`
gives `list` and not `panel`, and `parts.panel.*` reaches inside `panel`. So the same key at two
depths, as `edit` in `parts` and in `parts.panel`, is an entry of each path once. An entry whose
value is anything else, such as a bare `10` or `TRUE`, makes nothing and is listed under `skipped`
as `entry low of group weights is not quoted text`. A key is quoted text or a bare word. A trailing
comma adds no entry. A key written twice in one group is an entry each time; when both give one id,
the node has both lines. A value that runs over two lines keeps the comment's margin between them,
as a key at the top level does.

The engine reads one annotation grammar, the one described above, and a pack cannot change it. The
pack sets the comment's node type, `identity.comment`, and the characters of a nested annotation's
name besides word characters, those of `identity.qualified_name.separator`.

A path the annotation does not hold makes nothing and lists nothing. An entry that is not
key = value is left out and listed under `skipped` at its line, as `group parts holds an entry that
is not key = value`; the other entries still map. A list group, as `names = {"id", "label"}`, holds
only such entries: a rule whose path reads it lists each item, and a rule whose path does not read
it lists nothing.

A group closed by the wrong mark, as `{` closed by `)`, stops the reading there. The entries a
comma ended before that mark stay; the entry the mark ends, and everything after it, is not read.
A rule lists the stop under `skipped`, as `group paths does not close` at the wrong mark's line,
when the reading stopped inside a group its path reads, inside a group below one, or inside a group
above one, or when no group its path names was read at all. A rule whose groups all closed before
the stop lists nothing.

## A class constant as a call's argument

This section is not a worked example. Its block is copied from the Drupal pack's manifest, in
src/periplus/packs, and `tests/test_demo_c_drupal.py` maps a class constant argument.

`{argument: N}` reads a text literal. A Drupal module often names an entity type by a class
constant, `getStorage(MyType::ENTITY_TYPE)`, declared once as text. Two keys of the manifest's
`grammar` block let the argument read it:

```yaml drupal_basic@0.4.0/pack.yaml
# A call argument written MyType::ENTITY_TYPE, self::X or static::X stands for the text that
# constant is declared with, when a mapped file declares it as one text literal. A constant read
# as parent::X, of core, of contrib, or declared by an expression gives the row "argument N is a
# class constant with no declared text".
constant_access:
  node: class_constant_access_expression
  scope: [name, qualified_name, relative_scope]
  name: [name]
  enclosing: [self, static]
constant_declaration:
  node: const_element
  name: [name]
  value: [string, encapsed_string]
```

`constant_access` names the tree node of a constant read. `scope` lists the node types its first
named child may have, and `name` those of its last, the constant's name. `constant_declaration`
names the node of one declaration in a class body. `name` lists the node types of its first named
child, and `value` those of its last. Each key needs the other: one alone refuses the map, naming
the key it lacks. Before any rule runs, the engine collects each declaration whose value is a text
literal, by its class's full name and the constant's name; of two with one key, the first read
stays. An argument written as a constant stands for that text when its scope is a written name that
the file's imports and namespace resolve to that class.

A scope that is not a written name, such as `self`, `static` or `parent`, stands for the enclosing
class only when `enclosing` lists its text. Drupal lists `self` and `static`. So `parent::X` gives
no edge and leaves the skipped row `argument N is a class constant with no declared text`, as does
a constant that only a parent class declares, one of core or contrib, or one declared by an
expression. An id from a call's argument reads a constant the same way. A constant in an
attribute's value or at an attribute edge's end goes through the same reading, but no test or check
exercises those two yet.
