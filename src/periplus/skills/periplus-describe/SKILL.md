---
name: periplus-describe
description: Writes what each node and edge of a Periplus slice does into .periplus/descriptions.yaml, after reading the code at its file and line. Use when the user says describe this feature, document these nodes, explain what this part of the map does, or fill the descriptions before a change, and when a slice file made with periplus slice is the working set.
---

# Describe the items of a slice

## Standing rules

1. Rules are small and add to each other: one rule solves one case, and several cases are several rules. Split by rule file inside one rutter, never by adding rutters; a new rutter repeats the file types and folders the covering one already holds, and a small rule can be read, tested and removed alone.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map. Each pass reads what the one before it found, so no rule has to look a thing up itself.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter. The engine then stays the same for every stack, and a third-party rutter can do all a built-in one does.
4. Write the rule and run it: probe before saying a rutter cannot, and quote the engine's message. A guess about the format's limits has been wrong before; the message is the evidence.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose. The name leaks the project and ties the rule to one site.

## Where the detail lives

- [The map skill, under its heading Read and write the descriptions file](https://github.com/camoa/periplus/blob/v0.5.2/src/periplus/skills/periplus-map/SKILL.md#read-and-write-the-descriptions-file), holds the file's two keys, the rest of the entry rules and the worked example of the file.
- [The descriptions schema](https://github.com/camoa/periplus/blob/v0.5.2/src/periplus/skills/periplus-map/references/descriptions.schema.json) holds the exact shape of the file.
- [Navigation](https://github.com/camoa/periplus/blob/v0.5.2/docs/navigation.md) holds the signature, output rows and exit codes of `periplus slice`.

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
5. Keep every entry already in the file. Leave it alone unless the person asks for a rewrite. When an existing entry looks stale against the code, report it and do not change it. The map skill's rule to rewrite a stale entry does not apply here.
6. When the code at a location no longer matches the item, the map is stale. Write nothing more, and tell the person to run `periplus map` and cut the slice again. Never edit the map or the slice.
7. Write only `.periplus/descriptions.yaml` yourself. The slice file is the one other file this work makes, and `periplus slice` writes it, not you.
