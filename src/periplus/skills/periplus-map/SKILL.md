---
name: periplus-map
description: Navigates a Periplus map by the question being asked, and records what a node or edge does in the descriptions file beside the map. Use when the user asks what calls this, what a change would affect, how two things connect, where something is defined, or what a node does, and when a project has a .periplus/map.json to read.
---

# Navigate a Periplus map

## Standing rules

1. Rules are small and add to each other: one rule solves one case, and several cases are several rules. Split by rule file inside one rutter, never by adding rutters; a new rutter repeats the file types and folders the covering one already holds, and a small rule can be read, tested and removed alone.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map. Each pass reads what the one before it found, so no rule has to look a thing up itself.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter. The engine then stays the same for every stack, and a third-party rutter can do all a built-in one does.
4. Write the rule and run it: probe before saying a rutter cannot, and quote the engine's message. A guess about the format's limits has been wrong before; the message is the evidence.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose. The name leaks the project and ties the rule to one site.

## Pick the command by the question

Run `periplus map` first. Then pick the one command that answers the question.

Read `periplus types` before you choose: a relation the question asks about often has an edge kind
of its own. Narrow to it with `--kind` on `periplus neighbors`, and to a node type with `--type`
on `periplus find`.

| Question | Command |
|---|---|
| What is one thing, and what are its neighbours? | `periplus show ID`, then `periplus neighbors ID` |
| What would a change to this thing affect? | `periplus affected ID` |
| What is the path between two things? | `periplus path FROM TO` |
| Which ids match a name? | `periplus find TEXT` |
| Which kinds of node and edge does the map hold? | `periplus types` |

Each command's options, output and exit codes are in [Navigation](https://github.com/camoa/periplus/blob/v0.7.0/docs/navigation.md). Take an id from
`periplus find` before passing it to the other commands. On the project in the Navigation
guide's worked example, these run as shown:

<!-- nav-run -->
```console
$ periplus types
$ periplus find helper
$ periplus show python.function::shop.tools.helper
$ periplus neighbors python.module::shop.cli --kind imports
$ periplus affected python.function::shop.tools.helper
$ periplus path python.module::shop.cli python.function::shop.tools.helper
```

## Answer a question about a feature

A feature, such as how authentication works, spans many nodes, and no one id names it. Cut a slice
of it from the map, then read the slice:

1. Run `periplus find` several times: once for each name the feature goes by, and with `--type`
   for each type it may hold. One search misses every name it does not hold.
2. Run `periplus show` on each candidate. Keep the ones whose type, location and edges belong to
   the feature.
3. Run one `periplus slice` from every confirmed start: each confirmed id, and one `--path` for a
   folder or file prefix the feature lives in. Repeat `--path` for each prefix.
4. To widen the slice, or join it to the slice of another feature, run `periplus slice` again and
   name both sets of starts: every id and every `--path` prefix of each. Each call reads the full
   map and replaces the file it writes, so the second call must hold the first call's starts too.
   `--depth` widens it further.
5. Read the slice with the commands above, each given `--map` and the slice file. Then read the
   code at each location, and describe the feature from what the code does.

On the Navigation guide's worked example, these steps run as shown:

```console
$ periplus find tools
$ periplus find hello
$ periplus show python.function::shop.tools.helper
$ periplus show typer.command::shop.cli.app:hello
$ periplus slice python.function::shop.tools.helper typer.command::shop.cli.app:hello --path shop/tools.py --out feature.map.json
$ periplus slice python.function::shop.tools.helper typer.command::shop.cli.app:hello --path shop/tools.py --depth 2 --out feature.map.json
$ periplus types --map feature.map.json
```

## Read and write the descriptions file

The map holds ids, types and locations, not what a thing does. That text lives in
`.periplus/descriptions.yaml`, beside the map and never inside it. The engine neither reads nor
writes the file, so the map stays byte-identical from run to run. Commit it with the map.

Open the descriptions file on every navigation, and read the entry of each id the command reached.

When you read the code of a node or an edge that has no entry, write its entry before you answer.
`periplus show` prints `description: none` for such a node, and no description line under such an
edge. A reading that leaves no entry leaves no record, so the next question reads the code again.

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
