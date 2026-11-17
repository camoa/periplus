---
name: periplus-map
description: Answers code questions from a Periplus map, the deterministic graph of a codebase in .periplus/map.json, and records what a node or edge does in the descriptions file beside it. Use when a project has a .periplus/map.json and the user asks what calls or uses this, who uses this service, what breaks if this changes, where something is defined, how A reaches B, which subscribers listen to an event, what makes up a feature, or which files take part in a feature. Ask the map first; read code to confirm a line or where the map has no answer.
---

# Answer code questions from a Periplus map

## What the map is

- A graph of the code's things and the links between them, each at a file and line. Rules make
  it, so the same code gives the same map, byte for byte.
- It holds what its rules find, nothing more. A thing missing from the map is a missing rule, not
  proof that the code lacks it.
- `[marks]` on a row, such as `[not installed]`, are facts about that thing. A mark the rutter
  spreads holds for everything inside the thing too.
- Each row has a state. `mapped`: found in the project, with a location. `boundary`: outside the
  project, and a rule says what it is. `referenced`: named by a link, defined elsewhere.
  `unresolved`: a rule looked for the target by name and found none; the link and its line are
  real. `unknown_boundary`: picked at run time, or outside with no rule; read the code there.
- What a thing does lives in `.periplus/descriptions.yaml`, beside the map. Rows print it after
  `#`, and `find` searches it.

## The tools

`periplus --help` prints this list; `periplus find --help` prints the options of one command. Every
option, output and exit code is in [Navigation](https://github.com/camoa/periplus/blob/v0.9.1/docs/navigation.md).

<!-- periplus-help -->
```text
set up and build:
  init         create this project's .periplus directory and a stub settings file
  status       report the settings, the pack search path and the directories on it
  spec         print the pack contract: the schemas, the rule format, the engine, and what is open
  validate     check one pack against the shipped schemas, then report what map refuses it for
  update       move this project's pins to the rutter versions that are installed
  map          extract the map of this project and write it
  check-map    check the written map against the map schema
  skills       manage the Claude skills this package ships

learn the map's words:
  types        list the node types and edge kinds in the written map
  legend       say what each edge kind and node type in the written map means

cheap counts: ask these before pulling rows:
  depth        say how far the walks from an item go, both ways, and where hubs stop them
  count        count the things ids name, by type and state, and the edges among them
  pieces       split ids into the groups that edges among them join
  files        list the files that hold a set of things, most first
  hubs         list the hubs the walk by cause from the ids stops at

fetch things and their links:
  find         find the things and edges that hold some words
  show         show nodes and the edges at each
  neighbors    list what an item sets off, hop by hop
  affected     list what sets an item off, hop by hop
  only         list what the ids set off that nothing else sets off
  members      list what a container holds, by the map's grouping kinds
  in           list the things the map holds in each file, in line order
  at           name the mapped thing at a file and line, and what holds it
  path         show every shortest chain of edges from one item to another

macros: several answers in one reply:
  reach        print depth, then what an item sets off and what sets it off, in one reply
  slice        print the piece of the map around some words, ids or a path, or write it to a file

sets and map files:
  extract      write the things ids name, and the edges among them, to a map file
  join         count or write the things and edges in any of the maps
  common       count or write the things and edges in every one of the maps
  minus        count or write the things in the first map and in no other, and the edges among them
  diff         list the things and edges added, removed and changed from one map to another
  export       print the map as GraphML, DOT or Mermaid

descriptions:
  undescribed  count the main things with no description, by file, type or container
  order        list a set so that each thing comes after what it calls or uses
  stamp        write a fingerprint of its code into each node entry of the descriptions file
  stale        list the node entries whose code changed or whose node is gone

Shared options, where a command has them: --ids prints only full ids, one a line; - in place
of the ids reads them from standard input; --format json prints JSON; --limit 0 lifts a
budget; --map PATH reads another map or a slice file. periplus COMMAND --help prints the
options of one command.
```

## Rules

- Ask the map first. It holds links that no text search finds: the method behind a route, the
  class behind a service, the template a hook renders, what calls what.
- Counts are cheap. Ask `periplus depth`, `periplus count`, or read the first lines of
  `periplus find`, before you pull rows.
- A cut reply names the command that prints the rest. A cut reply is not the whole answer: never
  say nothing else touches a thing from one.
- Pass ids between periplus commands with `--ids` and `-`. Do not copy ids by hand; long ids get
  mangled. Pipe a periplus command only into another periplus command; `head` or `grep` drop
  rows without a word:

```
periplus find invoice --ids | periplus count -
```

- Widen loose words yourself. The user's word may not be the code's word: for login, also search
  authentication, sign in, session. Search each.
- Paste names as printed. A short name that fits several things exits 31 and lists their ids; run
  again with one of them.
- Run commands from the project root, the folder that holds `.periplus/`.
- Do not run `periplus map` unless the user asks. The map is already built.
- When the map and the code disagree, say so. It is a map gap worth reporting; the periplus-gaps
  skill records one.

## Words the commands use

- A walk by cause follows the kinds where one thing sets off another. `periplus legend` prints
  each kind's cause: `from`, the from end sets off the to end, as a call; `to`, the to end sets
  off the from end, as a hook runs its function; `none`, structure, never followed; `touch`,
  points at a thing without running it, not followed unless you pass `--touch`.
- A hub is a thing with more links to follow than `--hub N`, 40 by default. A walk lists it and
  stops there; `--through ID` walks on from one. Only the links the walk follows in its
  direction count, and a start is never a hub, so no hubs does not mean no shared code.
- `periplus only` lists what nothing outside the ids sets off: what would go unused without
  them. That is not the list of what belongs to a feature. Give it a feature's own things: a
  shared thing among the ids brings in all that it sets off.
- `periplus slice` walks out from its starts. `periplus extract` takes exactly the ids given.

## Recommendations

These are ways that tend to work, not required steps.

- Start with `periplus find` on the question's words, then `periplus reach` on the few main
  things it names.
- Let the tool combine sets. `periplus extract` writes ids to a map file, and `periplus join`,
  `periplus common` and `periplus minus` combine map files. This beats reasoning over long lists.
  Each such file is a map, the same as a slice file: any command reads it with `--map`.
- To test the edge of a set, list what touches it with `periplus neighbors` and
  `periplus affected`, extract that, and take the set out with `periplus minus`. Run
  `periplus count` and `periplus hubs` on what is left to see what matters.
- When `periplus pieces` splits a set that should be one flow, the map may lack a link there.
- When `periplus find` matches many things, count them first, then narrow with `--type` or
  `--path`.
- `periplus show` on a main thing prints every link kind in and out. Read the kinds before you
  say a link is missing.
- From a code-search hit, `periplus at FILE:12` gets back to the map: the thing at that line and
  what holds it.
- Read the source line under a row first. Open the file only when the answer needs more.
- When you read the code of a thing that has no description, add its entry; the
  periplus-describe skill says how.

When the map has no answer, or to confirm a line, search the code:
see references/code-search.md.
