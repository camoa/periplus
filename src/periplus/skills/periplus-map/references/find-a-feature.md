# Find everything that takes part in a feature

The goal is a set: everything connected to the feature and still related to it. You reach it by
following nodes and edges. Words only find where to start. You decide the words, how far to walk
and what stays in. The parts below are what the work holds; do them in the order that suits you.
A saved slice for the feature, read with `--map FILE`, is work you do not repeat: ask for one.

## Starts: few calls, widened words

The user's word may not be the code's. Put the word and its likely forms in one call with `--any`,
and read only the counts: `periplus find "invoice billing payment" --any --limit 1`. The counts by
type show where the words land. Then fetch rows for the types that matter with `--type`, or for one
folder with `--path`. One wide count and a few narrow fetches cost less than a call per word.
Drop what the words bring that is not the feature.

## Back to the entrances

A start is often in the middle of a flow. The set is found by walking out from its entrances: the
things nothing in the map sets off, such as a route or a hook the framework runs.
`periplus affected START --depth all` shows what sets the start off, hop by hop; the things at the
far end of each chain are the entrances. `periplus depth X` confirms one: nothing on its walk by.
No command lists entrances alone. Stop going back once a chain leaves the feature.

Words find what is named after the feature. But a feature is what it does to the system, and some
of its entrances carry other names. Name its few defining actions: for registration, what creates
an account; for login, what starts a session or checks a password; for invoicing, what writes or
sends an invoice. Find the things that do them, by word or with `periplus show` on a start, and
walk back from each with `periplus affected ID --depth all`. The far ends are entrances, whatever
their names. A defining action is often shared code or a framework method, so this walk can be
wide: ask `depth` first, and keep only the chains about the topic, up to where the action happens.

## Plan before you walk

Before any slice, a cheap answer should tell you roughly how big it will be and whether it leaves
the feature. A slice refused at the cap, or full of other features, means a planning question was
skipped. The replies below are cut to the lines that matter; how to read them is what to keep.

```
$ periplus depth invoice.view
sets off:     6 hops, 140 things; 62% within 2, 88% within 3, 97% within 5; 1 hub stopped (php.method::Logger::log)
set off by:   2 hops, 41 things; 0 hubs stopped
```

Hops are how far the walk goes before it reaches nothing new. The shares say how much lies near:
here most lies within 3, so `--depth 3` gets nearly all, and the tail can be judged apart. Things
times a share is roughly the slice at that depth, so the 500 cap shows before you hit it. A hub
stopped means the walk was cut at shared code; see Hubs below. A large "set off by" means much
depends on the thing: it is shared, and walking back from it pulls in other features. With
several ids, `depth` reports the total, and newer versions add a row per start. A total hides
which start drives the walk, so when the starts differ, ask per entrance. Then list the walk you
mean to save, and ask about its ids:

```
$ periplus neighbors invoice.view --depth 3 --ids | periplus count -
124 ids given: 124 things in the map
by state: mapped 102, unresolved 15, referenced 7
$ periplus neighbors invoice.view --depth 3 --ids | periplus files -
124 things in 9 files
  52  src/Invoice/InvoiceController.php
  11  src/Customer/CustomerRepository.php
$ periplus neighbors invoice.view --depth 3 --ids | periplus pieces -
124 things in 3 pieces
piece 1: 115 things
```

`count` is the size; many `unresolved` ends are links to read before the set is complete. In
`files`, a file you did not expect, holding many things, is where the walk left the feature. In
`pieces`, one large piece is one flow; small ones are a missing start or link, or do not belong.

`periplus only` lists what would go unused without the ids. It is not the feature's set: a shared
thing among the ids brings in all it sets off.

## Walk out and save

Walk off from the entrances, what they set off, and save as you go with `--out`. The walk off
rarely reaches tests; the walk by from a shared thing reaches every test and caller of it. A
saved slice keeps supporting code such as tests, though the printed slice hides it. No option
drops it from the file: `periplus files` shows how much there is; say so in the answer, and
leave it out with `periplus extract` and `periplus minus` when it does not belong.

A slice from words takes at most 12 starts, walks 2 hops by default, and with `--out` refuses
more than 500 things (exit 32). Do not fight these in one call. Make partial slices, one per
entrance or part, each at the depth its `depth` reply suggests, and combine them with
`periplus join A B --out FILE`.

## Hubs

A hub is a thing with more than 40 links to follow; the walk lists it and stops. `hubs` names
each with its hop and its fan, the links the walk would follow past it:

```
$ periplus hubs invoice.view
sets off: 1 hub (more than 40 links to follow)
  Logger::log  php.method  hop 3  fan 212
```

A large fan is usually shared code: a logger, a base class, a mailer. Walk through it with
`--through ID` only when it is part of the feature; otherwise name it as shared code the set uses.

## The rim

The rim is what lies one hop from the set, either way, and is not in it. It is where a set is
too small or too big. Read it, and for each thing decide: in, or out for a reason (shared code,
another feature, a test). A set whose rim was never read is not finished.

## Gaps on the way

When a set that should be one flow falls into pieces, or the code holds a link the map lacks,
that is a map gap. Report it with the file and line; the periplus-gaps skill records it. Do not
patch over it by adding things the map does not link.

## Code, descriptions and cost

The map comes first. Open code once the set is saved, to confirm a line or where a row is
`unknown_boundary`; see code-search.md beside this file. When you read the code of a thing with
no description, add its entry with the periplus-describe skill.

Read output whole, and ask for less with periplus instead of a pipe: counts with `--limit 1` on
`find` or `--ids` into `periplus count -`; one type or folder with `--type`, `--path`; fewer edges
with `--no-edges` on `find`, `--limit N` rows on `show`, `--kind` on `neighbors`, `affected` and
`slice`; one direction with `--direction off` or `by` on `slice`, `reach` and `hubs`. No option
hides the source line under a `find` row. Read those rows; they are short.

## Worked example: an invoice feature

```
periplus find "invoice billing" --any --limit 1
periplus find invoice --type route
periplus affected InvoiceMailer::send --depth all
periplus affected InvoiceRepository::save --depth all
periplus depth invoice.view
periplus depth invoice.pay
periplus hubs invoice.view invoice.pay
periplus slice --from invoice.view --direction off --depth 3 --out invoice-view.map.json
periplus slice --from invoice.pay --direction off --depth 3 --out invoice-pay.map.json
periplus join invoice-view.map.json invoice-pay.map.json --out invoice.map.json
periplus find --map invoice.map.json --ids | periplus files -
periplus find --map invoice.map.json --ids | periplus pieces -
periplus find --map invoice.map.json --ids | periplus reach - --depth 1 --ids | periplus extract - --out rim.map.json
periplus minus rim.map.json invoice.map.json
periplus undescribed --map invoice.map.json
```

The counts show the words land on routes and a mailer; the mailer's walk by leads back to the two
routes, the entrances. The walk back from what writes an invoice, the repository's save, leads to
the same two routes, so no entrance hides under another name. `depth`, asked per route, puts most
of each walk within 3 hops, with one hub, a logger, left unwalked. Two partial slices, joined,
make the set. `files` shows one test folder, named in the answer; `pieces`, one flow. The rim
holds the customer record, shared with other features, so it stays out. The set is saved as
`invoice.map.json`, and `undescribed` says what to describe next.
