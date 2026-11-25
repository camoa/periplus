# Extending Periplus

When the map lacks something the code holds, this page tells you where the fix goes: a new rule,
a new rutter, or the engine. A gap is a rutter matter first: the engine changes only when no rule
can state the shape. Each answer below ends with the commands that show the fix works.

## What a rule can do today

Periplus is new, so the bundled rutters do not cover many stacks yet. What a rutter can say
without an engine change is the measure. A rule can:

- Find a thing in a file of any text format, by a pattern, or in a parse tree, by node type.
- Read the entries of a data file, such as YAML or JSON, and the entries of a docblock
  annotation, group by group.
- Join what other rules found, across files, formats and rutters, in passes, one hop each.
- Look a name up in a table, and take a type from it. Another rutter adds rows to that table
  without a copy of the rule.
- Mark a call or a place whose target is decided at run time, rather than guess one.
- Cite the line that shows each fact, also when a join walks an edge found on another line.

A rutter adds to another rutter's types, tables and rules without copying them: it names the
types of a rutter it depends on, adds table rows with `add_table_rows`, and adds its own rule
files. [Writing a rutter](rutter-author-guide.md) leads to the section for each ability.

When rules cannot express a pattern, the engine gains a general ability that every rutter can
use, never knowledge of one stack. This release shows the effect. When the engine gained the table
lookup, three families of one-rule-per-row rules in the Drupal rutter became table rows: 117 rules
became 7, and a rutter for a contributed module can now add its own rows. When annotation groups
became readable entry by entry, 49 rules became 16, and a limit of twenty entries went away.

Those were copies of one rule, repeated for each name or each position. Small rules stay the way
to write a rutter: each way of writing a thing is one rule, every such rule ends at the same thing
in the map, and each can be read, changed or removed alone.
[Rule composition](rule-composition.md) shows it on Drupal hooks, where each way of implementing
a hook keeps its own rule.

## Decide

Read the list from the top and stop at the first line that fits.

1. **A bundled rutter covers the stack, and a rule can match the thing.** Write a rule. Put it
   in your project's own rutter first. Offer it to the bundled rutter when any project on that
   stack could hold the same thing.
2. **The thing is a convention of your project only.** Write a project rutter in
   `.periplus/packs` that depends on the bundled one. It stays in your repository.
3. **No rutter covers the stack.** Start a new rutter.
4. **No rule can state the shape, and you have shown it.** Only then is it the engine.

[Where a rule belongs](map-report-guide.md#where-a-rule-belongs) gives the detail for the first
three. [When a gap is the engine's](map-report-guide.md#when-a-gap-is-the-engines) gives the test
for the fourth. [Bundled rutters](rutters.md) lists what ships.

## 1. A rule for a covered stack

Many bundled rutters start their `pack.yaml` with a comment that lists what they do not map yet.
A shape listed there is a rule nobody wrote yet, not a defect. `js_basic` lists generators:
`function* pages(list) {}` gives no node. A rule file in the project rutter of section 2 adds
them, with the type `js_basic` already declares:

```yaml .periplus/packs/acme_js@0.1.0/rules/generators.yaml
rules:
- rule: generator_declaration
  reads: file
  in: [js_source]
  match: {declaration: generator_function_declaration, name_child: name, filetype: javascript}
  id: {from: qualified_name}
  emits: [{node: {type: js.function}}]
  confidence: declared
```

```text
$ periplus map
...
  acme_js generator_declaration fired 1
$ periplus find pages --no-edges
js.function::src/pages.js:pages  js.function  mapped  src/pages.js:1
```

Any JavaScript project can hold a generator, so this rule belongs in `js_basic` in the end.
[CONTRIBUTING](../CONTRIBUTING.md) says how to propose it.

## 2. A project rutter for your own conventions

A project rutter is a folder in `.periplus/packs`. The smallest one names itself and the
rutter it builds on:

```yaml .periplus/packs/acme_js@0.1.0/pack.yaml
pack: acme_js
version: 0.1.0
depends: [js_basic]
```

Pin both rutters in `.periplus/settings.yml`, then check the new one:

```text
$ periplus validate acme_js
...
Problems:
  none
```

It may use the folders, file types and node types of `js_basic`. When the convention lives in a
file the bundled rutter does not read, the rutter declares its own folder and file type.
[Rule composition](rule-composition.md) shows one: a routes file joined to the JavaScript
functions it names.

## 3. A new rutter for a new stack

No bundled rutter reads Ruby. A new rutter declares the file type, the folder and the first
rule, and depends on nothing:

```yaml .periplus/packs/ruby_text@0.1.0/pack.yaml
pack: ruby_text
version: 0.1.0
depends: []
folders:
  ruby: ./lib/**
files:
  types:
    ruby:
      endings: [rb]
      reader: text
```

```yaml .periplus/packs/ruby_text@0.1.0/rules/classes.yaml
node_types:
- name: ruby.class
  id_namespace: ruby.class
  description: "a Ruby class, named by its name"
rules:
- rule: class
  reads: file
  in: [ruby]
  match: {file: '**', filetype: ruby, text: '(?m)^[ \t]*class[ \t]+(?<name>\w+)'}
  id: {template: '{name}'}
  emits: [{node: {type: ruby.class}}]
  confidence: declared
```

```text
$ periplus validate ruby_text
$ periplus map
$ periplus find Invoice --no-edges
ruby.class::Invoice  ruby.class  mapped  lib/invoice.rb:1
```

Start with the structure, then add one small rule file at a time. Do not start a second rutter
for a stack one already covers. [Writing a rutter](rutter-author-guide.md) has every rule shape.

## 4. The engine, last

A refusal of one rule is not yet an engine gap. Write the shape a second way and run it. A text
rule whose edge names both ends as templates, `from: {template: ...}` and `to: {template: ...}`,
is refused:

```text
$ periplus validate invoice_routes
Problems:
  26  invoice_routes/rules/handled_by.yaml: the rule route_handler cannot be executed: an edge of a text rule does not run between this_node and a capture or a template
```

The same edge with `from: this_node` runs, and the map holds it. That gap was a rule written the
wrong way, not the engine's.

Rules also build on each other in passes. A map rule joins what file rules and earlier map rules
put in the map, within the limits that
[What a map rule can and cannot read](rule-composition.md#what-a-map-rule-can-and-cannot-read) lists.

The engine changes only for an operation that any rutter can reuse and that no small rule can
state. It never learns a fact about one language or one framework, as
[Principles](principles.md) says. A request for an engine change holds:

- The rutter and its version, from the map's `packs` list.
- The smallest example of the shape, written fresh, with no private code.
- Each formulation you ran, with the engine's message for each, word for word.
- What the map holds now, and what it should hold.

[Report a wrong map](../CONTRIBUTING.md#report-a-wrong-map) gives the rest of the issue form.
