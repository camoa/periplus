---
name: periplus-document
description: Connects a project's existing documentation to its Periplus map with small rules in the project's own rutter, records the agreed documentation conventions in .periplus/documentation.md, and keeps new pages connected. Use when the user says connect or link our docs to the code, map the documentation, which docs talk about this, which docs are out of date or name things that no longer exist, document this feature so it stays connected, or set documentation conventions for this project. Saying what one thing or one link does is the periplus-describe skill; writing and checking a rule is the periplus-rutter skill.
---

# Connect a project's documentation to its map

Once the project's rutter reads its pages, the map answers three things: which pages and sections
name a piece of code, which names in the pages match nothing in the code, and how the pages link
to each other. When the code changes, `periplus diff OLD NEW` shows which pages lost their link.

Periplus keeps three kinds of knowledge. A rule says how to find things in code. A description
says what one thing or one link means. A page of documentation says how things fit together:
features, flows, decisions. A sentence about one thing belongs in a description; a sentence about
how several things fit belongs on a page. Nothing in Periplus changes for this work: a rutter the
project owns reads the pages.

## 1. Read what the project already has

Read the pages first. List each way they name code, with one real example and its file and line:
a name in inline code, a `Class::method` form, a link to a source file, one heading per feature, a
decision record with a Status line or a "Related" list, links between pages. Note what is not a
code name too, such as a setting key or a shell command in inline code. Nobody rewrites the pages
to fit a format; the rules fit the pages.

## 2. Agree the conventions with the developer

Show the list and ask which habits to keep. Only where the project has no habit, propose the
lightest one for new pages: write a code name in inline code, as the code spells it, so a rule
can find it. Never record a convention the developer did not agree to.

## 3. Record them in the project

Write the agreed habits to `.periplus/documentation.md`, a short plain page. The next agent
looks there without being told. The developer and the agent own it. Periplus does not read it
and defines no format for it. Each habit names the rule file that reads it. The rules are what
the map is built from; the page explains them. A habit and its rule are added together.

<!-- example conventions: .periplus/documentation.md -->
```markdown
# Documentation conventions

Agreed with the developer. Each habit below is read by the named rule file in
.periplus/packs/invoicing@0.1.0/rules.

- A section per feature, under a heading. Read by docs_pages.yaml.
- A class or method in inline code, as the code spells it: `Invoice::send()`. Read by
  docs_names_call.yaml and docs_names_bare.yaml; joined by php_fits.yaml.
- A decision record starts with `Status: Accepted`. Read by docs_status.yaml.
```

## 4. Write one small rule per habit

Put the rules in the project's own rutter under `.periplus/packs`, one rule file per habit. If a
project writes a code name in ten ways, that is ten small rules, and the eleventh touches none of
them. The joins to code are the same: one join rule per form of a name, such as full class,
short class and `Class::method`. The Markdown rules know no language; only the joins know the
stack. A way of writing that only the stack has, such as a PHP name with a leading backslash,
goes with the joins. In the reference, adding that one file and changing no other gave one new
link in `periplus diff` and removed nothing; the join rules picked the new name up unchanged.

Write each rule through the periplus-rutter skill: `periplus validate PACK`, then a tiny fixture
that holds the habit, then the map. references/documentation-rules.md holds a worked example to
adapt: the rule files of one small project, the gate for missing names, and real output. No rule
reads a file under `.periplus`, so the conventions page is never mapped as documentation.

## 5. Map, then check each answer

Run `periplus map` only when the user asked for this work. It reads every selected file and can
take minutes on a large project. Then check each answer on a thing you know:

- **Pages that name a thing:** `periplus show ID` lists them under the join's link kind, each at
  the page's line.
- **Names that match nothing:** `periplus find --type TYPE --limit 0`, with the type the
  missing-name rule emits. `periplus show` on one of them gives the page and line.
- **Links between pages:** `periplus show` on a page lists its links both ways.
  `periplus find WORDS --kinds` lists every link whose kind's meaning holds the words.
- **Code that no page names:** no single command gives it. Save two map files and subtract:

```
periplus find --type PAGE_TYPE --ids | periplus neighbors - --touch --kind KIND --depth 1 --ids | periplus extract - --out documented.json
periplus find --type CODE_TYPE --ids | periplus extract - --out code.json
periplus minus code.json documented.json --ids
```

Read the map report's passes too: the missing-name rule must fire in a later pass than every join.

## 6. Use it when the code changes

Keep a copy of the old map before you map again. `periplus diff OLD NEW` then lists each lost
link from a page beside the missing-name mark that took its place, so the change names the
sections to rewrite. A page or a section can take a description, and `periplus stale` lists it
when its text changes. A renamed heading shows as gone: a section's id is its anchor, so every
link to the old anchor breaks too.
[Navigation](https://github.com/camoa/periplus/blob/v0.11.0/docs/navigation.md#diff) gives the
options.

## Writing new documentation

- Find what takes part with the map first: the periplus-map skill saves the set as a slice.
- Read the code before you write about it. The map says where; the code says what.
- Follow the conventions in `.periplus/documentation.md`, so the new page joins the map.
- Do not repeat what a page or a description already says. Link to the page, and leave what one
  thing does to its description.

## What a mapped reference means

A link from a page to a class shows that the page names the class. It does not show that what
the page says is true. A page is not evidence about the code: read the code. A name with no
link means no join rule fits it, not that the code lacks it. Every join rests on a name written
as text, so declare its confidence `mentioned`.

## Limits

- **A missing-name rule can run too early.** A map rule's `unless` sees the map as it stood when
  its pass began, so the plain rule fires beside the joins and marks real names missing, with no
  message. A gate edge written in pass 1 makes it wait for pass 2. It holds only while every join
  fires in pass 1. The reference shows the gate.
- **A link to a source file stops at the file.** No map rule can read the file a node sits in.
  Run `periplus in FILE` on the link's target to list what the file holds, or agree a habit that
  writes the class name beside the link.
- **Junk and false positives.** Inline code with a space is no name. Name nodes are internal, so a
  name nothing joins stays out of the written map. Only a name shaped like code can be marked
  missing, and a table of words such as `JSON` keeps those out. A new word of that kind is a
  false mark until it joins the table.
- **A lowercase method alone joins nothing.** `email()` without its class could be any method.

## Rules

- Change only `.periplus/` and the documentation files the user asked for.
- Never invent a convention the developer did not agree to.
- A new habit is a new small rule, recorded on the page with its rule file.
- Stack knowledge stays in rules. Do not ask for an engine change before two ways of writing the
  rule are each refused with an engine message:
  [Extending Periplus](https://github.com/camoa/periplus/blob/v0.11.0/docs/extending-periplus.md#4-the-engine-last).
