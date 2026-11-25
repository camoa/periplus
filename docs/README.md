# Periplus docs

Find the page for what you want to do. Each line says what the page gives you. The pages are
grouped by kind: lessons to follow, recipes for one task, facts to look up, and the reasons behind
the design.

New to Periplus? Read [Get started](../README.md#get-started), then the
[glossary](glossary.md) when a word is new.

## Tutorials

Follow these from the start to learn by doing.

- [Get started](../README.md#get-started): install Periplus, pin a rutter, make a first map and
  ask it a question.
- [Using the map with an AI agent](using-the-map-with-an-agent.md): requests to copy that make an
  AI agent use the map, and how to tell that it did.

## How-to guides

Each one solves one task.

- [Reading the map report](map-report-guide.md): read what `periplus map` reports, part by part,
  and decide where the rule for a gap belongs.
- [Extending Periplus](extending-periplus.md): choose between a new rule, a new rutter and an
  engine change.
- [One word, several things](disambiguation.md): tell apart the things that share one name, and
  save the answer as descriptions.
- [Visualize the map](visualize-the-map.md): export a slice of the map and look at it in a graph
  tool.

Write a rutter. Start with the first page, then open the one that fits the rule you need.

- [Writing a rutter](rutter-author-guide.md): the files of a rutter, one rule of each shape, and
  how to check a rutter.
- [Text spans](rutter-author-guide-text.md): rules on text files. Spans, values from enclosing
  spans, the line of a node, and a path below a folder.
- [Reading the Drupal rutters](rutter-author-guide-drupal.md): parse-tree rules, read through the
  PHP and Drupal rutters.
- [Tree references](rutter-author-guide-references.md): calls read from a parse tree, tables,
  `add_table_rows`, `in_table`, `encloses_for`, and every key the schemas accept that the engine
  does not run.
- [Import paths and call arguments](rutter-author-guide-imports.md): a name bound from an import
  path, and a call's arguments.
- [Second children and id patterns](rutter-author-guide-abilities.md): a condition on a second
  child, an id that must fit a pattern, a declared end, and a class constant as a call's argument.
- [Map rules](rutter-author-guide-map-rules.md): rules that read the map the file rules made, run
  in passes, one hop each.

## Reference

Look these up while you work.

- [Navigating the map](navigation.md): which command answers which question, and each command's
  options, output and exit codes.
- [Bundled rutters](rutters.md): every rutter that ships with Periplus, what it maps and what it
  depends on.
- [Questions and answers](faq.md): short answers to what people and agents ask, each with a
  link to the page that holds the detail.
- [Glossary](glossary.md): the words Periplus uses, each in one or two sentences, and the pairs
  that get confused.
- `periplus spec`: the contract, printed by the tool. The schemas, the rule format, the engine,
  and what the format cannot say yet.
- [Changelog](../CHANGELOG.md): what each release added and changed.
- [Contributing](../CONTRIBUTING.md): how to propose a rutter, run the tests and report a wrong
  map.

## Explanation

Read these to understand why Periplus works as it does.

- [How Periplus fits together](architecture.md): the five parts, what passes between them, and
  how what you learn is kept.
- [Principles](principles.md): why a new mapper, why rutters and not built-in support, and what
  the map must hold.
- [Rule composition](rule-composition.md): how small rules build on what other rules found.
- [Judging a map](mapping-quality.md): how far to trust a map, and what a map cannot tell you.
- [The evals page](evals.md): jobs done by the same agent with a map and without one, and what each side
  cost.

## For AI agents

[`AGENTS.md`](../AGENTS.md) holds the rules an agent follows in this repository or with a map.
[`llms.txt`](../llms.txt) lists the main pages for a language model. The skills that Periplus
installs with `periplus skills install` hold the fuller instructions.
