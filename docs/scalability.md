# Size, time and memory

This page says how long Periplus takes and how much memory it uses as a project grows, from one
set of runs. Use it to judge what to expect on your project, and what to do when the map is large.

The numbers come from one Linux machine and from generated code. They show how the cost grows.
They are not a promise for your code or your machine.

## In short

- Time, memory and map size grow in step with the number of things in the map. Ten times the
  things cost about ten times as much.
- A map of about 10,000 things builds in seconds, and each question takes under a second.
- A map of about 100,000 things builds in about three minutes, and each question takes 3 to 8
  seconds.
- A map of about 1,000,000 things builds in about 30 minutes and needs about 17 GiB of memory.
  Each question takes 30 to 75 seconds and about 7 GiB.
- `periplus fresh` stays fast at every size, because it runs no rule.

## How the runs were made

- **Machine:** AMD Ryzen 9 8945HS (8 cores), 60 GiB of memory, Linux, Python 3.11.
- **Code:** a generated invoicing project in PHP, one class per file, 50 to 300 lines each, with
  inheritance, interfaces and calls between classes. About one class in 200 is a hub that many
  classes call.
- **Rutter:** `php_basic` only.
- **Periplus:** the code released as 0.10.3, measured shortly before the release.
- **Timing:** each command ran alone. The two smaller sizes ran three times, and the tables give
  the middle run. The largest size ran once.

## The three sizes

| PHP files | Lines | Things | Links | Map file |
|---|---|---|---|---|
| 127 | 22,229 | 10,303 | 21,623 | 19.2 MB |
| 1,270 | 226,698 | 104,036 | 218,475 | 193.6 MB |
| 12,700 | 2,288,901 | 1,057,986 | 2,229,433 | 1.97 GB |

`php_basic` maps each method, each property and each call site as a thing. So a line count gives
a rough idea only: this code made one thing for about every two lines. A rutter that maps less
makes a smaller map from the same code.

## Building the map

| Things | `periplus map` | Peak memory |
|---|---|---|
| 10,303 | 16.9 s | 208 MiB |
| 104,036 | 173 s | 1.73 GiB |
| 1,057,986 | 1,797 s (30 min) | 16.9 GiB |

From the middle size to the largest, the things grew 10.2 times, the time 10.4 times and the
memory 9.8 times.

`periplus map` builds the whole map each time. It does not update a part of it.

## Checking that the map is current

| Things | `periplus fresh` | Peak memory |
|---|---|---|
| 10,303 | 0.9 s | 51 MiB |
| 104,036 | 1.2 s | 217 MiB |
| 1,057,986 | 6.6 s | 1.87 GiB |

After one file was edited, `fresh` took the same time, named the file and exited 34. So on a
large project, run `fresh` first and build the map only when it says the map is stale.

## Asking the map

Wall time for one command. Memory was about 100 MiB at the small size, 730 MiB at the middle size
and 7 GiB at the largest, for every command.

| Command | 10,303 things | 104,036 things | 1,057,986 things |
|---|---|---|---|
| `find WORD --limit 1` | 0.75 s | 7.0 s | 74.6 s |
| `show ID` | 0.37 s | 3.3 s | 31.8 s |
| `affected ID --depth all` | 0.58 s | 6.0 s | 67.7 s |
| `neighbors ID --depth all` | 0.59 s | 6.4 s | 71.0 s |
| `path A B` | 0.44 s | 3.8 s | 37.7 s |
| `slice --from ID --depth 3 --out FILE` | 0.66 s | 5.3 s | 55.6 s |
| `depth ID` | 0.39 s | 3.5 s | 35.0 s |
| `count -` with 1,000 ids | 0.32 s | 3.5 s | 33.2 s |
| `diff OLD NEW` | 0.81 s | 8.4 s | not run |

Each command reads the whole map file when it starts. Periplus keeps no server and no index
between commands, so that cost is paid each time. At the largest size, `count` of 1,000 ids took
33 seconds, and that command does very little work of its own.

At the largest size, the walks were large too: `affected` on the most-called method reached
100,354 things in 17 hops.

## What to do with a large map

- **Work on a slice.** `periplus slice ... --out FILE` writes the part of the map around a
  feature to its own map file. Every navigation command takes `--map FILE`, and a small file
  answers at the speed of a small map. See [Navigating the map](navigation.md).
- **Map less.** `folders` and `exclude` in `.periplus/settings.yml` decide which files Periplus
  reads. Vendored code and generated code are the usual things to leave out.
- **Run `fresh` before `map`.** It tells you in seconds whether a build is needed.
- **Find a slow rule.** `periplus map --slow-after SECONDS` names each rule that runs longer than
  that on one file.

## The same map each time

The same runs compared maps byte for byte. On two projects, the map came out identical when:

- the same command ran again;
- the command ran from a subfolder, or from outside the project with `--settings`;
- the project sat at a different absolute path;
- Python's hash seed was 0, 1 or random;
- the locale was C, C.UTF-8, en_US, de_DE or ja_JP;
- the time zone was UTC, America/Bogota, Asia/Kolkata or Pacific/Chatham;
- the files were created in reversed or shuffled order.

With the rutter pins in `settings.yml` in reversed order, the map was identical too. The inputs
record was not, because it holds a digest of the settings file. So `periplus fresh` reports a map
as stale after the pins are reordered, though a new build gives the same map.

## What was not measured

- Other operating systems, and other machines.
- Projects above about one million things.
- Stacks other than PHP with `php_basic`. Other rutters do other work on each file.
- Real code. Generated code is more even than a real project.
- Where the time goes inside a build. `--slow-after` times rules on files only.
