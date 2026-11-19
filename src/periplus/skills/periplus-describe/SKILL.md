---
name: periplus-describe
description: Writes what the main things of a Periplus map do into .periplus/descriptions.yaml, each from its own code, so periplus find reaches them by plain words. Use when the user says describe this feature, this folder or this project, document these nodes, explain what this part of the map does, or fill the descriptions before a change, and when a map file made with periplus slice, extract, join, common or minus is the working set.
---

# Describe the things of a Periplus map

A description says what one thing does, in plain words. Entries live in
`.periplus/descriptions.yaml`, beside the map. `periplus find` searches them, and rows print
them after `#`, so a plain-word question reaches a thing whose id lacks those words.

## Rules

- Write from the thing's own code only. Open its file at its line and read the whole body. Never
  write from the name alone, and never generate entries by script.
- A class is described after its methods, from its own header and their entries. Each method
  has its own entry, so the class entry says what the class is for.
- Make no claim about the rest of the codebase: no callers, no "only", "unused" or "never
  called", no installed or on/off state. Marks and config values carry those. An entry that
  speaks only of its own code stays true until that code changes, so `periplus stale` can find
  the entries to redo.
- One or two plain sentences, with the words a person would search for: the feature, the
  business term, the effect a user sees. Never restate the id, the type or the source line.
- Edge entries are short phrases, only for links where something happens, such as a call, a use,
  an alter, a redirect, a read or a write. Say what happens, by its meaning. Write them while the
  node's code is open. They carry no fingerprint, and `periplus stale` does not list them: when
  you rewrite a node's entry, read its edge entries again.
- Keep an entry that exists, unless `periplus stale` lists it; then read the code again and
  rewrite it.
- An entry with no fingerprint was never checked against its code. `periplus stale` counts these
  as not stamped and does not list them. Read the code again and rewrite such an entry too.
- `periplus stamp` stamps every entry that has no fingerprint, in or out of your working set.
  Run it only when each of those was read against its code, or it marks an unread entry as fresh.
- A thing with several locations, such as a hook that several modules implement, is described
  from the code at its own locations, not from other files.
- Skip a thing with no location, or whose line holds nothing that fits it, and report it. When
  several lines in one file miss, the map is stale: tell the person to run `periplus map`.
- Write only the descriptions file. Never edit the map or a map file made from it.

Good: `Sends the payment reminder email to a customer whose invoice is overdue.`

Bad: `The ReminderMailer class.` (restates the id), `Called only by the nightly job.` (a claim
about other code).

## How the work goes

The words are those of the periplus-map skill. An **entrance** sets something off, and nothing in
the map sets it off. A **walk** follows what a thing sets off. A **slice** is a saved map file. A
slice read with `--map` is the map.

1. Know the working set: the map, or a slice read with `--map SLICE`. Give every command the
   same `--map`, so the walk stays inside the set. Keep the slice in the project's `.periplus`
   folder: a command given `--map` looks for the descriptions file from the slice's folder up.
2. Find its entrances. Give `periplus depth --entrances` all the set's ids; it lists the
   entrances. With `--map`, only links inside the set count. An id with nothing either way is a
   separate piece, left for step 6.
3. Take one entrance at a time and what it sets off in the set, callees before callers, as
   `periplus order` puts them. You then know what each call does when you read the caller.
4. Describe each file when the walk first reaches it: all of the set's undescribed things in that
   file, while it is open. Before each thing's code, read `periplus show ID`: the entries under
   its links say what the things it calls do. When a thing in the open file calls one that
   has no entry yet, describe that one first, then come back.
5. Write each entry into `.periplus/descriptions.yaml` as soon as it is written, so
   `periplus show` prints it for the next thing. An entry held back to the end helps no caller.
6. Then the things of the set that no entrance reaches, such as config, templates and separate
   pieces, file by file. `periplus undescribed` names what is left.
7. Have a sample read against the code, then run `periplus stamp`.

```
periplus find --map SLICE --ids | periplus depth --map SLICE - --entrances
periplus neighbors --map SLICE ENTRANCE --depth all --ids | periplus order --map SLICE - --ids
periplus in --map SLICE FILE --ids | periplus undescribed --map SLICE - --ids
periplus slice --map SLICE --from ENTRANCE --direction off --depth all --out FLOW-A.map.json
periplus common FLOW-A.map.json FLOW-B.map.json
```

When several writers share the work:
- Split by entrance or flow, not by a list of files.
- Things that several flows reach, such as a shared service, are written and saved first, so
  every writer reads them through `periplus show`. Save one slice per entrance;
  `periplus common` lists what two of them share.
- A writer's entries reach the descriptions file before any writer starts on things that call
  them. Two writers editing the file at once can lose each other's entries.
- A cheaper model can write. Before the stamp, a stronger model reads some entries of every
  batch or flow against the code.

## Tools

- `periplus undescribed` counts the main things with no entry, by file; `--ids` lists them.
- `periplus in FILE --ids` lists the ids of what the map holds in a file, in line order.
- `periplus order` puts a set in order, each thing after what it calls or uses.
- `periplus show ID` prints, under each link, the entry of the thing at the other end: what each
  thing it calls does, once that thing is described.
- `periplus stamp` writes a fingerprint of each entry's code into the entry.
- `periplus stale` lists the entries whose code changed since the stamp, and those whose node is
  gone.
- `periplus find` with an entry's words checks that the entry is reachable.

Each takes `--map PATH`, so a file written by `periplus slice`, `extract`, `join`, `common` or
`minus` works as the map. Options and output are in
[Navigation](https://github.com/camoa/periplus/blob/v0.10.0/docs/navigation.md#undescribed).

## Tips

- Put what you learn about a step in the link's entry, not in the node's.
- An entry is a hint, and the code decides. When the code you read contradicts an entry, of this
  thing or of one it links to, rewrite that entry.
- To see how much of one file is described, in the whole map or in a working set:

```
periplus in FILE --ids | periplus undescribed -
```

## The file

Two top-level keys. `nodes` maps a node id to its entry. `edges` is a list of entries, each with
`from`, `kind` and `to` exactly as the map writes them, since an edge has no id. Every entry
carries `text`, and `file` and `line`: where you read the code. `fingerprint` is written by
`periplus stamp`; do not write it by hand. Keep `nodes` sorted by id and `edges` by `from`,
`kind`, `to`, so a new pass adds lines without moving old ones. The exact shape is in
[the descriptions schema](https://github.com/camoa/periplus/blob/v0.10.0/src/periplus/skills/periplus-map/references/descriptions.schema.json).

- Quote a `text` that holds `: ` or ` #`; unquoted, YAML misreads it.
- Write ids with single backslashes, as `--ids` prints them. Text rows and raw JSON print each
  backslash twice.
- Copy an edge entry's `from`, `kind` and `to` from the map, as `periplus show` on the node lists
  the link. Never guess them from the meaning.

<!-- example descriptions: .periplus/descriptions.yaml -->
```yaml
nodes:
  php.method::Shop\Mail\Reminder::send:
    text: Sends the payment reminder email to a customer whose invoice is overdue.
    file: src/Mail/Reminder.php
    line: 24
edges:
  - from: php.method::Shop\Mail\Reminder::send
    kind: calls
    to: php.method::Shop\Mail\Mailer::deliver
    text: hands the reminder to the mailer
    file: src/Mail/Reminder.php
    line: 31
```
