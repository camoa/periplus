#!/usr/bin/env bash
# The bundled TypeScript stacks, typescript@0.1.0, react@0.1.0 and nextjs@0.2.0, read as text.
# A small Next.js application holds a module with a relative import and an exported function, a
# component that uses a hook and renders another component, a page, a layout, a route handler
# exporting GET, and a fetch('/api/items') call. The check names each node type and edge kind the
# map must hold, and fails naming the ones missing.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
mkdir -p "$site/.periplus" "$site/lib" "$site/components" "$site/app/api/items"
cat >"$site/lib/format.ts" <<'TS'
export function formatItem(name: string): string {
  return name.trim();
}
TS
cat >"$site/lib/load.ts" <<'TS'
import { formatItem } from './format';

export async function loadItems(): Promise<string[]> {
  async function inner(): Promise<string[]> {
    const response = await fetch('/api/items');
    return response.json();
  }
  const items: string[] = await inner();
  return items.map(formatItem);
}
TS
cat >"$site/components/Card.tsx" <<'TS'
export function Card({ name }: { name: string }) {
  return <p>{name}</p>;
}
TS
cat >"$site/components/List.tsx" <<'TS'
import { Card } from './Card';
import { useItems } from './useItems';

export function List() {
  const items = useItems();
  const Row = () => {
    return <li><Card name={items[0]} /></li>;
  };
  return <ul><Row /></ul>;
}
TS
cat >"$site/components/useItems.ts" <<'TS'
export function useItems(): string[] {
  return [];
}
TS
cat >"$site/app/page.tsx" <<'TS'
import { List } from '../components/List';

export default function Page() {
  return <List />;
}
TS
cat >"$site/app/layout.tsx" <<'TS'
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html><body>{children}</body></html>;
}
TS
cat >"$site/app/api/items/route.ts" <<'TS'
export async function GET() {
  return Response.json(['one']);
}
TS
cat >"$site/.periplus/settings.yml" <<'YML'
periplus_version: 0
packs:
  - typescript@0.1.0
  - react@0.1.0
  - nextjs@0.2.0
values:
  typescript_alias_root: .
YML

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report

types = {n["type"] for n in document["nodes"]}
kinds = {e["kind"] for e in document["edges"]}
handles = {e["to"] for e in document["edges"] if e["kind"] == "handles_method"}
missing = [t for t in ("typescript.module", "typescript.function", "react.component",
                       "nextjs.page", "nextjs.layout", "nextjs.route_handler") if t not in types]
missing += [k for k in ("imports", "uses_hook", "renders_component", "calls_route")
            if k not in kinds]
if not any(target.endswith("GET") for target in handles):
    missing.append("handles_method for GET")
def edge(kind, src, dst):
    return any(e["kind"] == kind and e["from"].endswith(src) and e["to"].endswith(dst)
               for e in document["edges"])
if not edge("renders_component", "components/List:List", "components/List:List:Row"):
    missing.append("renders_component from List to its nested Row, written right after >")
if not edge("renders_component", "components/List:List:Row", "components/Card:Card"):
    missing.append("renders_component from the nested Row to Card")
if not any(e["kind"] == "function_calls_route" and e["from"].endswith("lib/load:loadItems:inner") for e in document["edges"]):
    missing.append("function_calls_route from the nested function inner")
if missing:
    sys.exit(f"typescript stacks: the map lacks {', '.join(missing)}")
PY
echo "typescript stacks ok"
