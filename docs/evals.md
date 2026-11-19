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

## Accuracy

To come.

## Using the result

To come: later questions answered from the saved slice and its descriptions, such as what
touches a given thing and what is unused.
