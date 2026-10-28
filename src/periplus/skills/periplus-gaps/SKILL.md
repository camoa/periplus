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
5. The product never names the client site; a rule tied to one site stays in that site's own rutter.

## Where the detail lives

- docs/navigation.md holds the signature, output rows and exit codes of each command used here.
- docs/map-report-guide.md holds the full choice of destination, under "Where a rule belongs" and
  "When a gap is the engine's".
- docs/rutter-author-guide.md and the rutter skill hold how a rule is written and a rutter started.

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

A rule for a convention only this project uses stays in the project's own rutter, a folder under
`.periplus/packs` named `<pack>@<version>` with a `pack.yaml`. A rule for a shape any project on
the stack can hold goes to the bundled rutter for that stack.
When a bundled rutter already covers the stack, that rule is a new rule file in it, or a rule
added to one of its rule files.
When no bundled rutter covers the stack at all, start that new rutter first with the rutter skill,
then write the rule in it.
Write a rule in the project first, and move it once a second project needs it.
A gap is the engine's only when `periplus validate` or `periplus map` refuses the rule with an
engine message; any other gap is a rule not yet written. The detail is in
docs/map-report-guide.md, under "Where a rule belongs" and "When a gap is the engine's".
