# Evals

One job, done twice by the same agent on the same code: once with a Periplus map, once without.
One run per side.

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

One later question, asked on both sides in a fresh session. The map side had the map and its
saved slice. The no-map side had its inventory.

With the map:

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

The question, the same on both sides:

```
We are going to change how a user account gets created on this site. List every way
a request ends up creating an account: the pages, forms, commands and scheduled jobs,
with the path from each one to the code that creates the account.
```

| | With map | No map |
|---|---:|---:|
| Model replies | 17 | 136 |
| Output tokens | 9,431 | 71,526 |
| Cache-read tokens | 1.8 million | 12.4 million |
| Shell commands | 12 | 135 |
| Subagents | 0 | 3 |
| Time | 3.6 minutes | 6.8 minutes |

Both sides gave the same list: eight web entry points, the commands that create accounts, and no
scheduled job.

The no-map side found its own inventory wrong in five places, so it traced the code again with
three subagents. It also reported five likely problems it saw while reading.

The map side walked back from the code that creates an account to the routes and commands that
reach it. It read code only where the map had no link, and it named those gaps.

### The tokens saved

A follow-up in the same map session asked it to read the code on those paths and say what is
likely to go wrong:

```
Now read the code on each of those paths and tell me what is likely to go wrong
when we change how accounts are created: bugs, steps in the wrong order, missing
checks. Give the file and line for each. Use periplus path for the steps of each path.
```

| | With map, both questions | No map |
|---|---:|---:|
| Model replies | 95 | 136 |
| Output tokens | 78,536 | 71,526 |
| Cache-read tokens | 9.6 million | 12.4 million |
| Subagents | 4 | 3 |
| Time | 9.4 minutes | 6.8 minutes |

For about the same cost, the map side reported about 45 likely problems with file and line. They
include four of the no-map side's five.

### A gap becomes a rule

The map side named two links the map did not hold: code that creates an entity through its
storage, and the methods a form runs. Both are rules in the Drupal rutter since 0.10.2. The next
question on that map starts with them.
