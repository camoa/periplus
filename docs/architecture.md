# How Periplus fits together

This page gives the picture to hold before any reference page. It names the five parts of
Periplus, says what passes between them, and says what each part knows and does not know. It then
follows one piece of knowledge from a first map to a rule or a description that keeps it.

## The five parts

- **The engine** runs rules and writes the map. It knows no language and no framework.
- **Rutters** hold the knowledge of one stack as small YAML rules. A rutter is one folder named
  `<pack>@<version>`, so file names and settings call it a *pack*.
- **The map** is one JSON file, `.periplus/map.json`, of nodes and edges. Each link carries the
  file and line where it was found, and each thing found in the code carries its own. A thing only
  named by a link has none.
- **Descriptions** say in plain words what a thing does. They live in
  `.periplus/descriptions.yaml`, beside the map.
- **Skills** teach an AI agent to use the other four. `periplus skills install` copies them into
  `~/.claude/skills`.

What passes between them:

```text
  .periplus/settings.yml          pins the rutters and says where the code is
          |
          v
  rutters ----> the engine <---- source files
               (periplus map)
                    |
                    v
  .periplus/map.json  +  the map report (printed)
          |
          |     .periplus/descriptions.yaml
          |          |
          v          v
     periplus find, show, neighbors, affected, slice ...
                    |
                    v
          a person, or an agent with the skills
                    |
                    +--> a new rule in a rutter, or a new description
```

`periplus map` reads the settings, loads the pinned rutters and the rutters they depend on, and
runs their rules over the project's files. It writes the map and prints a report on the run. It
never reads the descriptions, so they are not an input of the map. Every other command reads the
map. The commands that print a thing also print its description, and
`periplus find` searches the descriptions too.

## What each part knows

Each part holds one kind of knowledge. None of them holds another's.

| Part | Knows | Does not know |
|---|---|---|
| Rutters | How one stack's things look in real files: which folders, which file types, which patterns | Anything about one project, unless it is that project's own rutter |
| The map | Which things exist and how they link, with a state, a confidence and the place each was found | What a thing is for, or what happens when it runs |
| Descriptions | What a thing does, in the words a person would search for | Which other code calls it: an entry speaks only of its own code |
| Skills and people | How to ask, what to judge, when an answer looks wrong | Nothing by themselves: they work from the map and the code |

**Facts and words stay in separate files.** The map holds only what rules found. The same code,
settings and rutters, on the same version of Periplus, give the same map, byte for byte. A
description is written by a person or an agent, and it is a reading of the code, not a fact a rule
can repeat. The map never reads the descriptions file, so a description can never change the map.

A description comes from one of two places. One written from a thing's code is tied to that code by
`periplus stamp`, and `periplus stale` lists it when the code changes. A meaning a person gave, in a
description or in a term with its `origin`, can change with no code change, and nothing marks
that. Descriptions of links are not stamped. So "not stale" means the code did not change since
the stamp, not that the words are right.

## How rutters work together

A large stack is several rutters, each small. A framework rutter does not repeat the language
rutter under it. It builds on it.

- **A rutter names what it depends on.** `depends: [php_basic]` in its `pack.yaml` gives it that
  rutter's folders, file types and types. A rutter may name only the types it declares or that a
  rutter it depends on declares. `periplus validate` checks this before any source file is read.
- **A type can sit below another.** A framework rutter declares its type with `parent`, below the
  language rutter's type. When two rules give one thing two types, the lower type wins. So a rule
  that finds a form refines what the class rule found, and does not fight it.
- **A general rutter marks, and a specific rutter identifies.** A general rule marks a call that
  leaves the mapped code. A rule in a rutter that depends on it says what that call reaches.
- **A rutter adds to another's lists.** `add_table_rows` adds rows to a table another rutter owns,
  such as a list of names to skip, without a copy of its rules.

Rules run in two kinds:

1. **File rules** (`reads: file`) read one file each. A file rule cannot see another file or
   another rule.
2. **Map rules** (`reads: map`) run after every file rule, over the map the file rules made. They
   join what was found in different files. The engine runs them in passes until a pass adds
   nothing. A map rule that reads an edge another map rule made fires one pass later.

So a chain across files is a series of small rules, one link each. The map report lists each pass
and the rules that fired in it. [Rule composition](rule-composition.md) works through an example,
and [Map rules](rutter-author-guide-map-rules.md) gives the full rule language.

## The life of what you learn

Knowledge about a code base gets into Periplus in one of two forms: a rule or a description. Both
are files in the project's `.periplus` folder. The loop below shows where each comes from.

A project's documentation is a third kind: how things fit together into features, flows and
decisions. Periplus does not change for it. Rules in the project's own rutter read the pages and
link each one to the code it names, as the `periplus-document` skill guides.

1. **Map.** Run `periplus map`. It writes the map and prints the report.
2. **Ask.** Ask the map with `periplus find`, `show`, `neighbors`, `affected`, `path` or `slice`.
   The `periplus-map` skill teaches an agent these commands. The `periplus-analyze` skill guides a
   review that reads the code the map names.
3. **Find a gap.** An answer is wrong or incomplete, or the report shows marks: unresolved names,
   unknown boundaries, skipped matches. The `periplus-gaps` skill reads the map and says which
   rule is missing and where it belongs. [Mapping quality](mapping-quality.md) says what to look
   at.
4. **Add a rule.** The `periplus-rutter` skill writes or changes a rutter. Run
   `periplus validate <pack>` on it. A rule closes a gap for every later map of every project that
   loads the rutter. [Extending Periplus](extending-periplus.md) helps to choose between a rule, a
   new rutter and an engine change.
5. **Or add a description.** The `periplus-describe` skill writes entries from each thing's own
   code. `periplus undescribed` counts what is left, and `periplus stamp` ties each entry to its
   code.
6. **Map again.** Run `periplus map` again. `periplus diff OLD NEW` lists what the change added,
   removed or changed in the map. `periplus stale` lists the descriptions whose code changed.

When you add a rule for a gap, the map holds that link from then on. A meaning you write as a description is there for
the next session, and for the next person.

## What the design refuses

[Principles](principles.md) gives the reasons in full. In short:

- **No server, no database, no viewer.** The map is a file, and the command line is the only
  interface. You commit the map and the inputs record beside it, compare two versions, and review
  the change in a pull request. `periplus export` writes GraphML, DOT or Mermaid for other tools
  to draw.
- **No guessing.** A reference a rule found and could not resolve, or that is decided at run
  time, is in the map and marked, never given a guessed target. A thing or link that no rule looks
  for is not in the map, and nothing marks its absence. Each rule declares its confidence, and the
  engine does not decide it at run time. No AI takes part in making a map.
- **No stack knowledge in the engine.** Knowledge of a language or a framework belongs in rutters,
  never in the engine. A rutter written by anyone can do everything a bundled rutter does. When
  rules cannot express a pattern, the engine gains a general ability that every rutter can use.

The cost is stated in the principles too: a map is only as good as its rutters. A convention no
rule reads is not in the map.
