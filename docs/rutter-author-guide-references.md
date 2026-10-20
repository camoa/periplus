# Tree references

Read [Writing a rutter](rutter-author-guide.md) and [Reading the Drupal
rutters](rutter-author-guide-drupal.md) first. A reference is a use of a thing in a body, as a call.
A tree rutter states one with a reference rule. `php_basic` has two for PHP calls, of a kind with
[php.function, php.method] at each end; each block below is from the file its fence names, in
src/periplus/packs. Check 67b-php-calls proves the two rules.

```yaml php_basic@0.2.0/edges/find_structure.yaml
- rule: calls_function
  reads: file
  in: [source]
  match:
    reference: function_call_expression
    name_child: function
    filetype: php
    skip_names: [isset, empty, unset, list, array, echo, print, exit, die, eval, include, require,
      include_once, require_once]
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [php.function], on_miss: unresolved}}}]
  confidence: declared

- rule: calls_static_method
  reads: file
  in: [source]
  match: {reference: scoped_call_expression, name_child: [scope, name], filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [php.method], separator: "::", on_miss: unresolved}}}]
  confidence: declared
```

`match.reference` names a tree node type. The rule fires once on each node of that type in each
file of its `filetype` under its `in` folders; `file` may narrow it by glob. A reference rule has
no `id`, and each of its emits is an edge whose `from` is `enclosing_declaration`.

The from end is the nearest declaration around the call that a declaration rule maps. That rule must
belong to this pack or to a pack it depends on, read the same file type, select this file, and emit
a type the kind allows at its from end. A call inside a closure counts the function around the
closure. A call with no such declaration around it, as at the top of a file or in a folder only the
reference rule reads, makes nothing and goes under `skipped`: no enclosing declaration is mapped.

`name_child` names the field whose whole text is the written name, so a qualified name stays whole.
The grammar's `resolve` steps then run on it with the file's imports and namespace, as on names
after `extends`. `name_child` with two fields, `[scope, name]`, resolves the first and joins the
second by the end's `separator`. `Util::make()` after `use App\Lib\Util` gives `App\Lib\Util::make`,
find_method's id for that method. The end's own `resolve` steps then run on the result, joined by
its `separator`. So a step in both runs twice, and a `"::"` end needs none. A child that is not a
written name, as `self`, `static`, `parent` or a variable, makes nothing and goes under `skipped` as
not a written name. A name the `resolve` steps hold for on no edge makes nothing, counts no fire and
goes under `skipped`: no resolution step holds for its `name_child`.

`skip_names` lists written names that make nothing: no edge, no unresolved node, no row under
`skipped`, and no fire. It compares the text of the first `name_child` field exactly as written,
case and all, before any `resolve` step runs, so `isset(` is skipped in every namespace while
`ISSET(` and `\isset(` are not unless listed so. With `[scope, name]` it compares the scope's
text. `php_basic` lists PHP's language constructs; the grammar parses only isset, empty, die and
eval as calls, and the rest are listed in case a release does too.

`types` lists the to end's candidate types. The end lands on the first a rule maps under the
resolved name. If none does, `on_miss: unresolved` gives an unresolved node searched for under that
name: `\Drupal::service('x')` in a custom module is an unresolved method `Drupal::service`, because
Drupal core is outside the project folders. An unresolved node's type is the first candidate, so its
id ignores how many a rule lists, and its `unresolved_detail` holds `types_tried`, every candidate
in the order tried. An end of one type may be written `type` in place of a one-item `types`.
Confidence is `declared`: the call is written in the file. The grammar's imports resolve the name;
[Import paths](rutter-author-guide-imports.md) binds slashed paths; the next section lists gaps.

## What a tree reference cannot say today

- A method call on an object, `$x->m()` or `$this->m()`, whose class is known only at run time.
- A function imported by `use function x as y`. The imports bind type names only, so `y()` is an
  unresolved `y` in the namespace: one table would merge a function and a class PHP keeps apart.
- PHP's fallback to a global function. In a namespace, `strlen()` resolves to
  `<namespace>\strlen` and is unresolved, where PHP calls the global `strlen`.
- A call in a class constant or a property default, which no function or method holds: skipped.
- A call on a variable function or class, `$f()` or `$class::m()`. The name is not written.
- A variable or parameter called by name, Go's `fn()`: an unresolved function of the namespace.

[Import paths and call arguments](rutter-author-guide-imports.md) covers `name_matches` and the keys
that read a call's argument.

## A name looked up in a table

A written name that no file declares, such as the method of a `\Drupal::` shortcut, can still name
its end through a table the rutter carries. `tables` is a top-level key of `pack.yaml`: a map from
a table's name to a map of written name to node name. The Drupal pack declares two:

```yaml drupal_basic@0.3.0/pack.yaml
# Name tables that call/call.yaml looks a written name up in.
tables:
  # Each static method of core's Drupal class, as of Drupal 11.4, that gets one fixed service from
  # the container, and that service. cache() names its service by its argument and is left out.
  shortcut_services:
    accessManager: access_manager
    classResolver: class_resolver
    config: config.factory
```

The resolution step `lookup_last_segment_in: <table>` splits the name at the end's `separator` and
looks its last segment up in the table; with no separator, the whole name is the segment. When the
segment is a key, the step gives that key's value alone. When it is not, the next step runs, and
when none holds, the end goes under `skipped`: no resolution step holds for its `name_child`. A rule
may name its own pack's tables and those of the packs it depends on. Of two tables with one name,
the nearer pack's wins whole, so a key that only the farther one holds is not found. A step naming
a table that none of them declares refuses the map with exit 26, naming the `tables` key.
`periplus map` checks this; `periplus validate`, which checks the schemas only, does not.

```yaml drupal_basic@0.3.0/call/call.yaml
# \Drupal::logger('my_module'), \Drupal::currentUser() and the other shortcuts, to the service the
# table shortcut_services gives for the method's name. Inferred: the table, not the file, names the
# service. The methods other rules read, and getContainer, are left to them.
- rule: drupal_shortcut_call
  reads: file
  in: [source]
  match:
    reference: scoped_call_expression
    name_child: [scope, name]
    filetype: php
    where:
    - name_matches: {child: scope, pattern: '\\?Drupal'}
    - name_matches: {child: name, pattern: '(?!(?:service|getContainer|entityQuery(?:Aggregate)?)$)\w+'}
  emits:
  - edge:
      kind: uses_service
      from: enclosing_declaration
      to: {resolve: [lookup_last_segment_in: shortcut_services], types: [drupal.service]}
  confidence: inferred
```

`\Drupal::logger('x')` ends at `drupal.service::logger.factory`. The end has no `on_miss`, so a
service that no mapped file declares is `referenced`. The rule `entity_class_static_call` beside it
looks a class's short name up in the table `entity_classes`, for `load`, `loadMultiple` and
`create`. A short name is not a class: a project class named like a core one, such as a module's
own `User`, gives a false `uses_entity_type` edge, and a `load` or `create` call on any other
capitalised class leaves a skipped row. Check 99s-drupal-table-step proves the two rules.

## Where the framework begins: boundary

The project's classes extend and implement classes the map never reads, such as Drupal core's.
`boundary` is a top-level key of `pack.yaml`: a map from a group's name to its `type`, its
`ancestry` and its `names`. The Drupal pack declares two groups, `core_classes` and
`core_interfaces`:

```yaml drupal_basic@0.3.0/pack.yaml
# The core and Symfony classes and interfaces that the custom code builds on and the map never
# reads. Each one an inherits or implements edge reaches becomes a declared node this pack draws,
# with no location. A custom class that descends from a name with a type takes that type: those
# roles have no attribute to read. A plugin base names no type, because its attribute or
# annotation already gives the plugin. Contributed modules' bases belong to their own rutters.
boundary:
  core_classes:
    type: php.class_like
    ancestry: [inherits, implements]
    names:
      Drupal\Component\Plugin\Attribute\Plugin: ~
      Drupal\Component\Plugin\Derivative\DeriverBase: ~
      Drupal\Core\Block\BlockBase: ~
      Drupal\Core\Config\Entity\ConfigEntityBase: ~
      Drupal\Core\Config\Entity\ConfigEntityListBuilder: ~
      Drupal\Core\Controller\ControllerBase: drupal.controller_class
```

A name lives in the id namespace of the group's `type`, so `ControllerBase` is the node
`php.type::Drupal\Core\Controller\ControllerBase`. When an edge ends on a listed name and no rule
found that node, the node has state `declared`, the group's type, no location, and one provenance
row: the pack, rule `boundary.<group>`, confidence `declared`. A name no edge reaches makes
nothing. An end not listed stays `referenced`.

A name's value is a node type, or `~` for none. A mapped class whose `ancestry` edges reach the
name, directly or through other mapped classes, is classified by that type. A referenced or
declared class in between stops the walk. A class whose type is an ancestor of the value takes
the value; one already of the value's type or below it keeps its type. Both gain a provenance row,
rule `boundary.<group>`, confidence `inferred`. Any other class keeps its type, and `skipped`
gets one row: `<id>: classification <value> from <boundary id> does not descend from <type>`.

`periplus map` refuses with exit 26 a group `type` or a names value that no pack visible to the
declaring pack declares, an `ancestry` kind that no loaded pack declares, and one id that two
packs list. Each problem names the shape to write. The
path-based keys of earlier releases, `applies_to_paths`, `emit_boundary_nodes` and
`type_hierarchy`, fail the manifest schema with exit 16. Check 99v-drupal-boundary proves the
Drupal groups.

## Two declaration rules on one tree node

Two packs may each match one tree node with a declaration rule, as a Laravel rutter does beside
`php_basic`. Both rules state their own node: each mints its id in its own type's namespace, and
neither replaces the other. An edge end named enclosing_class, and the enclosing type a method id is
built from, takes its class from a declaration rule that has a `body_child`, emits a node, and
belongs to the rule's own pack or a pack it depends on. Packs load dependencies first, so the rule's
own pack wins, else the dependency loaded last; a pack it does not depend on, or an edge-only rule,
never names the class. An enclosing method takes its id from the first node rule on that type among
the rule's own pack and its dependencies, in load order. A reference rule's from end is the other
way round: it takes the first declaration rule in load order, a dependency's before the pack's own.

Two such rules in one pack on one tree node do not combine: the enclosing class comes from the
last, and the `in` folders and `file` glob of the rule that gives it are not consulted. A
dependent pack whose class rule reads only one folder still names its own class in any folder.

## Tree ids and has_child

A declaration rule's id may name, beside declared_name, namespace, qualified_name and
enclosing_type, a path value of its file type, a settings value, or a field of the matched node. A
template needs a `from` listing exactly the names it names, or the rule refuses the map with exit
26: `id: {from: [dir, name, return_type], template: '{dir}.{name}:{return_type}'}`. The engine's
names, then path values and settings, shadow a field of the same name. A name that is none of these,
nor a grammar field, refuses the map with exit 19; a match lacking one makes nothing, and `skipped`
names it once per file. Under `identity`, `namespace: {path_value: pkg}` takes the file's namespace
from a path value. A field fills with the whole text of that child node: `{parameters}` gives `(int
$a, string $b)`. `normalize` on the id, as on a text rule's, cleans the finished id. It changes only
the rule's node and the ends built from it: an enclosing class or method, and a reference's from
end. A reference's to end, or a written-name end such as inherits, seeks the written name. So
normalizing a name another rule uses splits the node: the edge ends at a second node under the
uncleaned name, not at the rule's node. enclosing_type is the class's full name as written, not its
cleaned id, so a method id must repeat that normalize to match.

`where: [{has_child: struct_type}]` fires a declaration rule only on a node with a direct child of
that type, and an enclosing class comes from the rule that fires. Elsewhere it refuses the map with
exit 26, as a `where` other than `name_matches` on a reference rule does. `name_child` takes field
names only, so Go's package_identifier, which has none, cannot be one. A path value added alone to
a parent's file type still needs the type declared again in full.

`id: {from: declared_name, pattern: '^{module}_(?<hook>\w+)$', template: '{hook}'}` gives a
declaration rule's id a pattern, searched in the text of its one source; anchor it with `^` and
`$`. Its named captures join the names the template may use. With no template the id is the
source text, and the pattern only filters. A match whose source the pattern does not fit makes no
node, no edge and no `skipped` row, and is no fire. A source that is absent is skipped as before.
`{module}` names a path value or a settings value whose name starts with a letter. It is filled
with that value as literal text, so `my.mod` matches only `my.mod`. A capture named like a name
the engine fills, a path value or a settings value refuses the map with exit 26. So does a pattern
with a list of sources, an id from a call's argument, or a pattern on a text or attribute rule.
A class whose name the pattern does not fit gives its members no enclosing type, and an enclosing
declaration it does not fit is passed for the next one out.

## The grammar's node kinds

No page lists a grammar's node types and fields. Print the tree of a sample file with the
pinned grammar, in an environment holding it, and read the names from it:

```
$ python3 -c "import sys, tree_sitter as ts, tree_sitter_php as g; \
  print(ts.Parser(ts.Language(g.language_php())).parse(open(sys.argv[1], 'rb').read()).root_node)" a.php
```

Each parenthesis opens a node type, such as function_call_expression, and a word before a colon is a
field, such as function: the names `match.reference`, `match.declaration` and `name_child` take.
Another grammar's package may name its function language(), as tree_sitter_go does.

## Filtering the keys of a list-form edge end

When an edge end's `from` is a list holding an `each` part, `where` may hold `listed_at`,
`matches` and `not_matches`. `matches: 'js/*'` keeps only the keys of the `each` part that the glob
selects. `not_matches` drops the keys its glob selects and may repeat, one glob per condition. A
key that is dropped gives no edge and no node. `listed_at` and `matches` may each appear once.
Any other condition, a repeat of those two, a glob that is not a string, or a glob on a list with
no `each` part refuses the edge, and the rule is not run.

## An edge from the file: enclosing_file

A declaration rule's edge may start or end at the file that holds the match, `from: enclosing_file`,
beside `this_node` and `enclosing_class`. The end is the node that a declaration rule on the file's
root made for that file, in this pack or in a pack it depends on; `js_basic` makes a `js.file`
node from `program`. The rule
needs a twin node rule with the same match and id, since a rule makes a node or an edge. When no
rule made a node for the file, the edge is skipped and `skipped` says
`no value for enclosing_file`. This is `drupal_js_basic` linking a script to its behavior:

```yaml drupal_js_basic@0.0.1/behavior/behavior.yaml
- rule: behavior_from_assignment_in_file
  reads: file
  in: [js_source]
  match: {declaration: assignment_expression, name_child: left, body_child: object, filetype: javascript, where: [{has_child: object}]}
  id: {from: declared_name, pattern: '^Drupal\.behaviors\.(?<behavior>[A-Za-z_$][\w$]*)$', template: '{behavior}'}
  emits: [{edge: {kind: script_declares_behavior, from: enclosing_file, to: this_node}}]
  confidence: declared
```

A pack outside the bundle uses both this end and the key filter above with no engine change:
check 99y-third-party-file-links maps a project-local pack that has them and gets the same nodes
and edges as the bundled rutters.

## An edge end from the file's path alone: from: []

A data rule's edge end may be `from: []` with a `template` and nothing else. The template is
filled once per fire from the file's path values, at the fire's line, and reads no key of the
file. `drupal_basic` uses it for `config_provided_by`: each simple configuration file links to the
module its name starts with. An end with `from: []` and no template is refused, and the rule is not
run. This project-local pack links each configuration file to the module its file name starts
with:

```yaml .periplus/packs/owner@0.0.1/pack.yaml
pack: owner
version: 0.0.1
depends: []
folders:
  config: ./config
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
      path_values:
        owner:
          pattern: '^(?:.*/)?(?<owner>[^/.]+)\.[^/]+\.yml$'
          template: '{owner}'
```

```yaml .periplus/packs/owner@0.0.1/rules/config.yaml
node_types:
- name: app.config
  id_namespace: app.config
- name: app.module
  id_namespace: app.module
edge_kinds:
- kind: provided_by
  from: app.config
  to: app.module
rules:
- rule: config_file
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}'}
  emits: [{node: {type: app.config}}]
  confidence: declared
- rule: config_provider
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}'}
  emits:
  - edge:
      kind: provided_by
      from: this_node
      to: {from: [], template: '{owner}'}
  confidence: inferred
```

`config/mymod.settings.yml` gives the edge `app.config::mymod.settings` to `app.module::mymod`, a
referenced node, since no rule maps the module. A file whose name the pattern does not fit has no
`owner` value and gives no edge. Check 99z-template-only-end maps these two blocks as written here.

## A call on a property of the enclosing object

A call such as `$this->mailer->send()` names a property of the enclosing object. `php_basic` maps
it with rules alone, and the engine looks up no declared type. Three declaration rules each mint a
`php.property_type` node, `<class>::$<name>::<type>`, at the property: `find_property_type` for a
typed property, `find_promoted_property_type` for a promoted constructor parameter, and
`find_var_property_type` for a docblock such as `/** @var Mailer */`, whose at-var pattern the
rutter writes. The type resolves through the file's imports and namespace, as a written name does.
A `property_typed_as` edge runs from each property to its type node. The map rule
`calls_through_typed_property` reads each call site:

```yaml php_basic@0.2.0/edges/find_structure.yaml
- rule: calls_through_typed_property
  reads: map
  match:
    node_type: php.call_site
    where: [{id_matches: '^php\.call_site::(?<site>(?<class>[^:]+)::[^:]+::\$this->(?<member>\w+)->(?<method>\w+))$'}]
    follow:
    - node: 'php.type::{class}'
    - ancestors: [inherits]
    - id_matches: '^php\.type::(?<owner>.+)$'
    - node: 'php.property::{owner}::${member}'
    - edge: property_typed_as
    - id_matches: '^php\.property_type::[^:]+::\$\w+::(?<type>\\?[A-Za-z_][\w\\]*)$'
    - node: 'php.call_site::{site}'
    - edge: call_site_in
  emits: [{edge: {kind: calls, from: matched_node, to: {template: "{type}::{method}", types: [php.method], on_miss: unresolved}}}]
  confidence: inferred
```

It goes up `inherits` from the call's class to the class that declares the property, through
`property_typed_as` to its type, and emits `calls` from the method around the call to
`<type>::<method>`, at the call site's line, inferred. A property with no declared type keeps its
call site node and gets no `calls` edge and no skipped row. Check 97t-typed-property-calls proves
the three forms.

A nullable type, `?Mailer`, and a union of one class name with null, false or scalars, such as
`Mailer|null` or `string|Mailer`, also give the class. `find_nullable_property_type` and its
promoted twin gate on `has_child: optional_type`; `find_union_property_type` and
`find_union_promoted_property_type` gate on `has_child: union_type`. `{qualified: type}` on a union
takes its first class-like name and skips null, false and scalars, so `Mailer|Other` would join
`Mailer`. The union rules therefore add a guard, a `name_matches` on the `type` child that admits
one class-like name among `null`, `false`, `true`, `int`, `float`, `string`, `bool`, `array`,
`iterable`, `mixed` and `callable`, in any order. `union_property_typed_as` and
`union_promoted_property_typed_as` carry the same gate and guard to the property. A union of two or
more class names makes no node, no edge and no skipped row. Check 97v-union-property-calls proves
the union shapes.

A property that a constructor assigns from a typed parameter has no declared type. `php_basic`
finds it the same way: small declaration rules state each part at its own line, and one
`reads: map` rule joins them. The
parts are a property, `{enclosing_type}::{declared_name}`, with a `declares_property` edge from
its class; a parameter of a method, `<class>::<method>::$<name>`, and for one typed by a class
name its twin, whose id ends in the type that `{qualified: type}` resolves through the file's
imports; an assignment `$this-><member> = ...`, one node for each class and member, with an
`assigned_value` edge to a twin holding the assigning method and the right-hand text; and a call
site `$this-><member>-><method>()`, with an edge to and from its enclosing method through
`enclosing_method`. A `{declared: <type>}` end reaches only a node whose id leaves out
`enclosing_method`: the type twin in the parameter pair, and in the assignment pair the assignment
node, not its twin. A function's parameter has no enclosing method and makes nothing. The map
rule reads each call site:

```yaml php_basic@0.2.0/edges/find_structure.yaml
- rule: calls_through_assigned_property
  reads: map
  match:
    node_type: php.call_site
    where: [{id_matches: '^php\.call_site::(?<site>(?<class>[^:]+)::[^:]+::\$this->(?<member>\w+)->(?<method>\w+))$'}]
    follow:
    - node: 'php.type::{class}'
    - ancestors: [inherits]
    - id_matches: '^php\.type::(?<owner>.+)$'
    - node: 'php.property::{owner}::${member}'
    - node: 'php.member_assignment::{owner}::$this->{member}'
    - edge: assigned_value
    - id_matches: '^php\.member_assignment_value::[^:]+::(?<setter>[^:]+)::\$this->\w+=\$(?<parameter>\w+)$'
    - node: 'php.parameter::{owner}::{setter}::${parameter}'
    - edge: parameter_typed_as
    - id_matches: '^php\.parameter_type::[^:]+::\$\w+::(?<type>\\?[A-Za-z_][\w\\]*)$'
    - node: 'php.call_site::{site}'
    - edge: call_site_in
  emits: [{edge: {kind: calls, from: matched_node, to: {template: "{type}::{method}", types: [php.method], on_miss: unresolved}}}]
  confidence: inferred
```

It goes up `inherits` to the call's class or its nearest ancestor that declares the property, to
that class's assignment of it, to the assigned parameter of the assigning method, and to its type.
Every step names a whole id with `node:` or follows an edge, because a follow pattern cannot name
an earlier capture. The `calls` edge runs from the method around the call to `<type>::<method>`,
at the call site's line, inferred. `drupal_basic@0.3.0/service` holds the same walk for a
property assigned `\Drupal::service('<id>')`, in single or double quotes: it follows
`service_class` from that service to its class.

`calls_through_property_assigned_here` is the same walk without the `php.type` node, the
`ancestors` step, the owner `id_matches` and the property node. It follows
`php.member_assignment::{class}::$this->{member}` in the calling class itself, so a child that
assigns a property its parent declares joins its own calls. A class that declares and assigns its
own property is matched by both map rules, and its edge carries two provenance rows. A call in a
parent class through a property only a child assigns gives no edge: no follow step walks an edge
backwards. A property typed by a union of two or more class names gives no edge either, and
neither does a property set in `create()` from `$container->get('<id>')`. Such a call keeps its
call site node, with no `calls` edge. Check 97s-inherited-property-calls proves the chain.

## Keys the schemas accept and the engine does not run

A rule holding one is not run, and `not_executed` names it; a manifest or pack file holding one
outside a rule refuses the map, naming it and the file. Each line is a holder and its keys; a
star is any key or item.

```text
file: embedded_regions excluded_tokens recommendations resolution
file.edge_kinds.*: confidence source
file.embedded_regions.*: close host_constructs_inside language line_offset open skip_when_empty
file.excluded_tokens.*: case_sensitive group positions tokens
file.imports.*: binds_through_alias
file.imports.*.facts: target_fqn
file.node_types.*: container synthetic
file.recommendations.*: text topic
file.resolution: detect_references_independently_of_imports match never_match_by
    on_multiple_definitions on_zero_definitions scope
file.rules.*.emits.*: role type
file.rules.*.emits.*.attribute: target
file.rules.*.emits.*.edge: attributes
file.rules.*.emits.*.edge.attributes.*: from literal normalize pattern template
file.rules.*.emits.*.edge.attributes.*.from: annotation_key argument argument_class argument_key
    array_key_class attribute_argument capture each each_key incoming_edges key literal qualified value
file.rules.*.emits.*.edge.attributes.*.normalize.*: replace with
file.rules.*.emits.*.edge.from.from: annotation_key argument argument_class argument_key
    array_key_class attribute_argument each each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.from.from.*: annotation_key argument argument_class argument_key
    array_key_class attribute_argument capture each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.from.where.*: ancestor_reaches applies_to attribute_argument
    base_is_known_plugin contained_by_type has_argument has_child has_incoming_edge has_key
    has_promoted_constructor_parameter id_matches in_method_with_attribute is_mapping key
    method_set_covers name name_matches on_service
file.rules.*.emits.*.edge.from.where.*.name_matches: child pattern
file.rules.*.emits.*.edge.to.from: annotation_key argument_class argument_key array_key_class
    each each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.to.from.*: annotation_key argument argument_class argument_key
    array_key_class attribute_argument capture each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.to.where.*: ancestor_reaches applies_to attribute_argument
    base_is_known_plugin contained_by_type has_argument has_child has_incoming_edge has_key
    has_promoted_constructor_parameter id_matches in_method_with_attribute is_mapping key
    method_set_covers name name_matches on_service
file.rules.*.emits.*.edge.to.where.*.name_matches: child pattern
file.rules.*.emits.*.node: state
file.rules.*.id: on_miss
file.rules.*.id.from: argument_class argument_key array_key_class each each_key incoming_edges
    key literal qualified value
file.rules.*.id.from.*: annotation_key argument argument_class argument_key array_key_class
    attribute_argument capture each each_key incoming_edges key literal value
file.rules.*.match: argument array_entry grammar method_call static_call subscript_assignment
file.rules.*.match.where.*: ancestor_reaches attribute_argument base_is_known_plugin
    contained_by_type has_argument has_incoming_edge has_promoted_constructor_parameter
    in_method_with_attribute listed_at matches method_set_covers name not_matches on_service
file.rules.*.values.*.from: annotation_key argument argument_class argument_key array_key_class
    attribute_argument each each_key incoming_edges key literal qualified value
manifest.files: cache_key_includes
```
