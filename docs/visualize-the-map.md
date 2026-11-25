# Visualize the map

You can look at part of a map as a picture: things as dots, links as lines. A picture shows which
things have many links, and which groups of things stand apart from the rest. Periplus has no
viewer, so you export a slice of the map and open it in a graph tool. This page uses
[Gephi](https://gephi.org), a free desktop tool, and covers two lighter routes.

A picture does not replace the CLI. For an exact answer, such as who calls a function, use
`periplus neighbors` or `periplus reach` (see [Navigation](navigation.md)). Use a picture to get
the shape of an area first.

## Export a slice

Do not export a whole map of a real project. It holds too many dots to read. Cut out the part you
want, write it to its own map file, and export that file. This slice holds everything in the files
under `shop/`:

```
$ periplus slice --path shop/ --out billing.map.json
periplus slice
wrote /path/to/project/billing.map.json: 8 nodes, 7 edges
$ periplus export --format graphml --map billing.map.json > billing.graphml
```

Other ways to cut: start from words or ids (`periplus slice login --out FILE`), keep only some
edge kinds (`--kind calls`), or set how far the walk goes (`--depth 1`). `periplus extract ID...
--out FILE` writes exactly the things you name. Give `--out` a new name, never the name of the
full map. See [slice](navigation.md#slice) for every option.

## What the GraphML holds

Each node carries these attributes, and each edge carries these:

| On | Attribute | Holds |
|---|---|---|
| node | `id` | the map id, such as `python.function::shop.tax.tax_for` |
| node | `label` | the short name of the id |
| node | `type` | the node type, such as `python.module` |
| node | `state` | `mapped`, `boundary`, `unknown_boundary`, `unresolved` or `referenced` |
| node | `file`, `line` | the first place in the code, where there is one |
| edge | `kind` and `label` | the edge kind, such as `calls`, `imports`, `contains` |
| edge | `file`, `line` | the place in the code, where there is one |

The export does not carry confidence, descriptions or a node's other locations. To check a link's
confidence, use `periplus show ID`.

## Open it in Gephi

These steps follow Gephi's own [quickstart](https://gephi.org/quickstart/) and
[FAQ](https://gephi.org/faq/). Menu names can differ a little between Gephi versions. This page
was written without running Gephi, so the steps say what to click and do not promise how the
picture looks.

1. Open `billing.graphml` from the Welcome window, or with File > Open. An Import report shows the
   node and edge counts. Check that they match the slice, import into a new workspace, and press
   OK.
2. Run a layout. In the Layout panel choose ForceAtlas 2 and press Run. When the picture stops
   moving, press Stop. If the dots crowd together, the Gephi pages suggest a Scaling of 100 and
   Prevent Overlap. Set them and run it again.
3. Colour by node type. In Appearance, choose Nodes, click the colour palette icon, choose
   Partition, pick the `type` attribute and press Apply. By default only the 8 largest categories
   get a colour and the rest are grey. To change that, click Palette, clear "Limit number of
   colors", press Generate, then OK. Do the same with `state` to see which things are
   `unresolved` or `unknown_boundary`.
4. Look at the links. The `kind` column is in the Edges table of the Data Laboratory (step 8).
   You can filter on it, as step 7 says. This page gives no menu steps for colouring edges.
5. Find the hubs. In Appearance choose Nodes, click the Size icon, choose Ranking, pick `Degree`,
   set a minimum and a maximum size (the quickstart uses 10 and 50) and press Apply. A bigger dot
   has more links.
6. Show names. In the folding menu at the bottom of the Graph window, tick the box that shows node
   labels. Under Labels > Configure, the Nodes tab picks which attribute is shown. Use `label`.
7. Hide what you do not need. The Filters window has an Attributes folder, which holds filters on
   the columns of the Data Laboratory, such as `kind` or `type`. Use one to keep only the values
   you want, for example only `calls` edges. The Topology folder holds filters on structure, such
   as Degree Range.
8. Read the numbers. The Data Laboratory tab has a Nodes table and an Edges table. Sort a column,
   such as `file`, or use the filter field. The `id` column holds the map id. Paste it into
   `periplus show ID` to read the node's full record.

The Preview tab makes a static image that exports as SVG, PDF or PNG.
Gephi has no undo. If a panel goes missing, Window > Reset Windows brings it back.

Pieces that stand apart in the picture have no links to the rest of the slice. `periplus pieces`
lists them as text and gives the same answer.

Gephi Lite, the browser version the README names, opens the same GraphML file. There the layout
buttons are Start and Stop, and the size ranking is Degree (dynamic).

## Lighter routes

**Mermaid** suits a small slice in a Markdown page, such as a pull request description. Wrap the
output in a code fence marked `mermaid`.

```
periplus export --format mermaid --map billing.map.json
flowchart LR
  n0["python.class::shop.billing.Invoice (python.class)"]
  n3["python.module::shop.billing (python.module)"]
  n3 -- "contains" --> n0
  ...
```

**DOT** is the input format of Graphviz. The output has one line for each node and each edge:

```
periplus export --format dot --map billing.map.json > billing.dot
digraph periplus {
  "python.class::shop.billing.Invoice" [label="python.class::shop.billing.Invoice\npython.class"];
  "python.module::shop.billing" -> "python.class::shop.billing.Invoice" [label="contains"];
  ...
}
```

Render it with Graphviz as you would any DOT file, for example `dot -Tsvg billing.dot -o
billing.svg`. This page was written without running Graphviz.

## How large a slice to draw

This is advice, not a measured limit.

- Mermaid: keep a slice to tens of nodes. The export warns on standard error above 500 edges or
  50,000 characters, and a page may refuse to draw a diagram that large.
- DOT: Graphviz draws a few hundred nodes before the picture is hard to read.
- GraphML in Gephi: hundreds to a few thousand nodes read well when you size by degree and filter
  by edge kind. The README suggests Gephi, not the lighter Gephi Lite, above about 10,000 nodes.

If a picture is too crowded, slice again with `--depth 1`, a single `--kind`, or a narrower
`--path`.
