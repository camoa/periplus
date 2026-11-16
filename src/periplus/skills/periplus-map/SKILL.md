---
name: periplus-map
description: Answers code questions with a Periplus map used together with code search, and records what a node or edge does in the descriptions file beside the map. Use when a project has a .periplus/map.json and the user asks what calls or uses this, who uses this service, what breaks if this changes, where something is defined, how A reaches B, which subscribers listen to an event, what makes up a feature, or which files take part in a feature. Search the code first, then ask the map what touches each thing found.
---

# Navigate a Periplus map

## Two kinds of finding

Use code search and the map together. They find different things.

- Text search finds what is written: every place a word or a name appears.
- The map holds ties that are not one text match: the method behind a route, the class behind a
  service, the template a hook renders, the config a thing reads, the library a template attaches,
  the module that owns a thing, and what calls a method and what it calls. Each tie sits at the
  file and line of the code that makes it.

## Order of work

1. Search the code for the question's words. Read the hits that bear on it. Note the real name of
   each thing you find: class, method, function, route, service, template, config name, module.
2. Ask the map what touches each name: `periplus show NAME`. You may send several `show` commands
   in one step. Each prints every link kind in and out, at its file and line.
3. Read the code of each linked thing you have not seen yet. It may be a second module, a template
   or a config record that changes the same feature.
4. Run `periplus slice "WORDS"` with the names and words you learned. It also matches the
   plain-words descriptions, so it reaches things whose names hold none of your search words.
5. Search the code again for each new name the map gave you. Repeat step 2 for those that matter.

The map names the links. Read the code of a thing before you say what it does.

## What a slice prints

`periplus slice "WORDS"` picks start things from the words and prints the piece of the map around
them, in one call. `periplus slice NAME` starts at that one thing. Read every part of the reply:

- `start` lines: one per start, with each word it matched and where, or `given as` for a name. A
  start that has nothing to do with the question is noise; skip its block.
- `members of NAME: ...`: the start is a container, such as a module. It counts what it holds.
- `piece N of M`: things that links join. Pieces share no link, but the words tie them. Read
  them all.
- One block per file: the path, then `:LINE  name  type` per thing, with its source line.
- `#` lines: what the thing does, in plain words. Read it before you open the file.
- Link lines: `calls -> X, Y` goes out, `calls <- Z` comes in. A name on a link line belongs to the
  answer as much as a name at the start of a line.
- `realized by (KIND) -> X`: X is the code that does the work of a declared thing, such as the
  method behind a route or the class behind an interface. X belongs in the answer.
- `+N in supporting code (...)`: tests and helpers the walk met and did not print. `--support`
  prints them.
- `[...]` after a row, such as `[not installed]`: a fact about that thing that holds for
  everything inside it. A function marked `[not installed]` sits in a module that is not
  installed, so its code does not run.
- `+N more links: ...; see periplus slice NAME`: the map holds more links of that thing than the
  piece shows. Run that command when the thing matters.
- `inventory:`: every thing the reply names, by type. Check your answer against it.
- Cut lines, after the inventory: `showing N of M rows`, `left out by kind: ...`, `cut to fit ...`
  and `go deeper with --depth N`. See the next section.
- `legend:` comes last, when the packs describe the kinds shown: one line per link kind.
  `periplus legend --kind K` prints one kind in full.

Use the question's own nouns, three or four words. Paste names as printed into the next command.

## A cut reply is not the whole answer

A slice keeps to about 50 rows. When its last lines say rows or link kinds were left out, and a
kind named there bears on the question, ask again on the thing that matters: `periplus show NAME`,
or `periplus slice NAME --kind K`.

Never answer that nothing else touches a thing from a cut reply, or from a search that found
nothing. Say what you ran and what it left out.

## The loop

1. `periplus find WORDS`. Each row is an id, its type, its state and `file:line`. The source line
   at that place follows, marked `|`. A description follows when there is one, marked `#`.
2. `periplus show NAME` on the item you want. It prints every edge kind in and out, each row with
   its `file:line` and source line.
3. `periplus neighbors NAME` lists what the item sets off, and `periplus affected NAME` what
   sets it off, each by the cause the map declares for each edge kind. Add `--kind K` to keep one
   kind and `--depth N` or `--depth all` to go further. `periplus depth NAME` first says how far
   each walk goes. `--raw` follows every edge by its own direction instead.
4. `periplus path FROM TO` prints the shortest chain between two items.

NAME may be the full id or a short name: `helper`, `MyForm` or `MyForm::buildForm`. When a short
name fits several items, the command lists their ids and exits 31. Run it again with one of them.

How to run each command:

- Run it from the project root, the folder that holds `.periplus/`. Never `cd` elsewhere first. A
  folder reached through a link may sit outside the project, and then no map is found (exit 29).
- Read each map reply in full before you choose the next step.
- Keep the default limit. Never pass `--limit 0`. Never pipe map output through `head`, `tail`,
  `cut` or `grep`, and never run map commands in a loop. Those hide rows you need.
- When a `find` list is cut, it ends with `showing N of M`, a `by type:` count and
  `narrow with --type T or --path P`. Narrow with `--type` and `--path`; each may be repeated.
- Take type names from that `by type:` line, or from the warning a wrong `--type` prints. The part
  of an id before `::` is not always its type name.
- `periplus types` prints every type and every edge kind, and it has no filter. On a large map it
  is long. Run it only when you need a name you cannot get from `find` or `show`.
- Do not run `periplus map`. The map is already built. Rebuild it only when the user asks.

## Before you answer

For each main item of the answer, run `show` and read every edge kind it lists. Base classes,
interfaces, injected services, callers, created classes and template links all appear there.
Follow each kind that bears on the question with `neighbors` or `affected`.

Calls end at methods, not at the class. So run `show` on the methods that matter too, and on the
interface method a caller may use instead. When a chain changes kind, start again
from the new item with the new kind. For example, `affected` on a class with `--kind instantiates`
gives the methods that create it, and `affected` on each of those methods with `--kind calls` gives
their callers.

## When to read code

The source line under a row is often enough. Open the file at the given line when the answer
needs more than that line.

A search hit is a lead, not an answer. Leave out hits in docs, tests and comments that are not
part of the answer.

Each row carries a state:

- `mapped`: found in the project's files, with a location.
- `boundary`: outside the mapped files, and a rule identified what it is. An API node of this
  state lists, under `affected`, what in the project touches that API.
- `unknown_boundary`: the map could not make it known, a call built at run time or an end that
  leaves the mapped files with no rule identifying it. Read the code at the caller's line.
- `referenced` or `declared`: named by an edge, defined outside the mapped files, no rule marked it.
- `unresolved`: a rule looked for the target by name and found none. The edge and its source
  line are real; the target is not in the map.

A call site marked `resolution: runtime` picks its target at run time. The map does not guess it.
Say so, and read the code at that line.

## What the map lacks

Never write that the map lacks something unless a command has just shown it. Name the check in
the answer:

- `periplus find NAME` printed `no matches`; or
- `periplus show ID` printed edge kinds, and none of them is the link in question.

`0 things` from `--kind K` means the walk found no edge of that kind to follow that way. It does
not mean the map lacks the link: run `show` first to see which kinds the item has. What each stack does not map yet is in
the header of its rutter's `pack.yaml`. To record a gap, use the periplus-gaps skill.

## Recipes by question

- **What uses this?** `periplus show NAME`. Then `periplus affected NAME --kind K` for each kind
  `show` lists that bears on the question. For a class, do the same on each public method, and on the interface methods it
  implements.
- **Where is this defined?** `periplus find NAME --type T`. The row's `file:line` is the place.
- **What breaks if this changes?** `periplus affected NAME --depth 2`, narrowed with `--kind`. For a
  class, cover its subclasses, the methods that create it, and the definitions that name it. Then
  repeat on each subclass.
- **How does A reach B?** `periplus path A B`. On `no path`, try `periplus path B A`. Then step by
  hand: `periplus neighbors A --kind K`, one method at a time.
- **What makes up a feature?** `periplus slice "WORDS"` with the feature's names. Then
  `periplus find "" --path FOLDER --type T` for each type the feature holds, and `show` on each
  main item. Things in other folders point in, so follow them with `affected`.

## Worked example

Each command's options, output and exit codes are in [Navigation](https://github.com/camoa/periplus/blob/v0.8.0/docs/navigation.md). On the
project in the Navigation guide's worked example, with the descriptions file below in place, these
print:

<!-- nav-run -->
```console
$ periplus find shop --limit 2
periplus find

python.function::shop.cli.greet  python.function  mapped  shop/cli.py:8
      | def greet():
python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
      | def helper():
      # Returns the constant 1. It reads nothing and changes nothing.
showing 2 of 6
by type: python.function 2, python.module 2, typer.app 1, typer.command 1
narrow with --type T or --path P
$ periplus show helper
periplus show python.function::shop.tools.helper
type: python.function
state: mapped
location: shop/tools.py:1
provenance: python_text:function  declared
description: Returns the constant 1. It reads nothing and changes nothing. (shop/tools.py:1)

Outgoing (0):
  none

Incoming (2):
  calls:
    python.module::shop.cli  python.module  mapped  shop/cli.py:9  x1  inferred  python_text:call
      | helper()
      description: The hello command's greet function calls helper and discards the result. (shop/cli.py:9)
  contains:
    python.module::shop.tools  python.module  mapped  shop/tools.py:1  x1  declared  python_text:function_contained
      | def helper():
warning: resolved 'helper' to python.function::shop.tools.helper
$ periplus slice "returns constant" --depth 1
periplus slice
no node matches 'returns constant' as a whole; started from its words
start helper  python.function  (words: 'returns' in description, 'constant' in description)
paths under: shop/

piece 1 of 1: 3 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
      # Returns the constant 1. It reads nothing and changes nothing.
      calls <- cli
  :1  tools  python.module
      | def helper():
      contains -> helper
      imports <- cli

cli.py
  :1  cli  python.module
      | import typer
      calls -> helper
      imports -> tools
      +3 more links: calls -> 1, contains -> 1, imports -> 1; see periplus slice cli

inventory: 3 nodes
  python.function 1: helper
  python.module 2: cli, tools
go deeper with --depth 2
```

The slice words matched the helper's description, not its name.

## Read and write the descriptions file

The map holds ids, types and locations, not what a thing does. That text lives in
`.periplus/descriptions.yaml`, beside the map and never inside it. The engine neither reads nor
writes the file, so the map stays byte-identical from run to run. Commit it with the map.

`periplus show` prints a node's entry, or `description: none` when it has none, and an edge's
entry under its row. The rows of `find` and `path`, and of `neighbors` and `affected` with
`--raw`, print the first line of each node's entry, marked `#`. `find` also searches the entries' text, and marks a row it
matched there `[description]`.

When you read the code of a node or an edge that has no entry, write its entry before you answer,
unless the user asked you to change no file. A reading that leaves no entry leaves no record, so
the next question reads the code again.

The file has two top-level keys:

- `nodes` maps a node id to an entry.
- `edges` is a list of entries. An edge has no id in the map, so each entry carries `from`,
  `kind` and `to` exactly as the map writes them.

Every entry carries `text`, one or more sentences on what the thing actually does, and `file` and
`line`, where you read it. When the code at that file and line no longer matches the text, read
the code again and rewrite the entry. The shape is in references/descriptions.schema.json.

<!-- example descriptions: .periplus/descriptions.yaml -->
```yaml
nodes:
  python.function::shop.tools.helper:
    text: Returns the constant 1. It reads nothing and changes nothing.
    file: shop/tools.py
    line: 1
edges:
  - from: python.module::shop.cli
    kind: calls
    to: python.function::shop.tools.helper
    text: The hello command's greet function calls helper and discards the result.
    file: shop/cli.py
    line: 9
```
