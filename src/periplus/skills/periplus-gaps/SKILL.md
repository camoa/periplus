---
name: periplus-gaps
description: Read a Periplus map and the code behind it, list what the map lacks, and say for each gap whether it needs a new rule or a new rutter, and where that rule belongs.
---

# Find the gaps in a map

## Standing rules

1. Rules are small and add to each other: split by rule file inside one rutter, never by adding rutters.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter.
4. Write the rule and run it: probe before saying a rutter cannot, and quote the engine's message.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose.

## Where the detail lives

- [Navigation](https://github.com/camoa/periplus/blob/v0.3.0/docs/navigation.md) holds the signature, output rows and exit codes of each command used here.
- [Where a rule belongs](https://github.com/camoa/periplus/blob/v0.3.0/docs/map-report-guide.md#where-a-rule-belongs) and
  [When a gap is the engine's](https://github.com/camoa/periplus/blob/v0.3.0/docs/map-report-guide.md#when-a-gap-is-the-engines) hold the full choice of destination.
- [The rutter author guide](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutter-author-guide.md) and the rutter skill hold how a rule is written and a rutter started.
- [Bundled rutters](https://github.com/camoa/periplus/blob/v0.3.0/docs/rutters.md) lists every rutter that ships with Periplus.

## Find the gaps

Run the steps in the project root, after `periplus map`.

1. Check the map and see what it holds. `periplus check-map` exits 0 on a valid map; fix any
   fault it names before you read further. `periplus types` counts the node types and edge kinds.
2. List every node. Every id holds the text `::`, so `periplus find :: --limit 0 --format json`
   prints all of them, each row with its id, type, state and first location. Keep the rows whose
   state is `referenced` (a name seen, with nothing describing it) or `unresolved` (a rule looked
   and failed). That is where a missing rule shows.
3. Open the file and line of each kept row and read the code; a row whose location is null has
   none, so `periplus affected ID` names the nodes whose edges reach it, and you read those. Decide whether a rule would resolve
   it: name the shape the rule would match and the node or edge it would emit.
4. Open `.periplus/descriptions.yaml`, the file the map skill describes. Count every node id in the
   step 2 list, whichever its state, with no descriptions entry under `nodes` as a description gap to fill; a file with no `nodes` key
   holds zero entries.

<!-- nav-run -->
```
$ periplus check-map
$ periplus types
$ periplus find :: --limit 0 --format json
```

## Where a rule belongs

Write the rule in the project's own rutter first: a rutter folder in the project's
`.periplus/packs`. When any other project on the stack could use it, move it to the bundled
rutter for that stack, as a new rule file or a rule added to one, once a second project needs it.
When no bundled rutter covers the stack at all, start a new rutter with the rutter skill, then
write the rule in it.
A gap is the engine's when the engine refuses the rule you wrote and no other rule can state the
shape. The test and the message to quote are in
[When a gap is the engine's](https://github.com/camoa/periplus/blob/v0.3.0/docs/map-report-guide.md#when-a-gap-is-the-engines).
