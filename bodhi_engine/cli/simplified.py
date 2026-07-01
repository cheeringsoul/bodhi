"""
Generate a *simplified* Mermaid diagram from .bodhi/ flow definitions.

Unlike :mod:`bodhi_engine.cli.graph`, which renders the full internal call
chain of every flow (entry → every function → every call/read/write/emit),
this module collapses each flow down to a data-centric summary:

    entry point  →  tables it reads/writes, events it emits, externals it calls

The internal function hops are dropped entirely. Shared targets (e.g. a
``users`` table touched by many endpoints) are merged into a single node, so
the result is dense and shows "which endpoints touch which data" at a glance —
without the stacked per-flow subgraphs that make the full graph mostly
whitespace.
"""

from __future__ import annotations

from bodhi_engine.cli.graph import (
    _sanitize_id, _escape_label, _is_non_db, _normalize_rw, _parse_event_name,
)
from bodhi_engine.parser.yaml_parser import Flow, Entity


def _clean_target(raw, strip_via: bool = False) -> str:
    """Reduce a reads/writes entry to a bare table/resource name."""
    name = _normalize_rw(raw).split("(")[0].strip()
    if strip_via and " via " in name:
        name = name.split(" via ")[0].strip()
    return name.strip()


def _flow_entry_label(flow: Flow) -> str:
    if flow.entry_method and flow.entry_path:
        return f"{flow.entry_method} {flow.entry_path}".strip()
    return flow.entry_path or flow.entry_method or flow.name


def flows_to_simple_mermaid(flows: list[Flow], entities: list[Entity] | None = None) -> str:
    """Render flows as a simplified entry → data/event/external diagram.

    Each flow becomes one entry node connected directly to the distinct
    resources it touches. Nodes are de-duplicated across flows so common
    tables/services appear once.
    """
    lines = ["graph LR"]
    declared: set[str] = set()
    edges: list[str] = []

    entry_ids: list[str] = []
    db_ids: set[str] = set()
    evt_ids: set[str] = set()
    ext_ids: set[str] = set()

    def declare(node_id: str, label: str, shape: str) -> None:
        if node_id in declared:
            return
        declared.add(node_id)
        opener, closer = {
            "entry": ('(["', '"])'),
            "db": ('[("', '")]'),
            "evt": ('{{"', '"}}'),
            "ext": ('[["', '"]]'),
        }[shape]
        lines.append(f'    {node_id}{opener}{_escape_label(label)}{closer}')

    for flow in flows:
        if not flow.entry_type:
            continue
        entry_id = f"e_{_sanitize_id(flow.name)}"
        declare(entry_id, _flow_entry_label(flow), "entry")
        entry_ids.append(entry_id)

        reads: set[str] = set()
        writes: set[str] = set()
        emits: set[str] = set()
        externals: set[str] = set()

        for step in flow.steps:
            for r in step.reads:
                name = _clean_target(r)
                if name and not _is_non_db(name) and not name.startswith("request"):
                    reads.add(name)
            for w in step.writes:
                name = _clean_target(w, strip_via=True)
                if name and not _is_non_db(name):
                    writes.add(name)
            for e in step.emits:
                name = _parse_event_name(e)
                if name:
                    emits.add(name)
            if step.remote:
                externals.add(step.remote)

        for table in sorted(reads):
            nid = f"db_{_sanitize_id(table)}"
            declare(nid, table, "db"); db_ids.add(nid)
            edges.append(f"    {nid} -.->|read| {entry_id}")
        for table in sorted(writes):
            nid = f"db_{_sanitize_id(table)}"
            declare(nid, table, "db"); db_ids.add(nid)
            edges.append(f"    {entry_id} -->|write| {nid}")
        for event in sorted(emits):
            nid = f"ev_{_sanitize_id(event)}"
            declare(nid, event, "evt"); evt_ids.add(nid)
            edges.append(f"    {entry_id} -.->|emit| {nid}")
        for ext in sorted(externals):
            nid = f"x_{_sanitize_id(ext)}"
            declare(nid, ext, "ext"); ext_ids.add(nid)
            edges.append(f"    {entry_id} ==>|calls| {nid}")

    lines.extend(edges)

    lines.append("")
    lines.append("    classDef entryStyle fill:#4CAF50,stroke:#2E7D32,color:#fff,stroke-width:2px")
    lines.append("    classDef dbStyle fill:#FF9800,stroke:#E65100,color:#fff,stroke-width:1px")
    lines.append("    classDef evtStyle fill:#AB47BC,stroke:#6A1B9A,color:#fff,stroke-width:1px")
    lines.append("    classDef extStyle fill:#EF5350,stroke:#B71C1C,color:#fff,stroke-width:2px")

    if entry_ids:
        lines.append(f"    class {','.join(entry_ids)} entryStyle")
    if db_ids:
        lines.append(f"    class {','.join(sorted(db_ids))} dbStyle")
    if evt_ids:
        lines.append(f"    class {','.join(sorted(evt_ids))} evtStyle")
    if ext_ids:
        lines.append(f"    class {','.join(sorted(ext_ids))} extStyle")

    return "\n".join(lines)
