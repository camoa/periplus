# Evals

Two jobs, each done by the same agent on the same code with a Periplus map and without one. The
first job is one run per side. The second is three runs per side.

## The job

Find and describe everything that takes part in user login and account registration.

The code is a client's Drupal site with 44 custom modules. It is not named here. Its map holds
47,972 nodes and 101,357 edges. The agent is Claude Code on Claude Opus 5.5.

## The prompts

With the map:

```
This project has a Periplus map. Use the periplus skills and commands.

Find everything that takes part in user login, authentication, login sessions and
account registration. Follow the nodes and edges in the map, and keep what is
connected to the feature and still related to it. There is no saved slice for this
yet: build one with the periplus commands and save it. Do not read the code until
the slice is saved.
```

```
This project has a Periplus map and a saved slice of the login feature at
.periplus/slices/login.map.json. Use the periplus skills and commands.

Describe what each thing in the slice does, and save the descriptions. Start at the
entrances of the slice, follow what each one sets off, and describe each file as the
walk reaches it.
```

Without the map:

```
Inventory all user login, authentication, login sessions, account registration and
related code: the classes, functions, methods, hooks, routes, templates and
configuration that take part. Describe what each one does. Save the inventory and
the descriptions.
```

## Cost

| | With map | No map |
|---|---:|---:|
| Model replies | 158 | 323 |
| Output tokens | 132,021 | 244,316 |
| Cache-read tokens | 15.8 million | 38.1 million |
| Shell commands | 127 | 313 |
| Subagents | 5 | 8 |
| Time | 21.4 minutes | 14.5 minutes |

The numbers come from the session transcripts, subagents included.

## What came out

| | With map | No map |
|---|---|---|
| Form | A saved slice of the map, and descriptions that `periplus find` searches | Seven Markdown files and an index |
| Size | 249 things and 436 links | 501 table rows |
| Described | 141 things and 129 links | Each row |

Both covered the login form, registration, password reset, logout, the code that runs at login,
and account creation by other code paths.

The map side stayed inside the feature and gave a reason for each area it left out. The no-map
side went through the codebase area by area, which also brought in site settings, scripts and
contributed modules.

## Using the result

One later job, run three times on each side by a script. Each run is a fresh session with the
same words. The map side had the map and its saved slice. The no-map side had its inventory.

With the map, the session opens with:

```
This project has a Periplus map, a saved slice of the login feature at
.periplus/slices/login.map.json, and descriptions. Use the periplus skills and commands.

Answer from the map first: use the periplus tools and follow the map before you open
any code. Go to the code only for what the map does not cover.
```

Without the map:

```
This project has an inventory of the login feature in auth-inventory/.
```

Then two prompts, the same on both sides. No prompt names a command or a skill.

```
We are going to change how a user account gets created on this site. List every way
a request ends up creating an account: the pages, forms, commands and scheduled jobs,
with the path from each one to the code that creates the account.
```

```
Now read the code on each of those paths and tell me what is likely to go wrong
when we change how accounts are created: bugs, steps in the wrong order, missing
checks. Give the file and line for each.
```

On the map side, runs 1 and 2 end with a third prompt in the same session:

```
Before the next question, make the map better from what you just learned. For each
gap in the map that you noticed, add a rule for it in this project's own rutter under
.periplus/packs, and rebuild the map. Describe the code you had to read, so the next
reader finds it by words. Change only files under .periplus/. Then tell me what you
added.
```

So run 2 uses the map that run 1 improved, and run 3 the map that run 2 improved. The no-map
side has nothing to carry over.

### With the map, the work was steadier

The list, in output tokens:

| | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| With map | 10,325 | 11,277 | 11,106 |
| No map | 11,649 | 13,631 | 80,804 |

All answers together name 17 ways to create an account. Every run on both sides listed 16 or 17
of them. The map side did it for the same cost each time. The no-map side matched that cost
twice, and the third time handed the job to subagents and cost seven times more.

### A better map helps more

The second prompt, on the map side:

| | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Likely problems reported | 37 | 49 | 68 |
| Map gaps reported | 2 | 9 | 0 |
| Output tokens | 71,118 | 75,926 | 98,085 |

The two improvement steps wrote a rutter of five rule files in the project, which added 1,804
links to the map, and 257 descriptions. They cost 81,562 and 106,554 output tokens. That cost is
paid once, and the map keeps what it gained.

On the map as generated, the no-map side reported more likely problems, 58 against 37. The map
side passed it after the two improvement steps.

### Without a map the answer changes

The second prompt, on the no-map side:

| | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Likely problems reported | 58 | 74 | 46 |
| Faults found in its own inventory | 0 | 6 | 1 |
| Output tokens | 98,917 | 133,348 | 121,342 |

Nothing changed between these runs. On one fact, whether a set of commands is guarded against
running in production, the three runs said "none found", "not checked" and "sandbox guard".

A likely problem is one an answer reported with a file and line. They were counted across the
answers, not tested.
