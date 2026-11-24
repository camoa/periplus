---
name: periplus-analyze
description: Guides a code review or analysis that uses a Periplus map. The map names the code that takes part; this skill says how to read and judge that code, and what a map cannot tell you. Use when a project has a .periplus/map.json and the user asks for a judgment about code: review or audit a feature, what can go wrong if this changes, find bugs, missing checks or steps in the wrong order, find code that does the same job twice, or how to improve a part of the code. For questions the map alone answers, such as who calls this or what uses that, the periplus-map skill is enough.
---

# Analyse code with a Periplus map

## A map is not the code

Start every review from this:

- A map holds the things its rules found and the links between them, each with a place. It says
  that A reaches B, and where.
- A map can have gaps. A link the code has and no rule reads is not in the map, and nothing
  marks its absence.
- A map does not hold what happens between the links: when a link runs, under what condition,
  in what order against another, and what is absent. Examples: the branch a call sits in, where
  an exception is caught, a step that should undo an earlier one and is not there.
- Each map says what it holds: it can list its own kinds of things and links. What is not a
  kind there, you take from the code.

So the map says where to read, and the code is what you judge.

## Identify with the map, then read

The periplus-map skill says how to use the map: the commands, what each shows, and how to follow
nodes and edges. This skill names no commands; take them from there, and every option from
[Navigation](https://github.com/camoa/periplus/blob/v0.10.2/docs/navigation.md). Use the map to
name, before you open any code:

- the target, the thing the question is about;
- every entrance that reaches it, and the steps from each one;
- what those steps share: the things more than one of them writes or reads.

Then read the code the map named. A review that reads first covers what the reader happened to
find. A review that identifies first covers what takes part.

## Look around each line

When the map sends you to a line, do not read that line alone, and do not read the whole module.
Read:

- the whole function or method around the line;
- what the map lists beside it in the same file, in line order.

Compare what you read with what the map says the function does. Most
differences are things a map does not hold, and those are what you are here to judge. A link the
map should hold and does not is a gap: note its file and line and go on. You are not looking for
gaps. You notice them because you read around the line.

## Strategies

- **Work back from the target.** Start at the thing the question is about and ask the map what
  reaches it. Starting at the entrances you know misses the ones you do not.
- **One entrance at a time.** Follow one entrance to the target and read it whole before the
  next. Then the differences between entrances stand out.
- **Read past the target.** The steps to the target are half of a function. What runs after it
  is where a failure leaves something behind.
- **Start from what is shared.** A thing that several paths write or read is where two pieces of
  code can disagree. Ask the map for every writer and reader of it, and compare them.
- **Compare before you read.** For code that may do one job twice, ask the map what two
  entrances both run and what only one runs. Read the difference.
- **Look for what attaches itself.** Some code runs on a path without being called from it. Ask
  the map what is tied to the things on the path by a link no walk follows.
- **Split a large reading by entrance.** Give each reader its steps with their files and lines,
  not a topic.

## Ask the same questions at every entrance

A free read finds what the reader looks for. The same questions at every entrance find the same
kind of fault everywhere. Adapt the words to the topic:

- What runs before the target, and what does it check?
- What runs after the target in the same function? If that fails, what is left behind?
- Which inputs reach the target, and where is each one checked?
- Who else writes what this path writes, and do they write it the same way?
- What does this entrance do that the other entrances to the same target do not?

## Report

- Give each finding its file and line, and the entrance it sits on.
- Say for each finding whether you read the lines yourself or it rests on a description or on
  another reader. Say that nothing was run, unless it was.
- List the gaps you noticed, each with its file and line. The periplus-gaps skill records a gap
  and says which rule would close it. Once the rule exists the map holds the link, and the next
  question starts with it.
- If part of the answer came from a text search and not from the map, say which part.
