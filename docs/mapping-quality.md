# Judging a map

This page says how far to trust a map, and what a map cannot tell you. Each check uses something
Periplus reports: a node's state, a link's confidence, the map report, and the description
commands. For each check, it says what the result means and what to do next.

## A map is not the code

A map holds the things its rules found and the links between them, each link with the file and
line where it was found. It says that A reaches B, and where. Three limits follow:

- **A map can have gaps.** A link the code has and no rule reads is not in the map, and nothing
  marks its absence. So a missing link does not show that the code has none.
- **A map does not hold what happens between the links:** when a link runs, under what condition,
  in what order against another, and what is absent. The branch a call sits in, or a step that
  should undo an earlier one and does not, is in the code only.
- **A bigger map is not a better one.** A node count says how much the rules found. It does not say
  whether the links a question needs are there, or how sure each one is.

So the map says where to read, and the code is what you judge.

## The example

The commands below ran on a small invented invoicing project with the bundled `php_basic` rutter.
`Reminder::send` takes a typed `Invoice` and `Mailer`, calls a global `format_amount()` that no
file declares, and `Reminder::run` calls `$this->$step()`. `Invoice` extends `\Acme\Core\Entity`,
which the project does not hold.

## First, check that the map is whole

```text
$ periplus check-map
/path/to/invoicing/.periplus/map.json matches the map schema
```

`periplus check-map` checks every node and edge against the map schema. It exits 0 on a valid map
and 30 on a failing one, with the first error. Fix what it names before you read anything else.

## Node states: what the map knows about each thing

Every node has one of five states. Every id holds `::`, so this command lists every node with
its state. The end of the list, shortened:

```text
$ periplus find :: --limit 0 --no-edges
...
php.call_site::Acme\\Billing\\Reminder::run::$this->$step  php.call_site  unknown_boundary  src/Billing/Reminder.php:15
      | $this->$step();
php.function::format_amount  php.function  unresolved  no location
php.type::Acme\\Core\\Entity  php.class_like  referenced  no location
```

| State | What it tells you | What to do |
|---|---|---|
| `mapped` | A rule found the thing in a file the project holds. | Nothing. |
| `boundary` | The thing is outside the mapped code, and a rule says what it is. | Nothing. |
| `referenced` | A file names the thing, but no rule read where it is defined. | A missing rule, or code outside the mapped folders. Read where the name is used. |
| `unresolved` | A rule looked for the name in the mapped code and found nothing. | Read the call. A missing rule, a missing folder or a wrong name in the code. |
| `unknown_boundary` | The thing leaves the mapped code and no rule says what it is, or it is a call whose target is built at run time. | For a `no rule` mark, write the rule. A run-time call is a limit, not a gap: read the code, then accept it under `accepted_unknowns` in the settings. |

The map's `counts.nodes_by_state` holds the count of each state. In the example it is
`mapped 17, referenced 1, unknown_boundary 1, unresolved 1`.

## Link confidence: how sure each link is

Each rule declares the confidence of what it makes, strongest first:

- `declared`: the code states the link, as `extends` or a registration in a file.
- `inferred`: a rule worked the link out, as from a parameter's type or a naming convention.
- `mentioned`: a name is written as text, such as a string equal to a known id.

`periplus show` prints the confidence and the rule on each link:

```text
$ periplus show 'php.method::Acme\Billing\Reminder::send'
...
  calls:
    php.function::format_amount  php.function  unresolved  src/Billing/Reminder.php:10  x1  declared  php_basic:calls_function
    php.method::Acme\\Billing\\Invoice::total  php.method  mapped  src/Billing/Reminder.php:8  x1  inferred  php_basic:calls_through_typed_parameter
```

Read an `inferred` or `mentioned` link at its line before an answer rests on it.

## The map report: what the run could not finish

`periplus map` prints a report on every run. `periplus map --format json` prints the report as
JSON. The parts that bear on quality:

- **Problems.** Anything here stopped the run, and no map was written.
- **Files no rule read.** The map knows nothing about these files. A whole family of one ending is
  a rule to write.
- **Matches skipped.** A rule matched at a file and line but could not build what it emits. Open
  the line: the shape there is one the rule does not cover.
- **Rules not executed.** The engine cannot run these rules, and the reason is given.
- **Unknown boundaries.** The count, by rutter and by reason, `no rule` or `run-time`.

In the example, Unknown boundaries shows `total 1` and `by reason: run-time 1`, and Matches skipped
shows `none`. [Reading the map report](map-report-guide.md) explains every part.

## The gaps report: two halves

The `periplus-gaps` skill runs a small program over the map file. Its report has two halves.
**Resolution gaps** counts the `referenced` and `unresolved` nodes and the `inferred` and
`mentioned` links. Each count is split into first-party, code with a location, and outside.
**Detail gaps** counts the nodes each rule made and each child type, so a large group left on a
general type shows where a more specific rutter would add detail. Unknown boundaries, site faults
and plain classes follow. From the example:

```text
Resolution gaps
referenced  1
first-party 0  outside 1
reached from first-party 1
unresolved  1
first-party 0  outside 1
reached from first-party 1
inferred  3
first-party 3  outside 0
...
```

The skill then groups the gaps by the rule that would close each one.

## Descriptions: how much is described, and is it current

```text
$ periplus undescribed
described 2 of 8 main things; 6 undescribed
...
$ periplus stale
2 node entries: 1 fresh, 1 changed, 0 gone, 0 unreadable, 0 not stamped
changed:
  Invoice::total  php.method  mapped  src/Billing/Invoice.php:6
```

`periplus undescribed` counts the main things with no description. `periplus stale` lists the
entries whose code changed since `periplus stamp`, those whose node is gone, and each term with an
id the map no longer holds. Read the code
again and rewrite each listed entry. An entry that is not stamped was never checked against its
code.

## When a gap shows in use

Most gaps leave a mark that the checks above show. A silent gap leaves none: code that no rule
looks at. It shows only when the map is used, as a wrong answer or a missing one. A caller you know
of does not appear, or a feature's slice stops short.

When that happens, note the file and line the map should have held. Give them to the
`periplus-gaps` skill, which reads the code there and names the rule that would hold the link.
Then write the rule, map again, and ask again. [Extending Periplus](extending-periplus.md) helps
to choose between a rule, a new rutter and an engine change.

## What static reading cannot see

Periplus reads files. It does not run the code. So the map does not hold:

- **Run-time behaviour:** which path a request takes, how often, and in what order.
- **Values built at run time:** a method name held in a variable, as in `$this->$step()`. The
  map marks such a call `unknown_boundary` and draws no edge from it.
- **Behaviour set by data or by the environment:** settings stored in a database, feature flags,
  environment variables, what a deployment turns on.

Other kinds of tools cover those, such as tracers that record what runs and security scanners
that follow data through the code.

## Freshness

A map describes the code it was built from. `periplus map` writes an inputs record beside the map,
`.periplus/map.inputs.json`: a digest of each file a rule reads, of the settings and of each
rutter, and the tool version. Commit it with the map. `periplus fresh` selects the files again,
runs no rule, and compares. After `Invoice` gained a method, a file `Tax.php` was added and a file
`Legacy.php` was deleted:

```text
$ periplus fresh
periplus fresh
map: /path/to/invoicing/.periplus/map.json
stale: 1 file changed, 1 added, 1 removed; settings same; rutters same; tool same
files changed:
  src/Billing/Invoice.php
files added:
  src/Billing/Tax.php
files removed:
  src/Billing/Legacy.php
run periplus map to rebuild
```

It exits 0 when the map is fresh and 34 when it is not. A changed settings value, a changed rule
in a rutter and another Periplus version each make the map stale too, and the line says which.
Run `periplus map` again to rebuild. Every run is a full run.

`periplus diff OLD NEW` compares two maps. After a new method `Invoice::tax` was added:

```text
$ periplus diff ../map-before.json .periplus/map.json
periplus diff
old: ../map-before.json (20 things, 24 edges)
new: .periplus/map.json (22 things, 28 edges)
header: same
things: 2 added, 0 removed, 1 changed
  added by type: php.call_site 1, php.method 1
  changed by type: php.method 1
edges: 4 added, 0 removed, 1 changed
...
edges added:
  calls  php.method::Acme\\Billing\\Invoice::total -> php.method::Acme\\Billing\\Invoice::tax
```

Between two builds of one project, the diff is the change a pull request makes to the map.
`periplus stale` then lists the descriptions that change made out of date.
