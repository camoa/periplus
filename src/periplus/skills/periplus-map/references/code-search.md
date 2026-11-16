# Code search beside the map

Search the code when the map has no answer, or to confirm what a line does. Text search finds
every place a word is written; the map finds links that are not one text match. Use each for what
it finds.

## When to search

- `periplus find` printed no match for the words and for the wider words you tried.
- A row's source line is not enough, and you need the code around it.
- The answer turns on a value built at run time, such as a row in state `unknown_boundary`.
- You want to check a map answer against the code.

## Back to the map from a hit

- `periplus at FILE:12` names the mapped thing on line 12 of FILE, or on the nearest line above
  that holds one, then what holds it: method, class, module.
- `periplus in FILE` lists everything the map holds in FILE, in line order. `--ids` prints the
  ids, to pipe into another periplus command.
- Then ask the map about what `at` named: `periplus show`, `periplus reach`.

A hit in docs, tests or comments is a lead, not an answer. Leave out hits that do not bear on the
question.

## When the two disagree

If the code holds a link the map lacks, or the map holds one the code does not, say so in the
answer, with the file and line. It is a map gap, and the periplus-gaps skill records it.
