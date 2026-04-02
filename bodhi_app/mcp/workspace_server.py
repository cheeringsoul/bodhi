"""
Bodhi Workspace MCP Server — federated knowledge graph across multiple services.

Loads a workspace directory containing multiple service repos,
merges their .bodhi/ metadata, and exposes cross-service query tools.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from bodhi_engine.workspace import WorkspaceResult, load_workspace

workspace_mcp = FastMCP("bodhi-workspace", instructions=(
    "Bodhi federated knowledge graph — cross-service flows, events, "
    "dependencies, and impact analysis across all services in the workspace."
))

_ws: WorkspaceResult | None = None


def _get_ws() -> WorkspaceResult:
    if _ws is None:
        raise RuntimeError("Workspace not initialized. Call init_workspace() first.")
    return _ws


def init_workspace(workspace_path: Path) -> WorkspaceResult:
    global _ws
    _ws = load_workspace(workspace_path)
    return _ws


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


# -- list tools --

@workspace_mcp.tool()
def list_services() -> str:
    """List all services in the workspace."""
    ws = _get_ws()
    result = []
    for name, sd in ws.service_data.items():
        entry = {"name": name, "path": str(sd.path)}
        if sd.meta:
            entry["description"] = sd.meta.description
        result.append(entry)
    return _json(result)


@workspace_mcp.tool()
def list_all_flows() -> str:
    """List all flows across all services. Format: "service:flow_name"."""
    return _json(list(_get_ws().all_flows.keys()))


@workspace_mcp.tool()
def list_all_events() -> str:
    """List all events across all services with producer/consumer counts."""
    ws = _get_ws()
    result = []
    for name, event in ws.all_events.items():
        result.append({
            "name": name,
            "producers": len(event.producers),
            "consumers": len(event.consumers),
            "channel": event.channel,
        })
    return _json(result)


# -- query tools --

@workspace_mcp.tool()
def query_flow(service_flow: str) -> str:
    """Query a flow by "service:flow_name" key.

    Args:
        service_flow: Flow key in "service:flow_name" format. Use list_all_flows to see available.
    """
    ws = _get_ws()
    flow = ws.all_flows.get(service_flow)
    if not flow:
        return f"Flow '{service_flow}' not found. Available: {', '.join(ws.all_flows.keys())}"
    return _json({
        "name": flow.name,
        "description": flow.description,
        "trace_key": flow.trace_key,
        "entry": {
            "type": flow.entry_type,
            "method": flow.entry_method,
            "path": flow.entry_path,
            "auth": flow.entry_auth,
        },
        "steps": [
            {
                "fn": s.fn,
                "intent": s.intent,
                "reads": s.reads,
                "writes": s.writes,
                "calls": s.calls,
                "emits": s.emits,
                "on_fail": s.on_fail,
                **({"remote": s.remote} if s.remote else {}),
                **({"protocol": s.protocol} if s.protocol else {}),
                **({"api": s.api} if s.api else {}),
                **({"flow_ref": s.flow_ref} if s.flow_ref else {}),
            }
            for s in flow.steps
        ],
        "entities": flow.entities,
        "events": flow.events,
    })


@workspace_mcp.tool()
def trace_event_chain(event: str) -> str:
    """Trace an event across all services: who produces it, who consumes it,
    and what downstream events each consumer triggers.

    This is the key cross-service tool — follows the full event chain
    across the entire system.

    Args:
        event: Event name (e.g. "order_created").
    """
    ws = _get_ws()
    evt = ws.all_events.get(event)
    if not evt:
        return f"Event '{event}' not found. Available: {', '.join(ws.all_events.keys())}"

    result = {
        "event": event,
        "description": evt.description,
        "channel": evt.channel,
        "producers": [{"fn": p.fn, "flow": p.flow} for p in evt.producers],
        "consumers": [{"fn": c.fn, "flow": c.flow} for c in evt.consumers],
    }

    # Check if any topology defines a chain starting with this event
    chains = []
    for topo_name, topo in ws.all_topologies.items():
        for chain in topo.chains:
            if chain.event == event:
                chains.append({
                    "topology": topo_name,
                    "channel": chain.channel,
                    "producer": chain.producer,
                    "consumers": [
                        {
                            "service": con.service,
                            "action": con.action,
                            "emits": con.emits,
                        }
                        for con in chain.consumers
                    ],
                })
    if chains:
        result["topology_chains"] = chains

    return _json(result)


@workspace_mcp.tool()
def cross_service_impact(target: str) -> str:
    """Trace the blast radius of a change across ALL services in the workspace.

    Given a function name, entity name, or event name, find all affected
    flows, events, and state machines across every service.

    Args:
        target: Function name (e.g. "OrderService.create"), entity (e.g. "orders"),
                or event (e.g. "order_created").
    """
    ws = _get_ws()
    affected_flows = []
    affected_events = []
    affected_state_machines = []

    # Check flows across all services
    for flow_key, flow in ws.all_flows.items():
        for step in flow.steps:
            if target in step.fn or target in step.calls:
                affected_flows.append(flow_key)
                break
            for rw in step.reads + step.writes:
                if target in rw:
                    affected_flows.append(flow_key)
                    break
            for e in step.emits:
                if target in e:
                    affected_flows.append(flow_key)
                    break

    # Check events
    for event_name, event in ws.all_events.items():
        if target == event_name:
            affected_events.append(event_name)
            continue
        for p in event.producers:
            if target in p.fn:
                affected_events.append(event_name)
                break
        for c in event.consumers:
            if target in c.fn:
                if event_name not in affected_events:
                    affected_events.append(event_name)
                break

    # Check state machines
    for sm_key, sm in ws.all_states.items():
        if target == sm.entity or target == sm.name:
            affected_state_machines.append(sm_key)
        for state in sm.states:
            for t in state.transitions:
                if t.fn and target in t.fn:
                    if sm_key not in affected_state_machines:
                        affected_state_machines.append(sm_key)

    return _json({
        "target": target,
        "affected_flows": affected_flows,
        "affected_events": affected_events,
        "affected_state_machines": affected_state_machines,
    })


@workspace_mcp.tool()
def event_schema_diff(event: str) -> str:
    """Compare an event's schema across all services that reference it.

    Detects field mismatches between producers and consumers.

    Args:
        event: Event name (e.g. "order_created").
    """
    ws = _get_ws()
    evt = ws.all_events.get(event)
    if not evt:
        return f"Event '{event}' not found."

    # Collect schemas from each service that defines this event
    schemas_by_service: dict[str, list[dict]] = {}
    for svc_name, sd in ws.service_data.items():
        for svc_event in sd.events:
            if svc_event.name == event and svc_event.schema:
                schemas_by_service[svc_name] = [
                    {"field": f.field, "type": f.type, "description": f.description}
                    for f in svc_event.schema
                ]

    if len(schemas_by_service) <= 1:
        return _json({
            "event": event,
            "schemas": schemas_by_service,
            "consistent": True,
            "message": "Only one service defines this event's schema.",
        })

    # Compare: find fields present in some but not all
    all_field_names: dict[str, set[str]] = {}
    for svc_name, fields in schemas_by_service.items():
        all_field_names[svc_name] = {f["field"] for f in fields}

    all_fields = set()
    for fields in all_field_names.values():
        all_fields |= fields

    mismatches = []
    for field_name in sorted(all_fields):
        present_in = [svc for svc, fields in all_field_names.items() if field_name in fields]
        missing_from = [svc for svc in all_field_names if svc not in present_in]
        if missing_from:
            mismatches.append({
                "field": field_name,
                "present_in": present_in,
                "missing_from": missing_from,
            })

    return _json({
        "event": event,
        "schemas": schemas_by_service,
        "consistent": len(mismatches) == 0,
        "mismatches": mismatches,
    })


@workspace_mcp.tool()
def service_deps(service: str) -> str:
    """Show full dependency graph for a service: what it depends on and who depends on it.

    Args:
        service: Service name (e.g. "order-service").
    """
    ws = _get_ws()
    svc = ws.all_services.get(service)
    if not svc:
        return f"Service '{service}' not found. Available: {', '.join(ws.all_services.keys())}"

    depended_by = []
    for other_name, other_svc in ws.all_services.items():
        if other_name == service:
            continue
        for dep in other_svc.depends_on:
            if dep.service == service:
                depended_by.append({
                    "service": other_name,
                    "protocol": dep.protocol,
                    "apis": dep.apis,
                })

    return _json({
        "name": svc.name,
        "description": svc.description,
        "depends_on": [
            {
                "service": d.service,
                "protocol": d.protocol or d.type,
                "apis": d.apis,
                "topics": d.topics,
            }
            for d in svc.depends_on
        ],
        "depended_by": depended_by,
    })


@workspace_mcp.tool()
def workspace_issues() -> str:
    """Show all cross-service validation issues found during workspace loading."""
    ws = _get_ws()
    return _json([
        {
            "severity": i.severity.value,
            "code": i.code,
            "message": i.message,
            "service": i.service,
            "related_service": i.related_service,
        }
        for i in ws.issues
    ])
