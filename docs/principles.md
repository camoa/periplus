# Principles

Periplus rests on one decision: the engine knows no language and no framework. Everything it
knows about a stack comes from a rutter, a folder of YAML files that anyone can write. This page
gives the reasons for that decision, and the reasons for a new mapper.

## Why a new mapper

Most code mappers read source files. In a code base built on a framework, the source files are a
small part of the structure.

Before the design, the custom code of two production Drupal sites was counted. Source files
were about 3% of it. The rest was framework configuration, templates and component definitions.
Those files hold the services, the routes, the content model and the page structure. A mapper
that reads only source files does not see them. Drupal is the example here, not the target. Any
framework with a container and a template layer has the same shape.

Existing tools were evaluated against their source code in August 2026. Each one failed at
least one need:

- **Configuration and templates.** Every tool mapped source files well. For configuration and
  templates, each produced little or nothing. One tool with declarative rules read only the
  top-level keys of a YAML file.
- **A map that is a file.** A widely used code map for AI is a ranked text made for one prompt.
  It changes with the conversation, and it is never saved. Two other tools came with a
  database, a server or a viewer.
- **A stack added without a code change.** In the closest match, each language was code inside
  the engine.

No tool was close enough to adapt. Periplus borrows ideas from them. One is to keep the rules
that read a parse tree as data and not as code.

## Why rutters, and not built-in support

A mapper with built-in support has one owner for every stack: its maintainers. Three problems
follow. A rutter removes each one.

1. **An unusual stack waits for a pull request.** Drupal shows this. A hook can be a function
   whose name starts with the module name. A service is an entry in a YAML file. A plugin is a
   class that carries an attribute. With built-in support, each convention is engine code that
   someone must write, review and release. With a rutter, each convention is a few lines of
   YAML. The person who knows the stack writes them and runs them the same day.
2. **Your own code never gets support.** Every code base has conventions of its own: an
   in-house framework, a naming rule, a registry file. No public mapper accepts code for them.
   A rutter in your repository maps them, in the same rule language the provided rutters use.
3. **A wrong result is a bug in a program you do not own.** With a rutter, a wrong result comes
   from a rule you can read. You correct the rule, remove it, or lower its confidence. The
   engine does not change.

One test guards this: *can a rutter written by a third party do everything a provided rutter
does?* The provided rutters get no private access to the engine. If a rutter needs an engine
change to say something, the engine gains a general ability that every rutter can use. It never
gains a fact about one language or one framework.

## What the map must hold

1. **Declared.** A rutter declares each node type and each edge kind. The engine refuses an
   edge that no rutter declared.
2. **Deterministic.** The same input always gives the same map, byte for byte.
3. **A file.** The map is JSON that you can commit, compare and review.
4. **No infrastructure.** No server, no database and no viewer. The command line is the only
   interface.
5. **Extensible by configuration.** A new stack is a new rutter.

## No guesses

Periplus runs with no AI. An AI can help a person write a rutter. After that, the rutter alone
decides what the map holds, so a result can be repeated and checked.

Each rule states its own confidence. A rule that reads an explicit declaration says `declared`.
A rule that relies on a naming convention says `inferred`. The rule declares the value. The
engine does not decide it at run time.

Each node states how it was found. `mapped` means a rule found its definition. `referenced`
means the code names it, and its definition is outside the mapped files. `unresolved` means a
rule searched for it and found nothing. A thing that no rule explains is marked. It is never
filled with a guess.

## What this design costs

- A rutter author must learn the rule language.
- A rutter can say only what the rule language allows. The report lists each rule that the
  engine accepted and did not run.
- A map is only as good as its rutters. A convention that no rule describes is absent from the
  map.
