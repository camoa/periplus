# A condition on a second child, an id that must fit a pattern, and a declared end

A tree rule can test the text of any child of its match, not only the name. A tree declaration
rule can also require that its id source fit a pattern, and start or end an edge at the node
another rule declares at the same match. No worked example below is Drupal. The check
`scripts/demo.d/97p-ability-examples.sh` runs each one from this page and gets the result stated
there. The last section reads a class constant as a call's argument.

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

## An id that must start with a setting

WordPress asks a plugin to prefix its functions with its own name. In the plugin `acme`,
`acme_init` is the plugin's own; `acmeshop_init` and `format_price` are not. The plugin's name is a
settings value, and the id pattern names it in braces:

<!-- example prefix: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - php_basic@0.2.0
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

## A class constant as a call's argument

This section is not a worked example. Its block is copied from the Drupal pack's manifest, in
src/periplus/packs, and check 99u-drupal-guide-fences compares the two.

`{argument: N}` reads a text literal. A Drupal module often names an entity type by a class
constant, `getStorage(MyType::ENTITY_TYPE)`, declared once as text. Two keys of the manifest's
`grammar` block let the argument read it:

```yaml drupal_basic@0.3.0/pack.yaml
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
