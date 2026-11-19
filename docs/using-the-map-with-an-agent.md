# Using the map with an AI agent

This page is for people who ask an AI coding agent questions about a project that has a Periplus
map. It says how to word a request so the agent uses the map, and how to tell that it did.

## Why the wording matters

An agent tends to skip the map. Left alone, it searches by words and filters the output with other
tools. It stops when the word search looks complete, and it reads code it did not need. The
periplus skills steer it toward the map. The wording of the request steers it more. What the skills
cannot enforce, the prompt can.

## What using the map means

Using the map means following its nodes and edges to find everything that is connected to the
topic and still related to it. Words only find where to start.

For a feature, or any request for everything that takes part in something, the result is a saved
slice. A slice is a map file that holds the set. The agent can build it in parts, one per entrance,
and join them into one file. The commands that read a map read a slice with `--map FILE`.

## Find a feature

Copy this, and name the feature in your own words:

```
This project has a Periplus map. Use the periplus skills and commands.

Find everything that takes part in sending invoice reminders. Follow the nodes and edges in the map, and keep what is connected to the feature and still related to it. There is no saved slice for this yet: build one with the periplus commands and save it. Do not read the code until the slice is saved.
```

What each sentence is for:

- **"This project has a Periplus map."** The agent knows the map is there before it searches.
- **"Use the periplus skills and commands."** This names the way of working.
- **"Follow the nodes and edges..."** This says what using the map means, and when to stop.
- **"There is no saved slice for this yet."** The agent does not need to ask whether one exists.
- **"Do not read the code until the slice is saved."** The agent finds the set first. Reading
  code too early pulls it back to word search.

To choose where the slice goes, add a path such as `.periplus/slices/invoice-reminders.map.json`.
Periplus creates the folder when it saves the slice.

## Describe it afterwards

Once the slice is saved, copy this:

```
This project has a Periplus map and a saved slice of sending invoice reminders at .periplus/slices/invoice-reminders.map.json. Use the periplus skills and commands.

Describe what each thing in the slice does, and save the descriptions. Start at the entrances of the slice, follow what each one sets off, and describe each file as the walk reaches it.
```

The descriptions go into `.periplus/descriptions.yaml`. After that, `periplus find` reaches each
thing by plain words, and `periplus show` prints what each linked thing does.

## When a slice already exists

Say so in the request, and give its path. The agent then reads it with `--map` and does not search
again. A saved slice and saved descriptions are paid for once. Every later question uses them.

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
