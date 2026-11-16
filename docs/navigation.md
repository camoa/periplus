# Navigating the map

`periplus map` writes the map. Ten commands read it. Seven answer a question about it. `slice` prints the
piece of the map around some words or items, or cuts it into a map file of its own; `export` prints the map in
another format. Each one loads the map, prints its output and stops. None of them changes the map or
starts a server. The question commands read a source file only to print one line of it under a row.

| Command | Question it answers |
|---|---|
| `periplus types` | Which node types and edge kinds does the map hold, and how many of each? |
| `periplus legend` | What does each edge kind and node type of the map mean, and which types does a kind join? |
| `periplus find TEXT` | Which nodes hold this text in their id, attributes or description? |
| `periplus show ID` | What is this node, and which edges leave and arrive at it? |
| `periplus neighbors ID` | Which items do this item's edges lead to? |
| `periplus affected ID` | Which items have edges that lead to this item? |
| `periplus path FROM TO` | What is the shortest chain of edges from one item to another? |
| `periplus slice WORDS` | What lies around the nodes these words or ids name, hop by hop? With `--out FILE`, write that piece to a map file of its own. |
| `periplus export --format F` | Print the map as GraphML, DOT or Mermaid. |

A tenth command, `periplus check-map`, checks the whole map against the map schema. See
[Checking the map](#checking-the-map).

## What every command shares

- `--map PATH` names the map file. Without it, the command reads `.periplus/map.json` under the
  project root, found by walking up from the working directory.
- The seven question commands and `slice` take `--format text|json` to pick the report (default
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

The question commands report ids, locations and source lines. A row of `find`, `neighbors`,
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

### legend

```
periplus legend [--kind K]... [--type T]... [--all] [--map PATH] [--format text|json]
```

Says what the map holds and what it means. It lists the edge kinds, most edges first, each as
`kind  count  from types -> to types` with the pack's description under it, then the node
types, most nodes first, each as `type  count  parent: P` with its description. An end names its
two most frequent types and counts the rest, `+N`. A kind or type whose pack gives no description
prints its line alone. Read it before a question, to learn which kind answers it: a kind that
is listed is a fact the map holds.

The text aims at 3 KB. Over that, it leaves out the kinds and types with the fewest edges or
nodes, and ends with `N left out, ...`. `--all` prints every one. `--kind K` or `--type T`
prints only that kind or type, in full: a kind with every type at each end and its count, a type
with the kinds of the edges leaving it (`out:`) and reaching it (`in:`). A name the map holds no
edge or node of is a warning. `--format json` prints `edge_kinds` (each with `kind`, `count`,
`from`, `to` and `description`), `node_types` (each with `type`, `count`, `parent`,
`description`, `out` and `in`), `left_out`, `warnings` and `problems`. The descriptions come from
the map's `legend`, which `periplus map` writes from the packs.

### find

```
periplus find TEXT [--type T]... [--path P]... [--limit N] [--map PATH] [--format text|json]
```

Lists the nodes whose id holds `TEXT`, closest match first, then the nodes whose string attribute
values hold it, then the nodes whose description alone holds it. Matching ignores case. A string
item of a list attribute counts; numbers, booleans and nested objects do not. Each row is the id,
the type, the state and the first location, then the source line and the description. The state is
`mapped`, `boundary`, `unknown_boundary`, `unresolved` or `referenced`; the map schema defines each,
and every command below prints it the same way. A row matched
by its description ends with `[description]`. A row matched by an attribute ends with
`[attribute NAME]`, the first matching name in sorted order, and prints `@ NAME: value` under the
source line. `--type T` keeps type
`T` and its subtypes. `--path P` keeps the nodes with a file that starts with `P`. Repeat either to
keep several types or paths. Given both, a node must fit a type and a path. A type the map does not hold prints a warning,
with up to five node types it may mean (`did you mean: ...`). A `--path` that no file in the map
starts with prints a warning.

A node in supporting code, one whose first file matches a pattern the map lists under
`supporting_paths`, such as a test, ends with `[supporting code]`, and such rows come after the
rest.

The JSON report adds `by_type`, every match counted by type, also when the list is cut. Each item
has `location`, `source`, `matched` (`id`, `attribute` or `description`), `matched_attribute` (the
attribute's name, or null), `description` and `supporting`.

### show

```
periplus show ID [--limit N] [--map PATH] [--format text|json]
```

Prints the node's type, state, location and provenance, then its outgoing and incoming edges
grouped by kind. Each edge row names the other end, the first location, the occurrence count, the
confidences (`declared`, `inferred` or `mentioned`, each once) and the rules, with the source line
under it. `--limit` applies to each of the two edge lists. Take `ID` from `find`. Edges whose
other end is supporting code come after the rest of each list, under `in supporting code:`. In
JSON each edge row adds `location`, `source` and `supporting`, and the report adds `warnings`.

An edge kind the map lists under `realizing_kinds` says its `from` end is a concrete form of its
`to` end, as a method implements an interface method; one under `realizing_to_kinds` says the
same of its `to` end, as a route's controller method. When nodes stand for the shown node this
way, a last section lists them, at most 8, the forms of those forms too:

```
Realized by (3):
  app.Base::send  php.method  by implements_method
  app.One::deliver  php.method  by overrides from app.Base::deliver
  +1 more
```

In JSON, `realized_by` holds `items` (`id`, `type`, `kind`, `stands_for`) and `more`. A node
outside the project has no section.

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
`location`, `source`, `description`, `stands_for` and `supporting`.

When the walk reaches a node, the mapped nodes that stand for it across realizing edges join at
the same depth, whatever `--kind` says: a row `realizes X by implements_method`. So the code
behind an interface method costs no extra hop. The start brings its own at depth 0. A node reached
along a realizing edge adds none, so the other forms of a declaration do not join as siblings, and
a node outside the project adds none. At most 8 join at one node; past that a line says `+N more
stand for X, past the first 8; see periplus show X`. Rows in supporting code come after the rest,
under `in supporting code:`.

### affected

```
periplus affected ID [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
```

The same report as `neighbors`, following the edges that arrive at `ID`. Here a node brings the
declarations it stands for, a row `realized by X by overrides`, so the callers of an abstract
method reach the method that replaces it.

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
periplus slice [WORDS ...] [--path PREFIX]... [--type T]... [--starts N] [--support] [--direction out|in|both] [--depth N] [--kind K] [--limit N] [--map PATH] [--format text|json]
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
id's last `::` that names its owner, adds nothing. The starts are picked in two passes. The
first covers the words: in turn from the rarest word down, it takes the best node that holds
the word, by score, until it holds half the starts, or one per word when that is more. The
second fills the rest by score. In the second pass, a start of
lower score never comes before one of higher score. Among starts of equal score, rarer types
come first, counted over the whole map, and at most two of a type, counted over all the starts,
come before the rest of that score. Inside a type, a mapped node comes first, then the node that
nodes in more other files have edges into, then the one whose id the words cover most, then
`find`'s order. `--starts N` sets how many starts the words pick in all (default 12). `--type T`
and `--path P` keep only the starts the words find of type `T` or under `P`, as they narrow
`find`.
Without words, `--path PREFIX` starts from every node whose first file starts with `PREFIX`.
When the whole text matches nothing and its words do, the piece says so on its second line.
Words that match nothing print `no matches`, and exit 0.

The output names each node by its short name: the shortest tail of its id that `slice NAME`, or
any command that takes an id, resolves back to that node alone, else the full id. Any name it
prints can be pasted into the next command.

The output lists each start first, on one line: its short name, its type, and why it was picked
(`given as 'helper'`, or each word and where it matched). Then `paths under: DIR/` names once the
longest folder that holds every printed file, and each file prints below it: `cli.py` under
`paths under: shop/` is `shop/cli.py`.

The words gather pieces of the map. A piece is a set of the printed nodes that edges of the map
join. An edge of a grouping kind joins none: two classes of one module are two pieces unless
another edge joins them. Each piece prints a header, `piece 1 of 4: 12 things, starts: A, B`,
then its nodes grouped by file. Pieces go by the summed word score of their starts, highest
first, then by the things they name, most first, then by their smallest start id. A start that
an edge joins to another start's piece prints in that piece. After the last of several pieces,
one line says that no edge of the map joins them as printed, that they may still meet through
nodes not printed or relate in ways the map does not hold, and gives `periplus path A B` with
the first starts of the first two pieces.

Inside a piece, each file prints once, as a header, with `in X` naming the containers its nodes
belong to by grouping edges. Under it, in line order, each node prints `:LINE  name  type`, its
source line and its description, then one line per edge kind and direction to other nodes of
the piece: `calls -> a, b` for edges the node has, `calls <- c` for edges to it. An edge between two nodes of one
file prints only under the node it starts from. Far ends a rule
did not map fold to `(+N outside the project: x, y)`, naming the first 3. Three or more far ends
that share an owner, the part of their ids before the last `::`, fold to the owner and a count,
`Mailer (3)`. A clause names at most 5 far ends and counts the rest, `(+N more)`. A node with
edges the piece does not show ends with `+N more links: calls -> 8, calls <- 3; see periplus
slice NAME`. A source line with fewer than two letters, digits or underscores, such as `{#`, is
not printed.

The output ends with an inventory: every node it names, grouped by type with a count, rarest type
first. When there are several pieces, each name is followed by its piece number, `send [2]`.
Check an answer against it. When the map's packs describe an edge kind the pieces' links show, a
`legend:` block comes last, one `kind: description` line per such kind, in up to 640 bytes; past
them it counts the rest, `+N more: periplus legend --kind K`.

An edge of a grouping kind, one the map lists under `grouping_kinds`, says its `from` end belongs
to the container at its `to` end, as a class belongs to its module. The walk follows such an
edge only from the member to the container. The container is named once, in the header of
its members' files, and the walk goes no further from it,
so one module does not pull every class, service and route it holds into the piece. `--kind K`
naming a grouping kind walks it as any other kind.

A start that is a container prints `members of NAME: N (type n, ...); list one type: periplus
slice NAME --type T --limit 0`, the types rarest first. Its members join the piece one type at a
time in turn, the member more other files depend on first, up to the start's share of
`--limit`. With `--type T` and no words, a container start lists only its members of type `T`
and its subtypes, and nothing else. In JSON, `members` holds, per container start, `container`,
`total`, `by_type` and `rows`; a walk row has `container: true` at a container.

A node whose edges, two or more, all join it to the node above is a satellite of that node. It
gets no row and costs no hop. The piece ends with how many were folded, by type.

The walk adds, at the hop of each node it reaches and of each start, the mapped nodes that stand
for it across realizing edges, as `neighbors` does, and costs no hop for them: the code behind an
interface method joins the piece with the method. The node prints them as `realized by
(implements_method) -> Base::send, Other::send`, and past 8 a line `+N more stand for NAME, past
the first 8; see periplus show NAME`.

Supporting code, the nodes whose first file matches a pattern the map lists under
`supporting_paths`, such as tests, is neither printed nor walked. Each piece ends with one line
that counts what its walk met there, `+14 in supporting code (**/tests/**): show with --support`.
A start comes from supporting code only when an argument names it, or when every node the words
match is there. `--support` prints supporting code as any other, and lets the words pick a start
there.

`--depth N` sets how many edges to follow from every start. Without it, the first 8 starts walk
2 hops and any later start 1 hop, so that more separate pieces fit; the output then says so on
a line `walked 2 hops from the first 8 starts and 1 hop from the other N`. `--direction`
defaults to `both`, since a chain often goes up one kind and down another. Without `--limit`,
the piece holds at most 50 rows and aims at 8 KB of text: over that, it leaves out the rows past
the first hop, farthest and lowest-ranked start first, then the `more links` lines, then names
per link, then the first-hop rows of the piece that names the most things, and says what it left
out in a line `cut to fit 8192 bytes: ...; --limit N prints N rows`. The legend is left out before any of these, and the
line says `legend left out`. It never leaves out a start's own line or the inventory. `--limit N` caps the rows at `N` (`0` for all)
with no byte aim. The cap keeps full rows before back-references. Among them it keeps first the nodes more
starts reach, then those reached from the starts of more words, then those whose own id,
attributes or description more of the words match, then rarer types, then nodes more other
files have edges into, then the nearer hop, then by id. It first gives each start an even share
of the cap, then fills the rest with the best rows left. A kept row brings the rows above it. A cut piece ends with what it left out, counted by hop and by edge
kind (at most 6 kinds, most left out first), and the flags that narrow it (`--kind`, `--direction`, `--depth`, and `--type`, `--path`
or `--starts` when words picked the starts). A piece that was not cut and has edges past its
last hop ends with `go deeper with --depth N`. `--format json` prints the same piece with full ids and full paths: `starts`,
`pieces` (each with `piece`, its number, `starts`, `things` and `supporting`, the count the text
prints),
`rows` (each with `start`, `hop`, `from`, `kind`, `direction`, `again`, `location`, `source`,
`description` and `piece`), `left_out`, `deeper`, `folded`, `notes`, `depth` and `direction`. Each
start and each row carries the `piece` number of its node.

With `--out FILE`, `slice` writes the items around the start items to a map file of their own
instead, and takes ids, not words. Name the start items as `ID`s, with `--path PREFIX` (every
node whose first file starts with `PREFIX`), or both; one of the two is required. Repeat
`--path` for several prefixes; each one must match a node. `--out` exits 27 when it is the map
being read, and `--type`, `--starts` or `--support` with it exits 2. `--depth N` defaults to 1 here. The nodes that stand for a
reached node join the file as in the printed piece, so the code behind an interface is in the
working set; supporting code is kept, and the file carries `supporting_paths`. `--limit
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

Print what lies around the helper, two hops out, in one call. Nodes group by file, and each
names its links:

<!-- nav-run -->
```console
$ periplus slice helper
periplus slice
start helper  python.function  (given as 'helper')
paths under: shop/

piece 1 of 1: 6 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
      calls <- cli
  :1  tools  python.module
      | def helper():
      contains -> helper
      imports <- cli

cli.py
  :1  cli  python.module
      | import typer
      calls -> helper (+1 outside the project: typer.Typer)
      contains -> greet
      imports -> tools (+1 outside the project: python.module::typer)
  :8  greet  python.function
      | def greet():

inventory: 6 nodes
  python.function 3: greet, helper, typer.Typer
  python.module 3: cli, python.module::typer, tools
warning: resolved 'helper' to python.function::shop.tools.helper
```

The same piece, cut to two rows, says what it left out, and `cli` counts the links it no longer
shows:

<!-- nav-run -->
```console
$ periplus slice helper --limit 2
periplus slice
start helper  python.function  (given as 'helper')
paths under: shop/

piece 1 of 1: 3 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
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
showing 2 of 6 rows
left out by hop: 2: 4
left out by kind: imports 2, calls 1, contains 1
narrow with --kind K (kinds here: imports, calls, contains), --direction out, --direction in or --depth 1
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
start helper  python.function  (words: 'tool' in id, 'help' in id)
paths under: shop/

piece 1 of 1: 3 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
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
