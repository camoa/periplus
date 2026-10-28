---
name: periplus-map
description: Navigate a Periplus map by the question being asked, and record what a node or edge does in the descriptions file beside the map.
---

# Navigate a Periplus map

## Standing rules

1. A rutter grows by small rules that add to each other: split by rule file inside one rutter, never by adding rutters.
2. A rutter reads the code in passes by depth: structure first, then one layer inside each class, then joins in the map.
3. There is no stack knowledge in the engine; what a stack means lives in its rutter.
4. Run a rule and read the engine's message: probe before saying a rutter cannot.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose.

## Pick the command by the question

Run `periplus map` first. Then pick the one command that answers the question.

| Question | Command |
|---|---|
| What is one thing, and what are its neighbours? | `periplus show ID`, then `periplus neighbors ID` |
| What would a change to this thing affect? | `periplus affected ID` |
| What is the path between two things? | `periplus path FROM TO` |
| Which ids match a name? | `periplus find TEXT` |
| Which kinds of node and edge does the map hold? | `periplus types` |

Each command's options, output and exit codes are in [Navigation](https://github.com/camoa/periplus/blob/v0.3.0/docs/navigation.md). Take an id from
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

## Read and write the descriptions file

The map holds ids, types and locations, not what a thing does. That text lives in
`.periplus/descriptions.yaml`, beside the map and never inside it. The engine neither reads nor
writes the file, so the map stays byte-identical from run to run. Commit it with the map.

Open the descriptions file on every navigation, and read the entry of each id the command reached.

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
