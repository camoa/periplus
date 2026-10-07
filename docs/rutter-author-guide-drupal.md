# Reading the Drupal rutters

Read [Writing a rutter](rutter-author-guide.md) first. Each block below is copied from the file
its fence names, in src/periplus/packs; each check named is a file in scripts/demo.d. The Drupal
map states what a site declares: configuration, services, routes, plugins, hooks, templates and
libraries, and the PHP classes behind them. `php_basic` is the language half: classes, interfaces,
traits, enums, functions, methods and their edges. `drupal_basic` is the framework half. It depends
on `yaml_basic`, `php_basic` and `twig_basic`, so its rules may name their types and file types.

## The manifest of php_basic

`grammar` pins the parser exactly, because the rules name tree node types and those change across
releases. `folders` names where the rules read. `files` claims the endings and excludes folders.

```yaml php_basic@0.2.0/pack.yaml
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"

# The whole project at any depth; a dependent pack or the project settings narrows it.
folders:
  source: ./**
```

`identity` says how a full name is built. `qualified_name` joins the namespace and the declared
name. `namespace` names the tree node that declares one. `written_names` lists the node types of a
written name. `resolve` turns a written name into a full one. The next two keys, `attribute` and
`comment`, name the tree nodes of an attribute and a docblock; the plugin rules below read them.

```yaml php_basic@0.2.0/pack.yaml
identity:
  qualified_name:
    parts: [namespace, declared_name]
    separator: "\\"
  namespace:
    declaration: namespace_definition
    name_child: name
  written_names: [name, qualified_name, namespace_name]
  # How a written name becomes a full one, the first step that holds giving it: a name with a
  # leading backslash is full without it; a name whose first segment a use of its namespace block
  # binds takes the used path in place of that segment; any other name takes the namespace.
  resolve:
  - full_if_prefixed: "\\"
  - bound_first_segment
  - prefix_with: namespace
```

## The rules of php_basic

An import rule names the tree nodes of a `use` statement. Its `bind` names a clause by its alias,
which must be a field of the clause, else by its path's last segment; a grouped use joins its
prefix; a function or const use binds nothing. Segments split on the `qualified_name` separator only, so with Go's dot
separator `"a/b"` binds whole; [`path` and `normalize`](rutter-author-guide-imports.md) bind b.

```yaml php_basic@0.2.0/imports/imports.yaml
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts:
    alias: alias
    use_kind: type
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\"
    skip_when_field_set: use_kind
```

A declaration rule fires once per tree node of the named type. `name_child` holds the name and
`body_child` the methods; the id is the full name.

```yaml php_basic@0.2.0/types/find_declarations.yaml
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: php.class}}]
  confidence: declared
```

A structure rule makes one edge per name written in a clause, from the enclosing class to the
name's full form.

```yaml php_basic@0.2.0/edges/find_structure.yaml
- rule: inherits_from_base_clause
  reads: file
  in: [source]
  match: {declaration: base_clause, filetype: php}
  emits: [{edge: {kind: inherits, from: enclosing_class, to: {from: qualified_name}}}]
  confidence: declared
```

## The folders of drupal_basic

A pack that depends on another narrows that pack's folder by naming it again. `drupal_basic` names
`source` once more, so php_basic's rules read only the custom modules and themes, not core or
contrib. `custom_module` is `./web/modules/custom`; `module_root` is each folder at any depth
below it. Each plugin kind reads its own folder below a module's `src`: `block_plugin_classes` is
`{module_root}/src/Plugin/Block/**`. A class outside that folder is not a plugin.

```yaml drupal_basic@0.3.0/pack.yaml
# php_basic's source, narrowed to the custom modules and themes at any depth.
source:
- "{custom_module}/**"
- "{custom_theme}/**"
```

## Three rules of drupal_basic

An attribute rule matches a PHP attribute by its class name, on a class. `must_be` refuses a
constant id, which goes under `skipped`.

```yaml drupal_basic@0.3.0/block_plugin/block_plugin_attribute.yaml
- rule: block_plugin_from_attribute
  reads: file
  in:
  - block_plugin_classes
  match:
    attribute: Drupal\Core\Block\Attribute\Block
    filetype: php
    where:
    - applies_to: class_declaration
  id:
    from:
      attribute_argument: id
    must_be: string_literal
```

An annotation rule, `block_plugin_from_annotation`, reads the docblock before a class. It
differs from the attribute rule in its match and id: it takes the id from the `id` key, and also
records `admin_label` on the node.

```yaml drupal_basic@0.3.0/block_plugin/block_plugin_annotation.yaml
match:
  annotation: Block
  filetype: php
  where:
  - applies_to: class_declaration
id:
  from:
    annotation_key: id
  must_be: string_literal
```

A data rule reads a YAML file as data. `each` fires once per key under `services`. `where` lists
conditions that must all hold: `id_matches` tests that key against a pattern, here no leading
underscore, and `key` tests a value below it, here that `alias` is set. `id` with `from: key` takes
the key itself, the service's name.

```yaml drupal_basic@0.3.0/service/service_definition.yaml
- rule: service_alias_from_services_file
  reads: file
  in:
  - module_root
  match:
    file: '*.services'
    filetype: yaml
    each: services.*
    where:
    - id_matches: ^[^_]
    - key:
        name: alias
        not_equals: null
  id:
    from: key
  emits:
  - node:
      type: drupal.service
  confidence: declared
```

## A rule read on one ending

`drupal_basic` claims the endings module, install, inc, theme and profile for PHP. `match.ending`
narrows a rule to the files of one ending, or of any in a list, written without the dot. With no
`ending`, every file the type claims passes. The rule for a theme's include files reads only `.inc`
files, so the theme's own `.theme` file leaves no skipped row:

```yaml drupal_basic@0.3.0/hook/hook_theme_include.yaml
- rule: hook_from_theme_include
  reads: file
  in:
  - theme_root
  match: {declaration: function_definition, name_child: name, filetype: php, ending: inc}
  id: {from: declared_name, pattern: '^{theme_name}_(?<hook>\w+)$', template: '{hook}'}
  emits:
  - node:
      type: drupal.hook
  confidence: inferred
```

`match.file` globs the stem, the name less its ending, so it cannot tell two endings apart.
A declaration, text or reference rule takes `ending`. An ending that no loaded pack claims refuses
the map with exit 26, and the problem lists the endings that are claimed. `periplus map` checks
this, and `periplus validate` does not. An ending that only another file type claims passes the
check and reads nothing. Check 99m-drupal-hooks proves the rule.

## Where to look when the map misses a thing

Run these in a Drupal project that names `drupal_basic` in its settings:

```
$ periplus validate drupal_basic
$ periplus status
$ periplus map --output map.json --format json >report.json
```

`periplus status` shows which rutters the project matched. In the map report, `not_executed` names
the rules the engine cannot run. `unread` names the files no rule read, and `unlisted` the folders
not listed. `skipped` names matches that made nothing. An `unresolved` node is an end no rule maps.

## What the parse-tree side cannot say today

- A method call on an object, `$x->m()`; plain and static calls are stated.
  [Tree references](rutter-author-guide-references.md) lists the other calls not stated.
- The tree layout. A rule names node types and fields; how the engine walks the tree, finds the
  enclosing class and nests namespace blocks is engine code. A text rule on PHP names its own
  file type, a second one claiming the ending php and read as text; then both readers run.
- A resolution or a token exclusion. The pack-file keys `resolution` and `excluded_tokens` pass
  the schemas and do not run. One in a rutter refuses the map: a problem names the key and its
  file, and the run exits with no map, as check 91-unexecuted-keys proves. The manifest's
  `boundary` block runs; [Tree references](rutter-author-guide-references.md) shows it.
