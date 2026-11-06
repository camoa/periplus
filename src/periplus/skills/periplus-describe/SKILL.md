---
name: periplus-describe
description: Writes descriptions for a Periplus slice, the smaller map cut with periplus slice, into the descriptions file beside the map. Use when the user asks to describe, document or explain the items of a slice or a feature of the map, to fill the descriptions file before a change, or mentions descriptions.yaml.
---

# Describe the items of a slice

## Standing rules

1. Rules are small and add to each other: split by rule file inside one rutter, never by adding rutters.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter.
4. Write the rule and run it: probe before saying a rutter cannot, and quote the engine's message.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose.

## Where the detail lives

- The map skill, under its heading Read and write the descriptions file, holds the file's two keys and the rest of the entry rules.
- [The descriptions schema](https://github.com/camoa/periplus/blob/v0.4.2/src/periplus/skills/periplus-map/references/descriptions.schema.json) holds the exact shape of the file.
- [Navigation](https://github.com/camoa/periplus/blob/v0.4.2/docs/navigation.md) holds the signature, output rows and exit codes of `periplus slice`.

## Describe a slice

The working set is a slice file: a map-shaped JSON file with a `nodes` list and an `edges` list.
Cut one with `periplus slice` after `periplus map`, with `--out` naming a file relative to the project root:

<!-- nav-run -->
```console
$ periplus slice python.function::shop.tools.helper --depth 1 --out helper.map.json
```

Work through the slice item by item, in the project root.

1. Read the slice file. Every node and edge carries a `locations` list of `file` and `line`.
2. Report each item whose `locations` list is empty, such as an unresolved name, to the person, and write no entry for it: an entry needs a file and a line. An edge has its own location even when its target has none.
3. For each item with a location, open the code at that file and line and read it. An item with several locations takes one entry, at the location you read.
4. Write one entry per located item in `.periplus/descriptions.yaml`. Every entry carries `text`, one or more sentences on what the code does, and the `file` and `line` you read. A node is keyed by its id under `nodes`. An edge entry in `edges` carries `from`, `kind` and `to` exactly as the slice writes them.
5. Keep every entry already in the file. Leave it alone unless the person asks for a rewrite. When an existing entry looks stale against the code, report it and do not change it.
6. When the code at a location no longer matches the item, the map is stale. Write nothing more, and tell the person to run `periplus map` and cut the slice again. Never edit the map or the slice.
7. Write only `.periplus/descriptions.yaml`; no other file.

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
