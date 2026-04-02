"""
Generate Mermaid diagrams from .bodhi/ flow definitions.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..parser import load_bodhi_dir
from ..parser.yaml_parser import Flow

# writes that are not real database tables
_NON_DB_WRITES = {"response", "request", "log", "cache", "session", "cookie", "header"}


def _sanitize_id(name: str) -> str:
    """Convert a name like 'OrderService.create' to a valid Mermaid node id."""
    return name.replace(".", "_").replace("/", "_").replace("-", "_").replace(" ", "_")


def _classify_write(raw: str) -> tuple[str, bool]:
    """Return (entity_name, is_db). Strips parenthesized details."""
    name = raw.split("(")[0].strip()
    # "inventory(stock) via UPDATE" -> strip " via ..." too
    if " via " in name:
        name = name.split(" via ")[0].strip()
    is_db = name.lower() not in _NON_DB_WRITES
    return name, is_db


def _build_flow_body(flow: Flow, declared: set[str]) -> list[str]:
    """Build Mermaid lines for a single flow's nodes and edges.

    `declared` is shared across flows so that common nodes (e.g. same DB table
    referenced by multiple flows) are only declared once.
    """
    lines: list[str] = []

    # -- entry point: stadium shape
    entry_id = f"entry_{_sanitize_id(flow.name)}"
    entry_label = f"{flow.entry_method} {flow.entry_path}"
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
                label = f"{step.fn}\\n[{step.remote}]"
                lines.append(f'    {fn_id}[["{label}"]]')
                remote_ids.append(fn_id)
            else:
                lines.append(f'    {fn_id}["{step.fn}"]')
            declared.add(fn_id)

        for call in step.calls:
            call_id = _sanitize_id(call)
            if call_id not in declared:
                lines.append(f'    {call_id}["{call}"]')
                declared.add(call_id)
            lines.append(f"    {fn_id} --> {call_id}")

        for read_raw in step.reads:
            name = read_raw.split("(")[0].strip()
            if name.lower() in _NON_DB_WRITES or name.startswith("request"):
                continue
            read_id = f"db_{_sanitize_id(name)}"
            if read_id not in declared:
                lines.append(f'    {read_id}[("{name}")]')
                declared.add(read_id)
            lines.append(f"    {read_id} -.->|read| {fn_id}")

        for write_raw in step.writes:
            name, is_db = _classify_write(write_raw)
            if not is_db:
                continue
            write_id = f"db_{_sanitize_id(name)}"
            if write_id not in declared:
                lines.append(f'    {write_id}[("{name}")]')
                declared.add(write_id)
            lines.append(f"    {fn_id} -->|write| {write_id}")

        for event in step.emits:
            event_name = event.split("(")[0].strip()
            event_id = f"evt_{_sanitize_id(event_name)}"
            if event_id not in declared:
                lines.append(f'    {event_id}{{{{{event_name}}}}}')
                declared.add(event_id)
            lines.append(f"    {fn_id} -.->|emit| {event_id}")

        for event in step.consumes:
            event_name = event.split("(")[0].strip()
            event_id = f"evt_{_sanitize_id(event_name)}"
            if event_id not in declared:
                lines.append(f'    {event_id}{{{{{event_name}}}}}')
                declared.add(event_id)
            lines.append(f"    {event_id} -.->|consume| {fn_id}")

    return lines, remote_ids


def flows_to_mermaid(flows: list[Flow]) -> str:
    """Convert one or more Flows into a single Mermaid graph."""
    lines = ["graph TD"]
    declared: set[str] = set()
    use_subgraph = len(flows) > 1

    entry_ids: list[str] = []
    fn_ids: list[str] = []
    all_remote_ids: list[str] = []

    for flow in flows:
        entry_ids.append(f"entry_{_sanitize_id(flow.name)}")
        for s in flow.steps:
            fn_ids.append(_sanitize_id(s.fn))

        if use_subgraph:
            lines.append(f'    subgraph {_sanitize_id(flow.name)}["{flow.name}"]')

        body, remote_ids = _build_flow_body(flow, declared)
        all_remote_ids.extend(remote_ids)
        if use_subgraph:
            # indent one more level inside subgraph
            body = [f"    {line}" for line in body]
        lines.extend(body)

        if use_subgraph:
            lines.append("    end")

    # -- styles
    db_nodes = [nid for nid in declared if nid.startswith("db_")]
    evt_nodes = [nid for nid in declared if nid.startswith("evt_")]

    lines.append("")
    lines.append("    classDef entryStyle fill:#4CAF50,stroke:#2E7D32,color:#fff,stroke-width:2px")
    lines.append("    classDef fnStyle fill:#42A5F5,stroke:#1565C0,color:#fff,stroke-width:1px")
    lines.append("    classDef dbStyle fill:#FF9800,stroke:#E65100,color:#fff,stroke-width:1px")
    lines.append("    classDef evtStyle fill:#AB47BC,stroke:#6A1B9A,color:#fff,stroke-width:1px")
    lines.append("    classDef remoteStyle fill:#EF5350,stroke:#B71C1C,color:#fff,stroke-width:2px,stroke-dasharray:5")

    if entry_ids:
        lines.append(f"    class {','.join(entry_ids)} entryStyle")
    if fn_ids:
        # Exclude remote ids from fnStyle
        local_fn_ids = [f for f in fn_ids if f not in all_remote_ids]
        if local_fn_ids:
            lines.append(f"    class {','.join(local_fn_ids)} fnStyle")
    if db_nodes:
        lines.append(f"    class {','.join(db_nodes)} dbStyle")
    if evt_nodes:
        lines.append(f"    class {','.join(evt_nodes)} evtStyle")
    if all_remote_ids:
        lines.append(f"    class {','.join(all_remote_ids)} remoteStyle")

    return "\n".join(lines)


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

    if flow_name:
        matched = [f for f in flows if f.name == flow_name]
        if not matched:
            available = ", ".join(f.name for f in flows)
            print(f"Flow '{flow_name}' not found. Available: {available}", file=sys.stderr)
            sys.exit(1)
        flows = matched

    mermaid_text = flows_to_mermaid(flows)

    if not output:
        print(mermaid_text)
        return

    output_path = Path(output)
    if _render_with_mmdc(mermaid_text, output_path):
        print(f"Rendered to {output_path}")
    else:
        # fallback: save .mmd file and tell user how to render
        mmd_path = output_path.with_suffix(".mmd")
        mmd_path.write_text(mermaid_text)
        print(f"Saved Mermaid source to {mmd_path}", file=sys.stderr)
        print("To render, install @mermaid-js/mermaid-cli:", file=sys.stderr)
        print(f"  npm install -g @mermaid-js/mermaid-cli", file=sys.stderr)
        print(f"  mmdc -i {mmd_path} -o {output_path}", file=sys.stderr)
