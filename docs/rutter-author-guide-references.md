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
    method_set_covers name name_matches on_service receiver
file.rules.*.emits.*.edge.from.where.*.name_matches: child pattern
file.rules.*.emits.*.edge.to.from: annotation_key argument_class argument_key array_key_class
    each each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.to.from.*: annotation_key argument argument_class argument_key
    array_key_class attribute_argument capture each_key incoming_edges literal qualified value
file.rules.*.emits.*.edge.to.where.*: ancestor_reaches applies_to attribute_argument
    base_is_known_plugin contained_by_type has_argument has_child has_incoming_edge has_key
    has_promoted_constructor_parameter id_matches in_method_with_attribute is_mapping key
    method_set_covers name name_matches on_service receiver
file.rules.*.emits.*.edge.to.where.*.name_matches: child pattern
file.rules.*.emits.*.node: state
file.rules.*.id: on_miss
file.rules.*.id.from: argument_class argument_key array_key_class each each_key incoming_edges
    key literal qualified value
file.rules.*.id.from.*: annotation_key argument argument_class argument_key array_key_class
    attribute_argument capture each each_key incoming_edges key literal qualified value
file.rules.*.match: argument array_entry grammar method_call node_type static_call subscript_assignment
file.rules.*.match.where.*: ancestor_reaches attribute_argument base_is_known_plugin
    contained_by_type has_argument has_incoming_edge has_promoted_constructor_parameter
    in_method_with_attribute listed_at matches method_set_covers name on_service receiver
file.rules.*.values.*.from: annotation_key argument argument_class argument_key array_key_class
    attribute_argument each each_key incoming_edges key literal qualified value
manifest: boundary
manifest.boundary: applies_to_paths emit_boundary_nodes type_hierarchy
manifest.boundary.type_hierarchy.*: extends implemented_by type
manifest.files: cache_key_includes
```
