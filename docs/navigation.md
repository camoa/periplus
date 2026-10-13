# Navigating the map

`periplus map` writes the map. Six commands read it and answer a question about it. Each one
loads the map, prints a report and stops. None of them reads the source, changes the map or
starts a server.

| Command | Question it answers |
|---|---|
| `periplus types` | Which node types and edge kinds does the map hold, and how many of each? |
| `periplus find TEXT` | Which node ids hold this text? |
| `periplus show ID` | What is this node, and which edges leave and arrive at it? |
| `periplus neighbors ID` | Which items do this item's edges lead to? |
| `periplus affected ID` | Which items have edges that lead to this item? |
| `periplus path FROM TO` | What is the shortest chain of edges from one item to another? |

A seventh command, `periplus check-map`, checks the whole map against the map schema. See
[Checking the map](#checking-the-map).

## What every command shares

- `--map PATH` names the map file. Without it, the command reads `.periplus/map.json` under the
  project root, found by walking up from the working directory.
- `--format text|json` picks the report (default `text`). The JSON report has sorted keys and is
  described by the shipped `navigation.schema.json`, which `periplus spec` also emits.
- `--limit N` caps the rows shown (`find`, `show`, `neighbors`, `affected`: default 50; `path`:
  default 10). `--limit 0` shows all. A cut list ends with `showing N of TOTAL` in text, and has
  `"truncated": true` in JSON.
- Output is the same on every run for the same map.

The commands report ids and nothing else. They do not print labels, they have no `between`
query, and they print no source spans: a location is a file and a line.

## Commands

### types

```
periplus types [--map PATH] [--format text|json]
```

Counts the node types, each with its parent type, and the edge kinds.

### find

```
periplus find TEXT [--type T] [--limit N] [--map PATH] [--format text|json]
```

Lists the nodes whose id holds `TEXT`, closest match first. Each row is the id, the type, the
state and the first location. `--type T` keeps type `T` and its subtypes. A type the map does not
hold prints a warning and no rows.

### show

```
periplus show ID [--limit N] [--map PATH] [--format text|json]
```

Prints the node's type, state, location and provenance, then its outgoing and incoming edges
grouped by kind. Each edge row names the other end, the first location, the occurrence count, the
confidence and the rule. `--limit` applies to each of the two edge lists. Take `ID` from `find`.

### neighbors

```
periplus neighbors ID [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
```

Follows the edges that leave `ID`. Each row gives the depth at which the item was first reached,
its id, type and state, and the edge it was reached by. `--depth N` (1 or more, default 1) sets
how many edges to follow. `--kind K` keeps only edges of kind `K`; repeat it for several kinds.

### affected

```
periplus affected ID [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
```

The same report as `neighbors`, following the edges that arrive at `ID`.

### path

```
periplus path FROM TO [--kind K] [--limit N] [--map PATH] [--format text|json]
```

Prints every shortest chain of edges from `FROM` to `TO`, following each edge in its own
direction. Without a chain it prints `no path`, and exits 0. `--kind K` follows only edges of kind
`K`; repeat it for several kinds.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The report printed. An empty result is still 0. |
| 2 | A bad option, such as `--depth 0`. |
| 29 | No map: no project above the working directory, or no file at the path. Run `periplus map`. |
| 30 | The file is not a map: not JSON, or missing the outline (`periplus_map_version`, `nodes`, `edges`). |
| 31 | An id names no node in the map. |

## Checking the map

The six commands check only the map's outline: a JSON object with a supported
`periplus_map_version` and lists `nodes` and `edges`. They do not check every node and edge, so
a map with a fault deeper in is still read. When you want the full check, run:

```
periplus check-map [--map PATH] [--format text|json]
```

It runs the full map schema check on the map the other commands would read. It exits 0 on a
valid map, 30 with the path and the first error on a failing one, and 29 with no map.

## A worked example

The shipped `examples/second-stack` holds three rutters and their settings. They need a project
to read. Make one in a new, empty folder, away from the Periplus checkout: copy the rutters and
settings into `.periplus/`, and add two Python files. Replace `/path/to/periplus` with the checkout.

```
mkdir -p .periplus shop
cp -r /path/to/periplus/examples/second-stack/packs /path/to/periplus/examples/second-stack/settings.yml .periplus/
```

<!-- nav-file: shop/tools.py -->
```python
def helper():
    return 1
```

<!-- nav-file: shop/cli.py -->
```python
import typer
from shop.tools import helper

app = typer.Typer()


@app.command("hello")
def greet():
    helper()
```

Then map it. `periplus map` writes `.periplus/map.json` by default, which is where the commands
look. Each block below is run by `scripts/demo.d/99zb-navigation.sh` and its output compared with
what is shown, so it cannot drift. Text after the output, as `(exit N)`, is the exit code.

Count what the map holds:

<!-- nav-run -->
```console
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

Find the helper, then everything under `shop` that is a function:

<!-- nav-run -->
```console
$ periplus find helper
periplus find

python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
```

<!-- nav-run -->
```console
$ periplus find shop --type python.function --limit 1
periplus find

python.function::shop.cli.greet  python.function  mapped  shop/cli.py:8
showing 1 of 2
```

Show the helper and its edges:

<!-- nav-run -->
```console
$ periplus show python.function::shop.tools.helper
periplus show python.function::shop.tools.helper
type: python.function
state: mapped
location: shop/tools.py:1
provenance: python_text:function  declared

Outgoing (0):
  none

Incoming (2):
  calls:
    python.module::shop.cli  python.module  mapped  shop/cli.py:9  x1  inferred  python_text:call
  contains:
    python.module::shop.tools  python.module  mapped  shop/tools.py:1  x1  declared  python_text:function_contained
```

See what the `shop.cli` module imports:

<!-- nav-run -->
```console
$ periplus neighbors python.module::shop.cli --kind imports
periplus neighbors python.module::shop.cli
2 items
  1  python.module::shop.tools  python.module  mapped  via imports from python.module::shop.cli
  1  python.module::typer  python.module  referenced  via imports from python.module::shop.cli
```

See what leads to the helper:

<!-- nav-run -->
```console
$ periplus affected python.function::shop.tools.helper
periplus affected python.function::shop.tools.helper
2 items
  1  python.module::shop.cli  python.module  mapped  via calls from python.function::shop.tools.helper
  1  python.module::shop.tools  python.module  mapped  via contains from python.function::shop.tools.helper
```

Find the chain from the module to the helper. Edges are followed in their own direction, so the
reverse query finds none:

<!-- nav-run -->
```console
$ periplus path python.module::shop.cli python.function::shop.tools.helper
periplus path python.module::shop.cli python.function::shop.tools.helper
1 shortest chains
  chain 1:
    python.module::shop.cli --calls--> python.function::shop.tools.helper
```

<!-- nav-run -->
```console
$ periplus path python.function::shop.tools.helper python.module::shop.cli
periplus path python.function::shop.tools.helper python.module::shop.cli
no path
```

An id that is not in the map exits 31:

<!-- nav-run -->
```console
$ periplus show nope
periplus show
31 no node has the id 'nope'; periplus find searches the ids
(exit 31)
```

Last, check the whole map. The path printed is the project's:

<!-- nav-run -->
```console
$ periplus check-map
/path/to/project/.periplus/map.json matches the map schema
```
