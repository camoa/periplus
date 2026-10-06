# The engine

What the tool must do, in order, and what it must refuse. The four schemas in `schema/` are
the machine-checkable half; this is the half a person builds against.

Every requirement here comes from something that happened. Where a line exists because
something broke, the measurement is beside it.

## What the engine is

A program that reads packs and a settings file, opens source files, and writes a map.

It contains no knowledge of any language, framework, or file format. Every construct name,
condition, id part and emit target comes from a pack. The test is mechanical: the string
`php`, `go`, `drupal`, `twig` must not appear in the engine outside a comment.

It is not a server, a daemon, a database, or a language server. It runs, writes a file, and
exits.

## The run, in order

The order is not an implementation detail. Two steps of it are load-bearing and named as
such below.

### 1. Resolve settings

Read the project settings file. It names the packs, and it may override any folder a pack
declares. Absent settings is an error, not a default — the engine must not guess where a
repository keeps its configuration.

### 2. Resolve the pack graph, and build the type table

**Before any source file is opened.** A pack may only name a type it declares or that a pack
in its dependency graph declares; that check runs here, against zero source files, and a
violation fails the run.

Packs form a directed acyclic graph, not a chain. Contributions merge additively and without
depending on order, because a graph has no single load order to appeal to. Two files
declaring the same type is a conflict and fails. Two files contributing rules to one type is
ordinary.

There are no kinds of pack. A pack with nothing beneath it is a root and need not be a
language. If any level were special, a third party could not occupy it.

### 3. Select files

From the folders each rule names, filtered by the extensions packs claim, minus every
exclusion.

Exclusion is not the boundary. A boundary file is unread and the things inside it may still
be nodes, because first-party code names them. An excluded file does not exist as far as the
map is concerned, not even as the target of a reference, and the check happens here, before
anything parses. A settings file may exclude what a pack would read and re-include what a
pack excluded; the project has the last word in both directions.

### 4. Run source rules

Every rule whose `reads` is `file`, over every selected file, in any order. They cannot see
each other, which is why their order does not matter.

A file is opened as a parse tree when a pack claims its extension and declares a grammar,
and as text otherwise. A pack with no grammar is legal and complete — `packs/twig` maps
templates with patterns alone.

### 5. Run map rules to a fixpoint

Every rule whose `reads` is `map`, repeatedly, until nothing changes.

It terminates because a pass may only add attributes or refine a type downward through a
hierarchy the packs declare, and that hierarchy is finite. Nothing moves back up.

The engine must report how many passes ran and which rules fired in each. The fixpoint hides
its own sequencing, and when a classification comes out wrong, "it fired in pass three off a
type assigned in pass two" is the only thing that makes it traceable.

### 6. Merge and resolve

Nodes merge on their id. Edges merge on `(kind, from, to)`; their locations accumulate and
`occurrences` is the count. Deduplicating per pair and discarding the rest was measured at
186 caller functions against 303 call sites, and one pair in a real map had 58.

An endpoint naming no node becomes one, per the pack's `emit_boundary_nodes` rule —
`declared` when a pack describes it, `referenced` when nothing does. Doing this took dangling
edges in one real map from 792 of 884 to zero.

### 7. Emit

Canonical JSON. Keys in a fixed order, arrays sorted by a declared key, LF, no trailing
whitespace, no timestamps, no absolute paths.

## What it must refuse

A run fails, loudly, on any of these. None of them may be a warning.

- A pack naming a type nothing in its dependency graph declares.
- Two packs declaring the same type.
- An edge whose endpoints are not legal for its kind.
- An unknown key anywhere in a pack. Three separate silent failures in one day came from
  keys that read fine and did nothing: `on:` parsed as the boolean `true` in five rules; two
  `id:` keys in one mapping discarded 48 rule names; a duplicate `pack:` key threw away a
  whole file.
- A rule shape the engine cannot execute. The spike printed these and ran on, which is the
  minimum; refusing is better, because a map missing a third of its rules is worse than no
  map.
- A grammar version that does not match what the pack pinned.

## What it must report

- Which rules fired, and how many times each.
- How many passes the fixpoint took.
- Every rule that matched nothing. A rule that fires zero times is either dead or broken,
  and the difference matters.
- Every unresolved node, with what the rule looked for and what it found. "Unresolved" alone
  is a shrug. The entry has to read as "add an anchor for this symbol", not "unknown".

## What it must never do

**Guess.** Where a rule cannot resolve something, it emits an unresolved node recording the
attempt. It never emits an edge to a name it could not resolve. The spike did, and produced
221 call edges to bare words — `Draft -> t`, where `t` is a translation method.

**Write prose.** Nothing a model wrote enters the map. The determinism gate extracts twice
and byte-compares; a model writing during extraction fails on the first run. Descriptions are
a separate committed artifact keyed by node id, joined through each node's `source_hash`.

**Carry advice.** A pack may recommend; the map holds the count and the pack holds the note,
joined at read time.

**Depend on locale, working directory, or filesystem order.** Proven by running twice and
byte-comparing, including under a Turkish locale, where `I` does not lowercase to `i`.

## Open, and deliberately not decided here

- **Cardinality.** Nothing expresses that a class extends one class and implements many. A
  second `inherits` edge on one PHP class would sit in a map looking fine. It belongs on the
  edge kind, per pack, because Go has no `inherits` at all and a Go struct embeds many.
- **Descriptions.** The join exists; the artifact has no schema.
- **Incremental runs.** Every run is a full run. `source_hash` is the obvious lever.
- **Addressing inside a data file.** `each: "services.*"` is one underspecified line, and two
  packs need it.
