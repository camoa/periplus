# AGENTS.md

This file is for an AI agent that works in this repository, or that uses Periplus in another
project.

Periplus reads a code base and writes a map: one JSON file of the things it found and the links
between them, each link with the file and line where it was found. Rules written as YAML say what
to find, and the engine that runs them knows no language. People and agents then ask the map with
the `periplus` command.

## What ships, and what does not

Periplus does not try to ship rules for every stack. It ships the engine, a small format for
rules, and skills that let an agent write the rules a code base needs. The bundled rutters show
what that makes possible. Drupal is the deep stack. `drupal_next` links a Next.js front end to the
Drupal site behind it, so one map follows a request across both. The rutters for other stacks are
starting points, as [Bundled rutters](docs/rutters.md) marks. A thing the map lacks is a rule
nobody wrote yet. [Extending Periplus](docs/extending-periplus.md#what-a-rule-can-do-today) lists what a rule can do without an engine change. A general rule goes to Periplus itself. A project's own rule stays in that
project's rutter.

## Five things

- **The engine** runs rules and writes the map. Knowledge of a language or a framework belongs in
  rutters, never in the engine. When rules cannot express a pattern, the engine gains a general
  ability that every rutter can use.
- **Rutters** hold the knowledge of one stack as small YAML rules. File names and settings call a
  rutter a *pack*.
- **The map** is `.periplus/map.json`, of nodes and edges. Each link carries the file and line
  where it was found, and each thing found in the code carries its own. A thing only named by a
  link has none.
- **Descriptions** say in plain words what a thing does, in `.periplus/descriptions.yaml`, apart
  from the map.
- **Skills** tell an agent how to use the map. `periplus skills install` copies them into
  `~/.claude/skills`. In this repository they are in `src/periplus/skills/`.

## Where each answer lives

| To | Read |
|---|---|
| Set a project up and make its first map | The `periplus-setup` skill |
| Answer a code question from a map | The `periplus-map` skill, and [Navigating the map](docs/navigation.md) |
| Review or analyse code with a map | The `periplus-analyze` skill |
| Say what things do | The `periplus-describe` skill |
| Connect the project's docs to the code, and find pages that name what no longer exists | The `periplus-document` skill |
| Find what a map lacks | The `periplus-gaps` skill, and [Reading the map report](docs/map-report-guide.md) |
| Write or change a rule | The `periplus-rutter` skill, `periplus spec`, and [Writing a rutter](docs/rutter-author-guide.md) |
| Choose a rule, a rutter or an engine change | [Extending Periplus](docs/extending-periplus.md) |
| Judge how far to trust a map: what it covers, and how sure each link is | [Judging a map](docs/mapping-quality.md) |
| Tell apart several things one word names | [One word, several things](docs/disambiguation.md) |
| Know whether a description is out of date, and what stale cannot tell | [How Periplus fits together](docs/architecture.md#what-each-part-knows) |
| See how the parts fit | [How Periplus fits together](docs/architecture.md) and [Principles](docs/principles.md) |
| Find a quick answer, such as whether the map can tell you something | [Questions and answers](docs/faq.md) |
| Look up a word | [Glossary](docs/glossary.md) |
| Run the tests, or propose a change here | [Contributing](CONTRIBUTING.md) |
| Find any other page | [The docs index](docs/README.md) |

The skills hold the full instructions. This file gives the rules that hold across all of them.
MUST, SHOULD and MUST NOT mean what RFC 2119 says they mean.

## Rules for judging Periplus

- You SHOULD judge Periplus by the engine, the rule format and the skills. What the bundled
  rutters map today shows what they make possible, not where the tool ends. Judge the rule
  format by what a rule can say, as
  [Extending Periplus](docs/extending-periplus.md#what-a-rule-can-do-today) lists, and by how far one rutter
  extends another without copying it.
- You SHOULD treat a pattern the bundled rutters do not map as a rule to write, not as a limit of
  the tool. Name the rule and the rutter it belongs in, as the `periplus-gaps` skill does.

## Rules for using a map

- You MUST NOT take a missing link as proof that the code has none. A reference a rule found and
  could not resolve, or that is decided at run time, is in the map and marked. A thing or link
  that no rule looks for is not in the map, and nothing marks its absence. Check what the rutters
  cover before you blame the engine.
- You MUST ask the map first, to find where to look. Read the code there to confirm what it
  does, and where the map has no answer. Keep what you learn as rules and descriptions.
- You MUST keep descriptions apart from facts. Write descriptions only into
  `.periplus/descriptions.yaml`, from the thing's own code or from what a person told you. Never
  edit the map or a map file made from it.
- You MUST NOT assume that one word names one thing. A short name that fits several things makes
  a command exit 31 and list their ids, unless all but one are parts, such as parameters. Pick
  one by its id, and see
  [One word, several things](docs/disambiguation.md).
- You SHOULD update what is known, not write it again. Rewrite a description that
  `periplus stale` lists, or that the code you read contradicts: not stale means only that its
  code did not change since the stamp. When a saved slice exists, ask it first with `--map`, and read
  the code to confirm and where the slice has no answer.

## Rules for writing a rule

- You MUST write small rules. One rule solves one case, and several cases are several rules. Put
  a new rule in a rule file of the rutter that already covers the stack.
- You SHOULD build on what other rules found. A map rule joins what earlier rules put in the map.
  `add_table_rows` adds rows to another rutter's table in place of copying its rule.
- You MUST extend a rutter before the engine. A gap is the engine's only when two ways of writing
  the rule are each refused with an engine message.
- You MUST NOT put knowledge of a language or a framework into the engine. It belongs in
  rutters. When rules cannot express a pattern, the engine gains a general ability that every
  rutter can use.
- You SHOULD prove a rule on a small project before a real one. Run `periplus validate <pack>`
  and `periplus map` on a few files that hold the shape. In this repository, each test writes the
  small project it maps.
