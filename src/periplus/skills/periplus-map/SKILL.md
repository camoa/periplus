---
name: periplus-map
description: Answers code questions from a Periplus map, the deterministic graph of a codebase in .periplus/map.json, and saves the set of things that take part in a feature as a map file. Use when a project has a .periplus/map.json and the user asks what calls or uses this, who uses this service, what breaks if this changes, where something is defined, how A reaches B, which subscribers listen to an event, what makes up a feature, everything that takes part in X, which files take part in a feature, or for an inventory of an area such as login or invoicing. Ask the map first; read code to confirm a line or where the map has no answer.
---

# Answer code questions from a Periplus map

Using the map means following its nodes and edges to find everything that is connected and still
related to the topic. Words only find where to start. "Still related" is also when to stop: walk
until what you reach is no longer about the topic. That judgement is yours.

Know which kind of work you are doing. A **lookup** asks one question about one thing: who calls
this, where is that defined. A **set** asks for everything that takes part in something: a
feature, a flow, an area. The product of set work is a slice. Before set work, read
references/find-a-feature.md: what the work holds, a worked example, and how to keep calls few.

## Words

- A **walk by cause** follows the kinds where one thing sets off another: the walk off lists
  what a thing sets off, the walk by what sets it off. `periplus legend` prints each kind's
  cause; `none` (structure) and `touch` (points, runs nothing) are not walked.
- A **hub** has more links to follow than `--hub N`, 40 by default. A walk lists it and stops.
  It is often shared code: walk on with `--through ID` only when it belongs to the topic.
- A **shared thing** is one that code writes and other code reads: a variable handed to a
  template, a config value, a global. Writers and readers both point at it, so a walk off
  ends there. They are still connected: `periplus show THING` lists every reader and writer.
  Walk on from the readers that belong to the topic.
- A **start** is where your words land. An **entrance** sets something off, and nothing in the
  map sets it off. A slice read with `--map` is the map. `periplus depth IDS --entrances` lists
  the entrances among many ids. The periplus-describe skill means the same.
- A **slice** is a map file that `periplus slice --out FILE`, `periplus extract`,
  `periplus join`, `periplus common` or `periplus minus` writes. Commands read it with `--map`.
- The **rim** of a set is what lies one hop from it, either way, and is not in it.
- Row states: `mapped`, here with a location; `boundary`, outside, a rule says what it is;
  `referenced`, named by a link, defined elsewhere; `unresolved`, no target by that name, but the
  link and line are real; `unknown_boundary`, picked at run time or outside with no rule: read
  the code. `[marks]`, such as `[not installed]`, are facts about a thing. `#` starts its
  description.

## The tools

`periplus --help` prints this list; `periplus find --help` prints one command's options. Every
option, output and exit code is in [Navigation](https://github.com/camoa/periplus/blob/v0.10.2/docs/navigation.md).

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
of the ids reads them from standard input; --format json prints JSON; --map PATH reads
another map or a slice file. --limit 0 lifts the budget of find, show, neighbors, affected,
path, reach, slice and diff; the other commands print every row and take no --limit.
periplus COMMAND --help prints the options of one command.
```

The commands are small; you combine them. By job:
- **Find starts:** `periplus find` (`--type`, `--path`, `--mark`, `--any`), `periplus at`,
  `periplus in`, `periplus members`, and `affected --depth all` from what the topic does.
- **Bound and plan:** cheap facts, the same each run, to decide what to read and how to slice.
  `depth` says how far each walk goes, both ways, and where hubs stop it; `hubs` names them.
  `count` and `files` say how big a set is and what it holds; `pieces`, one flow or several.
  `neighbors` lists what a start sets off, `affected` what sets it off, `reach` both. Before a
  slice, they should say roughly how big it will be and whether it leaves the topic; a refused or
  oversized slice means a planning question was skipped. references/find-a-feature.md shows how
  to read each reply. Leave counting and walking to the commands; spend your effort on meaning:
  which words, what is still related, what is in or out.
- **Save and combine:** `periplus slice --out FILE`, `extract`, `join`, `common`, `minus`.
- **Inspect one thing:** `periplus show`, `periplus path`.

Defaults that bound a result:
- `slice` from words takes at most 12 starts (`--starts`), favouring two of one type, and walks
  2 hops each way (`--depth`). It prints 50 things past the starts; with `--out` it holds at
  most 500, and over that writes nothing and exits 32.
- `neighbors` and `affected` walk 1 hop unless given `--depth`; `reach` and `hubs` walk all.
- `--limit` counts characters in `find` (12,000), `neighbors`, `affected` and `reach` (20,000),
  rows in `show` (50) and chains in `path` (10). `--ids` is never cut.

## Rules

- Ask the map first: it holds links no text search finds. A thing missing from it is a missing
  rule, not proof the code lacks it.
- Set work always goes through a slice. Ask the user whether a saved slice for it exists, and
  read it with `--map FILE`. If none does, make one with `periplus slice --out FILE`. The tool
  names no folder for slices: put it beside the map and tell the user where.
- Before you say a set is complete: it is saved as a slice; it was walked from its entrances
  until what the walk reached was no longer about the topic; and its rim was read, with a
  stated reason for each thing left out.
- Read periplus output whole, or narrow it with periplus: `periplus find WORDS --limit 1` for
  the counts, `--type`, `--path`, `--ids` piped into `periplus count -`, slices. Never cut it
  with `grep`, `head`, `awk`, `cut` or a script, JSON included: they drop rows without a word.
- A cut reply names the command for the rest. It never shows that nothing else is there.
- Widen loose words yourself (login: authentication, sign in, session); drop what does not fit.
- Run from the folder that holds `.periplus/`, and run `periplus map` only when asked. A short
  name that fits several things exits 31 and lists their ids; paste one as printed.
- When the map and the code disagree, say so. It is a map gap; the periplus-gaps skill records it.

## Ways that tend to work

- A lookup: `periplus find` on the words, then `periplus reach` or `periplus show`.
- The steps from A to B: `periplus path A B`, one step a line, each with its file and line. A
  chain holds only the steps that lead to B. For what a method does after that step, run
  `periplus show` on the method: it lists every call the method makes, each with its line.
- From a line, in an error, a diff or a search hit: `periplus at FILE:42` names the thing on
  that line and what holds it. `periplus in FILE` lists what else the map holds in that file, in
  line order.
- What touches a thing, such as a role, a permission or a config value: `periplus show THING`.
  It lists every link in and out, the `touch` kinds too, such as a role check, which no walk
  follows. `periplus find` lists only the links that hold your words, never all links of a thing.
- One slice need not hold it all. When the start count, the depth or the 500 cap gets in the
  way, make partial slices, one per entrance or part, and join them into one file:

```
periplus slice --from ENTRANCE --direction off --depth 4 --out login-form.map.json
periplus join login-form.map.json login-reset.map.json --out login.map.json
```

- Read the rim, then decide what belongs. `periplus extract` and `periplus minus` take things out:

```
periplus find --map login.map.json --ids | periplus reach - --depth 1 --ids | periplus extract - --out rim.map.json
periplus minus rim.map.json login.map.json
```

- A set that should be one flow but falls into pieces may lack a start, or a link in the map.
- The periplus-describe skill describes a thing whose code you read, and a saved set (`--map`).
- The periplus-analyze skill guides a review of the code the map named: what can go wrong.
- When the map has no answer, or to confirm a line, see references/code-search.md.
