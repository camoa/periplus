# The rules

Sixteen rules. Every one came from something breaking, and the evidence is beside it.

They are here because the format was proved across five packs — `php`, `yaml`, `go`,
`drupal`, `twig` — and what made that work is not the schema's field list. It is these.

---

## 1. A rule fills seven slots, and none of them names a language

```
rule         its own name, recorded as provenance on everything it produces
reads        file, or map
in           named folders — only when it reads files
match        one kind, plus a where list
id           where the id comes from, and how it is reshaped
emits        node, edge, attribute, type, or role
confidence   declared or inferred
```

102 rules across five packs use exactly these seven keys and no others. A rule that finds a
PHP class, a YAML mapping entry, a Go interface and a Drupal block plugin has the same shape
in all four cases.

**The test applied to every proposed key:** can it be stated without naming a language or a
language construct? `deriver_argument`, `unwrap: constructor_arg_0` and
`alter_hook_definition_key` all failed it and were removed. Those belong in the values a pack
writes.

---

## 2. Two relationships, and `reads` is the whole of it

```
supplementary   independent. each rule finds the thing on its own.
complementary   dependent.   the second reads what the first produced.
```

`reads: file` and `reads: map` make that mechanical, and it is the only ordering the engine
ever needs. No weights, no numbers — Drupal's own weight systems show where numbers end up,
with everything at `-49` beside a comment explaining why it is not `-50`.

**It tracks how explicit a language is, not where a pack sits.** PHP writes `extends` and
`implements` at the declaration site, so 21 of its 21 rules read files and none reads the
map. Go states no interface relationship anywhere, so it needs map rules — and Go is a base
pack with nothing beneath it.

```
php     21 file rules    0 map rules
yaml     1              0
go       6              2
drupal  32             16
```

---

## 3. Merging is an outcome of matching ids, not a property of rules

Two rules land on one node **only if both extract the same id**. If they do not, the map
grows two nodes for one thing, looks fully populated, and nothing errors.

> The PHP pack's identity was `parts: [namespace, declared_name]` — right for a class, wrong
> for anything inside one. Run against a real module it merged four different `build()`
> methods on four different classes into one node. No error, no warning.

The failure modes differ, which is why the two names in rule 2 are worth having. Lose a
supplementary rule and the node still arrives by the other route — what is lost is the link.
Lose a complementary rule and the thing never appears.

---

## 4. Identity is a named source, optionally reshaped

```
from        a named source: a file stem, a matched argument, a captured value
pattern     optional. searched in that source; its named captures become parts
template    optional. assembles the parts into the id
normalize   optional. declared substitutions
```

The steps run in that order: from, pattern, template, normalize. On a tree declaration rule,
`pattern` reads one source and is searched in its text, not matched whole. A source it does not
fit makes nothing: no node, no edge, no skipped row, and no fire. A `{name}` in the pattern is a
path value or a settings value, filled in as literal text.

This closed the sharpest question the design had open — whether id transformations are a
closed set of engine functions, in which case a pack needing a new one needs a release. They
are not a set. Regex is a general string language written as data.

> `field.field.block_content.type_way_code.body` carries three facts in one name — entity
> type, bundle, field. One pattern with named captures reads it, and reads
> `field.field.node.article.body` unchanged.

**The id comes from the thing, never from the rule.** Renaming a rule must not churn ids
across a committed map.

---

## 5. A rule emits nodes or edges, never both

The part of a file that makes a node is a different part from the part that makes an edge,
and they sit on different lines. One rule doing both stamps one location on all of it.

```
block.block.block_ways_1_attribute.yml
  line 1    the file exists                  -> the node
  line 5    dependencies: block_ways         -> an edge
  line 13   plugin: 'block_ways_attribute'   -> another edge
```

The schema refuses a rule that emits both. Before the split, all three said line 1, and
"where is this block placed" answered with the top of the file.

An edge rule still computes an id — it needs one to name its endpoint. It just does not emit
a node with it.

---

## 6. A rule never writes a path

The pack names folders; the project settings override them.

```
pack       config = ./config/sync
rule       in: [config, module_config]
settings   config = ./drupal-app/config/default
```

> Three real Drupal sites keep exported config in three different places, and one of them is
> computed in PHP at runtime: `dirname($app_root) . '/config/default'`. With the path in the
> rule, that is a pack edit. With a name, it is one line of settings and no rule changes.

---

## 7. A rule never writes a file extension

```
match:
  file: "block_content.type.*"
  filetype: yaml
```

The rule names the file and declares the type. The pack that owns the language claims the
extensions — `[yml, yaml]` — so a site keeping config as `.yaml` needs no rule change, and
a glob can never accidentally match a file of another type sharing a name.

`match.ending` is the one place a rule names an ending, and only one a pack already claims: it
keeps the files of that ending, or of any in a list, where the glob, which reads the stem, cannot
tell `.inc` from `.theme`. An ending that no loaded pack claims is refused, and the refusal lists
the claimed endings.

---

## 8. Confidence is declared on the rule, never computed

```
Go      formatter.go   ^[A-Z] on a name   declared    capitalisation IS visibility
React   Footer.tsx     ^[A-Z] on a name   inferred    a convention people can ignore
```

Same primitive, same regex, same character. Only the pack author knows which.

The case that proves it is not the regex: the alter-hook rule reads a string **literal**, so
a runtime check would call it `declared`. What is uncertain is not the literal — it is that
assigning into `$definitions[...]` inside a `block_alter` implementation *constitutes
declaring a plugin*. That is a claim about what the hook means.

---

## 9. A type is declared once; rules for it arrive from anywhere

```
block/block_type.yaml          declares drupal.block_type, finds nothing
block/block_type_config.yaml   one rule, the config file
block/block_type_code.yaml     one rule, BlockContentType::create
```

Each mechanism file names what it contributes to, so a typo fails the type-table build rather
than minting a type nothing ever finds.

**What this opens is the point.** A rule file written locally for one repository is the same
kind of thing as a rule file in the shipped pack. The test, and it is mechanically checkable:
*a local rule file, copied unchanged into the official pack, does exactly the same thing.*

---

## 10. An edge target is an id, not a second vocabulary

Edge targets grew eight keys — `compose`, `namespace`, `key`, `argument_key`,
`class_from_argument`, `matching`, `each`, `template`. Every one of them collapsed into the
id block that already existed. What is left is `from`, `template`, `where` for filtering, and
`each` for cardinality — three of which are the id block and one of which is not identity at
all.

A tree declaration rule's end may also be `{declared: <type>}`: the id of the node of that
type that a rule of the same pack, or of a pack it depends on, declares at the same match; the
first such rule that fires there and mints an id gives it. The type must be declared by one of
those packs, or the map stops with exit 23, and must meet the kind's types at that end, or it
stops with exit 22. When no such rule mints an id there, the edge is not made and one skipped row
names the end; when no rule maps that id, the end is a referenced node of the named type alone.
The end does not test the other rule's folders. It, `enclosing_class` and `enclosing_method` take
another rule's whole id, so an end filled only by whole ids may list types with different id
namespaces.

An end may also find its name in a table the pack carries. `tables`, a top-level key of
`pack.yaml`, maps a table's name to a map of written name to node name; the resolution step
`lookup_last_segment_in: <table>` gives the value of the name's last segment, and a rule may name
the tables of its pack and of the packs it depends on, the nearer pack's winning. A step naming a
table none of them declares is refused, naming the `tables` key. The table is data, so the engine
still holds no language knowledge. An end read `{argument: N}` also takes a class constant
declared as text, when the grammar block declares `constant_access` and `constant_declaration`,
the node types of a constant read and of a declaration; one without the other is refused.

---

## 11. A match is one kind plus a `where` list

`match` reached 24 keys, most used once. The top eight name what is being matched:

```
declaration  attribute  annotation  static_call  method_call  array_entry
subscript_assignment  node_type  text
```

Everything else was a condition wearing the wrong shape — `in_method_with_attribute`,
`argument_present`, `on_service`, `has_child`, `ancestor_reaches` — and moved under `where`.

Two conditions force `reads: map`, because they cannot be answered from one file:
`ancestor_reaches` and `contained_by_type`.

`name_matches` tests a child's whole text. Its string form tests the first `name_child`. Its
mapping form, `{child: scope, pattern: Config}`, names the child: a field of the match, or else
its first child of that node type. So one rule can test a call's class and its method. A match
without that child, or whose child does not match, makes nothing and is not a fire.

---

## 12. Code is text; the tree is an optimisation

A file is text and a pattern can read it. The parse tree makes containment and disambiguation
cheap and correct, and it is not the foundation.

> Signature normalisation was called "language knowledge the format cannot express". It is a
> pattern and three substitutions:
>
> ```yaml
> pattern: '(?s)interface\s*\{(?<body>.*?)\}'
> normalize:
>   - {replace: 'interface\{\}', with: 'any'}
>   - {replace: '\n',            with: ';'}
>   - {replace: '[ \t]+',        with: ' '}
> ```
>
> That produced `MarshalYAML() (any, error)` and four correct `satisfies` edges, from an
> engine containing no Go.

**The consequence is the floor.** `packs/twig` has no grammar block, two files, and it maps
templates. Adding a stack needs patterns, not a tree-sitter grammar.

---

## 13. Claim only what the method can see

A pattern cannot tell these apart:

```
{{ way }}            a variable
{{ way|upper }}      a variable with a filter
{{ path('front') }}  a function call
{{ user.name }}      a property on an object
```

So the twig pack emits `twig.reference`, not `twig.variable`, and marks it `inferred`. The
alternative is calling `path` a variable, which is a wrong entry in a committed artifact.

Nothing is lost by being honest. The names are still there, still connected, still findable —
and a reader knows not to trust them as variables.

---

## 14. A pack may only name types it declares or a dependency declares

Checkable before a single source file is opened, which is what makes building the type table
an ordering commitment rather than an implementation detail. Checked mechanically across five
packs; it found one violation.

There are no kinds of pack. A root is a pack with nothing beneath it and need not be a
language. If any level were special, a third party could not occupy it.

---

## 15. Something is a node when the two sides can exist without each other — and always when something names it

```
a block plugin and its class   two nodes    views_block:… is a plugin with no first-party class
a field storage and its use    one node,    one `body` storage, three bundles,
                               three edges  the attachment is the edge
a class extending another      one edge     "the extending" is not a thing anyone asks about
```

**And the harder half:** if something else names it by id, it must be a node, because an edge
cannot be the target of an edge. Two displays name a field instance, and that was the
argument for keeping it a node — until the displays turned out to declare their own bundle,
so pointing at the storage loses nothing.

---

## 16. Silence is the enemy

Every failure worth naming from building this was silent. A pack that reads fine and does
nothing:

```
on: class_declaration       parsed as the boolean key `true`, in five rules
two `id:` keys in a mapping YAML kept the last, discarding 48 rule names
a duplicate `pack:` key      discarded an entire file of React rules
find: {file: "*.yml"}        matched nothing on three real sites, silently
name_child                   a field name in one pack, a node type in another
```

So: the meta-schema rejects unknown keys, the engine reports every rule that fired zero times,
and a rule shape it cannot execute is named rather than skipped.

**And the map does the same.** A rule that looked and failed emits a node recording what it
searched for and what it found — not a warning, and never an edge to a name it could not
resolve.

> The spike emitted 221 call edges to bare words. `Draft -> t`, fifty-eight times, where `t`
> is a translation method.

---

## Still open

- **Cardinality.** Nothing says a class extends one class and implements many. A second
  `inherits` edge would sit in a map looking fine. It belongs on the edge kind, per pack —
  Go has no `inherits` at all and a Go struct embeds many.
- **Descriptions.** Each node carries `source_hash`; the artifact keyed by node id has no
  schema.
- **Addressing inside a data file.** `each: "services.*"` is one underspecified line, and two
  packs need it.
- **Resolution.** The PHP pack declares a whole section — `scope`, `match`,
  `never_match_by`, `on_zero_definitions` — and nothing specifies how an engine uses it.
