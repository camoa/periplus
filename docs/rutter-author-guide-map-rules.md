# Map rules: a chain in passes

Read [Writing a rutter](rutter-author-guide.md) first.

A rule with `reads: file` reads one file and cannot see another rule. A rule with `reads: map`
runs after every file rule, over the map they made, and the engine runs the map rules in passes
until a pass adds nothing. Each pass reads the map as it stood when the pass began, so a map rule
that reads an edge another map rule made fires one pass later. A chain across files is small
rules, one hop each; no rule takes a weight or a number.

A map rule takes no `in`. Its `match` holds `node_type`, the type of the node it fires on (or a
type below it), an optional `where` of `id_matches` patterns searched in that node's whole id,
with `in_table` or `not_in_table` conditions on that id or on one of their captures
([tables](rutter-author-guide-references.md#a-name-tested-against-a-table-in_table-and-not_in_table)),
and an optional `follow`, a list of steps from that node:

- `edge: <kind>` moves to each node an edge of that kind runs to.
- `incoming_edge: <kind>` walks the other way: it moves to each node an edge of that kind runs
  from, in id order. From a class, `[{incoming_edge: assigned}]` reaches each variable
  assigned from it.
- `edge_attribute: <name>`, right after an `edge` or `incoming_edge` step or a step that reads the
  same edge, adds the value the edge just walked holds for that edge attribute as the capture
  `<name>`, one result for each value it holds; an edge without it gives nothing. It reads what
  file rules wrote, never what a map rule wrote.
  `[{edge: manages_plugin_type}, {edge_attribute: subdirectory}]` carries a plugin manager's
  discovery folder to the edge the rule makes.
- `place: edge`, right after an `edge` or `incoming_edge` step or an `edge_attribute` step on the
  same edge, and in `follow` only, places what the fire makes at each location of the edge just
  walked, not at the matched node. A route node sits at line 1 of a routes file, and a file rule
  made its `names_handler` edge at line 7, where the key names the handler;
  `[{edge: names_handler}, {place: edge}]` puts the new edge at line 7. An edge a map rule made
  sits where that rule placed it. A later `place` step replaces an earlier one, and one inside a
  `try` that reaches nothing places nothing, so the fire keeps the place it had. `edge_attribute`
  and `place` read one edge in either order. A `place` step that does not come right after an edge
  step or an `edge_attribute` step, one in an `unless` or `unless_matched` chain, and one in a
  rule that withholds leave the rule not executed
  ([A fire at the line of the edge it walked](#a-fire-at-the-line-of-the-edge-it-walked)).
- `ancestors: [<kind>]` runs the steps after it from the current node, else from the nearest
  node those kinds reach that gives a result: a member found on a class or its nearest ancestor.
- `node: <template>` moves to the node whose whole id the template gives from the captures.
- `id_matches: <pattern>` keeps a node whose whole id the pattern fits, and adds its captures.
  Each `{name}` in it is first filled with that capture, as literal text, so
  `'^my_module\.var::(?!{name}$)'` keeps a variable other than the one the rule came through. A
  name starts with a letter, so a quantifier such as `\w{2}` stays one; a name no step before it
  captures leaves the rule not executed.
- `in_table: {table: <table>, capture: <name>}` stays on the current node when the text of that
  capture is a key of the table, and gives nothing when it is not. With `value: <new name>`, the
  table's value for that key joins the captures under the new name, for the steps after it and
  the rule's templates. One table then does the work of one rule per row: with the table `sorts`
  holding `red: Paint`, a use whose id captures `kind` as `red` and `name` as `apple` reaches
  `my.thing::Paint.apple` through
  `[{in_table: {table: sorts, capture: kind, value: sort}}, {node: 'my.thing::{sort}.{name}'}]`.
  The table is found as the `where` condition finds one, with
  the rows loaded rutters add under `add_table_rows`. A table no visible rutter declares, a capture
  no step before it makes, and a new name a step before it already captures leave the rule not
  executed. Inside a `try`, a key the table lacks lets the later steps run without the new name.
  A template end may take its type from such a value, `{template: '{name}', types: ['{sort}']}`,
  when the table's values are type names. Before any file is read, every value of the table, the
  rows other rutters add included, must be a type the rutter or one it depends on declares and
  one the edge kind allows at that end; a row that is not stops the map and names the row, and
  the rutter that added it. The step that gives the type sits outside any `try`, so the end
  always has a type when it is built, and no later step may capture the same name. Such an end
  takes no `boundary`. A `{name}` type in any other place is refused before any file is read: on
  a file rule, beside another type, as `type:`, from any other capture, from a step inside a
  `try`, or from a name a later step captures again
  ([A table in place of one rule per row](#a-table-in-place-of-one-rule-per-row)).
- `try: [<steps>]` holds steps of these kinds. The steps inside and after it run from the current
  node, and if they reach nothing the later steps run with the captures it had, so a lookup that
  may fail (a method on an ancestor the map does not hold) leaves the end to `on_miss`. When
  they reach a node, an `id_matches` inside rebinds the captures it names.

An optional `unless` holds one or more chains of the same steps, each run from the matched node
with the captures of `where`. When any chain reaches a node, the rule makes nothing for that node,
which counts as no fire and no skip. A join on a variable assigned twice is a guess, so this rule
stops when a second assignment node exists:

```yaml
match:
  node_type: my_module.use
  where: [{id_matches: '^my_module\.use::(?<name>\w+)$'}]
  follow: [{node: 'my_module.var::{name}'}, {edge: assigned}]
  unless:
  - [{node: 'my_module.again::{name}'}]
  - [{edge: guarded}]
```

An optional `unless_matched`, with `follow` only, holds chains of the same steps, each run from
the node `follow` reached with the captures `follow` made. When any chain reaches a node, the rule
makes nothing for that one result, and the other results of the same node still fire. The key
decides the scope: `unless` blocks the matched node and knows only the captures of `where`;
`unless_matched` blocks one result. A chain under `unless` that names a capture of `follow` leaves
the rule not executed, with a message that points to `unless_matched`. This rule skips each class
that a stop node names:

```yaml
match:
  node_type: my_module.use
  where: [{id_matches: '^my_module\.use::(?<name>\w+)$'}]
  follow: [{node: 'my_module.var::{name}'}, {edge: assigned}, {id_matches: '::(?<class>\w+)$'}]
  unless_matched: [[{node: 'my_module.stop::{class}'}]]
```

An `unless` or `unless_matched` chain reads the map as it stood when the pass began, so an edge a
later pass makes does not take back what the rule already made.

It emits edges whose ends are `this_node`, the node it matched, `matched_node`, the node its
`follow` reached, or one template end filled from the captures, with `type` or `types` and
`on_miss` as on any end, and attributes, as [An attribute from a map rule](#an-attribute-from-a-map-rule)
says; or one node, whose `id` is a template. A template end of one type mints
its id in that type's id namespace, and in the kind's only when it names no type. What a fire makes sits at each
location of the node it matched, whatever its ends name, so a rule that matches a call-site node
places its edge at the call; a `place: edge` step places it at the edge that step walked. Every kind and type it names is
declared by its rutter or one it depends on. A map rule reads only the nodes the rules found and
the edges the file rules made, and edges map rules made between those; an end a map rule composed
is never read, so the passes end. A node a map rule makes is read only when a file rule found the
same id; when a later map rule would start from it or reach it by a `node` step, the map report
lists that rule under Matches skipped. A node that is only referenced, an edge end no rule found,
is never a start for `node_type`. Two steps, in a file type `fleet`:

<!-- map-example: .periplus/packs/fleet@0.0.1/pack.yaml -->
```yaml
pack: fleet
version: 0.0.1
depends: []
folders:
  yard: ./yard
files:
  types:
    fleet:
      endings: [fleet]
      reader: text
```

<!-- map-example: .periplus/packs/fleet@0.0.1/rules/fleet.yaml -->
```yaml
node_types:
- name: fleet.class
  id_namespace: fleet.class
- name: fleet.method
  id_namespace: fleet.method
- name: fleet.ask
  id_namespace: fleet.ask
edge_kinds:
- kind: inherits
  from: fleet.class
  to: fleet.class
- kind: holds
  from: fleet.class
  to: fleet.class
- kind: calls
  from: fleet.ask
  to: fleet.method
rules:
- rule: class
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^class (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: fleet.class}}]
  confidence: declared
- rule: class_extends
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^class (?<name>\w+) extends (?<parent>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: inherits, from: this_node, to: {from: {capture: parent}}}}]
  confidence: declared
- rule: class_holds
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^class (?<name>\w+) holds (?<part>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: holds, from: this_node, to: {from: {capture: part}}}}]
  confidence: declared
- rule: method
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^method (?<owner>\w+) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits: [{node: {type: fleet.method}}]
  confidence: declared
- rule: ask
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^ask (?<owner>\w+) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits: [{node: {type: fleet.ask}}]
  confidence: declared
- rule: inherited_holds
  reads: map
  match:
    node_type: fleet.class
    follow:
    - edge: inherits
    - ancestors: [inherits]
    - edge: holds
  emits: [{edge: {kind: holds, from: this_node, to: matched_node}}]
  confidence: inferred
- rule: ask_through_part
  reads: map
  match:
    node_type: fleet.ask
    where:
    - id_matches: '^fleet\.ask::(?<owner>\w+)\.(?<name>\w+)$'
    follow:
    - node: 'fleet.class::{owner}'
    - edge: holds
    - id_matches: '^fleet\.class::(?<part>\w+)$'
  emits: [{edge: {kind: calls, from: this_node, to: {template: '{part}.{name}', on_miss: unresolved}}}]
  confidence: inferred
```

<!-- map-example: yard/cars.fleet -->
```text
class Engine
method Engine start
class Base holds Engine
class Car extends Base
ask Car start
```

`inherited_holds` gives `Car` what its nearest ancestor holds: `holds` from `fleet.class::Car`
to `fleet.class::Engine`, in pass 1. `ask_through_part` reads that edge in pass 2 and composes
the end `fleet.method::Engine.start` from the part's id and the captured method name. The map
report's `map_passes` lists each pass with the rules that added something in it, the last pass
adding nothing:

```text
Map rule passes:
  pass 1: fleet inherited_holds fired 1
  pass 2: fleet ask_through_part fired 1
  pass 3: none
```

## A fire at the line of the edge it walked

A map rule's fire sits at the lines of the node it matched. That is the wrong line when the node
is large, such as a route at line 1 of a routes file, and the fact is written on one line inside
it. A `place: edge` step, right after the step that walked an edge, puts the fire at that edge's
lines instead. No internal node is needed only to carry a line. In a file type `desk`:

```text
route /send calls send_it
route /drop calls drop_it
function send_it
```

```yaml
- rule: route_handled_by
  reads: map
  match:
    node_type: desk.function
    where: [{id_matches: '^desk\.function::(?<fn>\w+)$'}]
    follow:
    - node: 'desk.handler_name::{fn}'
    - incoming_edge: names_handler
    - place: edge
  emits: [{edge: {kind: handled_by, from: matched_node, to: this_node}}]
  confidence: inferred
```

A file rule made the `names_handler` edge from `desk.route::/send` at line 1. The `handled_by`
edge sits at line 1 too, the line that names the handler, and not at line 3, where the function
is. `/drop` names no function, so the walk reaches nothing and nothing is made.

`place` takes only the value `edge`. A `place` step that does not follow an edge step or an
`edge_attribute` step, one in an `unless` or `unless_matched` chain, and one in a rule that
withholds leave the rule not executed, as in:

```
the rule route_handled_by cannot be executed: the follow step place comes right after an edge step
```

## A table in place of one rule per row

When the same join differs only by a name, such as which type a kind of use reaches, write one
rule and a table, not one rule per row. This is for copies of one rule: the same match, the same
walk and the same edge. Rules that differ in what they match, in the walk, in the edge they make
or in what it means stay separate small rules, each with its own name in the map report. The `in_table` follow step looks a capture up in a table.
With `value`, the table's value for that key becomes a new capture. A template end may take its
type from that capture with `types: ['{name}']`:

```yaml
# pack.yaml
tables:
  sorts: {red: desk.paint, blue: desk.ink}
```

```yaml
- rule: use_of_sort
  reads: map
  match:
    node_type: desk.use
    where: [{id_matches: '^desk\.use::(?<kind>\w+)\.(?<name>\w+)$'}]
    follow:
    - in_table: {table: sorts, capture: kind, value: sort}
  emits: [{edge: {kind: uses, from: this_node, to: {template: '{name}', types: ['{sort}']}}}]
  confidence: inferred
```

The kind `uses` allows `desk.paint` and `desk.ink` at its `to` end. `use red apple` gives an edge
to `desk.paint::apple`, and `use blue sky` one to `desk.ink::sky`. `use green leaf` names a key
the table lacks, so the rule makes nothing for it and lists no row. Another rutter adds a row with
`add_table_rows`, and the rule reads it with no change.

The engine checks the table before any file is read. Each value must be a type the rutter or one
it depends on declares, and one the edge kind allows at that end. A row that is not stops the map
with exit 23 and names the row and the rutter that added it:

```
the rule use_of_sort takes the type of its to end from the table sorts, whose row green: desk.leaf names a type neither desk nor a pack it depends on declares
```

A table no visible rutter declares leaves the rule not executed:

```
the rule use_of_sort cannot be executed: the follow step in_table names the table colours, which no tables key of the pack or a pack it depends on declares
```

The step that gives a type sits outside any `try`, because a `try` can leave the capture unset:

```
the rule use_of_sort cannot be executed: the to end's type {sort} comes from an in_table step inside a try, which can leave it unset; an end takes a type only from an in_table step outside any try
```

No later step may capture the same name again, and an end typed this way takes no `boundary`.

## An attribute from a map rule

A map rule may emit attributes beside its edges. Beside a node it emits only the run-time mark,
as [Mark a place decided at run time](#mark-a-place-decided-at-run-time) says. Each is
`{name, template}`, the template filled from the captures, with an optional `target`:
`this_node`, the default, writes on the node the rule matched, and `matched_node` on the node its
`follow` reached. A template that
names an absent capture writes nothing. The attribute must be declared by the rule's rutter or one
it depends on, as [Declared attributes](rutter-author-guide-references.md#declared-attributes)
says. This rule writes `switched: 'off'` on each unit no list names:

```yaml
- rule: unit_off
  reads: map
  match:
    node_type: box.unit
    follow: [{node: 'box.list::on'}]
    unless: [[{incoming_edge: lists}]]
  emits:
  - attribute: {name: switched, template: 'off'}
  confidence: inferred
```

A write changes no type, id or location. The node keeps what the other rules found, and gains the
value and one provenance row whose `sets` names only the attribute. A write on a node no rule
found, or on a node whose type is not at or below a type the declaration's `on` lists, writes
nothing; the map report lists it under Matches skipped, so a referenced end never turns into a
mapped node. Two rules that give one value write it once, each with its row; two that give
different values write `differs`, even at the same place, and the report lists the node under
Attributes that differ between files. No `follow` step reads a node attribute, and
`edge_attribute` reads only the values file rules wrote, so the passes still end.

An edge a map rule emits may carry its own `attributes`, filled from the same captures; a map rule
writes only a declared one, as
[Attributes on edges](rutter-author-guide-references.md#attributes-on-edges) says.

## Mark a place decided at run time

A join can show that the code names no target: an ask goes through a part, and the class holds
no part a rule could name. A map rule then marks the place as a file rule does. It emits one node
with an id from one template and, beside it, `resolution: runtime`:

```yaml
node_types:
- name: fleet.call
  id_namespace: fleet.call
rules:
- rule: ask_no_part
  reads: map
  match:
    node_type: fleet.ask
    where: [{id_matches: '^fleet\.ask::(?<owner>\w+)\.(?<name>\w+)$'}]
    unless: [[{node: 'fleet.class::{owner}'}, {edge: holds}]]
  id: {template: '{owner}.{name}'}
  emits:
  - node: {type: fleet.call}
  - attribute: {name: resolution, template: runtime}
  confidence: inferred
```

The node sits where any fire of a map rule sits: at each location of the node the rule matched,
or of the edge a `place: edge` step walked. Add the lines `ask Bike start` and `class Bike` to
the fleet file above. `Bike` holds no part, so the map holds `fleet.call::Bike.start` at the
ask's line, and the report lists the rule in its own last pass:

```text
Map rule passes:
  pass 1: fleet inherited_holds fired 1
  pass 2: fleet ask_through_part fired 1
  pass 3: none
  pass 4: fleet ask_no_part fired 1
```

The node's state is `unknown_boundary`, its `resolution` is `runtime`, and its
provenance row lists `resolution` in `sets`, as the [run-time
mark](rutter-author-guide-references.md#an-attribute-on-a-declaration-rules-node) of a file rule is
stored. `periplus find`, `periplus show` and the map report's unknown boundaries treat the two
alike. The mark needs no declaration.

A rule that writes `resolution` runs in one last pass, after a pass of the other map rules adds
nothing, and reads the map as it stood then. A mark is never taken back, so it must not mark a
place that a later pass would join. The map report lists that pass after the pass that added
nothing. A rule that finds the same node later, or draws an edge from it to a real target, adds
its records; the mark stays, as a file rule's does.

Beside its node a map rule writes no other attribute, and `resolution` takes only `runtime`. A map
rule that writes `resolution` with no node of its own, on `this_node` or `matched_node`, is not
executed. The message reads:

```
the rule ask_no_part cannot be executed: a map rule writes the attribute resolution only beside the node it emits
```

Use the mark where a join shows that the code itself names no target. Do not use it for a
target that a rule could find but the map lacks: that is an end with `on_miss: unresolved`.

## Withhold what a file rule found

A name convention can read a thing that other code shows is something else, and a file rule
cannot see that other code. A map rule whose one emit is `withhold: matched_node` or
`withhold: this_node` takes such a node back. It runs once, before pass 1, over the map the file
rules made, and matches, follows and blocks as any map rule does. At each location of the node it
matched, it takes out every record of the named node, and every file edge there with that node at
an end. A record of the same node at another location stays, so the node stays in the map while
one is left. No pass reads what was taken out, and no withholding rule sees what another took out.
The report counts each rule's fires under `executed`. This rule takes out, at each registered
function's place, the hook its name gave it:

```yaml
- rule: hidden
  reads: map
  match:
    node_type: own.fn
    where: [{id_matches: '^own\.fn::(?<name>\w+)$'}]
    follow:
    - node: 'own.reg::{name}'
    - node: 'own.fn::{name}'
    - edge: implements
  emits: [{withhold: matched_node}]
  confidence: inferred
```

A rule that withholds emits nothing else, and `matched_node` needs `follow`; either refusal leaves
the rule not executed. A file rule cannot withhold.

## Internal node types

A node type marked `internal: true` serves the map rules and stays out of the written map. File
rules emit its nodes and map rules read them like any others, so a map rule can join through a
call site and emit the edge the call site stands for. When the map is written, each node of an
internal type, or of a type below one, is left out, with every edge that has an end on it. A node
of another type stays, even when every edge it had is gone. When the map leaves anything out, the
Map section of the report prints `internal: <n> nodes and <m> edges left out`; the JSON report's
`internal` holds both counts on every run.

## Join an internal node to its real target

Many shapes take two rules. A file rule writes an internal node where the code names a thing: a
call site, a hub for a name, or a name guessed from how it is written. A map rule joins that node
to the real target, and only when the map holds the target. A target the map lacks leaves a mark:
an end with `on_miss: unresolved`, or a referenced node. The map never gets an invented target,
and the call is never dropped in silence. The internal type keeps the file rule's node out of the
written map.

Three bundled rule files show the pattern: `role/role_call.yaml` of `drupal_basic`, a role-name
hub joined to the role's configuration; `member/member_call.yaml` of `js_basic`, a member call
joined to the member function its script declares; and `edges/var_type_as_written.yaml` of
`php_basic`, a name kept as written and as resolved, joined to whichever the map holds.
