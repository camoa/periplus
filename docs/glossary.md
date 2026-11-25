# Glossary

This page gives each word Periplus uses one meaning, in one or two sentences. The docs, the
skills and the command output use the words this way. The last section separates pairs of ideas
that are easy to mix up.

## Words

### cause

What each edge kind says about which end sets off the other. `from`: the from end sets off the
to end, as a function calls another. `to`: the to end sets off the from end, as a hook runs the
function that implements it. `none`: structure, as a module contains a function. `touch`: the
from end only points at the to end, as a link names a route. `periplus legend` prints the cause
of each kind.

### confidence

How sure a rule is, declared on the rule and never decided at run time. `declared`: the file
states the thing. `inferred`: the rule relies on a convention, such as a naming pattern.
`mentioned`: the rule links two things only because a name is written as text.

### coverage

What the loaded rutters look for. Periplus gives no single coverage number. The map report
names the files that no rule read, and each pinned rutter that selected no file.

### description

A sentence or two in plain words that says what one thing does. Descriptions live in
`.periplus/descriptions.yaml`, beside the map. `periplus find` searches them, and command rows
print them after `#`. Use the words that set a thing apart, and do not name the other meaning:
`periplus find` matches every word.

### edge

A link between two nodes, such as a call from one function to another. Each edge has a
kind, its two ends, the file and line where the link is written, and the rule that found it.

### edge kind

The name of one sort of link, such as `calls` or `waits_for`. A rutter declares each kind with
the node types its ends may have. The engine refuses an edge of a kind that no rutter declared.

### engine

The program that reads the files, runs the rules and writes the map. Knowledge of a language or
a framework belongs in rutters, never in the engine. When rules cannot express a pattern, the
engine gains a general ability that every rutter can use.

### entrance

A thing that sets something off, while nothing in the map sets it off. `periplus depth IDS --entrances` lists the entrances among many ids.

### evidence

What lets you check a node or an edge against the code. Each carries its `provenance`, the
rutter, rule and confidence that made it, and its `locations`: for an edge, the file and line where
it was found; for a node found in the code, its own. A node only named by an edge has none.
`periplus show` also prints the source line under each edge.

### fingerprint

A short hash of the code that a description entry describes. `periplus stamp` writes it into
each node entry. Edge entries get none.

### fresh

A map is fresh when `periplus map` run now would write it as it is: the files the rules read, the
settings, the rutters and the tool are the ones it was built from. `periplus fresh` checks this
against the inputs record that `map` writes beside the map, `.periplus/map.inputs.json`.

### gap

Something the code holds and the map lacks. Some gaps leave a mark, such as a `referenced` or
`unresolved` node, or a row the map report lists as skipped. A silent gap leaves none: it shows
only as a wrong or missing answer. A gap closes with a rule.

### hub

A thing with more links to follow than `--hub N`, 40 by default. A walk lists a hub and does
not go on from it. A hub is often shared code: walk on with `--through ID` only when it belongs
to the topic.

### map

The JSON file that `periplus map` writes, `.periplus/map.json`. It holds the nodes and edges
that the rules found. The same code, settings and rutters, on the same version of Periplus, give
the same map, byte for byte.

### node

One thing in the map, such as a class, a route, a template or a setting. Each node has an id,
a type, a state and the rule that found it. A node found in the code has its file and line, and a
node only named by an edge has none.

### node type

The name of one sort of thing, such as `php.class` or `chores.chore`. A rutter declares each
node type. A rule may emit only the types its rutter declares, or that a rutter it depends on
declares.

### rim

The things one hop from a set, in either direction, that are not in the set. Read the rim
before you call a set complete, and give a reason for each thing you leave out.

### rule

One entry in a rutter that finds one kind of thing or link. A file rule reads files. A map rule
reads the map that earlier rules made and joins what they found.

### rutter

A folder of YAML files that holds the knowledge of one stack: its folders, its file types, its
node types and edge kinds, and its rules. File names and settings call a rutter a *pack*, so it
lives in a folder named `<pack>@<version>` and is pinned under `packs`.

### shared thing

A thing that code writes and other code reads, such as a variable handed to a template, a
config value or a global. Writers and readers both point at it, so a walk off ends there and does not reach the readers.
`periplus show THING` lists every reader and writer.

### skill

A folder of instructions that tells an AI agent how to use Periplus for one kind of work.
Periplus ships seven: `periplus-setup`, `periplus-map`, `periplus-analyze`, `periplus-describe`,
`periplus-document`, `periplus-gaps` and `periplus-rutter`.

### slice

A map file that holds a part of the map, written by `periplus slice --out FILE`, `extract`,
`join`, `common` or `minus`. Every command that takes `--map` reads it as a map.

### stale

A description entry whose code changed since `periplus stamp` wrote its fingerprint, or whose
node is gone. `periplus stale` lists them, and each term with an id the map no longer holds, so
you know which entries to write again.

### state

How the map knows a node, one of five. `mapped`: a rule found the thing in the project's files.
`boundary`: it is outside the mapped code, and a rule says what it is. `unknown_boundary`: it
leaves the mapped code and no rule says what it is, or it is a call whose target is built at
run time. `unresolved`: a rule searched the mapped code for the name and found nothing.
`referenced`: a file names the thing, but no rule read where it is defined.

### term

What a word of the project means, and the things it names, written under `terms:` in the
descriptions file. `periplus find` prints the terms its words match, each meaning of a word.

### walk

Following edges by their cause, hop by hop. The walk off lists what a thing sets off, and the
walk by lists what sets it off. A walk does not follow `none` or `touch` kinds.

## Pairs that get confused

**The map and the code.** The map holds the things its rules found and the links between them,
each with a place. It does not hold what happens between the links: the condition around a call,
the order of two steps, or a step that is missing. The map says where to read. The code is what
you judge.

**A reference and a definition.** A `referenced` node is a name that a file uses, while no rule
read the place that defines it. A `mapped` node is one whose definition a rule found. A
reference to code outside the mapped folders, such as a framework's own code, stays `referenced`.

**A description and a fact in the map.** A rule makes each fact in the map, and it gives the
same fact on every run. A person or an agent writes a description, in its own file,
and it can go stale when the code changes. The map never reads the descriptions file.

**Fresh and stale.** `fresh` is about the map: whether the code, the settings, the rutters or the
tool changed since `periplus map` built it. `stale` is about a description: whether the code that
one entry describes changed since `periplus stamp`. A fresh map can hold stale descriptions.

**A gap in coverage and a limit of the engine.** A gap is almost always a rule that is not
written yet, and you close it in a rutter. A gap is the engine's only when no rule can state the
shape: two ways of writing the rule, each refused with an engine message.
[How Periplus behaves](../README.md#how-periplus-behaves) lists the known limits of the engine.

**Unresolved and unknown boundary.** `unresolved` means a rule searched the mapped code for a
name and found nothing. The link and its line are real, and the target is missing.
`unknown_boundary` means the link leaves the mapped code and no rule says where, or the target is
built at run time. For both, read the code at the line.
