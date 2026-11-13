---
name: periplus-map
description: Answers code questions from a Periplus map by following its edges, and records what a node or edge does in the descriptions file beside the map. Use when a project has a .periplus/map.json and the user asks what calls or uses this, who uses this service, what breaks if this changes, where something is defined, how A reaches B, which subscribers listen to an event, what makes up a feature, or which files take part in a feature. Use it before grep.
---

# Navigate a Periplus map

## The loop

1. `periplus find WORDS`. Each row is an id, its type, its state and `file:line`. The source line
   at that place follows, marked `|`. A description follows when there is one, marked `#`.
2. `periplus show NAME` on the item you want. It prints every edge kind in and out, each row with
   its `file:line` and source line.
3. `periplus neighbors NAME --kind K` follows edges out. `periplus affected NAME --kind K`
   follows edges in. Add `--depth N` to go further.
4. `periplus path FROM TO` prints the shortest chain between two items.

NAME may be the full id or a short name: `helper`, `MyForm` or `MyForm::buildForm`. When a short
name fits several items, the command lists their ids and exits 31. Run it again with one of them.

How to run each command:

- Run it from the project root, the folder that holds `.periplus/`. Never `cd` elsewhere first. A
  folder reached through a link may sit outside the project, and then no map is found (exit 29).
- Run one map command per step. Read its output before you choose the next one. Never send a file
  search in the same step as a map command.
- Keep the default limit. Never pass `--limit 0`. Never pipe map output through `head`, `tail`,
  `cut` or `grep`, and never run map commands in a loop. Those hide rows you need.
- When a list is cut, it ends with `showing N of M`, a `by type:` count and
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

The source line under a row is often enough. Open the file at the given line only when the answer
needs more than that line.

Search files only for what the map cannot hold, and only after a map command has shown it absent.
Search for that one thing. Do not add every file that holds the question's words: those hits bring
in docs, tests and comments that are not part of the answer.

Each row carries a state:

- `mapped`: found in the project's files, with a location.
- `referenced` or `declared`: named by an edge, defined outside the mapped files.
- `unresolved`: a rule looked for the target by name and found none. The edge and its source
  line are real; the target is not in the map.

A call site marked `resolution: runtime` picks its target at run time. The map does not guess it.
Say so, and read the code at that line.

## What the map lacks

Never write that the map lacks something unless a command has just shown it. Name the check in
the answer:

- `periplus find NAME` printed `no matches`; or
- `periplus show ID` printed edge kinds, and none of them is the link in question.

`0 items` from `--kind K` means the item has no edge of that kind. It does not mean the map lacks
the link: run `show` first to see which kinds the item has. What each stack does not map yet is in
[Known limitations](https://github.com/camoa/periplus/blob/v0.8.0/docs/known-limitations.md). To
record a gap, use the periplus-gaps skill.

## Recipes by question

- **What uses this?** `periplus show NAME`. Then `periplus affected NAME --kind K` for each kind
  under Incoming. For a class, do the same on each public method, and on the interface methods it
  implements.
- **Where is this defined?** `periplus find NAME --type T`. The row's `file:line` is the place.
- **What breaks if this changes?** `periplus affected NAME --depth 2`, narrowed with `--kind`. For a
  class, cover its subclasses, the methods that create it, and the definitions that name it. Then
  repeat on each subclass.
- **How does A reach B?** `periplus path A B`. On `no path`, try `periplus path B A`. Then step by
  hand: `periplus neighbors A --kind K`, one method at a time.
- **What makes up a feature?** `periplus find "" --path FOLDER --type T` for each type the feature
  holds. Run `show` on each main item. Things in other folders point in, so follow the incoming
  kinds with `affected`: links, includes, placements and callers.

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
$ periplus neighbors cli --kind calls
periplus neighbors python.module::shop.cli
2 items
  1  python.function::shop.tools.helper  python.function  mapped  via calls from python.module::shop.cli  shop/cli.py:9
      | helper()
      # Returns the constant 1. It reads nothing and changes nothing.
  1  python.function::typer.Typer  python.function  unresolved  via calls from python.module::shop.cli  shop/cli.py:4
      | app = typer.Typer()
warning: resolved 'cli' to python.module::shop.cli
$ periplus affected helper --depth 2
periplus affected python.function::shop.tools.helper
2 items
  1  python.module::shop.cli  python.module  mapped  via calls to python.function::shop.tools.helper  shop/cli.py:9
      | helper()
  1  python.module::shop.tools  python.module  mapped  via contains to python.function::shop.tools.helper  shop/tools.py:1
      | def helper():
warning: resolved 'helper' to python.function::shop.tools.helper
$ periplus path cli helper
periplus path python.module::shop.cli python.function::shop.tools.helper
1 shortest chains
  chain 1:
    python.module::shop.cli --calls--> python.function::shop.tools.helper  shop/cli.py:9
      | helper()
      # Returns the constant 1. It reads nothing and changes nothing.
warning: resolved 'cli' to python.module::shop.cli
warning: resolved 'helper' to python.function::shop.tools.helper
$ periplus types
periplus types

Node types:
  python.function  3  parent: none
  python.module  3  parent: none
  typer.app  1  parent: none
  typer.command  1  parent: none

Edge kinds:
  calls  2
  contains  2
  imports  2
  registered_on  1

Problems:
  none
```

A short name that fits two items lists both and exits 31:

```console
$ periplus show typer
periplus show
31 'typer' matches 2 nodes; give one of these ids
  python.function::typer.Typer  python.function  no location
  python.module::typer  python.module  no location
```

## Read and write the descriptions file

The map holds ids, types and locations, not what a thing does. That text lives in
`.periplus/descriptions.yaml`, beside the map and never inside it. The engine neither reads nor
writes the file, so the map stays byte-identical from run to run. Commit it with the map.

`periplus show` prints a node's entry, or `description: none` when it has none, and an edge's
entry under its row. The rows of `find`, `neighbors`, `affected` and `path` print the first line
of each node's entry, marked `#`. `find` also searches the entries' text, and marks a row it
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
