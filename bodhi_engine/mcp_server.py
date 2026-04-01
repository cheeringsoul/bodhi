"""
Bodhi MCP Server — expose DSL knowledge graph to AI coding assistants.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .knowledge import BodhiKnowledge

mcp = FastMCP("bodhi", instructions=(
    "Bodhi DSL knowledge graph. Query flows, entities, events, "
    "state machines, and service dependencies for this project."
))

_kb: BodhiKnowledge | None = None


def _get_kb() -> BodhiKnowledge:
    if _kb is None:
        raise RuntimeError("BodhiKnowledge not initialized. Call init_knowledge() first.")
    return _kb


def init_knowledge(project_root: Path, exclude_dirs: set[str] | None = None):
    global _kb
    _kb = BodhiKnowledge(project_root, exclude_dirs=exclude_dirs)


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


# -- tools --

@mcp.tool()
def query_flow(name: str) -> str:
    """Return the complete call chain for a flow.

    Shows entry point, each step's function/intent/reads/writes/calls/emits/on_fail,
    related entities and events. Use this to answer "How does X work?" questions.

    Args:
        name: Flow name (e.g. "create_order"). Use list_flows to see available names.
    """
    kb = _get_kb()
    result = kb.query_flow(name)
    if not result:
        available = kb.list_flows()
        return f"Flow '{name}' not found. Available flows: {', '.join(available)}"
    return _json(result)


@mcp.tool()
def trace_entity(entity: str) -> str:
    """Find all functions that read or write a given database entity/table.

    Returns the entity schema (if defined) and all read/write references
    from both flow definitions and inline tags.

    Args:
        entity: Entity/table name (e.g. "orders"). Use list_entities to see available names.
    """
    kb = _get_kb()
    return _json(kb.trace_entity(entity))


@mcp.tool()
def find_consumers(event: str) -> str:
    """Find all producers and consumers of a given domain event.

    Shows who emits the event, who consumes it, the channel, and schema.

    Args:
        event: Event name (e.g. "order_created"). Use list_events to see available names.
    """
    kb = _get_kb()
    return _json(kb.find_consumers(event))


@mcp.tool()
def impact_analysis(target: str) -> str:
    """Trace the blast radius of changing a function, entity, or component.

    Returns all affected flows, functions, events, and state machines.

    Args:
        target: Function name (e.g. "OrderService.create") or entity name (e.g. "orders").
    """
    kb = _get_kb()
    return _json(kb.impact_analysis(target))


@mcp.tool()
def query_state(state_machine: str, state: str | None = None) -> str:
    """Query a state machine's structure or a specific state's transitions.

    Without state param: returns overview of all states.
    With state param: returns that state's transitions, triggers, and conditions.

    Args:
        state_machine: State machine name (e.g. "order_lifecycle").
        state: Optional specific state ID (e.g. "PAID") to get its transitions.
    """
    kb = _get_kb()
    result = kb.query_state(state_machine, state)
    if not result:
        available = kb.list_state_machines()
        return f"Not found. Available state machines: {', '.join(available)}"
    return _json(result)


@mcp.tool()
def service_deps(service: str) -> str:
    """Return upstream and downstream dependencies for a service.

    Shows what this service depends on (with protocols, resilience config)
    and what other services depend on it.

    Args:
        service: Service name (e.g. "order-service"). Use list_services to see available names.
    """
    kb = _get_kb()
    result = kb.service_deps(service)
    if not result:
        available = kb.list_services()
        return f"Service '{service}' not found. Available: {', '.join(available)}"
    return _json(result)


@mcp.tool()
def list_flows() -> str:
    """List all available flow names in this project."""
    return _json(_get_kb().list_flows())


@mcp.tool()
def list_entities() -> str:
    """List all available entity/table names in this project."""
    return _json(_get_kb().list_entities())


@mcp.tool()
def list_events() -> str:
    """List all available event names in this project."""
    return _json(_get_kb().list_events())


@mcp.tool()
def list_services() -> str:
    """List all available service names in this project."""
    return _json(_get_kb().list_services())


@mcp.tool()
def list_state_machines() -> str:
    """List all available state machine names in this project."""
    return _json(_get_kb().list_state_machines())
