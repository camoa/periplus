---
name: periplus-setup
description: Sets Periplus up in a project and builds its first map. It pins the rutters the project needs, sets the folders, exclusions and values only the project knows, runs periplus map, and says in plain words what the map holds and what it lacks. Use when the user says set up Periplus, install or initialise Periplus in this project, map this project, make a map of this code base, or which rutters does this project need, and when the project has no .periplus folder or no .periplus/map.json and the user asks a question a map would answer. Answering from a map that exists is the periplus-map skill.
---

# Set a project up and make its first map

A map holds what its rutters look for. Setup decides which rutters load and where they look, so
most of the map's quality is decided here. Change only files under `.periplus/`. Never write
inside the project's code.

## 1. Check the tool

Run `periplus --version`. If the command is missing, tell the user how to install it and stop:
`uv tool install periplus-map`, or `pip install periplus-map`. Do not install it without asking.

To get a newer Periplus, the order is: `periplus upgrade` first, which upgrades the tool and
refreshes the installed skills, then `periplus update` in each project, which moves that
project's pins to the new rutter versions. Then build the map again. Do not upgrade without
asking.

## 2. Run init

Run `periplus init` in the project root, the folder that holds the code and its manifests.

- It creates `.periplus/settings.yml` and `.periplus/packs/`. It prints one `detected` line per
  rutter it pinned, with the file that matched.
- It prints one line per folder a pinned rutter reads: `folder` when found, `optional` when the
  rutter needs none, and `unplaced` when it found the folder nowhere. A folder found away from the
  rutter's default is written under `folders` in the settings.
- When it prints `refused` and exit 10, the project already has a settings file. Read it and go
  on from what it says. Never delete it or write it again.

Then run `periplus status`. Under Effective settings it shows the pins and folders now in force.
Under Candidates it lists every rutter Periplus can load, the bundled ones included.

## 3. Find what init could not see

A rutter is pinned only when its `pack.yaml` declares a detector that matches. The detectors of
the language and framework rutters look at the project root and its `src` or `lib` folder, so a
stack in a subfolder, such as a front end in `frontend/`, is not detected. When nothing matched,
init says so. So look at the project yourself: the manifests at the root and in subfolders, and
the file endings that hold most of the code.

[Bundled rutters](https://github.com/camoa/periplus/blob/v0.11.0/docs/rutters.md) says what each
rutter maps, what it depends on and what settings it needs. For each stack you find:

- **Pinned.** Nothing to do.
- **Pinned, not wanted.** The list under `packs` is the project's to change. When the user does
  not want a rutter that init pinned, delete its line and say so.
- **Present, not pinned.** Pin it by hand under `packs`, with the version `periplus status`
  lists. Tell the user why init missed it. For example, a JavaScript project whose scripts are
  not in `index.js`, `src` or `lib` gets:

```yaml
packs:
  - js_basic@0.0.2
```

- **Present, and no rutter covers it.** Say so plainly, and name the files the map will not
  hold. A Python project is one: no bundled rutter reads Python. The
  [example rutters](https://github.com/camoa/periplus/blob/v0.11.0/examples/second-stack/packs),
  one of them for Python, can be copied into `.periplus/packs`. A new rutter is the periplus-rutter skill's work. Never
  pin a rutter the project gives no evidence for.

When init left nothing under `packs`, the settings file has no active `packs` key. Add one at the
end of the file.

## 4. Set what only the project knows

The settings file names every key, with a comment on each. A first setup needs these:

- `folders`: where the code is, when it is not where a rutter's default says. The names and
  defaults are under `folders` in the rutter's `pack.yaml`; `periplus status` prints its path.
  For an `unplaced` folder, set it when the project has that code elsewhere. Leave it when the
  project has none.
- `exclude`: what is not the project's code: generated output, vendored copies, build folders.
  `php_basic` already leaves out `vendor` and `node_modules`, and `js_basic` and `typescript`
  leave out `node_modules`. A generated file that is read anyway can show as a skipped match.
- `values`: text a rutter cannot find for itself. `go_basic` needs the module path as `module`.
  `typescript`, which `react` and `nextjs` load, needs `typescript_alias_root`, the folder the
  `@/` import alias points at.

Ask the user when the code alone cannot say, such as whether a folder of copied code is theirs.

For Drupal, two more cases:

- `drupal_basic` reads the `*.services.yml` files of Drupal core and of contributed modules, so a
  service the code injects is a mapped thing. From core it reads nothing else. It finds core in
  the folder `core`, by default `web/core`, and contributed modules in `contrib_module`, by
  default `web/modules/contrib`. init writes `docroot/core` or `core` when it finds one. When the
  site keeps them elsewhere, set `folders: {core: <path>, contrib_module: <path>}`.
- A module, theme or install profile that is its own repository has its `*.info.yml` file at the
  root. init detects it, but the rules name a module by the folder that holds it, so they need
  its machine name. Run `periplus init` in the module's own folder, then add
  `folders: {custom_module: .}`, or `custom_theme: .` for a theme, and
  `values: {drupal_extension: <machine name>}`, the name of its `*.info.yml` file. Run
  `periplus map` in that folder.

## 5. Build the map

Run `periplus map`. It reads every selected file, so it can take minutes on a large project. It is
the one command here that runs only because setup was asked for. Run it again only to fix a
setup fault it reports, or when the user asks.

When it stops, the Problems section names the cause, and no map is written:

- exit 17: no rutter is pinned. Go back to step 3.
- exit 26 naming a settings value: add that value under `values`.
- exit 33: no pinned rutter found a file. The section Packs that selected no file names each
  folder it looked in. Set the right ones under `folders`.

## 6. Tell the user what they have

The report lists every rule of every loaded rutter, so it is long. Read these parts:
Problems, Packs that selected no file, Files, Files no rule read, Files that did not parse
cleanly, and Matches skipped. Then run `periplus types` for the counts by type. Tell the user,
in plain words:

- what was mapped: the main types and their counts, and the rutters that loaded;
- which files no rule read, by ending. The map knows nothing about them. A manifest such as
  `composer.json` is normal; a family of code files is a rule or a rutter still missing;
- any pinned rutter that found nothing, any skipped match and any file that did not parse;
- that a map holds what its rutters look for, so a link no rule reads is not in it.

[Reading the map report](https://github.com/camoa/periplus/blob/v0.11.0/docs/map-report-guide.md)
explains each part, and [Judging a map](https://github.com/camoa/periplus/blob/v0.11.0/docs/mapping-quality.md)
says how far to trust it.

## 7. Say what to commit and what comes next

Commit `.periplus/settings.yml`: the settings decide what the map holds. The map,
`.periplus/map.json`, is a file to commit, compare and review. Commit the inputs record beside
it, `.periplus/map.inputs.json`, so that `periplus fresh` can tell whether the map still matches
the code. Commit `.periplus/packs` when it holds a rutter of the project's own.

Next steps: ask the map questions (the periplus-map skill), describe what the main things do (the
periplus-describe skill), or find what the map lacks (the periplus-gaps skill).
