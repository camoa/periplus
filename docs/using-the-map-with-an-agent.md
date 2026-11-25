# Using the map with an AI agent

Ask your AI coding agent about your code in plain words, and it answers from the map: what takes
part in a feature, what breaks if a thing changes, every way a request reaches some code. Each
answer names files and lines. What the agent learns stays in files, so the next session starts
from it.

This page gives requests to copy, the jobs they suit, and how to tell that the agent used the map.
It assumes the project has a map and the skills are installed: see [Get
started](../README.md#get-started). Short answers to common questions are in the [FAQ](faq.md).

## What to expect

A map is not the code, and Periplus is not magic. The map holds what its rutters look for. A link
that no rule reads is not in the map, so a missing link does not show that the code has none.

- The agent asks the map first, and still reads code: to confirm a line, to judge what the code
  does, and where the map has no answer.
- When an answer looks wrong or incomplete, the cause is often a gap in the map. A gap becomes a
  rule, and the next question starts with the link the rule adds.
- The map makes the work steadier, and a better map helps more. The numbers from real runs are in
  [How Periplus is evaluated](evals.md).

You do not need to know the commands. The skills give the agent Periplus's options and its way of
working. You say what you want to know.

## Why the wording matters

An agent tends to skip the map. Left alone, it searches by words and filters the output with other
tools. It stops when the word search looks complete, and it reads code it did not need. The
periplus skills steer it toward the map. The wording of the request steers it more. What the skills
cannot enforce, the prompt can.

Start a request with **"This project has a Periplus map."** The agent then knows the map is there
before it searches.

## Things you can ask

Each use below gives the situation, a request to copy, what the agent does with the map, and what
you get back. Change the names to your own.

**Learn how a feature works before you touch it.**

```
This project has a Periplus map. How does sending invoice reminders work? Show me each step.
```

The agent finds where the feature starts and follows the links from there. You get the steps,
each with its file and line.

**See what breaks if you change something.**

```
This project has a Periplus map. I want to change how the invoice total is worked out. What
depends on it, directly and further out?
```

The agent lists what sets the code off, hop by hop, and reads the code at the places that matter.
You get the callers and the features they belong to, each with its file and line.

**Find every way a request reaches some code.**

```
This project has a Periplus map. List every way a request ends up creating a customer: the pages,
forms, commands and scheduled jobs, with the path from each one to that code.
```

The agent works back from the code to each place where something starts. You get one path for
each way in, step by step.

**Review a feature before a change.**

```
This project has a Periplus map. We are going to change how a customer gets created. Read the
code on every path that leads to it and tell me what is likely to go wrong: bugs, steps in the
wrong order, missing checks. Give the file and line for each.
```

The map names the code that takes part, and the agent reads and judges it, one way in at a time.
You get findings with file and line, and a list of the gaps in the map it noticed.

**Find code that does the same job twice.**

```
This project has a Periplus map. Do the order form and the quick checkout do the same work in two
places? Show me what each one runs that the other does not.
```

The agent saves what each feature takes part in, compares the two sets, and reads the difference.
You get the shared code, the code only one side runs, and where the two copies differ.

**Get to know a code base you did not write.**

```
This project has a Periplus map. I am new here. What kinds of things does the code have, and
where do requests come in? Then walk me through the main parts of billing.
```

The agent reads the map's own list of what it holds and the entrances of an area. You get the
main parts, where each one starts, and the files that hold them.

**Write down what a part of the code does.**

```
This project has a Periplus map. Describe what each part of the invoice reminder feature does,
and save the descriptions.
```

The agent reads the code of each thing and writes one or two plain sentences for it in
`.periplus/descriptions.yaml`. You then find each thing by plain words, and the next session reads
the descriptions with each answer.

**Check whether something is still used.**

```
This project has a Periplus map. Is anything still using the old PDF exporter? Check the code too.
```

The agent asks the map what sets the exporter off and what would go unused without it. It then
searches the code, because a link no rule reads is not in the map. You get what uses it, with
file and line, and any use the code holds that the map lacks.

**Close a gap when an answer looks wrong or incomplete.**

```
This project has a Periplus map. The map did not show that the nightly job sends reminders. Find
what the map is missing, add a rule for it in this project's own rutter under .periplus/packs,
and rebuild the map. Change only files under .periplus/.
```

The agent lists what the map lacks and says what kind of rule would close each gap. It writes the
rule, rebuilds the map, and checks that the link is there. You get the new rule and what it added.

**Keep the map current after the code changes.**

```
This project has a Periplus map. The code changed since it was built. Keep a copy of the old map,
map the project again, and tell me what changed. Then list the descriptions whose code changed
and rewrite them.
```

The agent builds the map again, compares the old map with the new one, and lists the
descriptions whose code no longer matches. You get the things and links added, removed and
changed, and the rewritten descriptions.

A word that names several things in one code base, such as "account", has its own page:
[One word, several things](disambiguation.md).

## Find a whole feature

For a feature, or any request for everything that takes part in something, the result is a saved
slice: a map file that holds the set. The agent can build it in parts and join them into one file.
Copy this, and name the feature in your own words:

```
This project has a Periplus map. Use the periplus skills and commands.

Find everything that takes part in sending invoice reminders. Follow the nodes and edges in the map, and keep what is connected to the feature and still related to it. There is no saved slice for this yet: build one with the periplus commands and save it. Do not read the code until the slice is saved.
```

- **"Follow the nodes and edges..."** says what using the map means, and when to stop.
- **"There is no saved slice for this yet."** The agent does not need to ask whether one exists.
- **"Do not read the code until the slice is saved."** The agent finds the set first. Reading
  code too early pulls it back to word search.

To choose where the slice goes, add a path such as `.periplus/slices/invoice-reminders.map.json`.
Periplus creates the folder when it saves the slice. Once it is saved, ask for descriptions:

```
This project has a Periplus map and a saved slice of sending invoice reminders at .periplus/slices/invoice-reminders.map.json. Use the periplus skills and commands.

Describe what each thing in the slice does, and save the descriptions. Start at the entrances of the slice, follow what each one sets off, and describe each file as the walk reaches it.
```

When a slice already exists, say so in the request and give its path. The agent then reads it and
does not search again. A saved slice and saved descriptions are paid for once. Every later
question uses them.

## Working as a team

The map is one JSON file that you commit, compare and review. The same code always gives the same
map, byte for byte. Between two builds, `periplus diff OLD NEW` lists the change a pull request
makes to the map: the things and links added, removed and changed.

The descriptions sit in their own file beside the map, `.periplus/descriptions.yaml`. Each entry
carries a fingerprint of the code it describes, so `periplus stale` lists the entries whose code
changed. A project's own rules live in `.periplus/packs`. Together these hold what the team has
learned about the code, in files the next person and the next session read.

## What a good run looks like

You can tell from the commands the agent runs and from its answer.

- It starts from what the feature does, and from its entrances. It does not start from a long list
  of words.
- It asks the cheap commands before it walks: `periplus depth`, `hubs`, `count`, `files` and
  `pieces`.
- It sends periplus output into other periplus commands, such as `--ids` into `periplus count -`.
  It does not cut periplus output with `grep` or `head`.
- It saves the set as a slice before it reads code.
- It looks at the rim of the set: what lies one hop outside it. It gives a reason for each thing
  it left out, such as shared code or another feature.
- It says which parts of the answer came from a code search and not from the map.

When you are not sure, ask plain follow-up questions:

- "Which entrances did you walk from?"
- "What did you leave out, and why?"
- "Did you check what touches the set from outside?"

## If the agent opens the map file

Some agents open `.periplus/map.json` directly and read it as text. If you see that, add this
line to the request:

```
Read the map only through the periplus skills and commands.
```

Do not tell the agent to stop reading files or searching code. Describing a thing needs its code,
and the map skill reads code to confirm a line or where the map has no answer.

The [navigation guide](navigation.md) gives each command's options and output.
