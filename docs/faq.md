# Questions and answers

Short answers to the questions people and AI agents ask about Periplus. Each answer links to the
page with the detail. The [glossary](glossary.md) defines each term.

## What it is

### What is Periplus?

A command-line tool that reads a code base and writes a map: the things its rules look for, such
as classes, routes, hooks, templates and settings, and the links between them, each link with the
file and line where it was found. A person or an AI agent asks the map first, to find where to
look, and reads the code there to confirm. See the [README](../README.md) and
[How Periplus fits together](architecture.md).

### What is a rutter?

A folder of small YAML rules that holds the knowledge of one stack, such as PHP, Drupal or Go.
Each rule finds one thing, and rules build on what other rules found. File names and settings call
a rutter a *pack*. See [Rule composition](rule-composition.md) and [Bundled
rutters](rutters.md).

### Does making the map use AI?

No. The engine runs the rules and writes the map. The same code, settings and rutters, on the
same version of Periplus, give the same map, byte for byte. AI comes in only after that, when an
agent uses the skills to ask the map, describe code or write a rule.
See [principles](principles.md).

### Does it need a server or a database?

No. The map is one JSON file in `.periplus/`. The commands read it, print an answer and stop.
Nothing runs in the background. See [principles](principles.md).

### Which languages and frameworks does it read today?

The rutters that ship with the package read PHP, JavaScript, TypeScript, React, Next.js, Go,
Drupal with several contributed modules, and Laravel. Python is not one of them:
`examples/second-stack/packs` holds example rutters for Python, Typer and spec-kitty, which you
copy into a project. Any other stack needs a rutter you write. See [Bundled rutters](rutters.md).

### How do I set it up with an AI agent?

Install Periplus and its skills, then ask the agent to set Periplus up in the project and make a
map. The setup skill pins the rutters, sets where the code is, builds the map and says what it
holds. See [Using the map with an AI agent](using-the-map-with-an-agent.md#things-you-can-ask).

### How do I upgrade Periplus?

Run `periplus upgrade`. It asks PyPI for the newest version, finds how Periplus was installed, and
runs the matching command. It also refreshes the skills in `~/.claude/skills` when they are
installed. Then run `periplus update` in each project to move its rutter pins, and map again.
`periplus upgrade --check` says what it would run and changes nothing. See
[Install Periplus](../README.md#1-install-periplus).

### How does it know which rutters my project needs?

`periplus init` pins each bundled rutter whose detector matches a file in the project, and prints
the file. A stack kept in a subfolder, such as a front end in `frontend/`, is not detected: pin
it by hand under `packs` in `.periplus/settings.yml`. When nothing matches, `init` says so. When no rutter covers a
stack, its files are not in the map until someone writes one. See [Get started](../README.md#2-pin-a-rutter).

### Does the Drupal rutter read Drupal core and contributed modules?

Partly. From core, `drupal_basic` reads only the `*.services.yml` files. From
contributed modules, it reads their `*.services.yml` files, the hook names their `*.api.php`
files define, and their event names. So a service your code injects, such as `config.factory`,
is a mapped thing with its file. Core's and contributed modules' PHP is not read.

It looks for core in the folder `core`, by default `web/core`. `periplus init` writes
`docroot/core` or `core` when it finds one of those instead. Contributed modules are in the folder
`contrib_module`, by default `web/modules/contrib`. When a site keeps them elsewhere, set both in
`.periplus/settings.yml`:

```yaml
folders:
  core: drupal/core
  contrib_module: vendor-modules
```

### How do I map a Drupal module that is its own repository?

Map it in its own folder, and give the rules its machine name. The rules name a module by the
folder it sits in, so without the name a map made inside the module's own folder misses some
links.

1. Run `periplus init` in the module's folder. It detects a module, theme or install profile by
   the `*.info.yml` file at its root, and prints the rutters it pins and the value
   `drupal_extension` to set.
2. Add the folder and the machine name, the name of the `*.info.yml` file, to its
   `.periplus/settings.yml`:

```yaml
folders:
  custom_module: .
values:
  drupal_extension: my_module
```

3. Run `periplus map` in that folder. For a theme, write `custom_theme: .` in place of
   `custom_module: .`. The map then holds the same ids it would hold with the module in a
   site's `web/modules/custom` folder.

### Can I add or remove a rutter myself?

Yes. The rutters a project uses are the lines under `packs` in `.periplus/settings.yml`. Add a
line to use a rutter, delete a line to stop using it, then run `periplus map` again. What
`periplus init` writes there is a starting point, and the list is yours. An AI agent can make the
change for you. Some rutters need a value under `values` before they map, such as the Go module
path. See [Bundled rutters](rutters.md).

### Is it only for Drupal?

No. Knowledge of a language or a framework belongs in rutters, never in the engine. Drupal has
the most rules, and the docs use it as the example, not the target. When rules cannot express a
pattern, the engine gains a general ability that every rutter can use.
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
an answer looks incomplete, the cause is often a missing rule. See [Judging a
map](mapping-quality.md).

### Why does the map not cover my stack, or all of my framework?

Periplus does not try to ship rules for every stack, and no tool can. It ships the engine, the
rule format, and skills that let an AI agent write the rules your code needs. Drupal is the deep
stack, chosen because one Drupal site mixes PHP, YAML configuration, templates and plugins. The
rutters for other stacks are starting points, and [Bundled rutters](rutters.md) marks each one.

A thing the map lacks is a rule nobody wrote yet. Ask the agent what the map is missing, then ask
it to write the rules. The `periplus-gaps` and `periplus-rutter` skills guide it. The rules stay
in your project's rutter, and every later map holds what they find. [The evals page](evals.md)
describes an agent that adds such rules at the end of a job. See
[Extending Periplus](extending-periplus.md).

### If the map shows no link, does that mean there is none?

No. It means no rule found one. Check the code before you rely on "none", and turn what you find
into a rule. See [Judging a map](mapping-quality.md).

### Does it know what happens at run time?

No. The map is read from files. A call whose target is built at run time, such as
`$this->$name()`, stays in the map as a marked call with no target. The map does not guess one.
See [the README](../README.md#what-the-map-holds).

### Will it make my AI agent faster or cheaper?

Not always. The project's own runs, on one large code base, show steadier work with the map: the
same job cost about the same each time, and the answers changed less. A map improved by new rules
helped more. Without a map, results varied from run to run. On the map as first built, the side
without a map reported more likely problems, and the first job took longer with the map.
See [the evals page](evals.md).

### Do I still need to read the code?

Yes. The map says where to read and what is linked. The code says what each piece does, under which
condition and in what order. The skills tell the agent to ask the map first and to read the code to
confirm a line or judge it. See [Using the map with an AI agent](using-the-map-with-an-agent.md).

### How do I know a map is good enough?

Read its marks: things in state `referenced` or `unresolved`, rule matches the map report lists
as skipped, and files no rule read. Each is a gap a rule could close. Read each link's
confidence too: in a Drupal map, a `named_like_hook` link is weaker than an `implements_hook`
link. Then use the map on real questions, and compare its answers with the code. See
[Judging a map](mapping-quality.md).

### What happens when the code changes?

The map does not change by itself. `periplus fresh` says whether the code, the settings, the
rutters or the tool changed since the map was built, and names the files. Run `periplus map` again
to rebuild. `periplus diff OLD NEW` lists what the change added, removed and changed, and `periplus
stale` lists the descriptions whose code changed. See [Navigating the map](navigation.md#fresh).

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
person settles what the code cannot say, and descriptions keep the answer. A term names each
meaning of the word, and `periplus find` prints them all. Prompt: "This project
has a Periplus map. 'Account' seems to mean two things here. Tell me how they differ."
See [One word, several things](disambiguation.md).

### …whether what I wrote down about the code is still true?

Partly. `periplus stamp` writes a fingerprint of each described thing's code into its entry.
`periplus stale` then lists the entries whose code changed, those whose thing is gone, and each
term with an id the map no longer holds. It checks node entries only, not link entries, and it cannot tell whether the words were right.
Prompt: "This project has a Periplus map. Which descriptions are out of date? Rewrite them."
See [Navigating the map](navigation.md#stale).

### …which docs talk about this, and which are out of date?

Yes, once the project's own rutter has rules for its docs. The rules link each page and section
to the code it names, and mark a name that matches nothing in the code. After a code change,
`periplus diff OLD NEW` lists each link a page lost. The link shows that a page names the thing,
not that the page is right. The `periplus-document` skill guides the agent through the rules,
built on the habits the docs already have. Prompt: "This project has a Periplus map. Connect our
docs to the code, and tell me which pages name things that no longer exist."
See [Using the map with an AI agent](using-the-map-with-an-agent.md#things-you-can-ask).

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
See [Judging a map](mapping-quality.md) and the [map report guide](map-report-guide.md).

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
again. Periplus then runs the rule with no AI. The same code, settings and rutters, on the same version
of Periplus, give the same map on every run.
See [Writing a rutter](rutter-author-guide.md).

### Can I contribute a rutter?

Yes, when it is general: rules for a language, a framework, a platform or common software that
other projects use too. A rule for one project's own conventions stays in that project's rutter.
Open a pull request with the rutter, its list of known gaps, and small tests, as
[CONTRIBUTING.md](../CONTRIBUTING.md) describes. To report a wrong map, open an issue with a
small case anybody can run.
