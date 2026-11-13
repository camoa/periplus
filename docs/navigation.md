# Navigating the map

`periplus map` writes the map. Nine commands read it. Six answer a question about it. `slice` prints the
piece of the map around some words or items, or cuts it into a map file of its own; `export` prints the map in
another format. Each one loads the map, prints its output and stops. None of them changes the map or
starts a server. The question commands read a source file only to print one line of it under a row.

| Command | Question it answers |
|---|---|
| `periplus types` | Which node types and edge kinds does the map hold, and how many of each? |
| `periplus find TEXT` | Which nodes hold this text in their id, attributes or description? |
| `periplus show ID` | What is this node, and which edges leave and arrive at it? |
| `periplus neighbors ID` | Which items do this item's edges lead to? |
| `periplus affected ID` | Which items have edges that lead to this item? |
| `periplus path FROM TO` | What is the shortest chain of edges from one item to another? |
| `periplus slice WORDS` | What lies around the nodes these words or ids name, hop by hop? With `--out FILE`, write that piece to a map file of its own. |
| `periplus export --format F` | Print the map as GraphML, DOT or Mermaid. |

A ninth command, `periplus check-map`, checks the whole map against the map schema. See
[Checking the map](#checking-the-map).

## What every command shares

- `--map PATH` names the map file. Without it, the command reads `.periplus/map.json` under the
  project root, found by walking up from the working directory.
- The six question commands and `slice` take `--format text|json` to pick the report (default
  `text`). The JSON report has sorted keys and is described by the shipped
  `navigation.schema.json`, which `periplus spec` also emits. `export` prints the graph itself and
  takes `--report text|json` for the warnings and problems it writes to standard error.
- An `ID` argument (`show`, `neighbors`, `affected`, `path`, and each argument of `slice`) is a node id or a short name: the
  id's name after its first `::`, or a tail of that name that starts after a character other than
  a letter, digit or underscore, compared without case. So `helper` and `tools.helper` both name
  `python.function::shop.tools.helper`. A short name that fits one node is used, with the warning
  `resolved 'helper' to python.function::shop.tools.helper`. One that fits several nodes exits 31
  and lists up to 20 of them, each with its type and location. In JSON the problem's `detail` holds
  `id` (the text given), `total` (how many nodes fit) and `candidates`, up to 20 objects with `id`,
  `type` and `location` (`null` when the node has none). One that fits none exits 31 with
  `hint: run periplus find TEXT`. Printed `slice` searches such an argument as words instead.
- `--limit N` caps the rows shown (`find`, `show`, `neighbors`, `affected`: default 50; `path`:
  default 10). `--limit 0` shows all. A cut list ends with `showing N of TOTAL` in text, and has
  `"truncated": true` in JSON. A cut `find` list adds two lines: `by type:` with the match count of
  each type, and `narrow with --type T or --path P`. Printed `slice` shows 50 rows by default. For `slice --out`,
  the limit (default 500) is the most items the slice may hold. Over it, the command writes nothing and exits 32.
- Output is the same on every run for the same map.

The six question commands report ids, locations and source lines. A row of `find`, `neighbors`,
`affected` or `path`, and an edge row of `show`, carries a location as `file:line`: where the edge
is written, else the node's first location. Under the row, marked `|`, comes the source line at
that place, stripped and cut to 160 characters. It is left out when the file or the line cannot be
read, as when the map is older than the tree, or when the file is not a regular file, lies outside
the project, or is over 5 MB. Files are read under the project root above the map
file, or beside the map file when no project is found. A row of `find`, `neighbors`, `affected` or `path` then prints the first line of its node's
entry in `.periplus/descriptions.yaml`, marked `#`, when it has one. The first line of each text
report names its command, also when the command stops before its answer. The commands have no
`between` query. `export` labels each node with its id (DOT and Mermaid add its type); GraphML labels it with the short name instead.

A slice is a smaller map, told apart from the full map by its file name. `slice` and `export`
read it with `--map`, like any other map. Do not give `--out` the path of the map you read: the
slice would replace it.

## Commands

### types

```
periplus types [--map PATH] [--format text|json]
```

Counts the node types, each with its parent type, and the edge kinds.

### find

```
periplus find TEXT [--type T]... [--path P]... [--limit N] [--map PATH] [--format text|json]
```

Lists the nodes whose id holds `TEXT`, closest match first, then the nodes whose string attribute
values hold it, then the nodes whose description alone holds it. Matching ignores case. A string
item of a list attribute counts; numbers, booleans and nested objects do not. Each row is the id,
the type, the state and the first location, then the source line and the description. A row matched
by its description ends with `[description]`. A row matched by an attribute ends with
`[attribute NAME]`, the first matching name in sorted order, and prints `@ NAME: value` under the
source line. `--type T` keeps type
`T` and its subtypes. `--path P` keeps the nodes with a file that starts with `P`. Repeat either to
keep several types or paths. Given both, a node must fit a type and a path. A type the map does not hold prints a warning,
with up to five node types it may mean (`did you mean: ...`). A `--path` that no file in the map
starts with prints a warning.

The JSON report adds `by_type`, every match counted by type, also when the list is cut. Each item
has `location`, `source`, `matched` (`id`, `attribute` or `description`), `matched_attribute` (the
attribute's name, or null) and `description`.

### show

```
periplus show ID [--limit N] [--map PATH] [--format text|json]
```

Prints the node's type, state, location and provenance, then its outgoing and incoming edges
grouped by kind. Each edge row names the other end, the first location, the occurrence count, the
confidence and the rule, with the source line under it. `--limit` applies to each of the two edge
lists. Take `ID` from `find`. In JSON each edge row adds `location` and `source`, and the report
adds `warnings`.

`show` also reads the project's `.periplus/descriptions.yaml`, when it exists. It finds the project
by walking up from the folder of the `--map` file, or of the default map when no `--map` is given.
When no project is found, it reads the `descriptions.yaml` beside the map file. It prints the node's
entry as `description: <text> (<file>:<line>)`, or `description: none` when the node has none. An
edge with an entry gets the same line, indented, under its row. JSON puts the entry, or `null`, in
a `description` key. A descriptions file that is not YAML, or not the shape the `periplus-map`
skill's `descriptions.schema.json` states, is a problem with exit 30, and `show` still prints the
node and its edges.

### neighbors

```
periplus neighbors ID [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
```

Follows the edges that leave `ID`. Each row gives the depth at which the item was first reached,
its id, type and state, the edge it was reached by and that edge's location, with the source line
and description under it. `--depth N` (1 or more, default 1) sets how many edges to follow.
`--kind K` keeps only edges of kind `K`; repeat it for several kinds. In JSON each row adds
`location`, `source` and `description`.

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
direction. Each step names its edge's location, with the source line and the description of the
node it reaches under it; in JSON a step adds `location`, `source` and `description`. Without a
chain it prints `no path`, and exits 0. `--kind K` follows only edges of kind `K`; repeat it for
several kinds.

### slice

```
periplus slice [WORDS ...] [--path PREFIX]... [--type T]... [--starts N] [--direction out|in|both] [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
periplus slice [ID ...] [--path PREFIX]... --out FILE [--direction out|in|both] [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
```

Without `--out`, `slice` prints the piece of the map around some start nodes, in one call. An
argument that names a node, by id or short name, starts there. Any other text is searched the
way `find` searches: as a whole, and word by word. A word is a run of letters, digits and
underscores, at least 3 long, so `sign-up` searches `sign`. When several words are given, one
that names a node is searched as a word too. Each word weighs the natural log of the map's
node count over the number of nodes it matches, rounded to 6 places, so a rare word outweighs a
common one. A start's score is the sum of the weights of the words it holds in its own name,
an attribute or its description; a word found only in the id's type, or in the part before the
id's last `::` that names its owner, adds nothing. A start of
lower score never comes before one of higher score. Among starts of equal score, rarer types
come first, counted over the whole map, and at most two of a type, counted over all the starts,
come before the rest of that score. Inside a type, a mapped node comes first, then the node that
nodes in more other files have edges into, then the one whose id the words cover most, then
`find`'s order. `--starts N` sets how many starts the words pick in all (default 8). `--type T`
and `--path P` keep only the starts the words find of type `T` or under `P`, as they narrow
`find`.
Without words, `--path PREFIX` starts from every node whose first file starts with `PREFIX`.
When the whole text matches nothing and its words do, the piece says so on its second line.
Words that match nothing print `no matches`, and exit 0.

The output lists each start first, with why it was picked (`given as 'helper'`, or each word and
where it matched), as a `find` row. Then, under `around START`, it prints the rows reached from
each start, breadth-first. Each row sits under the node it was reached from, indented one step
per hop, and names the hop, the edge kind and its direction: `--calls-->` when the node above
has the edge, `<--calls--` when the row's node has it. Then come the node's id, type, state and
`file:line`, with the source line and the description under it. When the file is the one the
node above was printed with, the row shows only `:line`; JSON keeps the full location. A node reached by a second
route prints once in full and then as `(again)`. A source line with fewer than two letters,
digits or underscores, such as `{#`, is not printed.

A node whose edges, two or more, all join it to the node above is a satellite of that node. It
gets no row and costs no hop. The piece ends with how many were folded, by type.

`--depth N` sets how many edges to follow (default 2). `--direction` defaults to `both`, since a
chain often goes up one kind and down another. `--limit N` caps the rows (default 50, `0` for
all). The cap keeps full rows before back-references. Among them it keeps first the nodes more
starts reach, then those reached from the starts of more words, then those whose own id,
attributes or description more of the words match, then rarer types, then nodes more other
files have edges into, then the nearer hop, then by id. It first gives each start an even share
of the cap, then fills the rest with the best rows left. A kept row brings the rows above it. A cut piece ends with what it left out, counted by hop and by edge
kind, and the flags that narrow it (`--kind`, `--direction`, `--depth`, and `--type`, `--path`
or `--starts` when words picked the starts). A piece that was not cut and has edges past its
last hop ends with `go deeper with --depth N`. `--format json` prints the same piece: `starts`,
`rows` (each with `start`, `hop`, `from`, `kind`, `direction`, `again`, `location`, `source` and
`description`), `left_out`, `deeper`, `folded`, `notes`, `depth` and `direction`.

With `--out FILE`, `slice` writes the items around the start items to a map file of their own
instead, and takes ids, not words. Name the start items as `ID`s, with `--path PREFIX` (every
node whose first file starts with `PREFIX`), or both; one of the two is required. Repeat
`--path` for several prefixes; each one must match a node. `--out` exits 27 when it is the map
being read, and `--type` or `--starts` with it exits 2. `--depth N` defaults to 1 here. `--limit
N` is the most items the slice may hold (default 500, `0` for no limit). It prints `wrote FILE: N
nodes, M edges`. `--format json` prints one JSON document to standard output instead: `out` (the
file written, or null), `nodes`, `edges`, `warnings` and `problems`. Problems stay in that
document, with the report.

A kind is the type of an edge: it says how two items relate. A slice that follows edges either
way widens through a hub, an item many others share, such as a service every feature uses or a
permission many routes require, and can reach far more than the feature. `--kind` keeps the
slice to the edges of the feature.

```
periplus slice ID --depth 2 --out foo.map.json
```

### export

```
periplus export --format graphml|dot|mermaid [--map PATH] [--report text|json]
```

Prints the map in another format to standard output. In GraphML the node id is a generated
token (`n0`, `n1`), the node's `label` is its short name (the id without its type prefix and
without namespaces) and the map id is in the node's `id` data; each edge's `label` is its kind.
`--format` is required. Warnings go to standard error: Mermaid warns above 500 edges or 50,000
characters. `--report json` writes them to standard error as one JSON document instead: `format`,
`warnings` and `problems`.

```
periplus export --format dot --map foo.map.json > foo.dot
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The report printed. An empty result is still 0. |
| 2 | A bad option, such as `--depth 0`, or `slice --out` with `--type` or `--starts`. |
| 17 | The slice does not pass the map schema, because the map it was cut from does not. Run `periplus check-map` on that map. |
| 27 | `slice --out` names the map being read, or the file cannot be written. |
| 29 | No map to read: no project above the working directory, a missing file at the path, or an unreadable file. Run `periplus map`, or fix the file's permissions. |
| 30 | The file is not a map: not JSON, missing the outline (`periplus_map_version`, `nodes`, `edges`), or damaged below the outline, a node or edge row malformed. Also a descriptions file `show` reads that is not YAML or does not match the descriptions schema. |
| 31 | An id names no node in the map, or a short name fits more than one node. |
| 32 | The slice reaches more items than `--limit` allows. |

## Checking the map

The commands check the map only as far as they need to answer. They first check the outline:
a JSON object whose `periplus_map_version` is a non-negative integer and whose `nodes` and `edges`
are lists. A map damaged below the outline may stop a command with exit 30 and a message that
points to `periplus check-map`, or a wrong-typed value may print as it is. Only
`periplus check-map` checks the whole map. To run it:

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
look. Text after the output, as `(exit N)`, is the exit code.

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
      | def helper():
```

<!-- nav-run -->
```console
$ periplus find shop --type python.function --limit 1
periplus find

python.function::shop.cli.greet  python.function  mapped  shop/cli.py:8
      | def greet():
showing 1 of 2
by type: python.function 2
narrow with --type T or --path P
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
description: none

Outgoing (0):
  none

Incoming (2):
  calls:
    python.module::shop.cli  python.module  mapped  shop/cli.py:9  x1  inferred  python_text:call
      | helper()
  contains:
    python.module::shop.tools  python.module  mapped  shop/tools.py:1  x1  declared  python_text:function_contained
      | def helper():
```

See what the `shop.cli` module imports:

<!-- nav-run -->
```console
$ periplus neighbors python.module::shop.cli --kind imports
periplus neighbors python.module::shop.cli
2 items
  1  python.module::shop.tools  python.module  mapped  via imports from python.module::shop.cli  shop/cli.py:2
      | from shop.tools import helper
  1  python.module::typer  python.module  referenced  via imports from python.module::shop.cli  shop/cli.py:1
      | import typer
```

See what leads to the helper, named by its short name:

<!-- nav-run -->
```console
$ periplus affected helper
periplus affected python.function::shop.tools.helper
2 items
  1  python.module::shop.cli  python.module  mapped  via calls to python.function::shop.tools.helper  shop/cli.py:9
      | helper()
  1  python.module::shop.tools  python.module  mapped  via contains to python.function::shop.tools.helper  shop/tools.py:1
      | def helper():
warning: resolved 'helper' to python.function::shop.tools.helper
```

Find the chain from the module to the helper. Edges are followed in their own direction, so the
reverse query finds none:

<!-- nav-run -->
```console
$ periplus path python.module::shop.cli python.function::shop.tools.helper
periplus path python.module::shop.cli python.function::shop.tools.helper
1 shortest chains
  chain 1:
    python.module::shop.cli --calls--> python.function::shop.tools.helper  shop/cli.py:9
      | helper()
```

<!-- nav-run -->
```console
$ periplus path python.function::shop.tools.helper python.module::shop.cli
periplus path python.function::shop.tools.helper python.module::shop.cli
no path
```

Print what lies around the helper, two hops out, in one call:

<!-- nav-run -->
```console
$ periplus slice helper
periplus slice
start 1 (given as 'helper')
python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
      | def helper():

around python.function::shop.tools.helper
  1 <--calls-- python.module::shop.cli  python.module  mapped  shop/cli.py:9
        | helper()
    2 --calls--> python.function::typer.Typer  python.function  unresolved  :4
          | app = typer.Typer()
    2 --contains--> python.function::shop.cli.greet  python.function  mapped  :8
          | def greet():
    2 --imports--> python.module::shop.tools  (again)  :2
    2 --imports--> python.module::typer  python.module  referenced  :1
          | import typer
  1 <--contains-- python.module::shop.tools  python.module  mapped  :1
        | def helper():
warning: resolved 'helper' to python.function::shop.tools.helper
```

The same piece, cut to two rows, says what it left out:

<!-- nav-run -->
```console
$ periplus slice helper --limit 2
periplus slice
start 1 (given as 'helper')
python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
      | def helper():

around python.function::shop.tools.helper
  1 <--calls-- python.module::shop.cli  python.module  mapped  shop/cli.py:9
        | helper()
  1 <--contains-- python.module::shop.tools  python.module  mapped  :1
        | def helper():
showing 2 of 6 rows
left out by hop: 2: 4
left out by kind: calls 1, contains 1, imports 2
narrow with --kind K (kinds here: calls, contains, imports), --direction out, --direction in or --depth 1
show all with --limit 0
warning: resolved 'helper' to python.function::shop.tools.helper
```

Start from plain words. Neither names a node, and the two together match nothing, so each word
is searched alone. Both find the helper:

<!-- nav-run -->
```console
$ periplus slice tool help --starts 1 --depth 1
periplus slice
no node matches 'tool help' as a whole; started from its words
start 1 (words: 'tool' in id, 'help' in id)
python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
      | def helper():

around python.function::shop.tools.helper
  1 <--calls-- python.module::shop.cli  python.module  mapped  shop/cli.py:9
        | helper()
  1 <--contains-- python.module::shop.tools  python.module  mapped  :1
        | def helper():
go deeper with --depth 2
```

An id that is not in the map exits 31:

<!-- nav-run -->
```console
$ periplus show nope
periplus show
31 no node has the id 'nope'; periplus find searches the ids
  hint: run periplus find nope
(exit 31)
```

A short name that fits two nodes lists them, and exits 31:

<!-- nav-run -->
```console
$ periplus show typer
periplus show
31 'typer' matches 2 nodes; give one of these ids
  python.function::typer.Typer  python.function  no location
  python.module::typer  python.module  no location
(exit 31)
```

Last, check the whole map. The path printed is the project's:

<!-- nav-run -->
```console
$ periplus check-map
/path/to/project/.periplus/map.json matches the map schema
```
