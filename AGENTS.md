# AGENTS.md

This file is for an AI agent that works in this repository, or that uses Periplus in another
project.

Periplus reads a code base and writes a map: one JSON file of the things it found and the links
between them, each with its file and line. Rules written as YAML say what to find, and the engine
that runs them knows no language. People and agents then ask the map with the `periplus` command.

## Five things

- **The engine** runs rules and writes the map. It knows no language and no framework.
- **Rutters** hold the knowledge of one stack as small YAML rules. File names and settings call a
  rutter a *pack*.
- **The map** is `.periplus/map.json`: nodes and edges, each with its file and line.
- **Descriptions** say in plain words what a thing does, in `.periplus/descriptions.yaml`, apart
  from the map.
- **Skills** tell an agent how to use the map. `periplus skills install` copies them into
  `~/.claude/skills`. In this repository they are in `src/periplus/skills/`.

## Where each answer lives

| To | Read |
|---|---|
| Answer a code question from a map | The `periplus-map` skill, and [Navigating the map](docs/navigation.md) |
| Review or analyse code with a map | The `periplus-analyze` skill |
| Say what things do | The `periplus-describe` skill |
| Find what a map lacks | The `periplus-gaps` skill, and [Reading the map report](docs/map-report-guide.md) |
| Write or change a rule | The `periplus-rutter` skill, `periplus spec`, and [Writing a rutter](docs/rutter-author-guide.md) |
| Choose a rule, a rutter or an engine change | [Extending Periplus](docs/extending-periplus.md) |
| Judge how far to trust a map | [Judging a map](docs/mapping-quality.md) |
| See how the parts fit | [How Periplus fits together](docs/architecture.md) and [Principles](docs/principles.md) |
| Find a quick answer, such as whether the map can tell you something | [Questions and answers](docs/faq.md) |
| Look up a word | [Glossary](docs/glossary.md) |
| Run the tests, or propose a change here | [Contributing](CONTRIBUTING.md) |
| Find any other page | [The docs index](docs/README.md) |

The skills hold the full instructions. This file gives the rules that hold across all of them.
MUST, SHOULD and MUST NOT mean what RFC 2119 says they mean.

## Rules for using a map

- You MUST NOT take a missing link as proof that the code has none. A link that no rule reads is
  not in the map. A thing the map lacks is a rule not written yet.
- You MUST check a claim about what code does against the source. The map says where to read,
  and the code is what you judge.
- You MUST keep descriptions apart from facts. Write descriptions only into
  `.periplus/descriptions.yaml`, each from the thing's own code. Never edit the map or a map file
  made from it.
- You MUST NOT assume that one word names one thing. A short name that fits several things makes
  a command exit 31 and list their ids. Pick one by its id, and see
  [One word, several things](docs/disambiguation.md).
- You SHOULD update what is known, not write it again. Keep a description unless `periplus stale`
  lists it. When a saved slice exists, read it with `--map` and do not search again.

## Rules for writing a rule

- You MUST write small rules. One rule solves one case, and several cases are several rules. Put
  a new rule in a rule file of the rutter that already covers the stack.
- You SHOULD build on what other rules found. A map rule joins what earlier rules put in the map.
  `add_table_rows` adds rows to another rutter's table in place of copying its rule.
- You MUST extend a rutter before the engine. A gap is the engine's only when two ways of writing
  the rule are each refused with an engine message.
- You MUST NOT put knowledge of a language or a framework into the engine. A new stack is a new
  rutter. When a rutter needs something new, the engine gains a general ability that every rutter
  can use.
- You SHOULD prove a rule on a small project before a real one. Run `periplus validate <pack>`
  and `periplus map` on a few files that hold the shape. In this repository, each test writes the
  small project it maps.
