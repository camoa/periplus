---
name: periplus-describe
description: Writes what the main items of a Periplus slice do into .periplus/descriptions.yaml, after reading the code at each item's file and line, so periplus find reaches them by plain words. Use when the user says describe this feature, this folder or this project, document these nodes, explain what this part of the map does, or fill the descriptions before a change, and when a slice file made with periplus slice is the working set.
---

# Describe the items of a slice

## Where the detail lives

- [The map skill, under its heading Read and write the descriptions file](https://github.com/camoa/periplus/blob/v0.8.0/src/periplus/skills/periplus-map/SKILL.md#read-and-write-the-descriptions-file), holds the file's two keys, the entry fields and a worked example of the file.
- [The descriptions schema](https://github.com/camoa/periplus/blob/v0.8.0/src/periplus/skills/periplus-map/references/descriptions.schema.json) holds the exact shape of the file.
- [Navigation](https://github.com/camoa/periplus/blob/v0.8.0/docs/navigation.md) holds the signature, output rows and exit codes of `periplus slice`.

## Tools for the work

- `periplus undescribed` counts the main things with no entry, by file; `--ids` lists them.
- `periplus in FILE` lists what the map holds in a file, in line order.
- `periplus at FILE:12` names the mapped thing at line 12, or nearest above, and what holds it.
- `periplus files ID...` counts a set by file, most first.
- `periplus order ID...` puts a set in order, each thing after what it calls or uses.
- `periplus stamp` writes a fingerprint of its code into each entry; `periplus stale` lists the
  entries whose code changed since, and those whose node is gone.

## Why an entry matters

`periplus find` searches entry text as well as ids. `find` and `path`, and `neighbors` and
`affected` with `--raw`, print the first line of a node's entry under its row. So an entry is how a plain-word question,
such as who sends the reminder email, reaches a node whose id lacks those words.

An entry that restates the id or the source line adds nothing, and it turns up as noise in every
search. A few dozen good entries for a module beat hundreds of empty ones.

## Cut the slice for one folder

Work one folder per pass, from the project root, after `periplus map`:

<!-- nav-run -->
```console
$ periplus slice --path shop/ --out shop.map.json
```

The slice holds the folder's items and the items one edge away. When it exits 32, the slice is over
its item limit: pass a smaller folder, or `--limit 0`. Then count what it holds:

<!-- nav-run -->
```console
$ periplus types --map shop.map.json
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

Decide per type, with the rule below, before you read any code.

## Which items get an entry

Describe an item when a person could ask for it by name or by what it does. Examples, from no one
stack: a class, a function, a method, a service, a route, a template, a command, a config item, a
module.

Skip these:

- **Pieces of another item**: a parameter, a call site, an assignment, a type mention. Read them
  as part of the item that holds them. A fact about a piece, such as an argument never used, goes
  in that item's entry.
- **Items with no location**, such as an unresolved name. Nothing can be read for them.
- **Items located outside the folder.** The slice pulls in neighbours from elsewhere; they wait
  for their own folder's pass.

Apply the rule to the type names the map has. When a type is unclear, open two of its items and
decide from what you read.

**Edges.** Most edges need no entry: the kind and the two ends already say it. Write one only
when the link itself needs explaining: why it exists, a condition on it, or a surprise.

## What the text says

One to three sentences.

1. What the item does, in the words a person would search for: the feature, the business term,
   the effect a user sees.
2. Then, when present: the contract (inputs, outputs, errors returned, who may call it), and
   anything surprising (an unused argument, a missing check, two things with one name).

Never restate the id, the type or the source line. Never write an entry from the name alone, and
never generate entries by script. Each entry comes from reading the code at its location: the
whole body of the function or class, not only its first line.

Good:

```yaml
text: Saves a customer's chosen newsletters. Returns 403 on a bad form token and 400 when the
  customer has no account number; on any later failure it returns 500 with the error list.
```

```yaml
text: Looks up a member's main email address. The query has no filter on the address type,
  although the name and comment say it returns the main one.
```

Bad:

```yaml
text: Parameter $config of create; signature line `public static function create(...)`.
```

```yaml
text: The OrderController class.
```

## Write the entries

1. Read `.periplus/descriptions.yaml` first, if it exists. An item with an entry is done: keep the
   entry as it is. When it looks stale against the code, report it and do not change it. The map
   skill's rule to rewrite a stale entry does not apply here.
2. For each item to describe, open its file at its line and read the code.
3. **A line that does not fit.** The line may be past the end of the file. It may hold nothing
   related to the item, as when a location comes from a file name. Write no entry for that item,
   note it for the report, and carry on. Stop only when several items in one file miss their
   lines. Then the map is stale: tell the person to run `periplus map` and cut the slice again.
4. **Several locations.** Read each. When they do different things, say so in the one entry. Set
   `file` and `line` to the first location.
5. Add each entry. Nodes go under `nodes`, keyed by id. Edges go under `edges`, with `from`,
   `kind` and `to` exactly as the slice writes them. Every entry carries `text`, `file` and `line`.
6. Keep the file in a stable order: `nodes` sorted by id, `edges` sorted by `from`, `kind`, `to`.
   A new pass then adds lines without moving old ones.

Write only `.periplus/descriptions.yaml`. Never edit the map or the slice; `periplus slice` writes
the slice.

## A whole project

Run one pass per folder, cutting a fresh slice each time. All passes append to the one
descriptions file. Step 1 above keeps every entry an earlier pass wrote.

## Report to the person

At the end, give:

- Entries written, counted by type and by edge kind.
- Types and edge kinds skipped, with the reason.
- Items with no location, and items whose line did not fit.
- Existing entries that look stale.
- Anything surprising found in the code: a missing check, an unused argument, two things with one
  name.
