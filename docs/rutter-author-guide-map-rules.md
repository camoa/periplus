# Map rules: a chain in passes

Read [Writing a rutter](rutter-author-guide.md) first.

A rule with `reads: file` reads one file and cannot see another rule. A rule with `reads: map`
runs after every file rule, over the map they made, and the engine runs the map rules in passes
until a pass adds nothing. Each pass reads the map as it stood when the pass began, so a map rule
that reads an edge another map rule made fires one pass later. A chain across files is small
rules, one hop each; no rule takes a weight or a number.

A map rule takes no `in`. Its `match` holds `node_type`, the type of the node it fires on (or a
type below it), an optional `where` of `id_matches` patterns searched in that node's whole id,
and an optional `follow`, a list of steps from that node:

- `edge: <kind>` moves to each node an edge of that kind runs to.
- `ancestors: [<kind>]` runs the steps after it from the current node, else from the nearest
  node those kinds reach that gives a result: a member found on a class or its nearest ancestor.
- `node: <template>` moves to the node whose whole id the template gives from the captures.
- `id_matches: <pattern>` keeps a node whose whole id the pattern fits, and adds its captures.

It emits edges whose ends are `this_node`, the node it matched, `matched_node`, the node its
`follow` reached, or one template end filled from the captures, with `type` or `types` and
`on_miss` as on any end; or one node, whose `id` is a template. Every kind and type it names is
declared by its rutter or one it depends on. A map rule reads only the nodes the rules found and
the edges the file rules made, and edges map rules made between those; an end a map rule composed
is never read, so the passes end. Two steps, in a file type `fleet`:

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

Check `scripts/demo.d/97r-map-rules.sh` maps this example from this page.
