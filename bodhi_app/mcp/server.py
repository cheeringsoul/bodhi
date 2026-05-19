"""
Bodhi MCP Server — expose DSL knowledge graph to AI coding assistants.

Application layer: composes engine capabilities into MCP tools.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from bodhi_engine.knowledge import BodhiKnowledge
from bodhi_app.diagnose import diagnose_from_log

mcp = FastMCP("bodhi", instructions=(
    "Bodhi DSL knowledge graph. Query flows, entities, events, "
    "state machines, service dependencies, diagnose issues from logs, "
    "and read source code of annotated functions."
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


# -- query tools --

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
def query_channel(name: str) -> str:
    """Return the definition of a bidirectional communication channel (WebSocket, TCP, etc.).

    Shows inbound events (client->server), outbound events (server->client),
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


# -- list tools --

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
def list_channels() -> str:
    """List all available channel names (WebSocket, TCP, etc.) in this project."""
    return _json(_get_kb().list_channels())


@mcp.tool()
def list_topologies() -> str:
    """List all available cross-service event topology names in this project."""
    return _json(_get_kb().list_topologies())


# -- source code tool --

@mcp.tool()
def read_source(fn_name: str, context_lines: int = 30) -> str:
    """Read the source code of a function by its qualified name.

    Returns the file path, line number, and surrounding source code.
    Use this after query_flow or trace_entity to inspect the actual implementation.

    Args:
        fn_name: Qualified function name (e.g. "OrderService.create"). Use list_flows + query_flow to discover names.
        context_lines: Number of lines to read after the function definition (default 30).
    """
    kb = _get_kb()
    fn = kb._fn_by_name.get(fn_name)
    if not fn:
        available = [f for f in kb._fn_by_name.keys() if fn_name.lower() in f.lower()]
        if available:
            return f"Function '{fn_name}' not found. Similar: {', '.join(available[:10])}"
        return f"Function '{fn_name}' not found. Use query_flow or trace_entity to find function names."

    file_path = kb.project_root / fn.file_path
    if not file_path.is_file():
        return f"Source file not found: {fn.file_path}"

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(0, fn.line_number - 1)
    end = min(len(lines), start + context_lines)
    snippet = "\n".join(f"{i+1:4d} | {lines[i]}" for i in range(start, end))

    return _json({
        "fn": fn_name,
        "file": fn.file_path,
        "line": fn.line_number,
        "tags": {
            "intent": fn.intent,
            "reads": fn.reads,
            "writes": fn.writes,
            "calls": fn.calls,
            "emits": fn.emits,
        },
        "source": snippet,
    })


# -- diagnose tool --

@mcp.tool()
def diagnose_log(log_text: str) -> str:
    """Diagnose an issue from a log snippet pasted by the user.

    Matches the log text against the @bodhi.log.* pattern registry in the
    knowledge graph. For each match, returns:
    - Which function produced this log
    - Whether it indicates success or error
    - Extracted business variables (e.g. orderId=12345)
    - Which flow(s) this function belongs to
    - Full flow context with upstream/downstream steps
    - Impact analysis (affected events, entities, state machines)

    Use this when a user pastes error logs or asks "why did this happen?".

    Args:
        log_text: One or more lines of log output to diagnose.
    """
    kb = _get_kb()
    result = diagnose_from_log(kb, log_text)
    return _json(result)


