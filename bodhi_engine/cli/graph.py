"""
Generate Mermaid diagrams from .bodhi/ flow definitions.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bodhi_engine.parser import load_bodhi_dir
from bodhi_engine.parser.yaml_parser import Flow, Entity

# writes that are not real database tables. Matched as exact names OR as
# prefixes followed by ':' (e.g. 'cache:lb:{competitionId}').
_NON_DB_WRITES = {"response", "request", "log", "cache", "session", "cookie", "header"}

# Matches any character that is not allowed in a Mermaid node id.
_ID_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_id(name: str) -> str:
    """Convert a name like 'OrderService.create' to a valid Mermaid node id.

    Mermaid node ids must only contain [A-Za-z0-9_]. Anything else (dots,
    colons, parentheses, braces, slashes, hyphens, spaces, CJK, etc.) is
    replaced with '_'. Consecutive underscores are collapsed to keep ids
    readable, and leading underscores are stripped.
    """
    sanitized = _ID_INVALID_CHARS.sub("_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "node"


def _is_non_db(name: str) -> bool:
    """Check if a read/write target is not a real DB table.

    Matches exact names (e.g. 'response') or prefixes followed by ':'
    (e.g. 'cache:lb:{competitionId}', 'session:user:{id}').
    """
    lowered = name.lower().strip()
    if lowered in _NON_DB_WRITES:
        return True
    for prefix in _NON_DB_WRITES:
        if lowered.startswith(prefix + ":"):
            return True
    return False


def _parse_event_name(raw: str) -> str:
    """Extract the bare event name from an emit/consume string.

    Handles these formats (per Bodhi DSL spec):
      - 'event_name(field1, field2)'
      - 'event_name(field1) to kafka:topic'
      - 'event_name to channel:foo'            (no payload)
      - 'ws:event_name(...) to channel:foo'
    Returns the part before '(' or ' to ', whichever comes first.
    """
    name = raw.strip()
    # Strip " to <destination>" tail first (if present without a preceding paren)
    to_idx = name.find(" to ")
    paren_idx = name.find("(")
    if to_idx != -1 and (paren_idx == -1 or to_idx < paren_idx):
        name = name[:to_idx]
    # Then strip the payload "(...)"
    if "(" in name:
        name = name.split("(")[0]
    return name.strip()


def _escape_label(text: str) -> str:
    """Escape a label for use inside a Mermaid "..." quoted string."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _classify_write(raw: str) -> tuple[str, bool]:
    """Return (entity_name, is_db). Strips parenthesized details."""
    name = raw.split("(")[0].strip()
    # "inventory(stock) via UPDATE" -> strip " via ..." too
    if " via " in name:
        name = name.split(" via ")[0].strip()
    is_db = not _is_non_db(name)
    return name, is_db


def _build_flow_body(flow: Flow, declared: set[str],
                     db_tables: set[str], db_edges: list[str]) -> list[str]:
    """Build Mermaid lines for a single flow's nodes and edges.

    `declared` is shared across flows so that common nodes (e.g. same DB table
    referenced by multiple flows) are only declared once.
    DB node declarations are deferred — only table names are collected into
    `db_tables`, and read/write edges into `db_edges`. The caller groups them
    by datasource as subgraphs.
    """
    lines: list[str] = []

    # -- entry point: stadium shape
    entry_id = f"entry_{_sanitize_id(flow.name)}"
    entry_label = _escape_label(f"{flow.entry_method} {flow.entry_path}")
    if entry_id not in declared:
        lines.append(f'    {entry_id}(["{entry_label}"])')
        declared.add(entry_id)

    if flow.steps:
        first_fn = _sanitize_id(flow.steps[0].fn)
        lines.append(f"    {entry_id} --> {first_fn}")

    remote_ids: list[str] = []

    for step in flow.steps:
        fn_id = _sanitize_id(step.fn)
        if fn_id not in declared:
            if step.remote:
                # Remote steps get a different shape (subroutine shape)
                label = _escape_label(f"{step.fn}\n[{step.remote}]")
                lines.append(f'    {fn_id}[["{label}"]]')
                remote_ids.append(fn_id)
            else:
                lines.append(f'    {fn_id}["{_escape_label(step.fn)}"]')
            declared.add(fn_id)

        for call in step.calls:
            call_id = _sanitize_id(call)
            if call_id not in declared:
                lines.append(f'    {call_id}["{_escape_label(call)}"]')
                declared.add(call_id)
            lines.append(f"    {fn_id} --> {call_id}")

        for read_raw in step.reads:
            name = read_raw.split("(")[0].strip()
            if _is_non_db(name) or name.startswith("request"):
                continue
            db_tables.add(name)
            read_id = f"db_{_sanitize_id(name)}"
            db_edges.append(f"    {read_id} -.->|read| {fn_id}")

        for write_raw in step.writes:
            name, is_db = _classify_write(write_raw)
            if not is_db:
                continue
            db_tables.add(name)
            write_id = f"db_{_sanitize_id(name)}"
            db_edges.append(f"    {fn_id} -->|write| {write_id}")

        for event in step.emits:
            event_name = _parse_event_name(event)
            event_id = f"evt_{_sanitize_id(event_name)}"
            if event_id not in declared:
                lines.append(f'    {event_id}{{{{"{_escape_label(event_name)}"}}}}')
                declared.add(event_id)
            lines.append(f"    {fn_id} -.->|emit| {event_id}")

        for event in step.consumes:
            event_name = _parse_event_name(event)
            event_id = f"evt_{_sanitize_id(event_name)}"
            if event_id not in declared:
                lines.append(f'    {event_id}{{{{"{_escape_label(event_name)}"}}}}')
                declared.add(event_id)
            lines.append(f"    {event_id} -.->|consume| {fn_id}")

    return lines, remote_ids


def _build_db_subgraphs(db_tables: set[str], entities: list[Entity]) -> list[str]:
    """Group DB table nodes by datasource into Mermaid subgraphs.

    Tables with the same datasource (or database, as fallback) are grouped
    into a single subgraph. Tables without entity definitions are ungrouped.
    """
    # Build table → datasource mapping from entity definitions
    table_to_ds: dict[str, str] = {}
    for e in entities:
        ds = e.datasource or e.database
        if ds:
            table_to_ds[e.table] = ds

    # Group tables by datasource
    ds_groups: dict[str, list[str]] = {}
    ungrouped: list[str] = []
    for table in sorted(db_tables):
        ds = table_to_ds.get(table)
        if ds:
            ds_groups.setdefault(ds, []).append(table)
        else:
            ungrouped.append(table)

    lines: list[str] = []

    for ds, tables in ds_groups.items():
        ds_id = f"ds_{_sanitize_id(ds)}"
        lines.append(f'    subgraph {ds_id}["{_escape_label(ds)}"]')
        for table in tables:
            db_id = f"db_{_sanitize_id(table)}"
            lines.append(f'        {db_id}[("{_escape_label(table)}")]')
        lines.append("    end")

    # Ungrouped tables (no entity definition with datasource)
    for table in ungrouped:
        db_id = f"db_{_sanitize_id(table)}"
        lines.append(f'    {db_id}[("{_escape_label(table)}")]')

    return lines


def flows_to_mermaid(flows: list[Flow], entities: list[Entity] | None = None) -> str:
    """Convert one or more Flows into a single Mermaid graph."""
    lines = ["graph TD"]
    declared: set[str] = set()
    use_subgraph = len(flows) > 1

    entry_ids: list[str] = []
    fn_ids: list[str] = []
    all_remote_ids: list[str] = []
    db_tables: set[str] = set()
    db_edges: list[str] = []

    for flow in flows:
        entry_ids.append(f"entry_{_sanitize_id(flow.name)}")
        for s in flow.steps:
            fn_ids.append(_sanitize_id(s.fn))

        if use_subgraph:
            lines.append(f'    subgraph {_sanitize_id(flow.name)}["{_escape_label(flow.name)}"]')

        body, remote_ids = _build_flow_body(flow, declared, db_tables, db_edges)
        all_remote_ids.extend(remote_ids)
        if use_subgraph:
            # indent one more level inside subgraph
            body = [f"    {line}" for line in body]
        lines.extend(body)

        if use_subgraph:
            lines.append("    end")

    # -- DB nodes grouped by datasource
    lines.extend(_build_db_subgraphs(db_tables, entities or []))
    lines.extend(db_edges)

    # -- collect node ids for styling
    db_node_ids = [f"db_{_sanitize_id(t)}" for t in db_tables]
    evt_nodes = [nid for nid in declared if nid.startswith("evt_")]

    lines.append("")
    lines.append("    classDef entryStyle fill:#4CAF50,stroke:#2E7D32,color:#fff,stroke-width:2px")
    lines.append("    classDef fnStyle fill:#42A5F5,stroke:#1565C0,color:#fff,stroke-width:1px")
    lines.append("    classDef dbStyle fill:#FF9800,stroke:#E65100,color:#fff,stroke-width:1px")
    lines.append("    classDef evtStyle fill:#AB47BC,stroke:#6A1B9A,color:#fff,stroke-width:1px")
    lines.append("    classDef remoteStyle fill:#EF5350,stroke:#B71C1C,color:#fff,stroke-width:2px,stroke-dasharray:5")
    lines.append("    classDef dsStyle fill:#FFF3E0,stroke:#E65100,color:#333,stroke-width:2px")

    if entry_ids:
        lines.append(f"    class {','.join(entry_ids)} entryStyle")
    if fn_ids:
        # Exclude remote ids from fnStyle
        local_fn_ids = [f for f in fn_ids if f not in all_remote_ids]
        if local_fn_ids:
            lines.append(f"    class {','.join(local_fn_ids)} fnStyle")
    if db_node_ids:
        lines.append(f"    class {','.join(db_node_ids)} dbStyle")
    if evt_nodes:
        lines.append(f"    class {','.join(evt_nodes)} evtStyle")
    if all_remote_ids:
        lines.append(f"    class {','.join(all_remote_ids)} remoteStyle")

    return "\n".join(lines)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bodhi Flow — {title}</title>
<style>
  body {{ background: #1e1e2e; margin: 0; display: flex; justify-content: center; padding: 2rem; }}
  .mermaid {{ background: #fff; border-radius: 8px; padding: 2rem; }}
  .mermaid svg {{ width: 100%; height: auto; min-width: 800px; }}
</style>
</head>
<body>
<pre class="mermaid">
{mermaid}
</pre>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{
  startOnLoad: true,
  theme: "default",
  maxTextSize: 100000,
  flowchart: {{ useMaxWidth: false }}
}});</script>
</body>
</html>
"""


def _render_html(mermaid_text: str, output_path: Path, title: str = "Bodhi Graph") -> None:
    """Render Mermaid text to a self-contained HTML file."""
    html = _HTML_TEMPLATE.format(mermaid=mermaid_text, title=title)
    output_path.write_text(html)


def _render_with_mmdc(mermaid_text: str, output_path: Path) -> bool:
    """Render Mermaid text to a file using mmdc. Returns True on success."""
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return False

    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as tmp:
        tmp.write(mermaid_text)
        tmp_path = tmp.name

    try:
        subprocess.run(
            [mmdc, "-i", tmp_path, "-o", str(output_path), "-b", "transparent"],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"mmdc failed: {e.stderr.decode()}", file=sys.stderr)
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def cmd_graph(project_root: Path, flow_name: str | None = None,
              output: str | None = None, **_):
    """Generate Mermaid diagram(s) from .bodhi/ flows."""
    bodhi_dir = project_root / ".bodhi"
    if not bodhi_dir.is_dir():
        print(f"No .bodhi/ directory found in {project_root}", file=sys.stderr)
        sys.exit(1)

    dsl = load_bodhi_dir(bodhi_dir)
    flows: list[Flow] = dsl["flows"]

    if not flows:
        print("No flows found in .bodhi/flows/", file=sys.stderr)
        sys.exit(1)

    entities: list[Entity] = dsl["entities"]

    if flow_name:
        matched = [f for f in flows if f.name == flow_name]
        if not matched:
            available = ", ".join(f.name for f in flows)
            print(f"Flow '{flow_name}' not found. Available: {available}", file=sys.stderr)
            sys.exit(1)
        flows = matched

    mermaid_text = flows_to_mermaid(flows, entities=entities)

    if not output:
        print(mermaid_text)
        return

    output_path = Path(output)
    if output_path.suffix == ".html":
        title = flow_name or "all flows"
        _render_html(mermaid_text, output_path, title=title)
        print(f"Rendered to {output_path}")
    elif _render_with_mmdc(mermaid_text, output_path):
        print(f"Rendered to {output_path}")
    else:
        # fallback: save .mmd file and tell user how to render
        mmd_path = output_path.with_suffix(".mmd")
        mmd_path.write_text(mermaid_text)
        print(f"Saved Mermaid source to {mmd_path}", file=sys.stderr)
        print("To render, install @mermaid-js/mermaid-cli:", file=sys.stderr)
        print(f"  npm install -g @mermaid-js/mermaid-cli", file=sys.stderr)
        print(f"  mmdc -i {mmd_path} -o {output_path}", file=sys.stderr)
