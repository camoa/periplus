# Questions and answers

Short answers to the questions people and AI agents ask about Periplus. Each answer links to the
page with the detail. The [glossary](glossary.md) defines each term.

## What it is

### What is Periplus?

A command-line tool that reads a code base and writes a map: the things its rules look for, such
as classes, routes, hooks, templates and settings, and the links between them, each with its file
and line. A person or an AI agent then asks the map, and does not search the code again.
See the [README](../README.md) and [the architecture](architecture.md).

### What is a rutter?

A folder of small YAML rules that holds the knowledge of one stack, such as PHP, Drupal or Go.
Each rule finds one thing, and rules build on what other rules found. File names and settings call
a rutter a *pack*. See [How rules work together](rule-composition.md) and [Bundled
rutters](rutters.md).

### Does making the map use AI?

No. The engine runs the rules and writes the map. The same code gives the same map, byte for
byte. AI comes in only after that, when an agent uses the skills to ask the map, describe code or
write a rule. See [principles](principles.md).

### Does it need a server or a database?

No. The map is one JSON file in `.periplus/`. The commands read it, print an answer and stop.
Nothing runs in the background. See [principles](principles.md).

### Which languages and frameworks does it read today?

The bundled rutters read PHP, JavaScript, TypeScript, React, Next.js, Go, Drupal with several
contributed modules, and Laravel. Most rutters open their `pack.yaml` with a list of what they do
not map yet. `examples/second-stack` holds three more rutters to copy, one of them for Python.
See [Bundled rutters](rutters.md).

### Is it only for Drupal?

No. The engine knows no language and no framework. Drupal has the most rules, and the docs use it
as the example, not the target. A new stack is a new rutter, never a change to the engine.
See [Extending Periplus](extending-periplus.md).

### How is a map different from searching the code?

A text search finds where a word is written. The map holds links that no single word shows: a
route to its controller, a template to the code that passes its variables, a hook to the code
that runs it. You follow those links one step at a time, each with its file and line.
See [Navigating the map](navigation.md).

### Can I see the map as a picture?

Yes. `periplus export` prints the map, or a slice of it, as GraphML, DOT or Mermaid, for a tool
that draws graphs. Periplus has no viewer of its own. See [Visualize the map](visualize-the-map.md).

## What to expect

### Is the map complete?

No. The map holds what its rutters look for. A link that no rule reads is not in the map. When
an answer looks incomplete, the cause is often a missing rule. See [Mapping
quality](mapping-quality.md).

### If the map shows no link, does that mean there is none?

No. It means no rule found one. Check the code before you rely on "none", and turn what you find
into a rule. See [Mapping quality](mapping-quality.md).

### Does it know what happens at run time?

No. The map is read from files. A call whose target is built at run time, such as
`$this->$name()`, stays in the map as a marked call with no target. The map does not guess one.
See [the README](../README.md#what-the-map-holds).

### Will it make my AI agent faster or cheaper?

Not always. The project's own runs, on one large code base, show steadier work with the map: the
same job cost about the same each time, and the answers changed less. A map improved by new rules
helped more. Without a map, results varied from run to run. On the map as first built, the side
without a map reported more likely problems, and some runs with the map took longer.
See [the evals page](evals.md).

### Do I still need to read the code?

Yes. The map says where to read and what is linked. The code says what each piece does, under which
condition and in what order. The skills tell the agent to ask the map first and to read the code to
confirm a line or judge it. See [Using the map with an AI agent](using-the-map-with-an-agent.md).

### How do I know a map is good enough?

Read its marks: things in state `referenced` or `unresolved`, rule matches the map report lists
as skipped, and files no rule read. Each is a gap a rule could close. Then use the map on real
questions, and compare its answers with the code. See [Mapping quality](mapping-quality.md).

### What happens when the code changes?

The map does not change by itself. Run `periplus map` again. `periplus diff OLD NEW` lists what
the change added, removed and changed, and `periplus stale` lists the descriptions whose code
changed. See [Navigating the map](navigation.md#diff).

## Can the map tell me…

Each answer says what makes it work: a bundled rutter, or a rule your project adds. The prompts
are what you would type to an agent that has the periplus skills.

### …everything that takes part in a feature?

Yes, with the bundled rutters for your stack, as far as their rules reach. The agent walks the
links from where the feature starts and saves the set as a slice.
Prompt: "This project has a Periplus map. Find everything that takes part in sending invoice
reminders, and save it." See [Using the map with an AI agent](using-the-map-with-an-agent.md).

### …what breaks if I change this?

Yes, through the links the rules read, such as calls, hooks and services. The map lists what sets
a thing off, hop by hop. Prompt: "This project has a Periplus map. What depends on the invoice
total, directly and further out?" See [Navigating the map](navigation.md#affected).

### …every way a request reaches a piece of code?

Yes, where the rules read the entrances, such as Drupal routes, forms, hooks and event subscribers,
Drush commands, and Laravel and Next.js routes. Prompt: "This project has a Periplus map. List every
way a request ends up creating a customer, with the path from each one." See [Navigating the
map](navigation.md#path).

### …who writes this field or setting, and whether two places write it differently?

Who reads and writes it: yes, where a rule reads it. `drupal_basic` links code to the
configuration objects it reads or edits, `drupal_more` to the fields it reads or writes by name,
and `laravel_basic` to the configuration keys code names. Whether two writers differ, the agent
judges by reading each one. Prompt: "This project has a Periplus map. Who writes the customer
status field, and do they all write it the same way?" See [Navigating the map](navigation.md#show).

### …who can reach this page or endpoint, and what checks a role or a permission?

Yes, for Drupal with `drupal_basic`. It reads each route's access requirements: the roles and
permissions it needs, and the method or service that checks a custom requirement. It also links
code that checks a role by name. `drupal_more` adds `hasPermission('...')` checks. Other stacks
need a rule that reads their access settings. Prompt: "This project has a Periplus map. Who can
open the invoice export page, and what checks it?" See [Bundled rutters](rutters.md).

### …what differs between environments?

Only once your project adds a rule for it. No bundled rutter reads per-environment configuration
files. A rule that reads those files, and links each value to its setting, makes the map hold
it. Prompt: "This project has a Periplus map. Add a rule that reads our per-environment settings
files." See [Extending Periplus](extending-periplus.md).

### …what ties this code to another system?

Partly, with the bundled rutters. `salesforce_basic` links each Salesforce mapping to its object
and to the fields it maps. `drupal_next` links a Next.js app's calls to the Drupal endpoints they
reach. Other systems need a rule that reads their settings and the code that names them.
Prompt: "This project has a Periplus map. What connects our code to the payment provider?"
See [Bundled rutters](rutters.md).

### …which templates read a variable, and which code passes it?

Yes, for Drupal with `drupal_basic`. It reads the variables a theme hook declares, the templates
that read them and the code that passes them. Laravel's Blade views are mapped with their
includes and components, not their variables. Prompt: "This project has a Periplus map. Which
templates use the invoice total variable, and where does it come from?" See [Bundled
rutters](rutters.md).

### …what changed in how things connect between two versions?

Yes. Map both versions and compare the two map files. `periplus diff OLD NEW` lists the things and
links added, removed and changed, by type and kind. Prompt: "This project has a Periplus map. Keep a
copy, map the project again, and tell me what changed." See [Navigating the
map](navigation.md#diff).

### …what my code depends on from outside the project?

Yes, as far as the rules name it. A thing your code names but no rule maps is in state
`referenced`, such as a class from a vendor package. A rule can also mark outside things as
`boundary` and say what they are. Prompt: "This project has a Periplus map. What outside classes
and services does billing depend on?" See [the README](../README.md#what-the-map-holds).

### …what is no longer used?

Only as a lead. The map lists what sets a thing off. When it lists nothing, the reason may be a
link no rule reads. So the agent also searches the code. Prompt: "This project has a Periplus
map. Is anything still using the old PDF exporter? Check the code too." See [Using the map with
an AI agent](using-the-map-with-an-agent.md).

### …where one word means two things?

Yes, as far as the code tells them apart. The map lists each thing with its type and place. A
person settles what the code cannot say, and descriptions keep the answer. Prompt: "This project
has a Periplus map. 'Account' seems to mean two things here. Tell me how they differ."
See [One word, several things](disambiguation.md).

### …whether what I wrote down about the code is still true?

Partly. `periplus stamp` writes a fingerprint of each described thing's code into its entry.
`periplus stale` then lists the entries whose code changed and those whose thing is gone. It
checks node entries only, not link entries, and it cannot tell whether the words were right.
Prompt: "This project has a Periplus map. Which descriptions are out of date? Rewrite them."
See [Navigating the map](navigation.md#stale).

### …which paths no test reaches?

Partly, for PHP. `php_basic` maps code under `tests` folders as supporting code, and its calls are
links like any other. So the map lists the test methods that call a method, directly or further
out, each marked `[supporting code]`. This rests on calls the rules read, not on running the
tests. Prompt: "This project has a Periplus map. Which billing methods does no test call, directly
or further out?" See [Navigating the map](navigation.md#affected).

## When the map lacks something

### How do I find out what the map is missing?

Ask the agent: "This project has a Periplus map. What is the map missing?" The periplus-gaps skill
reads the map's marks, opens the code at each one, and says which rule would close each gap.
See [Mapping quality](mapping-quality.md) and the [map report guide](map-report-guide.md).

### Do I have to change Periplus to map something new?

No. You add a rule, in a rutter of your own. A rutter you write can do all that a bundled one
does. See [Extending Periplus](extending-periplus.md).

### What is the smallest thing I can add?

One rule, in one YAML file, in your project's own rutter under `.periplus/packs`. That rutter can
build on a bundled one by naming it in `depends`, and the bundled rutter's files stay as
installed. Pin it in `.periplus/settings.yml`, run `periplus validate`, then map again.
See [Writing a rutter](rutter-author-guide.md).

### When is it the engine's job?

Only when no rule can state the shape. The test is to write the rule two ways, run each, and get
an engine message for each. Any other gap is a rule not yet written.
See [the map report guide](map-report-guide.md#when-a-gap-is-the-engines).

### Can an AI write the rule?

Yes. The periplus-rutter skill guides an agent through writing a rule, validating it and mapping
again. Periplus then runs the rule with no AI, and the map stays the same on every run.
See [Writing a rutter](rutter-author-guide.md).

### How do I share a rule that others would want?

Open a pull request with the rutter, its list of known gaps, and small tests, as
[CONTRIBUTING.md](../CONTRIBUTING.md) describes. To report a wrong map, open an issue with a
small case anybody can run.
