# Import paths and call arguments

Read [Writing a rutter](rutter-author-guide.md) and [Tree
references](rutter-author-guide-references.md) first. This page covers the keys that bind a name
from a whole import path and resolve a dotted call only through a bound name, and the keys that
read a call's arguments.

Some languages write an import as a path with another separator than their names use, and call
through it with a dotted name. Check 97k-import-names-and-dotted-references proves each import key
below on a planted PHP rutter read that way. Check 98d-laravel-pack, check
97l-call-arguments-second-grammar and tests/test_argument_ends.py prove the call-argument keys. Only
tests/test_argument_ends.py proves `call_argument_name` and `call_literal_delimiters`, and only on
PHP.

An import's `bind.name` source `path` is the whole written path. `bind.normalize` runs its replace
and with steps, in order, on the bound name, whichever source gave it; the binding's target stays
the written path. So `name: [alias, path]` with `normalize: [{replace: '^.*/', with: ''}, {replace:
'_v\d+$', with: ''}]` binds `App/Util/Strings_v2` as `Strings`, where last_segment splits on the
grammar's separator only. A fact is read on the clause, and on the import's own node when the clause
has no such field. `bind.unbound_aliases` lists fact texts that bind no name, as `[_]`: a clause
whose name comes from a fact written so binds nothing, and the sources after it are not tried.

The resolve step `prefix_bare_with: namespace` holds only for a name without the separator, and
gives the namespace joined with it. After `bound_first_segment`, it gives `local()` the caller's
namespace. `Strings\up()` lands under the bound path only when the file binds `Strings`.

`prefix_with` holds for every name, so no step after it runs. Use it when every name belongs under
the namespace. Use `prefix_bare_with` when a dotted name must go on to a later step, or be skipped
when none holds.

Step order matters. With `bound_first_segment` first, a bare call of a local name equal to an
import's bound name resolves to the imported package: a parameter `fmt` called as `fmt()` lands on
the package fmt. Put `prefix_bare_with` first when a bare name can never be a package in that
language, as `go_basic` does for Go.

`match.whole_written: true` on a reference rule makes a name whose node holds a node of a type not
in `written_names`, at any depth, go under `skipped` as not a written name. So a chained call, as
`Strings::make()()`, makes nothing even when its node type is listed as a written name.

A reference that the steps resolve on no edge of the rule makes nothing, counts no fire and goes
under `skipped`: no resolution step holds for its `name_child`. `Missing\thing()` with no import of
`Missing` is one, under the two steps above. In a rule with two edges, when the steps hold on one
edge and fail on the other, only the edge they hold on is made. The reference counts a fire, and no
row under `skipped` names the other edge.

## A call's argument and its name

`name_matches` in `where`, on a tree declaration or reference rule, passes over with no row or fire
a match whose first `name_child` field's whole text does not match. The mapping form names the
child it tests, by field or else by node type, so one rule can test two parts of a call:
`where: [{name_matches: {child: scope, pattern: Reg}}, {name_matches: {child: name, pattern: get}}]`
fires on `Reg::get()` alone. A match without that child fails the condition, with no row.

A reference end `from: {argument: 0}` takes the text literal of the call's first argument. The
grammar's steps do not run on it, and the end's own steps do. A variable, missing or empty argument
makes nothing and goes under `skipped`, on an end and on an id alike. `laravel_basic` reads a view
name so:

```yaml laravel_basic@0.0.5/rules/views.yaml
- rule: view_call
  reads: file
  in: [source]
  match:
    reference: function_call_expression
    name_child: function
    filetype: php
    where: [{name_matches: '(?i)\\?view'}]
  emits:
  - edge:
      kind: renders
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [laravel.view], on_miss: unresolved}
  confidence: declared
```

Keys under `identity` say how the grammar writes a call's arguments. They are read apart from the
`attribute` block:

- `call_arguments` names the field that holds the arguments, `arguments` by default.
- `call_argument` names the node type that wraps one argument, whose value is its last named child.
  Without it, each named child of the field is one argument by position, and a comment is none.
- `call_argument_name` names the field of a named argument's name. That argument is found by name.
- `call_literals` lists the node types of a text literal, and `call_literal_content` those of its
  text. Without them, no argument is a text literal.
- `call_literal_delimiters` lists the named children of a literal that are skipped.

`php_basic` wraps each argument and names it:

```yaml php_basic@0.2.0/pack.yaml
# A call's arguments: their field, one argument and the field of its name, and the text
# literals with the node of their text. view('a') holds 'a' at position 0.
call_arguments: arguments
call_argument: argument
call_argument_name: name
call_literals: [string, encapsed_string]
call_literal_content: [string_content]
```

`go_basic` has no wrapper, and two literals, each with its own node of text:

```yaml go_basic@0.0.3/pack.yaml
# A call's arguments are the named children of its arguments field, by position. Its text
# literals are an interpreted and a raw string, each with its own node of text.
call_arguments: arguments
call_literals: [interpreted_string_literal, raw_string_literal]
call_literal_content: [interpreted_string_literal_content, raw_string_literal_content]
```

These keys are proven on these two grammars, by check 97l-call-arguments-second-grammar for Go,
except two. On PHP, tests/test_argument_ends.py maps `show(x: 'c')` and `show("b\n")` with each key
and without it: a named argument is not read at its position, and a declared `escape_sequence` is
skipped. No test plants either key on Go. A grammar whose string node holds named delimiter children, such as a start and an end quote,
declares them in `call_literal_delimiters`; no bundled pack does yet.

A declaration rule's id may come from an argument too, with an optional `normalize` and no other
key. Check 98d-laravel-pack plants this rule, which gives one node per
`Route::get` or `Route::post` call, named by its URI:

```
- rule: planted_route
  reads: file
  in: [planted_routes]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: 'get|post'}]
  id: {from: {argument: 0}}
  emits: [{node: {type: planted.route}}]
  confidence: declared
```

Such a node is never a reference's from end. A rule with an id from an argument and a
`match.body_child` refuses the map with exit 26: its id cannot name the class an enclosing id needs.
