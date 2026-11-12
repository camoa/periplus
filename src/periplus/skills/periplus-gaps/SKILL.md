---
name: periplus-gaps
description: Reads a Periplus map and the code behind it, lists what the map lacks, and says for each gap whether it needs a new rule, a new rutter or the engine, and where the rule belongs. Use when the user asks what the map is missing, why a thing is not in the map, whether the map is complete, or what to write next, and after periplus map when unresolved names or unknown boundaries show.
---

# Find the gaps in a map

## Standing rules

1. Rules are small and add to each other: one rule solves one case, and several cases are several rules. Split by rule file inside one rutter, never by adding rutters; a new rutter repeats the file types and folders the covering one already holds, and a small rule can be read, tested and removed alone.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map. Each pass reads what the one before it found, so no rule has to look a thing up itself.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter. The engine then stays the same for every stack, and a third-party rutter can do all a built-in one does.
4. Write the rule and run it: probe before saying a rutter cannot. Call a gap the engine's only after two formulations of the rule were written, run and refused, and quote the engine's message for each. A guess about the format's limits has been wrong before; the message is the evidence.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose. The name leaks the project and ties the rule to one site.

## Where the detail lives

- [Navigation](https://github.com/camoa/periplus/blob/v0.7.0/docs/navigation.md) holds the signature, output rows and exit codes of each command used here.
- [Where a rule belongs](https://github.com/camoa/periplus/blob/v0.7.0/docs/map-report-guide.md#where-a-rule-belongs) and
  [When a gap is the engine's](https://github.com/camoa/periplus/blob/v0.7.0/docs/map-report-guide.md#when-a-gap-is-the-engines) hold the full choice of destination.
- [The rutter author guide](https://github.com/camoa/periplus/blob/v0.7.0/docs/rutter-author-guide.md) and the rutter skill hold how a rule is written and a rutter started.
- [Bundled rutters](https://github.com/camoa/periplus/blob/v0.7.0/docs/rutters.md) lists every rutter that ships with Periplus.

## Find the gaps

The gaps are read from the map's own marks: `referenced` and `unresolved` nodes, the report's
`skipped` rows, `inferred` edges, `runtime` marks, the Detail gaps lines and the site faults. Code
is opened only at the file and line a mark points to. This skill does not survey the code for
things the map lacks. A silent gap, code no rule looks at, leaves no mark: it shows as a wrong or
missing answer when the map is used. Survey the code wider only when the user asks for it.

Run the steps in the project root, after `periplus map`. The report has two halves, resolution
gaps and detail gaps, and three lists apart from both: site faults, unknown boundaries and plain
classes.

1. Check the map and see what it holds. `periplus check-map` exits 0 on a valid map; fix any
   fault it names before you read further. `periplus types` counts the node types and edge kinds.
2. List every node. Every id holds the text `::`, so `periplus find :: --limit 0 --format json`
   prints all of them, each row with its id, type, state and first location. A row whose state
   is `referenced` (a name seen, with nothing describing it) or `unresolved` (a rule looked and
   failed) is where a missing rule shows, except an id step 4 prints under Site faults.
3. Read the rows the map skipped. `periplus map --format json` prints the map report; read its
   `skipped` rows, each a file, line, rule and reason, for code a rule matched and could not use.
4. Print the report from the map file. The program ships with this skill and needs only the
   standard library. Run it from the project root:
   `python3 ${CLAUDE_SKILL_DIR}/scripts/gap_read.py .periplus/map.json`. Under Resolution gaps it prints the count of `referenced` nodes,
   of `unresolved` nodes and of edges whose confidence is `inferred`, each followed by a
   `first-party` split. A node is first-party when its state is `mapped` and it has a location,
   so a `referenced` or `unresolved` node is always outside; for those two lists a
   `reached from first-party` line counts the ones an edge from a first-party node reaches. The
   map file holds no folder list, so read the folders `custom_module`, `custom_theme` and
   `js_source` in `settings.yml` to tell which first-party files a gap sits in.
5. Open the file and line of each gap and read the code; a row whose location is null has none,
   so `periplus affected ID` names the nodes whose edges reach it, and you read those. Skip
   the ids printed under Site faults; they are site faults, not missing rules. Decide
   whether a rule would resolve it: name the shape the rule would match and the node or edge it
   would emit.
6. Open `.periplus/descriptions.yaml`, the file the map skill describes. Count every node id in the
   step 2 list, whichever its state, with no descriptions entry under `nodes` as a description gap to fill; a file with no `nodes` key
   holds zero entries.
7. Report the gaps grouped by the rule that would close them: one entry per rule, with the count
   of marks it closes and a file and line or two to read, never one entry per mark.

<!-- nav-run -->
```
$ periplus check-map
$ periplus types
$ periplus find :: --limit 0 --format json
$ periplus map --format json
```

## Detail gaps

The second half of the report says what a sibling rutter would add, from the map file alone.
Read the Detail gaps lines in three groups. Under each rule line and each child-type line with
nodes, a `first-party <n>  outside <n>` line splits its nodes as the Resolution gaps lines do.

- A rule line, `<rule>  <discriminator>  <count>`, counts the nodes one rule made. A catch-all rule
  hides what it made, so its nodes are split by a discriminator: for `any_config_file` the config
  prefix, the id text after `drupal.config::` up to the first dot; for a rule that makes
  `php.class` nodes the module in the namespace `Drupal\<module>\...`, or `none`; for every other
  rule there is none, printed as `-`. A plugin class splits by its module. Its attribute class is
  a `has_attribute` edge, which Plain classes groups by; a docblock annotation is read into an
  internal node, so it reaches the map only as a `plugin_of_type` edge, when the map holds its
  class as a plugin type.
- A child-type line, `<parent>  <child>  <count>`, shows for each parent type the child types the
  map holds and how many nodes each has; a parent with no child prints the word `none` and 0. A
  parent with children also prints `<parent>  own <discriminator>  <count>` for the nodes left on the
  parent itself, grouped by the rule line's discriminator: a group no child type took. That is the
  room a sibling rutter would fill.
- A module line, `<module>  <count>  rutter: <pack>`, groups the referenced `drupal.module` nodes
  and the referenced `php.type` nodes by module, all outside the mapped code, counts the distinct
  mapped nodes that lean on it, and names the first pack in the map file's `packs` list that covers it, or `none`. Highest first:
  a module with a large count and no rutter is the next rutter to write. `periplus status` lists
  the packs on disk.

## Site faults

A site fault is a name the map was right about and the site has wrong. It prints as
`<id>  <file>:<line>  <kind>`, with the file and line of the first edge that reaches it. Fix the
site, not the rules; no site fault needs a rule. The program prints five kinds, each only when the
place that should define the name is itself in the mapped code.

- `method no class defines`: a method called on a mapped class or enum whose chain is mapped and
  holds no method of that name. The chain is the class, every class it inherits from, every trait
  it mixes in and every interface it implements. A chain that declares `__call` or `__callStatic`
  defines every method, on a class and on an enum.
  PHP builds `cases` into every enum, so it is never a fault. PHP builds `from` and `tryFrom` only
  into a backed enum, one declared with a colon and a type after its name, so on a pure enum they
  print as this fault. The map does not hold the backing: the program reads the declaration at the
  enum's location, relative to the project root. When it cannot, it names the file in one stderr
  line and the name stays a resolution gap.
- `library no libraries file defines`: a library attached whose module or theme is mapped and whose
  libraries file has no such library. A fourth field, `near <id>`, names a library that file
  defines whose name differs only in case.
- `class no file holds`: a class named under `Drupal\<module>\` whose module is mapped and which no
  file holds.
- `menu link no links file defines`: a menu link's parent whose name, up to its first dot, is a
  mapped module's name, and which no links file defines. A parent holding a colon is a derivative made
  at run time, and never prints.
- `theme hook no hook_theme declares`: a hook a class renders, whose template a mapped module holds,
  and which no hook_theme of the mapped code declares. A theme's template does not count, since it
  may override a hook core declares. A hook_theme that builds its keys at run time, as in a loop,
  prints here too: read it before calling the hook a fault.

A script a libraries file names and the disk lacks is not printed: the map holds a referenced
script node both for a missing file and for one outside the mapped folders.

When a class, trait or interface in the chain is referenced, outside the mapped code, the name stays a resolution gap:
the missing rule is the PHP rutter's, never a site fault. An enum is concrete, so an outside
interface gives it no method: on an enum only an outside trait keeps the name a resolution gap.

## Unknown boundaries

An unknown boundary is a place where static reading stops: a call whose method name, callee or
argument is built at run time. A rule marks it with the node attribute `resolution` set to
`runtime` and gives it no target, because any target would be invented. The program prints a
`runtime  <count>` line, the `first-party` split, then one line per marked node as
`<id>  <file>:<line>  <pack>.<rule>`, with every location of the node and the rule that set the
mark, named as an `accepted_unknowns` entry names it. The `referenced` and `unresolved` lists never
hold it.

It is not a gap for a new rule to fill, unless the mark is wrong: the code there is not a run-time
call. Read the code at each location, then accept the place or leave it for the next rule. To
accept it, add an entry under `accepted_unknowns` in `.periplus/settings.yml` with the node id as
`id` and the marking rule as `rule`, written `<pack>.<rule name>`, with the `reason`,
`accepted_by` and `accepted_on` the entry needs.

## Plain classes

A plain class is a first-party class, interface, trait or enum that no more specific type claims:
its type is still the language rutter's, and no edge from a node of another stack reaches it. The
program prints `claimed  <n>` and `plain  <n>`, then one group per line,
`<kind>  <outside id>  <count>  <example id>`, highest count first:

- `inherits`: the first parent outside the mapped code, reached through mapped parents.
- `implements`: for a class with no outside parent, the first outside interface it or a mapped
  parent implements.
- `has_attribute`: each attribute class the class carries. These groups overlap the two above.

Last, `none  <n>` counts the plain classes with no outside parent, interface or attribute. The map
holds no folder list, so test classes count with the rest; their groups name a test base class.

For each group, name the role the outside parent or attribute gives, from what you know of the
framework: a form, a controller, an event subscriber, a plugin of some type. Check with
`periplus types` whether the map has a node type for that role. If it has none, propose the
framework rule: the node, and the two or three relations a developer needs from it, such as what
registers it, what calls it and what it acts on. If the type exists, the rule that gives it misses
this parent or attribute. A group whose parent gives no framework role, such as an exception base,
is not a gap. What you know proposes the rule; the rule is still written and run.

## Where a rule belongs

Write the rule in the project's own rutter first: a rutter folder in the project's
`.periplus/packs`. When any other project on the stack could use it, move it to the bundled
rutter for that stack, as a new rule file or a rule added to one, once a second project needs it.
When no bundled rutter covers the stack at all, start a new rutter with the rutter skill, then
write the rule in it.
A framework rutter adds to a language rutter's lists through tables: `add_table_rows` in its
`pack.yaml` adds rows to a table the language rutter owns, such as a skip list. It never copies the
language rutter's rule to change one list.
A gap is the engine's when the engine refuses the rule you wrote and no other rule can state the
shape. Claim it only after two formulations were written, run and refused, quoting the engine's
message for each. The test is in
[When a gap is the engine's](https://github.com/camoa/periplus/blob/v0.7.0/docs/map-report-guide.md#when-a-gap-is-the-engines).

## Run it again

Every rule changes the list. After you write a rule and run `periplus map`, run these steps again
and read the report anew: a gap the rule closed leaves it, and a gap the rule exposed joins it.
Stop when the report holds only gaps no rule of yours can close.
