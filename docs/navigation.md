# Navigating the map

`periplus map` writes the map. Twenty-nine commands read it. Each one loads the map, prints its
output and stops. None of them changes the map or starts a server.

The commands come in two layers:

- **Small commands** do one job each: count, list or fetch one kind of answer. Their output is
  short, and a list from one can be piped into another.
- **Macros**, `reach` and `slice`, run several small commands in one reply. When a macro cuts a
  part to fit, it names the small command that prints that part in full.

Start with the counts, to learn how big an answer is, then fetch what you need. Use a macro when
you want several answers about the same items at once.

## Which command to use

**Learn the map's words.**

| Command | Question it answers |
|---|---|
| `periplus types` | Which node types and edge kinds does the map hold, and how many of each? |
| `periplus legend` | What does each edge kind and node type of the map mean, and which types does a kind join? |

**Cheap counts, to decide what to read.**

| Command | Question it answers |
|---|---|
| `periplus depth ID...` | How far does what these items set off reach, and what sets them off? |
| `periplus count ID...` | How many things do these ids name, of which types and states, with how many edges among them? |
| `periplus pieces ID...` | Into which groups do edges join these items? |
| `periplus files ID...` | Which files hold these things, and how many each? |
| `periplus hubs ID...` | Which hubs does the walk from these items stop at? |

**Fetch things and their links.**

| Command | Question it answers |
|---|---|
| `periplus find [TEXT]` | Which things hold these words in their id, attributes or description, and which edges in their description, attributes or code line? |
| `periplus show ID...` | What is each of these nodes, and which edges leave and arrive at it? |
| `periplus neighbors ID...` | What do these items set off, hop by hop? |
| `periplus affected ID...` | What sets these items off, hop by hop? |
| `periplus only ID...` | What do these items set off that nothing else sets off? |
| `periplus members ID...` | What does this container hold? |
| `periplus in FILE...` | Which things does the map hold in this file, line by line? |
| `periplus at FILE:LINE...` | Which mapped thing is at this line, or nearest above it, and what holds it? |
| `periplus path FROM TO` | What is the shortest chain of edges from one item to another? |

**Macros.**

| Command | What it combines |
|---|---|
| `periplus reach ID...` | `depth`, `neighbors`, `affected`, `only` and `hubs` for these items, in one reply. |
| `periplus slice [WORDS...]` | `find`, `members`, `neighbors`, `affected` and `pieces`: the things around the nodes these words or ids name, each with its file, source line and links. With `--out FILE`, it writes them to a map file of its own. |

**Sets and map files.**

| Command | Question it answers |
|---|---|
| `periplus extract ID... --out FILE` | Write the things these ids name, and the edges among them, to a map file. |
| `periplus join MAP MAP...` | What do any of these map files hold? |
| `periplus common MAP MAP...` | What do all of these map files hold, as what two features share? |
| `periplus minus MAP MAP...` | What does the first map file hold that no other does? |
| `periplus diff OLD NEW` | Which things and edges were added, removed and changed from one map to another? |
| `periplus export --format F` | Print the map as GraphML, DOT or Mermaid. |

**Descriptions.**

| Command | Question it answers |
|---|---|
| `periplus undescribed [ID...]` | Which main things have no description yet, counted by file, type or container? |
| `periplus order ID...` | In what order should these things be described, each after what it calls or uses? |
| `periplus stamp` | Write into each node entry a fingerprint of the code it describes. |
| `periplus stale` | Which node entries describe code that changed since they were stamped, or a node that is gone? |

A twenty-ninth command, `periplus check-map`, checks the whole map against the map schema. See
[Checking the map](#checking-the-map).

Six commands write a file: `stamp` writes the descriptions file; `extract` writes a map file;
`slice`, `join`, `common` and `minus` write one only with `--out`. No other command writes.

## What every command shares

**The map.** `--map PATH` names the map file. Without it, a command reads `.periplus/map.json`
under the project root, found by walking up from the working directory. A slice or any other map
file that `slice --out`, `extract`, `join`, `common` or `minus` writes is a map too: every
command that takes `--map` reads it. `join`, `common`, `minus` and `diff` take map files as
their arguments instead. Do not give `--out` the path of the map you read: the new file would
replace it.

**JSON.** Every command takes `--format text|json` to pick the report (default `text`), except
`export`. The JSON report has sorted keys and is described by the shipped
`navigation.schema.json`, which `periplus spec` also emits. `export` prints the graph itself and
takes `--report text|json` for the warnings and problems it writes to standard error.

**Ids and short names.** An `ID` argument is a node id or a short name. A short name is the id's
name after its first `::`, or a tail of that name that starts after a character other than a
letter, digit or underscore, compared without case. So `helper` and `tools.helper` both name
`python.function::shop.tools.helper`.

- A short name that fits one node is used, with the warning
  `resolved 'helper' to python.function::shop.tools.helper`.
- One that fits several nodes exits 31 and lists up to 20 of them, each with its type and
  location. In JSON the problem's `detail` holds `id` (the text given), `total` (how many nodes
  fit) and `candidates`, up to 20 objects with `id`, `type` and `location` (`null` when the node
  has none).
- One that fits none exits 31 with `hint: run periplus find TEXT`. `slice` searches such an
  argument as words instead, unless it came with `--from`.

Most rows print a thing by its short name: the shortest tail of its id that names this node
alone, else the full id. Any name a row prints can be pasted into the next command. The thing
rows of `find` and the rows of `show` and `path` print full ids; `--full` makes the walks and
`reach` print them too. Every JSON report carries full ids and full paths.

**`-` reads ids from standard input.** Every command that takes several `ID`s reads them from
standard input when given `-` in their place, one id a line: `show`, `depth`, `reach`,
`neighbors`, `affected`, `only`, `hubs`, `members`, `pieces`, `count`, `files`, `undescribed`,
`order` and `extract`, and `slice --from`. Only the line ending is taken off, so an id keeps its
spaces; empty lines are skipped. `-` that reads no id exits 2. `path` takes two single ids and
`slice` reads its other arguments as words, so neither reads standard input there.

**`--ids` prints ids for the next command.** It prints the ids a command lists, one full id a
line, and nothing else:

- `find`: the things, then both ends of each edge;
- `show`: the other end of each edge;
- `reach`: the starts, then what `neighbors --ids` and `affected --ids` list, each once;
- `slice`: the starts, the members of each container start, then what `neighbors --ids` and
  `affected --ids` list from them, each once;
- `neighbors` and `affected`: the starts, then every thing within `--depth`, and with `--touch`
  the touching things;
- `pieces`: a blank line between two pieces;
- `diff`: the things added, removed and changed;
- `only`, `hubs`, `members`, `in`, `at`, `undescribed`, `stale`, `order`, `join`, `common` and
  `minus`: the things of the result.

The list is never cut: `--limit` does not apply. The count, such as `5 ids`, the warnings and the
problems go to standard error, so a pipe carries ids only. An id holding a control character, such
as a line break, prints escaped instead, and a line on standard error says how many did; the
commands read the escaped form back. `--ids` with `--format json` exits 2.

Pipe a periplus command only into another periplus command. A pipe into `head`, `grep` or `cut`
drops rows without a word; a periplus command reads every id and counts what it reads.

```
periplus neighbors ID --depth all --ids | periplus count -
periplus find login --ids | periplus pieces -
```

A command a report suggests, such as the one that shows all, names the starts it was given when
there are three or fewer. When there are more, or they came from standard input, it names `-`
instead and ends with `(with the same ids piped in)`: pipe in the same ids again. When a command
was given `--map PATH`, each command its report or its messages suggest carries the same
`--map PATH`.

**`--limit` budgets.** `--limit N` sets how much a text report may hold, and `--limit 0` lifts the
limit. What `N` counts depends on the command:

| Command | `--limit N` counts | Default |
|---|---|---|
| `find` | characters of text | 12,000 |
| `neighbors`, `affected` | characters of text | 20,000 |
| `reach` | characters of the whole reply | 20,000 |
| `neighbors --raw`, `affected --raw` | rows | 50 |
| `show` | rows of each edge list | 50 |
| `path` | chains | 10 |
| `slice` | things past the starts, aiming at 8 KB of text | 50 |
| `slice --out` | things the slice file may hold; over it, nothing is written and it exits 32 | 500 |
| `diff` | rows of each list | 50 |

Nothing is cut without a line that says so. A cut list of `show`, `path` or a raw walk ends with
`showing N of TOTAL` in text, and has `"truncated": true` in JSON. The JSON of `find`, of the
walks by cause and of `reach` is never cut.

**Marks.** A mark is a short fact a rutter declares about a thing, such as `[not installed]`.
The map's `marks` header names the mark of each attribute that has one, so no pack is needed to
read it. A node that holds such an attribute prints its mark in brackets on every row that names
it: in `find`, `show`, `neighbors`, `affected`, `reach`, `only`, `hubs`, `members`, `pieces`,
`path`, `slice`, `in`, `at`, `stale` and `order`. The mark comes after `[attribute NAME]` or
`[description]` and before `[supporting code]`. Several marks print in attribute-name order. A
mark the rutter spreads holds for everything inside the thing: a function in a module that is not
installed prints `[not installed]` too. A map with no `marks` header prints no marks. The JSON
rows carry `marks`, a list that is empty when the node has none. `find --mark TEXT` keeps the
nodes that carry a mark.

**Edge attributes.** A rutter may write attributes on an edge, such as the key a callable is
registered under. A row reached by such an edge prints them after the kind, in brackets, by name:
`registers_element_callback [key: #pre_render]` in `show`, `find`, `neighbors`, `affected`,
`reach` and the raw walks, and after each name a `slice` link shows. An edge found at several
places with different values prints each value once, in the order of its places:
`[key: #process, #pre_render]`; the map and `show --format json` hold which value is at which
place. The JSON rows carry the edge's attributes as the map holds them, an empty object when it
has none: `attributes` in `show`, `find`, the raw walks and `slice`, `via_attributes` in the walks
by cause. `diff` names `attributes` among the fields of an edge that changed.

**Supporting code.** A node in supporting code, one whose first file matches a pattern the map
lists under `supporting_paths`, such as a test, ends its row with `[supporting code]`. The JSON
rows carry `supporting`.

**Locations, source lines and descriptions.** A row of `find`, `neighbors`, `affected` or `path`,
and an edge row of `show`, carries a location as `file:line`: where the edge is written, else the
node's first location. A walk by cause prints `:line` when the row above is in the same file.
Under a row of `find`, `path`, `show`, or `neighbors` or `affected` with `--raw`, marked `|`,
comes the source line at that place, stripped and cut to 160 characters. It is left out when the
file or the line cannot be read, as when the map is older than the tree, or when the file is not a
regular file, lies outside the project, or is over 5 MB. Files are read under the project root
above the map file, or beside the map file when no project is found. A row of `find` or `path`,
or of `neighbors` or `affected` with `--raw`, then prints the first line of its node's entry in
`.periplus/descriptions.yaml`, marked `#`, when it has one. The commands read a source file only
to print one line of it under a row, or, for `stamp` and `stale`, to fingerprint the code an
entry describes.

**First line and output.** The first line of each text report names its command, also when the
command stops before its answer; only a walk by cause that does not show everything puts its
`showing` line first. Output is the same on every run for the same map. A command whose standard
output is closed early, as by `| head`, stops quietly and exits 141. The commands have no
`between` query.

## The walk by cause

`depth`, `neighbors`, `affected`, `reach`, `only`, `hubs` and `slice` walk the map by cause. Each edge
kind of a map made by Periplus 0.9 or later has a cause, which `periplus legend` prints:

- `from`: the from end sets off the to end, as a function calls another.
- `to`: the to end sets off the from end, as a hook runs the function that implements it.
- `none`: structure, as a module contains a function. It is never followed.
- `touch`: the from end only points at the to end without running it, as a link names a route.
  It is not followed either; `--touch` shows it.

The walk off, what the items set off, follows a `from` kind forward and a `to` kind backward. The
walk by, what sets the items off, does the opposite. A kind the map lists under no cause is
undeclared: the walk off follows it forward, the walk by backward, by its raw direction, and a last
line names it: `undeclared kinds, walked by raw direction: K`.

The walk goes breadth first to its end, and reaches each thing once, at its nearest hop, by the
first edge in (kind, other end) order. A thing with more edges to follow than the hub limit,
`--hub N` (default 40), is a hub: it is listed with `[hub: N links not walked]` and the walk does
not go on from it. `--hub 0` walks every hub; `--through ID` walks one hub all the same, and can
be repeated. A start is always walked from. Several `ID`s walk as one set.

A map with no cause list, such as one written before 0.9, has no walk by cause. There,
`neighbors` and `affected` give the raw walk of `--raw`, from one `ID` only, and several `ID`s
exit 2; `slice` takes that raw walk from each start in turn; `depth` walks every kind by its raw
direction and says so on a last line.

## Learn the map's words

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
two most frequent types and counts the rest, `+N`. A kind the map lists under a cause ends its
line with `cause: from`, `cause: to`, `cause: none` or `cause: touch`: which end sets off the
other, neither, or the from end only points at the to end. A
kind or type whose pack gives no description prints its line alone. Read it before a question, to learn which kind answers it: a kind that
is listed is a fact the map holds.

The text aims at 3 KB. Over that, it leaves out the kinds and types with the fewest edges or
nodes, and ends with `N left out, ...`. `--all` prints every one. `--kind K` or `--type T`
prints only that kind or type, in full: a kind with every type at each end and its count, a type
with the kinds of the edges leaving it (`out:`) and reaching it (`in:`). A name the map holds no
edge or node of is a warning. `--format json` prints `edge_kinds` (each with `kind`, `count`,
`from`, `to`, `description` and `cause`, null for an undeclared kind), `node_types` (each with `type`, `count`, `parent`,
`description`, `out` and `in`), `left_out`, `warnings` and `problems`. The descriptions come from
the map's `legend`, which `periplus map` writes from the packs.

## Cheap counts

### depth

```
periplus depth ID... [--hub N] [--through ID]... [--map PATH] [--format text|json]
```

Says, in a few lines, how far the walk by cause goes from the `ID`s each way, so you can pick a
`--depth` for `neighbors` and `affected` before you list anything. For each direction it prints one line: the hops until the walk reaches nothing new, the things it
reached, the share of them within 2, 3 and 5 hops, and the hubs it stopped at, up to three named:

```
sets off:    10 hops, 128 things; 8% within 2, 21% within 3, 57% within 5; 0 hubs stopped
set off by:   2 hops, 2 things; 0 hubs stopped
```

A share is left out when the walk ends at or before its hop. A `touching:` line follows when edges
of a `touch` kind point at the `ID`s or leave them: how many things, the kinds with their edge
counts (three named, the rest counted), and the command that lists them, `see periplus affected
ID --touch`. A last line names the
kinds the walk followed undeclared, or says the map declares no cause directions. `--hub` and
`--through` work as in [the walk by cause](#the-walk-by-cause). In JSON, `sets_off` and `set_off_by` each hold `hops`,
`things`, `per_hop` (the things each hop reached, from hop 1) and `hubs` (`id`, `hop`, `fan`);
`touching` holds `point_at_starts` and `starts_point_at`, each with `things` and `kinds`; and
`undeclared` and `declares_causes`.

### count

```
periplus count ID... [--map PATH] [--format text|json]
```

Counts what the `ID`s name: how many ids were given and how many things they name, then the things
by type and by state, most first, and the edges both of whose ends are among them, by kind. An id
that names no node, or a short name that fits several, is listed under `not in the map:`, with
`(fits N nodes)` for a short name, and is not a problem: `count` exits 0. The first line also says
how many ids named a thing an earlier id named (`repeated`) and how many were short names. In JSON:
`command`, `given`, `things`, `repeated`, `short_names`, `by_type`, `by_state`, `edges`,
`not_found` (each with `id` and `fits`) and `problems`.

### pieces

```
periplus pieces ID... [--ids] [--map PATH] [--format text|json]
```

Splits the things the `ID`s name into pieces. Two share a piece when an edge of any kind joins them
directly, or a chain of such edges does through other things of the set; a thing outside the set
joins nothing. Pieces go largest first, then by their smallest id. The text prints `N things in M
pieces`, then each piece's header, `piece 1: 3 things`, and one row a thing, by file and line:
name, type, state and place. `--ids` prints the ids with a blank line between two pieces. `slice`
groups its output into pieces by the same function, leaving out grouping kinds. In JSON:
`command`, `pieces` (a list of lists, each thing with `id`, `type`, `state` and `location`),
`warnings` and `problems`.

### files

```
periplus files ID... [--map PATH] [--format text|json]
```

Counts the things the `ID`s name by the files of their locations, most first, then by file. A
thing with locations in two files counts in each. It prints `N things in M files`, one row a file,
`count  file`, then `no location: N` for things with none. In JSON: `command`, `things`, `files`
(each with `file` and `count`), `no_location`, `warnings` and `problems`.

### hubs

```
periplus hubs ID... [--direction off|by] [--depth N|all] [--hub N] [--through ID]... [--ids] [--map PATH] [--format text|json]
```

Lists the hubs the walk by cause from the `ID`s stops at: what they set off (`--direction off`, the
default, as `neighbors`) or what sets them off (`by`, as `affected`). A hub is a thing with more
edges to follow than `--hub N` (default 40); see [the walk by cause](#the-walk-by-cause). The walk
does not go on from a hub, so a hub past another hub is not listed. `--depth N` keeps the hubs within `N` hops (default
all). The text prints a count line, `sets off: 2 hubs (more than 40 links to follow)`, then one line
a hub: name, type, `hop N` and `fan N`, the edges it would follow. In JSON: `command`,
`direction`, `starts`, `depth`, `hub`, `hubs` (each with `id`, `type`, `hop` and `fan`),
`warnings` and `problems`. To walk on from one hub, give it to `--through`, here or in `neighbors`.

## Fetch things and their links

### find

```
periplus find [TEXT] [--any] [--type T]... [--path P]... [--mark TEXT]... [--parts] [--edges|--no-edges] [--kinds] [--source|--no-source] [--limit N] [--ids] [--map PATH] [--format text|json]
```

Lists the things that hold the words of `TEXT`, then the edges that hold them. `TEXT` is split at
spaces. Each word must match a thing, in its id, a string attribute value or its description;
`--any` keeps a thing that matches any one word. Matching ignores case, and a word matches inside
a longer one. A string item of a list attribute counts; numbers, booleans and nested objects do
not.

**Order.** Main things come first, then parts, then things not mapped or with no location, then
things in supporting code. A main thing is what `undescribed` counts as one: mapped, located, not
in supporting code and not of a part type; see [undescribed](#undescribed). Inside each group the
words are taken from the rarest, the one that matches the fewest things, to the commonest. A thing
whose id or attribute holds the word comes before one whose description alone holds it; then the
closer match comes first: the whole id, the name, a name that starts with the word, a name that
holds it, the id, an attribute, the description. Ties go by id.

**Counts first.** The first line counts the things by group and the edges, and the next lines
count the main things, the other things and the edges by type or kind:

```
periplus find: 9 things (4 main, 3 parts, 1 in supporting code, 1 not mapped or with no location), 0 edges
main by type: t.method 3, t.class 1
not main by type: t.call 2, t.class 1, t.function 1, t.param 1
```

Each row is the id, the type, the state and the first location, then the source line and the
description. The state is `mapped`, `boundary`, `unknown_boundary`, `unresolved` or `referenced`;
the map schema defines each, and every command prints it the same way. A row matched by its
description ends with `[description]`. A row matched by an attribute ends with `[attribute NAME]`,
the first matching name in sorted order, and prints `@ NAME: value` under the source line. A line
`not main:` comes before the first row that is not a main thing.

**The budget.** `--limit N` is the most characters the text may hold (default 12000; `--limit 0`
lifts it). Past the budget, the things that are not
main print as counts first, by the container of each, as `undescribed --by container` counts it,
with the command that lists them:

```
not main, not listed: 5
  by container: shop 3, (no container) 2
  list them: periplus find login --parts
```

If the text still does not fit, the edges print as counts by kind, then the rows are cut, keeping
at least one. A line after the counts then says how many show and gives the command that shows
all: `showing 31 of 93 main things; all: periplus find login --limit 0`. `--parts` lists only the
things that are not main, and `--type T` lists those types; neither folds its rows into counts.
`--ids` prints every id whatever the budget, and the JSON lists every match.

**Edges.** After the things, under `edges:`, come the edges that hold the words, each with its
kind and attributes, the short names of its two ends, its place and why it matched. An edge
matches in four ways:

- `[description]`: its entry in the descriptions file holds the words. The entry is under `edges`,
  keyed by `from`, `kind` and `to`, as the map writes them; see the `periplus-describe` skill.
- `[attribute NAME]`: the value of its attribute `NAME` holds the words, as
  `periplus find "#pre_render"` finds every edge registered under that key.
- `[source]`: the code line at one of its places holds the words. This finds a name that is
  only in a line of code, such as a string passed to a call. `--no-source` turns it off.
- `[kind]`: the meaning of its kind, as `periplus legend` prints it, holds the words. A common word
  would bring every edge of a kind, so this happens only with `--kinds`, or when no thing matches.

In the text, the edges matched by `[source]` at one file and line, with no description, print as
one row: the place once, `[source]`, then each edge's kind and ends, separated by `;`, or past
three edges `N edges:` with the count by kind; then the code line once. The count line, `--ids`
and the JSON still hold every edge.

An edge found by its description:

```
$ periplus find lockout
periplus find: 0 things, 1 edge
edges by kind: calls 1

edges:
  calls  submit -> record  shop/Login.php:9  [description]
      | $this->audit->record($name);
      # Records the failed attempt for the lockout count.
```

An edge found by its code line, the word in no id or description:

```
$ periplus find blocked_admin
periplus find: 0 things, 1 edge
edges by kind: calls 1

edges:
  calls  form -> record  shop/Login.php:23  [source]
      | $this->audit->record('blocked_admin');
```

The words must all be in one place: the description, or one attribute value, or the code line,
or the meaning. An edge whose description matches comes first, then those whose attribute does,
then those whose code line does, then those whose kind does; then by place, kind and ends. An edge is kept when one of its ends fits `--type`, `--path`
and `--mark`. `--no-edges` leaves the edges out. `--ids` prints the ids of the things, then both
ends of each edge, each id once. A `TEXT` left out matches no edge.

**Narrowing.** `--type T` keeps type `T` and its subtypes. `--path P` keeps the nodes with a file
that starts with `P`. Repeat either to keep several types or paths. Given both, a node must fit a
type and a path. A type the map does not hold prints a warning, with up to five node types it may
mean (`did you mean: ...`). A `--path` that no file in the map starts with prints a warning.

`--mark TEXT` keeps the nodes that carry the mark `TEXT`, as the rows print it without the
brackets. Repeat it to keep nodes that carry any of several marks. `TEXT` may then be left out:
`periplus find --mark "not installed"` lists every marked node. A mark no node carries prints a
warning that names the marks the map holds.

The JSON report is never cut: `items` holds every match, so `shown` equals `total`. It adds
`by_type`, every match counted by type, and `edges`, each with `kind`, `from`, `to`, `location`,
`source`, `matched` (`description`, `attribute`, `source` or `kind`), `matched_attribute` (the
attribute's name, or null), `attributes` and `description` (the entry's text, or null). Each item has `location`, `source`, `matched` (`id`, `attribute` or `description`),
`matched_attribute` (the attribute's name, or null), `description`, `supporting`, `marks`, a list
of the node's mark texts, empty when it has none, and `group` (`main`, `part`, `unplaced` or
`supporting`).

### show

```
periplus show ID... [--limit N] [--ids] [--map PATH] [--format text|json]
```

Several `ID`s print one report each, in the order given, with a line `---` between two, from one
load of the map. In JSON, several `ID`s print `{"shown": [...]}`, one report each; one `ID` prints
its report alone. When one `ID` names no node, its report says so, the others print, and the exit
code is that problem's. `--ids` prints the other end of each edge, each once.

Prints the node's type, state, location and provenance, then its outgoing and incoming edges
grouped by kind. Each edge row names the other end, the first location, the occurrence count, the
confidences (`declared`, `inferred` or `mentioned`, each once) and the rules, with the source line
under it. `--limit` applies to each of the two edge lists. Take `ID` from `find`. Edges whose
other end is supporting code come after the rest of each list, under `in supporting code:`. The
shown node's marks end its first line, and each edge row ends with the other end's marks. In JSON
each edge row adds `location`, `source`, `supporting` and `other_marks`, and the report adds
`marks` and `warnings`.

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
periplus neighbors ID... [--depth N|all] [--kind K]... [--hub N] [--through ID]... [--touch] [--full] [--ids] [--limit N] [--map PATH] [--format text|json]
periplus neighbors ID --raw [--depth N|all] [--kind K]... [--limit N] [--map PATH] [--format text|json]
```

Lists what the `ID`s set off, hop by hop, by [the walk by cause](#the-walk-by-cause): a `from`
kind forward, a `to` kind backward, and an undeclared kind forward. `--kind K` keeps only edges of
kind `K`; a kind listed under `none` or `touch` given there is a warning.

The text names the command and the starts, the first three and how many more, `+5 more`, then a
line for the whole walk, `sets off: 10 hops, 128
things; 0 hubs stopped`, then a tree. Each start prints first, then each thing under the thing it
was reached from, indented two spaces a hop: its name, type and state, the kind of the edge that
reached it, with `(rev)` when that edge was followed from its to end, its place, and its
marks. The name is the short name. The place is `file:line`, or `:line` alone when the row just
above it, in print order whatever its indent, is in the same file. `--full` prints the full id and
`file:line` on every row. No source line or description prints here; `periplus show ID` prints them. `--depth N` (1 or more, default 1) sets the hops shown, and
`--depth all` shows every hop. Each hop not shown prints one count line instead, `hop 4: 37 things
(php.method 20, php.class 17)`, so nothing is left out unsaid. When the text would pass the budget,
20,000 characters by default, the farthest hops shown become count lines too, until it fits or
only hop 1 is left. When anything is not shown as a row, the first line says so and gives the
command that shows all:
`showing 40 of 128 (hops 1-3 of 10); all: periplus neighbors ID --depth all --limit 0`.

`--touch` adds, under each start and each thing shown, what it points at by a `touch` kind, one hop
out, each marked `[touch]` and never walked from. A count line counts the touching things of its
hop.

`--format json` prints `command`, `direction` (`off`), `starts`, and `rows`: every thing within
`--depth`, with no budget, each with `hop`, `id`, `type`, `state`, `via_kind`, `via_direction`
(`forward` or `backward`), `from` (the thing it was reached from), `file`, `line`, `marks`,
`supporting`, `hub` (its fan when the walk stopped there, else null) and `touch`. It adds `hops`
(every hop of the whole walk with `things` and `by_type`), `total`, `last_hop`, `shown_hops`,
`hubs` (`id`, `hop`, `fan`), `undeclared`, `again` (the command that shows all), `warnings` and
`problems`.

#### The raw walk

`--raw` follows every edge leaving `ID` by its own direction, whatever its kind, as the walk did
before 0.9; it takes one `ID` and no `--hub`, `--through`, `--touch` or `--full`. With `--ids` it
prints the start and every row, past `--limit`. A map with no cause list gets this walk without
`--raw`, from one `ID`, and a last line
`warning: the map declares no cause directions; walked by raw direction, as --raw does`. Each row
gives the depth at which the item was first reached, its id, type and state, the edge it was
reached by and that edge's location, with the source line and description under it. `--depth N`
(default 1) sets how many edges to follow. `--limit N` caps the rows (default 50). In JSON (`direction` `out`) each row adds `location`, `source`, `description`,
`stands_for`, `supporting` and `marks`.

When the raw walk reaches a node, the mapped nodes that stand for it across realizing edges join at
the same depth, whatever `--kind` says: a row `realizes X by implements_method`. So the code
behind an interface method costs no extra hop. The start brings its own at depth 0. A node reached
along a realizing edge adds none, so the other forms of a declaration do not join as siblings, and
a node outside the project adds none. At most 8 join at one node; past that a line says `+N more
stand for X, past the first 8; see periplus show X`. Rows in supporting code come after the rest,
under `in supporting code:`. The walk by cause needs none of this: a realizing kind has a cause,
so the code behind a declaration is one hop along it.

### affected

```
periplus affected ID... [--depth N|all] [--kind K]... [--hub N] [--through ID]... [--touch] [--full] [--ids] [--limit N] [--map PATH] [--format text|json]
periplus affected ID --raw [--depth N|all] [--kind K]... [--limit N] [--map PATH] [--format text|json]
```

The same report as `neighbors`, the other way: what sets the `ID`s off. It follows a `from` kind
backward and a `to` kind forward, and an undeclared kind backward. Its line for the whole walk
starts `set off by:`, its JSON `direction` is `by`, and `--touch` adds what points at each thing
shown. With `--raw` it follows the edges that arrive at `ID`; there a node brings the
declarations it stands for, a row `realized by X by overrides`, so the callers of an abstract
method reach the method that replaces it.

### only

```
periplus only ID... [--hub N] [--through ID]... [--ids] [--map PATH] [--format text|json]
```

Lists what the `ID`s set off, by [the walk by cause](#the-walk-by-cause), that nothing else sets
off. A thing is kept when every chain of things that sets it off, followed back
as far as it goes, passes through an `ID`: remove the `ID`s, and nothing outside what they set off
still sets it off. A loop that only the `ID`s feed is kept. Several `ID`s count as one set. The
text names the command and the `ID`s, prints the walk's `sets off:` line, then `only through the
starts: N of M`, then one row a thing: its name, type, state, `hop N` and its own first
`file:line` (`:line` when the row above is in the same file). In JSON: `command`, `starts`,
`reached` (the things the walk set off), `only` (each with `id`, `type`, `state`, `hop` and
`location`), `warnings` and `problems`.

Given the ids `neighbors --ids` printed, `only` answers what lies past them that only they reach:
the things they set off are already in the set.

### members

```
periplus members ID... [--type T]... [--ids] [--map PATH] [--format text|json]
```

Lists what each `ID` holds: the from end of every edge of a grouping kind, one the map lists under
`grouping_kinds`, that arrives at it, each member once. Only direct members count: a method of a
class of a module is a member of the class, not of the module. `--type T` keeps members of type
`T` and its subtypes; repeat it for several. Each `ID` prints `members of NAME: N (type n, ...)`,
the types most first, then one row a member: name, type, state and its own first `file:line`,
grouped by type in that order, then by file and line. `slice` lists a container start's members
by the same function. In JSON: `command`, `containers` (each with `container`, `total`, `by_type`
and `members`, each member with `id`, `type`, `state`, `location` and `kind`, the grouping kind),
`warnings` and `problems`.

### in

```
periplus in FILE... [--type T]... [--ids] [--map PATH] [--format text|json]
```

Lists the things the map locates in each `FILE`, as the map names the file, relative to the
project root; a leading `./` is taken off. Each `FILE` prints `FILE: N things`, then one row a
thing in line order, then by id: short name, type, state, `:LINE` and marks. A thing with several
locations in the file prints once, at its smallest line. A file the map locates nothing in prints
`FILE: nothing mapped`, and exits 0. `--type T` keeps things of type `T` and its subtypes. In
JSON: `command`, `files` (each with `file` and `things`), `warnings` and `problems`.

### at

```
periplus at FILE:LINE... [--ids] [--map PATH] [--format text|json]
```

The bridge from a line of code, such as a search hit, to the map. A location in the map is a file
and a start line, never a span, so `at` takes the mapped things on `LINE`, or else on the nearest
line above it that holds one, and says `nearest above: :N`. Several things on one line print
innermost first. Then `in` rows name what holds them, outward. A thing is held by the node its id
nests inside, the node whose name, the id after its first `::`, is the longest part of its own
name before one of its `::`; else by the container its grouping edge names. So a call site on a
method's line prints, then `in` the method, its class and the class's module. A line above every
mapped thing prints `nothing mapped at or above this line`, a file with none `nothing mapped in
this file`; both exit 0. A `FILE:LINE` without a line number of 1 or more exits 2. In JSON:
`command`, `places` (each with `file`, `line`, `found_line`, `things` and `containers`) and
`problems`.

### path

```
periplus path FROM TO [--kind K] [--limit N] [--map PATH] [--format text|json]
```

Prints every shortest chain of edges from `FROM` to `TO`, following each edge in its own
direction. Each step names its edge's location, with the source line and the description of the
node it reaches under it. Each end of a step is followed by its marks,
`a --calls--> b  [not installed]  file:line`. In JSON a step adds `location`, `source`,
`description`, `from_marks` and `to_marks`. Without a
chain it prints `no path`, and exits 0. `--kind K` follows only edges of kind `K`; repeat it for
several kinds.

## Macros

### reach

```
periplus reach ID... [--direction off|by|both] [--depth N|all] [--hub N] [--through ID]... [--touch] [--full] [--ids] [--limit N] [--map PATH] [--format text|json]
```

A named combination of the small commands, in one reply. It prints `periplus reach` and the
`ID`s, then, a blank line apart: the `depth` report of the `ID`s; a line `only through the starts:
N of M things set off, tagged [only]; all: periplus only ID`; the `neighbors` walk, its rows of
the things `only` returns ending `[only]`; the `hubs` report of that walk when it stopped at any;
then the `affected` walk and its `hubs` report. Each part is that command's own report, with its
own first line, built by the same function from the one map read, so each one can be had again by
running the command it names. `--direction off` prints only the walk off, `by` only the walk by and
no `only` line.

`--limit N` (default 20,000 characters) is the budget for the whole reply. The `depth` report, the
`only` line and the hubs come first; each walk gets an even share of what is left, and a walk that
fits whole in less gives the rest to the other. A walk over its share prints its farthest hops as
count lines, as `neighbors` does over its budget, and its first line names the command that prints
it all. A walk cut down to hop 1 can still pass its share. `--depth N` caps the hops either walk
shows (default all that fit). `--hub`, `--through`, `--touch` and `--full` work as in `neighbors`
and reach every part. `--ids` prints the starts, then what each walk lists with `--ids`, each id
once. `--format json` prints `command`, `starts`, `depth` (the `depth` document), `only` (the ids)
and `only_command`, `walks` (each walk's `neighbors` or `affected` document, every row within
`--depth`), `hubs` (each walk's `hubs` document), `warnings` and `problems`.

### slice

```
periplus slice [WORDS ...] [--from ID...] [--path PREFIX]... [--type T]... [--starts N] [--support] [--direction off|by|both] [--depth N|all] [--kind K]... [--hub N] [--through ID]... [--touch] [--ids] [--limit N] [--map PATH] [--format text|json]
periplus slice [WORDS ...] [--from ID...] [--path PREFIX]... [--type T]... [--starts N] --out FILE [--direction off|by|both] [--depth N|all] [--kind K]... [--hub N] [--through ID]... [--touch] [--limit N] [--map PATH] [--format text|json]
```

A named combination of the small commands. It picks the starts, as below. It adds the members of
each start that is a container, as `members` lists them, since a container sets nothing off by
itself. Then it walks by cause from the starts and those members, as `neighbors` and `affected`
do from the same ids, `--depth N` hops each way. What it adds over `reach` is the content of each
thing it reached: its file, source line, description, marks and links among the result, the
legend of the kinds met and an inventory.

`--ids` prints every id of the result, never cut: the starts, the members, then what
`neighbors --ids` and `affected --ids` list from the starts and members at the same depth, each
once. So `periplus slice --from X --ids` gives the same set as `periplus members X --ids` together
with `periplus neighbors` and `periplus affected` on X and those members, `--depth 2 --ids`.
`--depth 0` walks nothing, so `--depth 0 --ids` prints the starts and their members alone: the ids
the walks start from.

**Starts.** An argument that names a node, by id or short name, starts there. Any other text is
searched as a whole and word by word, each as `find` searches one word. A word is a run of
letters, digits and underscores, at least 3 long, so `sign-up` searches `sign`. When several words
are given, one that names a node is searched as a word too. Each word weighs the natural log of
the map's node count over the number of nodes it matches, rounded to 6 places, so a rare word
outweighs a common one. A start's score is the sum of the weights of the words it holds in its own
name, an attribute or its description; a word found only in the id's type, or in the part before
the id's last `::` that names its owner, adds nothing. The starts are picked in two passes. The
first covers the words: in turn from the rarest word down, it takes the best node that holds the
word, by score, until it holds half the starts, or one per word when that is more. The second
fills the rest by score. In the second pass, a start of lower score never comes before one of
higher score. Among starts of equal score, rarer types come first, counted over the whole map, and
at most two of a type, counted over all the starts, come before the rest of that score. Inside a
type, a mapped node comes first, then the node that nodes in more other files have edges into,
then the one whose id the words cover most, then `find`'s order. `--starts N` sets how many starts
the words pick in all (default 12). `--type T` and `--path P` keep only the starts the words find
of type `T` or under `P`, as they narrow `find`. Without words, `--path PREFIX` starts from every
node whose first file starts with `PREFIX`, and `--type T` keeps the members of a container start
of type `T` and its subtypes. When the whole text matches nothing and its words do, the slice says
so on its second line. Words that match nothing print `no matches`, and exit 0. When the start
count leaves out nodes the words match, a line under the starts says how many and how to list
them: `+N more nodes match the words: periplus find WORD --limit 0 for each of: user, login; start
from any with periplus slice --from ID`.

`--from ID...` starts from those ids alone, and searches no word: pick the starts with `find` and
give them here, or `-` to read them from standard input. An id that names no node exits 31.
`--from` takes no `WORDS` with it.

**Members.** A start that is a container prints `members of NAME: N (type n, ...); all: periplus
members NAME (--type T for one type)`, the types most first, as `members` counts them. Its members
are things of the slice at hop 0, and the walks start from them too. Only direct members count,
as for `members`.

**The walks.** `--direction off` walks only what the starts and members set off, `by` only what
sets them off; `both`, the default, walks both. `--depth N` sets the hops each walk goes, `--depth
0` none, and `--depth all` walks to the end. It defaults to 2: a walk by cause often goes past 10 hops, and
most of what one start sets off lies past hop 2, so 2 keeps a slice from one start near its 8 KB
aim. `periplus depth` says how far each walk goes before you ask for more. `--kind`, `--hub`,
`--through` and `--touch` work as in `neighbors`, for both walks. `--direction out` and `in`, the
raw directions `slice` took before it walked by cause, exit 2 and name `off` and `by`.

Under the starts and members, each walk prints one line, as `neighbors` and `affected` sum theirs
up: `sets off:     12 hops, 88 things; 0 hubs stopped`. When the walk goes past the depth, the line
adds what the slice holds and the command that prints the whole walk: `; this slice holds hops
1-2: 13; all: periplus neighbors ID --depth all --limit 0`. A last line names the kinds the walks
followed undeclared. A thing the walk stopped at prints `[hub: N links not walked]` on its line.

On a map with no cause list, such as one written before 0.9, each walk is the raw walk that
`neighbors` and `affected` fall back to, from each start and member in turn, and a warning says so:
`warning: the map declares no cause directions; walked by raw direction, as --raw does`. The walk
line then reads `sets off:   4 things by the raw walk, as the map lists no cause; each: periplus
neighbors ID --raw --depth 2 --limit 0 (for each of the 2 ids it walks from)`.

**The content.** The output names each thing by its short name. It lists the first 4 starts, each
on one line: its short name, its type, and why it was picked (`given as 'helper'`, or each word and
where it matched), then its marks. More starts are counted in one line that names the command
listing them all, with their members: `+8 more starts; the starts and their members: periplus
slice 'user login' --depth 0 --ids`. Each start still prints under its file below. Then `paths under: DIR/` names once the longest folder that holds
every printed file, and each file prints below it: `cli.py` under `paths under: shop/` is
`shop/cli.py`.

The result falls into pieces. A piece is a set of the printed things that edges of the map join.
An edge of a grouping kind joins none: two classes of one module are two pieces unless another
edge joins them. A member joins the piece of its container. Each piece prints a header, `piece 1
of 4: 12 things, starts: A, B`, then its things grouped by file. Pieces go by the summed word score
of their starts, highest first, then by the things they name, most first, then by their smallest
start id. After the last of several pieces, one line says that no edge of the map joins them as
printed, that they may still meet through things not printed or relate in ways the map does not
hold, and gives `periplus path A B` with the first starts of the first two pieces. `pieces` splits
a set by the same function.

Inside a piece, each file prints once, as a header, with `in X` naming the containers its things
belong to by grouping edges. Under it, in line order, each thing prints `:LINE  name  type` and its
marks, its source line and its description, then one line per edge kind and direction to other
things of the slice: `calls -> a, b` for edges the thing has, `calls <- c` for edges to it. An edge
between two things of one file prints only under the thing it starts from. Far ends a rule did not
map fold to `(+N outside the project: x, y)`, naming the first 3. Three or more far ends that share
an owner, the part of their ids before the last `::`, fold to the owner and a count, `Mailer (3)`.
A clause names at most 5 far ends and counts the rest, `(+N more)`. A link to the concrete end of a
realizing kind prints `realized by (implements_method) -> Base::send, Other::send`. A thing with
edges the slice does not show ends with `+N more links: calls -> 8, calls <- 3; see periplus show
NAME --limit 0`. A thing with no such edge, but a clause that counts or folds ends, ends with `all
links: periplus show NAME --limit 0`. A source line with fewer than two letters, digits or
underscores, such as `{#`, is not printed.

The output ends with an inventory: every thing it names, grouped by type with a count, rarest type
first. When there are several pieces, each name is followed by its piece number, `send [2]`.
Check an answer against it. When the map's packs describe an edge kind the links show, a `legend:`
block comes last, one `kind: description` line per such kind, in up to 640 bytes; past them it
counts the rest, `+N more: periplus legend --kind K`.

Supporting code, the things whose first file matches a pattern the map lists under
`supporting_paths`, such as tests, is not printed: the walks go through it as `neighbors` does,
and `--ids` and `--out` keep it. Each piece ends with one line that counts it, `+14 in supporting
code (**/tests/**): show with --support, or with the in-full commands at the end`. A start comes
from supporting code only when an argument names it, or when every node the words match is there.
`--support` prints supporting code as any other, and lets the words pick a start there.

**The budget.** Without `--limit`, the text shows at most 50 things past the starts and aims at 8
KB. Over the aim it lowers detail first: it leaves out the legend, then the `more links` lines,
then halves the names per link down to 1. Then it leaves out things, the farthest hop first; at
one hop, the walk off before the walk by, then by id. It keeps the first 10 things past the starts
even over the aim, so a slice of many starts still shows what its walks reached, and then says
`the first 10 things past the starts kept over it`. It never leaves out a start or the inventory,
and says what it did in a line `cut to fit 8192 bytes: ...; --limit N prints N things`.
That line adds `what a kind means: periplus legend --kind K` when it left out the legend, and `a
node's links in full: periplus show NAME --limit 0` when it dropped the `more links` lines or names
per link. `--limit N` shows at most `N` things past the starts (`0` for all), with no byte aim, in
the same order.

When things are left out, the slice ends with `showing N of M things past the starts`, what it left
out by hop and by edge kind (at most 6 kinds, most left out first), and the flags that narrow it
(`--kind`, `--direction`, `--depth`, and `--type`, `--path` or `--starts` when words picked the
starts). When it left out things, link details or supporting code, it then names the small
commands that print each walk it holds in full:

```
in full, each part this slice holds:
  sets off: periplus neighbors helper --depth 2 --limit 0
  set off by: periplus affected helper --depth 2 --limit 0
```

With more than three ids to walk from, or ids read from standard input, each of these commands
reads `-` from the `slice --depth 0 --ids` command that lists those ids, so the line runs as
printed: `periplus slice 'user login' --depth 0 --ids | periplus neighbors - --depth 2 --limit 0`.
When the starts came from standard input, it ends `(with the same ids piped into the first
command)`.

Every command the slice suggests carries `--map PATH` when it was given one, as the commands
`reach` and the walks suggest do, so each runs as printed.

`--format json` prints the same slice with full ids and full paths: `starts` (each as `find` prints
a row, with `given`, `words` and `piece`), `pieces` (each with `piece`, `starts`, `things` and
`supporting`), `members` (each with `container`, `total` and `by_type`), `walks` (each with
`direction`, `off` or `by`, `raw`, `total`, `held`, `last_hop`, `hubs`, `undeclared`, `command`,
the part the slice holds, and `all`, the whole walk), `rows` (each thing past the starts, with
`piece`, `start`, `hop`, `from`, `kind`, `direction`, `walk` (`off`, `by` or `members`), `id`,
`type`, `state`, `marks`, `location`, `source`, `description`, `hub` and `touch`), `left_out`,
`held` (how many things `--ids` prints), `notes`, `depth` (null for all), `direction`, `warnings`
and `problems`.

**`--out FILE`** writes the things `--ids` prints, and the edges between two of them, to `FILE` as
a map, by the same writer as `extract`: `periplus extract` given those ids writes the same bytes.
It takes the starts and walk options the printed slice takes. `--limit N` is the most things the
file may hold (default 500, `0` for no limit); over it, nothing is written and it exits 32. Starts
that match nothing write nothing and exit 31. `--out` naming the map being read exits 27, and
`--ids` with `--out` exits 2. The file keeps supporting code and carries `supporting_paths`. It
prints `wrote FILE: N nodes, M edges`. `--format json` prints one JSON document instead: `out` (the
file written, or null), `nodes`, `edges`, `warnings` and `problems`.

```
periplus slice ID --depth 3 --out foo.map.json
```

## Sets and map files

### extract

```
periplus extract ID... --out FILE [--map PATH] [--format text|json]
```

Writes the things the `ID`s name, and the edges between two of them, to `FILE` as a map. It follows
no edge: what it writes is what the ids name. The file has the form `slice --out` writes: the
map's header, counts and type hierarchy made from what it holds, and a legend cut to its kinds and
types. It matches the map schema, and every command reads it with `--map`. `-` reads the ids from
standard input, so `periplus neighbors ID --depth all --ids | periplus extract - --out F` writes a
walk to a file. An id that names no node exits 31 and writes nothing. `--out` naming the map being
read exits 27. The text prints `wrote FILE: N nodes, M edges`. In JSON: `command`, `out`, `nodes`,
`edges`, `warnings` and `problems`.

### join, common and minus

```
periplus join MAP MAP... [--out FILE] [--ids] [--format text|json]
periplus common MAP MAP... [--out FILE] [--ids] [--format text|json]
periplus minus MAP MAP... [--out FILE] [--ids] [--format text|json]
```

Read two map files or more, whole maps or slices, as sets of things and edges. `join` keeps what
any of them holds; `common` keeps the things every one holds and the edges every one holds;
`minus` keeps the things the first holds and no other does, and the edges among them. A thing is
the same thing in two maps when its id is the same; an edge is the same edge when its kind, from
and to are.

The text names each input with its size, then the result: things and edges, things by type and by
state, edges by kind. With `--out`, the result is also written to `FILE` as a map, and a last line
says so; without it nothing is written. `--ids` prints the result's ids instead.

- **Copies that differ.** Maps from different builds can hold one id with a different state,
  location or provenance. The result keeps one copy, the one whose JSON, keys sorted, sorts
  first, and a warning counts the things and edges that differ and names the first. `diff` on
  the two maps names the fields.
- **Header.** `minus` keeps the first map's header. `join` and `common` merge the inputs':
  `packs`, `roots` and the kind lists hold each item of every input once, sorted; `generated_by`
  and `settings` hold each input's value once, sorted and joined with `; `, so a result of two
  builds says `periplus 0.8.0; periplus 0.9.0`; `marks` and `legend` are merged by key. The
  counts, the type hierarchy and the legend are then made from what the result holds, as
  `extract` makes them. The file does not record the command or the input files, so the same
  inputs give the same bytes from any folder.
- **Order.** `join` and `common` give the same bytes whatever the order of their inputs, and list
  the inputs sorted by path. `minus` reads the first input apart and lists the others sorted.

Two maps of different `periplus_map_version`, or a single input, exit 2. A file that is not a map
exits 30. `--out` naming one of the inputs exits 27. In JSON: `command`, `inputs` (each with
`path`, `things` and `edges`), `things`, `edges`, `by_type`, `by_state`, `by_kind`, `out`,
`warnings` and `problems`.

### diff

```
periplus diff OLD NEW [--limit N] [--ids [--change added|removed|changed]...] [--format text|json]
```

Says what changed from the map `OLD` to the map `NEW`, with the compare `join` uses: things and
edges are matched by id and by kind, from and to. The text names the two maps, then the header
fields other than nodes, edges and counts whose values differ (`header: same` when none), then
counts: things added, removed and changed, each by type, and edges added, removed and changed,
each by kind. Each count line names the eight most frequent types or kinds and ends with `, and N
more types` (or `kinds`); `--limit 0` names them all. Then each list: a thing with its type (a removed thing's type in `OLD`), an edge as
`kind  from -> to`, and for a changed one the fields that differ, as `(locations, provenance)`.
Each list shows `--limit` rows (default 50; `0` shows all). A cut list ends with `showing N of
TOTAL`, and the report then ends with `--limit 0 prints every row`; the totals above it are never
cut. `--ids` prints the ids of the things added, removed and changed, never cut; `--change`,
repeated, keeps the changes named. `--change` without `--ids` exits 2. In JSON: `command`, `maps`
(each with `path`, `things` and `edges`), `header`, `things` and `edges` (each with `added`,
`removed` and `changed`, each a cut list whose items hold `id`, `type` and `fields`, or `kind`,
`from`, `to` and `fields`), `things_by_type`, `edges_by_kind`, `warnings` and `problems`.

Between two builds of one project, it is the change a pull request makes to the map. Between the
whole map and a slice, it is what the slice leaves out.

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

## Descriptions

### undescribed

```
periplus undescribed [ID...] [--by file|type|container] [--parts-too] [--ids] [--map PATH] [--format text|json]
```

Counts the main things that `.periplus/descriptions.yaml` has no entry for under `nodes`: in the
whole map, or among the `ID`s. Entries under `edges` do not count. The first line says `described N of M main things`. A main thing is
what the `periplus-describe` skill describes, and the rule uses the map alone:

- it is mapped and has a location;
- it is not in supporting code, by the map's `supporting_paths`;
- its type is not a part type. A type is a part type when more than half of its mapped, located
  things nest inside another node by their id, as `at` reads nesting, and have no node nesting
  inside them: a parameter or a call site, read as part of the method that holds it.

A `left out:` line counts the rest: the parts by type, the things in supporting code, and those not
mapped or with no location. A `part types:` line then names each part type met, with its share:
the percent, rounded down, of its mapped, located things in the whole map that nest inside another
thing and hold none. Over 50 makes a part type, so a share near 50 is a close call. `--parts-too`
counts the things of part types as main things; the line then ends `counted as main things
(--parts-too)`. Then the undescribed things are counted by file (the default), by type
(`--by type`) or by container (`--by container`): the first grouping container of the thing or of
what holds it, `(no container)` for none. `--ids` prints their ids by file, line, then id. A
descriptions file that is not YAML or does not match its schema exits 30. In JSON: `command`,
`by`, `main`, `described`, `counts` (each with `key`, `null` for no container, and `count`),
`undescribed` (the ids), `left_out` (`parts` by type, `supporting`, `unplaced`), `part_types`
(each with `type` and `share`), `parts_too`, `warnings` and `problems`.

### order

```
periplus order ID... [--ids] [--map PATH] [--format text|json]
```

Prints the things the `ID`s name so that each comes after the things of the set it calls or uses:
a thing uses another when an edge between them is of a kind whose cause, as `periplus legend`
shows it, is `from` (the user is the from end) or `to` (the user is the to end). A `none` or
`touch` kind orders nothing. A kind under no cause list goes by its raw direction, its from end the
user, and a last line names it; on a map with no cause list every kind does, but a grouping kind,
and a last line says so. Things that use each other through a chain are a loop: they print
together, by place, each marked `[loop N]`. Ties go by the first file and line, then id. The text
prints `N things, M loops`, then one row a thing. Describing the things in this order reads each
callee before its callers. In JSON: `command`, `things` (each a row with `loop`, a number or
`null`), `warnings` and `problems`.

### stamp

```
periplus stamp [--all] [--map PATH] [--format text|json]
```

Writes into each node entry of `.periplus/descriptions.yaml` that has none a `fingerprint`: the
first 16 hex digits of the SHA-256 of the code the entry describes. That code runs from the node's
first location to the line before the next mapped thing of the same file, on a later line, that
the node does not hold, as `at` reads holding; or to the end of the file. Blank lines at its end
are left out. So a method's code ends where the next method starts, and a class holds its methods.
`--all` writes a fresh fingerprint into every node entry.

`stamp` adds one line, `fingerprint: '<digits>'`, after the entry's `line` key, at its indent, or
replaces the value of the entry's `fingerprint`. No other byte of the file changes: comments, order,
quoting and line endings stay. An entry written inline, `{text: ...}`, an entry whose node the map
does not hold, and one whose code cannot be read are skipped and listed with why. If the file read
back would differ in anything but the fingerprints, nothing is written and it exits 30; a file
that cannot be written exits 27. Run `periplus map` first, so the lines are the code's. The map
never reads the descriptions file, so its bytes do not depend on it, and a file without
fingerprints loads as before. Edge entries are not stamped. In JSON: `command`, `found` (false
without a descriptions file), `stamped`, `kept`, `skipped` (each with `id` and `reason`) and
`problems`.

### stale

```
periplus stale [--ids] [--map PATH] [--format text|json]
```

Compares each stamped node entry's fingerprint with its code now, as `stamp` reads it. Entries
under `edges` are skipped. The first
line counts the node entries: fresh, changed, gone (the map holds no node of that id), unreadable
(the code cannot be read) and not stamped. Then it lists the changed, the gone and the unreadable
entries under a heading each. `--ids` prints the changed, then the gone, then the unreadable ids.
In JSON: `command`, `found`, `entries`, `fresh`, `changed`, `gone`, `unreadable`, `unstamped` and
`problems`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The report printed. An empty result is still 0. |
| 2 | A bad option, such as `--depth 0` outside `slice`, `--raw` with `--touch` or with several `ID`s, `--ids` with `--format json`, `-` that reads no id, `slice` with no start, `slice --direction out` or `in`, `slice --ids` with `--out`, `slice --from` with `WORDS`, `at` with no line number of 1 or more, or `diff --change` without `--ids`. `join`, `common` or `minus` with one map, or `join`, `common`, `minus` or `diff` with maps of different versions. A walk on a map with no cause list from several `ID`s. |
| 17 | The map file that `slice --out`, `extract`, `join`, `common` or `minus` would write does not pass the map schema, because a map it was made from does not. Nothing is written. Run `periplus check-map` on that map. |
| 27 | `slice --out` or `extract --out` names the map being read, `--out` of `join`, `common` or `minus` names one of its inputs, or the file cannot be written; or `stamp` cannot write the descriptions file. |
| 29 | No map to read: no project above the working directory, a missing file at the path, or an unreadable file. Run `periplus map`, or fix the file's permissions. |
| 30 | The file is not a map: not JSON, missing the outline (`periplus_map_version`, `nodes`, `edges`), or damaged below the outline, a node or edge row malformed. Also a descriptions file a command reads that is not YAML or does not match the descriptions schema, or one `stamp` cannot change without changing other text. |
| 31 | An id names no node in the map, or a short name fits more than one node; or `slice --out` has no start, as when its words match nothing. |
| 32 | `slice --out` holds more things than `--limit` allows. |
| 141 | Standard output was closed before the report was written, as when the output is piped into `head`. Nothing more is printed. |

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
settings into `.periplus/`, and add two Python files and a descriptions file. Replace
`/path/to/periplus` with the checkout.

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

The descriptions file describes two things. The first carries a fingerprint that does not match
its code, so `stale` has something to show:

<!-- nav-file: .periplus/descriptions.yaml -->
```yaml
nodes:
  typer.app::shop.cli.app:
    text: The shop's command-line app.
    file: shop/cli.py
    line: 4
    fingerprint: '0000000000000000'
  typer.command::shop.cli.app:hello:
    text: The hello command; it runs greet.
    file: shop/cli.py
    line: 7
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
periplus find: 1 thing (1 main), 3 edges
main by type: python.function 1
edges by kind: calls 1, contains 1, imports 1

python.function::shop.tools.helper  python.function  mapped  shop/tools.py:1
      | def helper():

edges:
  imports  cli -> tools  shop/cli.py:2  [source]
      | from shop.tools import helper
  calls  cli -> helper  shop/cli.py:9  [source]
      | helper()
  contains  tools -> helper  shop/tools.py:1  [source]
      | def helper():
```

<!-- nav-run -->
```console
$ periplus find shop --type python.function --limit 100
periplus find: 2 things (2 main), 0 edges
main by type: python.function 2
showing 1 of 2 things; all: periplus find shop --type python.function --limit 0

python.function::shop.cli.greet  python.function  mapped  shop/cli.py:8
      | def greet():
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

See what the `shop.cli` module sets off by its imports. Each row names the kind that reached it
and where that edge is written. A row prints the short name where one fits, and `:2` says the
edge is in the file of the row above:

<!-- nav-run -->
```console
$ periplus neighbors python.module::shop.cli --kind imports
periplus neighbors python.module::shop.cli
sets off:     1 hop, 2 things; 0 hubs stopped
cli  python.module  mapped  start  shop/cli.py:1
  tools  python.module  mapped  imports  :2
  python.module::typer  python.module  referenced  imports  :1
```

The same walk with full ids and paths:

<!-- nav-run -->
```console
$ periplus neighbors python.module::shop.cli --kind imports --full
periplus neighbors python.module::shop.cli
sets off:     1 hop, 2 things; 0 hubs stopped
python.module::shop.cli  python.module  mapped  start  shop/cli.py:1
  python.module::shop.tools  python.module  mapped  imports  shop/cli.py:2
  python.module::typer  python.module  referenced  imports  shop/cli.py:1
```

The ids alone, for another command to read; the count goes to standard error:

<!-- nav-run -->
```console
$ periplus neighbors python.module::shop.cli --ids
python.module::shop.cli
python.function::shop.tools.helper
python.function::typer.Typer
python.module::shop.tools
python.module::typer
5 ids
```

See what sets the helper off, named by its short name. The `calls` edge runs from the module to
the helper, so the walk follows it backward, `(rev)`:

<!-- nav-run -->
```console
$ periplus affected helper
periplus affected python.function::shop.tools.helper
set off by:   1 hop, 1 thing; 0 hubs stopped
helper  python.function  mapped  start  shop/tools.py:1
  cli  python.module  mapped  calls (rev)  shop/cli.py:9
warning: resolved 'helper' to python.function::shop.tools.helper
```

The module `shop.tools` contains the helper, and `contains` is structure: it sets nothing off, so
the walk by cause leaves it out. The raw walk follows every edge that arrives, whatever its kind:

<!-- nav-run -->
```console
$ periplus affected helper --raw
periplus affected python.function::shop.tools.helper
2 items
  1  python.module::shop.cli  python.module  mapped  via calls to python.function::shop.tools.helper  shop/cli.py:9
      | helper()
  1  python.module::shop.tools  python.module  mapped  via contains to python.function::shop.tools.helper  shop/tools.py:1
      | def helper():
warning: resolved 'helper' to python.function::shop.tools.helper
```

Ask how far the walks from the module go before listing them:

<!-- nav-run -->
```console
$ periplus depth python.module::shop.cli
periplus depth python.module::shop.cli
sets off:     1 hop, 4 things; 0 hubs stopped
set off by:   0 hops, 0 things; 0 hubs stopped
```

What the module sets off that nothing else sets off. Nothing else in this project calls the
helper or imports the tools module, so all four are kept:

<!-- nav-run -->
```console
$ periplus only python.module::shop.cli
periplus only python.module::shop.cli
sets off:     1 hop, 4 things; 0 hubs stopped
only through the starts: 4 of 4
  helper  python.function  mapped  hop 1  shop/tools.py:1
  typer.Typer  python.function  unresolved  hop 1  no location
  tools  python.module  mapped  hop 1  shop/tools.py:1
  python.module::typer  python.module  referenced  hop 1  no location
```

All of the above for the module, in one reply: the `depth` report, the `only` line, then each walk
with what `only` returns tagged `[only]`. Nothing was cut, so no part names another command:

<!-- nav-run -->
```console
$ periplus reach python.module::shop.cli
periplus reach python.module::shop.cli

periplus depth python.module::shop.cli
sets off:     1 hop, 4 things; 0 hubs stopped
set off by:   0 hops, 0 things; 0 hubs stopped
only through the starts: 4 of 4 things set off, tagged [only]; all: periplus only python.module::shop.cli

periplus neighbors python.module::shop.cli
sets off:     1 hop, 4 things; 0 hubs stopped
cli  python.module  mapped  start  shop/cli.py:1
  helper  python.function  mapped  calls  :9  [only]
  typer.Typer  python.function  unresolved  calls  :4  [only]
  tools  python.module  mapped  imports  :2  [only]
  python.module::typer  python.module  referenced  imports  :1  [only]

periplus affected python.module::shop.cli
set off by:   0 hops, 0 things; 0 hubs stopped
cli  python.module  mapped  start  shop/cli.py:1
```

The walk from the module stops at no hub:

<!-- nav-run -->
```console
$ periplus hubs python.module::shop.cli
periplus hubs python.module::shop.cli
sets off: 0 hubs (more than 40 links to follow)
```

This example's rutters declare no grouping kind, so a module holds no members here; on a map whose
rutters do, `members` lists them by type:

<!-- nav-run -->
```console
$ periplus members python.module::shop.cli
periplus members
members of cli: 0
```

Split three items into the groups edges join. The tools module contains the helper; nothing among
the three joins `greet`:

<!-- nav-run -->
```console
$ periplus pieces helper greet python.module::shop.tools
periplus pieces
3 things in 2 pieces
piece 1: 2 things
  helper  python.function  mapped  shop/tools.py:1
  tools  python.module  mapped  :1
piece 2: 1 thing
  greet  python.function  mapped  shop/cli.py:8
warning: resolved 'helper' to python.function::shop.tools.helper
warning: resolved 'greet' to python.function::shop.cli.greet
```

Count a set. An id that names nothing is listed, not an error:

<!-- nav-run -->
```console
$ periplus count python.module::shop.cli helper greet nope
periplus count
4 ids given: 3 things in the map, 1 not; 2 by a short name
by type: python.function 2, python.module 1
by state: mapped 3
edges among them: 2 (calls 1, contains 1)
not in the map:
  nope
```

Find the chain from the module to the helper. Edges are followed in their own direction, so the
reverse query finds none:

<!-- nav-run -->
```console
$ periplus path python.module::shop.cli python.function::shop.tools.helper
periplus path python.module::shop.cli python.function::shop.tools.helper
1 shortest chain
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

Print what lies around the helper in one call: what the walks by cause reach from it, two hops
each way, each thing under its file with its links among them. Nothing calls into the module, so
the walk by stops at it:

<!-- nav-run -->
```console
$ periplus slice helper
periplus slice
start helper  python.function  (given as 'helper')
sets off:     0 hops, 0 things; 0 hubs stopped
set off by:   1 hop, 1 thing; 0 hubs stopped
paths under: shop/

piece 1 of 1: 2 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
      calls <- cli
      +1 more link: contains <- 1; see periplus show helper --limit 0

cli.py
  :1  cli  python.module
      | import typer
      calls -> helper
      +4 more links: imports -> 2, calls -> 1, contains -> 1; see periplus show cli --limit 0

inventory: 2 nodes
  python.function 1: helper
  python.module 1: cli
warning: resolved 'helper' to python.function::shop.tools.helper
```

The same ids, for another command; `affected helper --ids` lists the same two, since the helper
sets nothing off:

<!-- nav-run -->
```console
$ periplus slice helper --ids
python.function::shop.tools.helper
python.module::shop.cli
2 ids
warning: resolved 'helper' to python.function::shop.tools.helper
```

From the module, cut to two things past the start: the slice says what it left out and names the
`neighbors` and `affected` commands that print each walk in full, and `cli` counts the links it no
longer shows:

<!-- nav-run -->
```console
$ periplus slice python.module::shop.cli --limit 2
periplus slice
start cli  python.module  (given as 'python.module::shop.cli')
sets off:     1 hop, 4 things; 0 hubs stopped
set off by:   0 hops, 0 things; 0 hubs stopped
paths under: shop/

piece 1 of 1: 3 things, starts: cli

cli.py
  :1  cli  python.module
      | import typer
      calls -> helper (+1 outside the project: typer.Typer)
      +3 more links: imports -> 2, contains -> 1; see periplus show cli --limit 0

tools.py
  :1  helper  python.function
      | def helper():
      calls <- cli
      +1 more link: contains <- 1; see periplus show helper --limit 0

inventory: 3 nodes
  python.function 2: helper, typer.Typer
  python.module 1: cli
showing 2 of 4 things past the starts
left out by hop: 1: 2
left out by kind: imports 2
narrow with --kind K (kinds here: imports, calls), --direction off or --direction by
in full, each part this slice holds:
  sets off: periplus neighbors cli --depth 2 --limit 0
  set off by: periplus affected cli --depth 2 --limit 0
```

Start from plain words. Neither names a node, and the two together match nothing, so each word
is searched alone. Both find the helper; one start is asked for, so a line counts the match left
out and names `find`:

<!-- nav-run -->
```console
$ periplus slice tool help --starts 1 --depth 1
periplus slice
no node matches 'tool help' as a whole; started from its words
start helper  python.function  (words: 'tool' in id, 'help' in id)
+1 more node matches the words: periplus find WORD --limit 0 for each of: tool, help; start from any with periplus slice --from ID
sets off:     0 hops, 0 things; 0 hubs stopped
set off by:   1 hop, 1 thing; 0 hubs stopped
paths under: shop/

piece 1 of 1: 2 things, starts: helper

tools.py
  :1  helper  python.function
      | def helper():
      calls <- cli
      +1 more link: contains <- 1; see periplus show helper --limit 0

cli.py
  :1  cli  python.module
      | import typer
      calls -> helper
      +4 more links: imports -> 2, calls -> 1, contains -> 1; see periplus show cli --limit 0

inventory: 2 nodes
  python.function 1: helper
  python.module 1: cli
```

List what the map holds in a file, line by line:

<!-- nav-run -->
```console
$ periplus in shop/cli.py
periplus in
shop/cli.py: 4 things
  cli  python.module  mapped  :1
  app  typer.app  mapped  :4
  hello  typer.command  mapped  :7
  greet  python.function  mapped  :8
```

Go from a line of code, such as a search hit on `helper()`, to the thing that holds it. Line 9
holds no mapped thing, so the nearest above answers:

<!-- nav-run -->
```console
$ periplus at shop/cli.py:9
periplus at
shop/cli.py:9  nearest above: :8
  greet  python.function  mapped  :8
```

Count a set by file:

<!-- nav-run -->
```console
$ periplus files greet helper python.module::shop.cli python.module::typer
periplus files
4 things in 2 files
  2  shop/cli.py
  1  shop/tools.py
no location: 1
warning: resolved 'greet' to python.function::shop.cli.greet
warning: resolved 'helper' to python.function::shop.tools.helper
```

See what is left to describe. The two things with no location are not main things:

<!-- nav-run -->
```console
$ periplus undescribed
periplus undescribed
described 2 of 6 main things; 4 undescribed
left out: 2 not mapped or with no location
by file:
  2  shop/cli.py
  2  shop/tools.py
```

<!-- nav-run -->
```console
$ periplus undescribed --ids
python.module::shop.cli
python.function::shop.cli.greet
python.function::shop.tools.helper
python.module::shop.tools
4 ids
```

Order a set so that each thing comes after what it uses. The module uses the helper and the tools
module, and the app runs the command registered on it, so the command comes before the app:

<!-- nav-run -->
```console
$ periplus order python.module::shop.cli python.module::shop.tools greet helper hello app
periplus order
6 things, 0 loops; each after what it calls or uses
  hello  typer.command  mapped  shop/cli.py:7
  app  typer.app  mapped  :4
  greet  python.function  mapped  :8
  helper  python.function  mapped  shop/tools.py:1
  tools  python.module  mapped  :1
  cli  python.module  mapped  shop/cli.py:1
warning: resolved 'greet' to python.function::shop.cli.greet
warning: resolved 'helper' to python.function::shop.tools.helper
warning: resolved 'hello' to typer.command::shop.cli.app:hello
warning: resolved 'app' to typer.app::shop.cli.app
```

Check the descriptions against the code. The app's fingerprint does not match, and the command's
entry has none yet:

<!-- nav-run -->
```console
$ periplus stale
periplus stale
2 node entries: 0 fresh, 1 changed, 0 gone, 0 unreadable, 1 not stamped
changed:
  app  typer.app  mapped  shop/cli.py:4
```

Stamp the entry that has no fingerprint. The app keeps its own until its description is checked
and `stamp --all` runs:

<!-- nav-run -->
```console
$ periplus stamp
periplus stamp
stamped 1 node entry; 1 kept the fingerprint they had
```

Cut two features out of the map and combine them. Extract the command and what it runs, and the
module's own parts:

<!-- nav-run -->
```console
$ periplus extract hello greet helper --out hello.map.json
periplus extract
wrote /path/to/project/hello.map.json: 3 nodes, 0 edges
warning: resolved 'hello' to typer.command::shop.cli.app:hello
warning: resolved 'greet' to python.function::shop.cli.greet
warning: resolved 'helper' to python.function::shop.tools.helper
```

<!-- nav-run -->
```console
$ periplus extract python.module::shop.cli greet app --out cli.map.json
periplus extract
wrote /path/to/project/cli.map.json: 3 nodes, 1 edge
warning: resolved 'greet' to python.function::shop.cli.greet
warning: resolved 'app' to typer.app::shop.cli.app
```

Join them into one map file:

<!-- nav-run -->
```console
$ periplus join hello.map.json cli.map.json --out both.map.json
periplus join
inputs: cli.map.json (3 things, 1 edge), hello.map.json (3 things, 0 edges)
result: 5 things, 1 edge
by type: python.function 2, python.module 1, typer.app 1, typer.command 1
by state: mapped 5
edges by kind: contains 1
wrote /path/to/project/both.map.json: 5 nodes, 1 edge
```

What the two features share, and what the command has that the module's parts do not:

<!-- nav-run -->
```console
$ periplus common hello.map.json cli.map.json
periplus common
inputs: cli.map.json (3 things, 1 edge), hello.map.json (3 things, 0 edges)
result: 1 thing, 0 edges
by type: python.function 1
by state: mapped 1
edges by kind: none
```

<!-- nav-run -->
```console
$ periplus minus hello.map.json cli.map.json --ids
python.function::shop.tools.helper
typer.command::shop.cli.app:hello
2 ids
```

What changes from one to the other:

<!-- nav-run -->
```console
$ periplus diff cli.map.json hello.map.json
periplus diff
old: cli.map.json (3 things, 1 edge)
new: hello.map.json (3 things, 0 edges)
header: type_hierarchy
things: 2 added, 2 removed, 0 changed
  added by type: python.function 1, typer.command 1
  removed by type: python.module 1, typer.app 1
edges: 0 added, 1 removed, 0 changed
  removed by kind: contains 1
things added:
  python.function::shop.tools.helper  python.function
  typer.command::shop.cli.app:hello  typer.command
things removed:
  python.module::shop.cli  python.module
  typer.app::shop.cli.app  typer.app
edges removed:
  contains  python.module::shop.cli -> python.function::shop.cli.greet
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
