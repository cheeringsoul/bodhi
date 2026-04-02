"""
Bodhi MCP Server — expose DSL knowledge graph to AI coding assistants.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .knowledge import BodhiKnowledge
from .runtime.debug_engine import DebugEngine
from .runtime.log_adapter import FileLogAdapter, LogAdapter

mcp = FastMCP("bodhi", instructions=(
    "Bodhi DSL knowledge graph. Query flows, entities, events, "
    "state machines, and service dependencies for this project."
))

_kb: BodhiKnowledge | None = None
_debug_engine: DebugEngine | None = None


def _get_kb() -> BodhiKnowledge:
    if _kb is None:
        raise RuntimeError("BodhiKnowledge not initialized. Call init_knowledge() first.")
    return _kb


def _get_debug_engine() -> DebugEngine | None:
    return _debug_engine


def init_knowledge(project_root: Path, exclude_dirs: set[str] | None = None):
    global _kb, _debug_engine
    _kb = BodhiKnowledge(project_root, exclude_dirs=exclude_dirs)

    # Initialize debug engine if runtime log config exists
    meta = _kb.dsl.get("meta")
    if meta and meta.runtime and meta.runtime.logs:
        adapters: list[LogAdapter] = []
        for log_src in meta.runtime.logs:
            if log_src.type == "file" and log_src.path:
                adapters.append(FileLogAdapter(
                    paths=[log_src.path],
                    format=log_src.format or "text",
                    timestamp_field=log_src.timestamp_field or "@timestamp",
                    message_field=log_src.message_field or "message",
                ))
        if adapters:
            # Use the first adapter for now; future: composite adapter
            _debug_engine = DebugEngine(
                adapter=adapters[0],
                flows=_kb._flow_by_name,
                functions=_kb._fn_by_name,
            )


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


@mcp.tool()
def query_channel(name: str) -> str:
    """Return the definition of a bidirectional communication channel (WebSocket, TCP, etc.).

    Shows inbound events (client→server), outbound events (server→client),
    schemas, and linked flows/events.

    Args:
        name: Channel name (e.g. "order_status_ws"). Use list_channels to see available names.
    """
    kb = _get_kb()
    result = kb.query_channel(name)
    if not result:
        available = kb.list_channels()
        return f"Channel '{name}' not found. Available: {', '.join(available)}"
    return _json(result)


@mcp.tool()
def query_topology(name: str) -> str:
    """Return a cross-service event topology — how events flow across the entire system.

    Shows each event in the chain, its producer service, consumer services,
    and what downstream events each consumer triggers.

    Args:
        name: Topology name (e.g. "order_fulfillment"). Use list_topologies to see available names.
    """
    kb = _get_kb()
    result = kb.query_topology(name)
    if not result:
        available = kb.list_topologies()
        return f"Topology '{name}' not found. Available: {', '.join(available)}"
    return _json(result)


@mcp.tool()
def list_channels() -> str:
    """List all available channel names (WebSocket, TCP, etc.) in this project."""
    return _json(_get_kb().list_channels())


@mcp.tool()
def list_topologies() -> str:
    """List all available cross-service event topology names in this project."""
    return _json(_get_kb().list_topologies())


@mcp.tool()
def debug_flow(
    flow: str,
    trace_value: str,
    trace_key: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
) -> str:
    """Trace a specific flow execution by correlation ID using log analysis.

    Walks each step in the flow, searches logs for evidence of success/failure,
    and builds a causal debug report showing where the flow broke and why.

    Requires runtime.logs configuration in bodhi.yaml.

    Args:
        flow: Flow name (e.g. "create_order").
        trace_value: Correlation ID value (e.g. "12345" for an order ID).
        trace_key: Correlation field name. Defaults to the flow's trace_key.
        time_from: Search window start (ISO 8601). Defaults to 1 hour ago.
        time_to: Search window end (ISO 8601). Defaults to now.
    """
    engine = _get_debug_engine()
    if not engine:
        return _json({"error": "Debug engine not available. Configure runtime.logs in bodhi.yaml."})

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    report = engine.debug_flow(
        flow_name=flow,
        trace_value=trace_value,
        trace_key=trace_key,
        time_from=tf,
        time_to=tt,
    )
    return _json(report.to_dict())


@mcp.tool()
def search_logs(
    fn: str | None = None,
    flow: str | None = None,
    level: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    correlation_key: str | None = None,
    correlation_value: str | None = None,
    limit: int = 50,
) -> str:
    """Search logs with knowledge-graph context.

    Unlike raw log search, results are annotated with which function produced
    the log and which flow step it belongs to.

    Requires runtime.logs configuration in bodhi.yaml.

    Args:
        fn: Search logs for a specific function (e.g. "PaymentService.hold").
        flow: Search logs for all steps in a flow (e.g. "create_order").
        level: Filter by log level (e.g. "ERROR").
        time_from: Search window start (ISO 8601). Defaults to 1 hour ago.
        time_to: Search window end (ISO 8601). Defaults to now.
        correlation_key: Correlation field name (e.g. "orderId").
        correlation_value: Correlation field value (e.g. "12345").
        limit: Maximum results (default 50).
    """
    engine = _get_debug_engine()
    if not engine:
        return _json({"error": "Debug engine not available. Configure runtime.logs in bodhi.yaml."})

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    correlation = None
    if correlation_key and correlation_value:
        correlation = {correlation_key: correlation_value}

    results = engine.search_logs(
        fn=fn,
        flow=flow,
        level=level,
        time_from=tf,
        time_to=tt,
        correlation=correlation,
        limit=limit,
    )
    return _json(results)
