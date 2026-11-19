# Evals

This page sets out one evaluation of Periplus: what it asks, how each run is set up, and how
each number is counted. It holds the numbers of the first run. Later runs add to it.

**One run per side is one data point.** The first run gives one number for each side. It shows
no spread between runs, and it is not a verdict.

## What the eval asks

Does a map, with descriptions, help an AI agent do work on a codebase? And at what cost?

The eval has two parts:

- **Inventory.** Find and describe everything that takes part in one feature.
- **Using the result.** Answer later questions from the saved slice and its descriptions. One
  example asks what touches a given thing. Another asks what is unused.

### Using the result

This part is planned. It has no numbers yet.

## Setup

- **The code.** A client's Drupal site. The site is not named, and its cases are not published.
  It has 44 custom modules and 3 custom themes.
- **The map.** 47,972 nodes and 101,357 edges, of 86 node types and 225 edge kinds, made with
  17 rutters.
- **Two copies of the same code.** The map side has a `.periplus/map.json`, the four periplus
  skills and Periplus 0.9.2. The no-map side has no map and no periplus skills.
- **The agent.** Claude Code. The main loop ran Claude Opus 5.5 on both sides.
- **Subagents.** Each side chose by itself to hand work to subagents. The map side used 4, all on
  Claude Sonnet 5.5, only to write descriptions. The no-map side used 8: 7 on Opus 5.5 and 1 on
  Sonnet 5.5.
- **Input.** Each side got one prompt and ran with no further input.

## Inventory

### The two prompts

Map side:

```
This project has a Periplus map. Use the periplus skills and commands.

Find everything that takes part in user login, authentication, login sessions and
account registration. Follow the nodes and edges in the map, and keep what is
connected to the feature and still related to it. There is no saved slice for this
yet: build one with the periplus commands and save it. Do not read the code until
the slice is saved.

Then describe what each thing in the slice does, and save the descriptions.
```

No-map side:

```
Inventory all user login, authentication, login sessions, account registration and
related code: the classes, functions, methods, hooks, routes, templates and
configuration that take part. Describe what each one does. Save the inventory and
the descriptions.
```

The prompts differ on purpose. Each asks for the same work in the way that fits its side.

### Cost

First run, one run per side.

| | With map | No map |
|---|---:|---:|
| Model replies | 111 | 323 |
| Output tokens | 108,385 | 244,316 |
| Cache-read tokens | 14.2 million | 38.1 million |
| Cache-write tokens | 603,023 | 1,306,708 |
| Fresh input tokens | 230 | 662 |
| Shell commands | 97 | 313 |
| Subagents | 4 | 8 |
| Time from prompt to final answer | 12 minutes | 14.5 minutes |

Note: after the inventory, the no-map run added one more subagent by its own choice. That
subagent checked claims the run had made about the code. Its share is 39 model replies, 21,394
output tokens and 3.6 million cache-read tokens. The table's figures include it. The inventory
files were complete 10 minutes after the prompt.

The map side, by phase:

| | Find and save the slice | Describe |
|---|---:|---:|
| Model replies | 32 | 79 |
| Output tokens | 18,443 | 89,942 |
| Cache-read tokens | 4.4 million | 9.8 million |
| Time | 6.7 minutes | 5.5 minutes |

The split matters because the slice and the descriptions are saved. A later question reads them
and does not repeat this work. Part two will measure what that is worth.

The describe step ran a second time, in a new session, on the same saved slice. Between the two
runs the describe skill changed: it now sets out the work as a walk from the entrances of the
slice. The prompt for the second run:

```
This project has a Periplus map and a saved slice of the login feature at
.periplus/slices/login.map.json. Use the periplus skills and commands.

Describe what each thing in the slice does, and save the descriptions. Start at the
entrances of the slice, follow what each one sets off, and describe each file as the
walk reaches it.
```

| | Describe, first run | Describe, second run |
|---|---:|---:|
| Model replies | 79 | 101 |
| Output tokens | 89,942 | 80,278 |
| Cache-read tokens | 9.8 million | 9.3 million |
| Time | 5.5 minutes | 11.6 minutes |
| Things described | 141 | 105 |
| Links described | 176 | 78 |
| Entries a second reader compared with the code | 3 | 92 things and 78 links |
| Entries rewritten after that reading | 0 | 15 things and 2 links |

The first run also described 36 methods inside classes. The second run described the classes
and not their methods. The second reader was a subagent of the run itself, on Opus 5.5. It is not the accuracy
measure planned below.

### Size of the result

| | With map | No map |
|---|---|---|
| Form | One slice file and entries in `.periplus/descriptions.yaml` | Seven Markdown files and an index |
| Things | 249 things and 436 edges in the slice | 584 items by the agent's own count, in 501 table rows (some rows name several things) |
| Descriptions | 141 main things, each with a description, and 176 links | One for each of the 501 rows |

`periplus find` searches the descriptions file, so a plain-word question reaches the entries.

### Scope

Both sides covered the same core:

- the login form and its changes
- registration and its validation
- password reset and logout
- the code that runs at login
- account creation by other code paths

The map side left out the sign-up flows of other features that create an account on the way. It
kept only the shared methods that create the account. It gave a reason for each area it left
out.

The no-map side split the codebase into seven areas. It listed what each area held that related
to accounts. That also brought in site settings, scripts and contributed modules.

Which scope is the right answer, the wider or the narrower, is not scored yet.

### Accuracy

Not measured yet. The planned method:

1. Draw a random sample of the same size from each side's descriptions.
2. Mix the two samples and hide which side wrote each entry.
3. A reader that did not write them checks each entry against the code.
4. Count every statement that the code can settle, and count the false ones.

## How the numbers are counted

- The numbers come from the session transcripts that Claude Code writes. They do not come from
  what the agent says about itself.
- Each model reply has one usage record. Subagent replies are counted too.
- Time runs from the prompt to the final answer.
- Each token type is reported on its own and not added up. The types are priced differently,
  and the two sides used different models for part of the work.

## Limits of this eval

- One run per side. No spread between runs is known.
- The subagent models differ between the sides, so tokens do not translate into money.
- The prompts differ.
- The results differ in kind: a slice with searchable descriptions on one side, documents on the
  other.
- Accuracy and scope are not scored yet.
- One site, one stack, one feature.
- The site and its cases are private, so a reader cannot repeat the run on the same code.

A reader can repeat the method on their own code with the two prompts above.
