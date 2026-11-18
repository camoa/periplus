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
- Make no claim about the rest of the codebase: no callers, no "only", "unused" or "never
  called", no installed or on/off state. Marks and config values carry those. An entry that
  speaks only of its own code stays true until that code changes, so `periplus stale` can find
  the entries to redo.
- One or two plain sentences, with the words a person would search for: the feature, the
  business term, the effect a user sees. Never restate the id, the type or the source line.
- Edge entries are short phrases, only for links where something happens, such as a call, a use,
  an alter, a redirect, a read or a write. Say what happens, by its meaning. Write them while the
  node's code is open.
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
[Navigation](https://github.com/camoa/periplus/blob/v0.9.2/docs/navigation.md#undescribed).

## Recommendations

These are ways that tend to work, not required steps.

- Work file by file: `periplus undescribed` names the files, `periplus in FILE --ids` the things
  in one.
- Describe callees before callers, so you know what each call does when you read the caller.
  Pipe a set into `periplus order` to get that order:

```
periplus in src/Mail/Reminder.php --ids | periplus order - --ids
```

- To describe a flow, start at its entrance, a thing that `periplus depth` says nothing sets
  off. Take what it sets off, in order, and stop when none is left undescribed:

```
periplus neighbors ENTRANCE --depth all --ids | periplus order - --ids
periplus neighbors ENTRANCE --depth all --ids | periplus undescribed -
```

- For each thing, read `periplus show ID` before its code. The entries under its links say what
  the things it calls do. Put what you learn about a step in the link's entry, not in the node's.
- An entry is a hint, and the code decides. When the code you read contradicts an entry, of this
  thing or of one it links to, rewrite that entry.
- To see how much of one file is described, in the whole map or in a working set:

```
periplus in FILE --ids | periplus undescribed -
```

- A cheaper model can write the entries, with a stronger model reading a small sample of each
  batch against the code.
- Run `periplus stamp` after writing.

## The file

Two top-level keys. `nodes` maps a node id to its entry. `edges` is a list of entries, each with
`from`, `kind` and `to` exactly as the map writes them, since an edge has no id. Every entry
carries `text`, and `file` and `line`: where you read the code. `fingerprint` is written by
`periplus stamp`; do not write it by hand. Keep `nodes` sorted by id and `edges` by `from`,
`kind`, `to`, so a new pass adds lines without moving old ones. The exact shape is in
[the descriptions schema](https://github.com/camoa/periplus/blob/v0.9.2/src/periplus/skills/periplus-map/references/descriptions.schema.json).

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
