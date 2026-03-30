"""
Derive Layer 2 YAML files from Layer 1 inline tags.

This module implements deterministic derivation (no AI involved):
- flows: trace @bodhi.calls chains from entry points
- events: pair @bodhi.emits with @bodhi.consumes
- services: group @bodhi.calls ... via by target service
"""

import re
from pathlib import Path
from typing import Optional

import yaml

from .parser.inline import FunctionDSL, parse_directory
from .parser.yaml_parser import (
    Flow, FlowStep, Event, EventEndpoint, EventSchemaField,
    Service, ServiceApi, ServiceDependency,
)


def _parse_emits_value(val: str) -> tuple[str, list[str], Optional[str]]:
    """Parse '@bodhi.emits order_created(orderId, userId) to kafka:order-events'.

    Returns (event_name, payload_fields, destination).
    """
    dest = None
    if " to " in val:
        val, dest = val.rsplit(" to ", 1)
        dest = dest.strip()

    if "(" in val:
        name = val[:val.index("(")].strip()
        fields_str = val[val.index("(") + 1:val.rindex(")")]
        fields = [f.strip() for f in fields_str.split(",") if f.strip()]
    else:
        name = val.strip()
        fields = []

    return name, fields, dest


def _parse_consumes_value(val: str) -> tuple[str, list[str], Optional[str]]:
    """Parse '@bodhi.consumes order_created(orderId, userId) from kafka:order-events'.

    Returns (event_name, payload_fields, source).
    """
    source = None
    if " from " in val:
        val, source = val.rsplit(" from ", 1)
        source = source.strip()

    if "(" in val:
        name = val[:val.index("(")].strip()
        fields_str = val[val.index("(") + 1:val.rindex(")")]
        fields = [f.strip() for f in fields_str.split(",") if f.strip()]
    else:
        name = val.strip()
        fields = []

    return name, fields, source


def _parse_calls_value(val: str) -> tuple[str, Optional[str]]:
    """Parse '@bodhi.calls PaymentService.hold via http:POST /api/payments/hold'.

    Returns (qualified_name, via_protocol_or_None).
    """
    if " via " in val:
        name, via = val.split(" via ", 1)
        return name.strip(), via.strip()
    return val.strip(), None


def _extract_entity_from_rw(val: str) -> Optional[str]:
    """Extract entity name from a reads/writes value.

    'orders(id, userId) via INSERT' -> 'orders'
    'request.body(userId)' -> None
    'cache:session(token)' -> None
    'response(200)' -> None
    """
    v = val.strip()
    for prefix in ("request.", "response", "env:", "config:", "cache:"):
        if v.startswith(prefix):
            return None
    if "(" in v:
        return v[:v.index("(")].strip()
    return v.split()[0] if v else None


def _fn_to_flow_step(fn: FunctionDSL) -> FlowStep:
    """Convert a FunctionDSL to a FlowStep."""
    return FlowStep(
        fn=fn.qualified_name,
        intent=fn.intent or "",
        reads=fn.reads,
        writes=fn.writes,
        calls=fn.calls,
        emits=fn.emits,
        consumes=fn.consumes,
        on_fail=fn.on_fail,
    )


def _build_fn_index(functions: list[FunctionDSL]) -> dict[str, FunctionDSL]:
    """Build qualified_name -> FunctionDSL index."""
    index: dict[str, FunctionDSL] = {}
    for fn in functions:
        index[fn.qualified_name] = fn
    return index


def derive_flows(functions: list[FunctionDSL]) -> list[Flow]:
    """Derive flows by tracing @bodhi.calls chains from entry points.

    Entry points are functions that:
    - Have @bodhi.reads request.* (HTTP handlers)
    - Have @bodhi.consumes (event consumers)
    - Are not called by any other tagged function
    """
    fn_index = _build_fn_index(functions)

    # Find all functions that are called by other functions
    called_fns: set[str] = set()
    for fn in functions:
        for call_val in fn.calls:
            name, _ = _parse_calls_value(call_val)
            # Handle comma-separated calls that were already split by FunctionDSL.calls
            called_fns.add(name)

    # Entry points: functions with request reads or consumes, or not called by anyone
    entry_points: list[FunctionDSL] = []
    for fn in functions:
        if not fn.intent:
            continue
        is_http_entry = any(r.startswith("request.") for r in fn.reads)
        is_event_entry = bool(fn.consumes)
        is_uncalled = fn.qualified_name not in called_fns

        if is_http_entry or is_event_entry or (is_uncalled and (fn.writes or fn.calls)):
            entry_points.append(fn)

    flows: list[Flow] = []
    for entry in entry_points:
        steps: list[FlowStep] = []
        visited: set[str] = set()
        entities: set[str] = set()
        events: set[str] = set()

        # BFS through call chain
        queue = [entry]
        while queue:
            current = queue.pop(0)
            if current.qualified_name in visited:
                continue
            visited.add(current.qualified_name)
            steps.append(_fn_to_flow_step(current))

            # Collect entities from reads/writes
            for rw in current.reads + current.writes:
                entity = _extract_entity_from_rw(rw)
                if entity:
                    entities.add(entity)

            # Collect events
            for emit_val in current.emits:
                event_name, _, _ = _parse_emits_value(emit_val)
                events.add(event_name)
            for consume_val in current.consumes:
                event_name, _, _ = _parse_consumes_value(consume_val)
                events.add(event_name)

            # Follow calls
            for call_val in current.calls:
                name, _ = _parse_calls_value(call_val)
                if name in fn_index and name not in visited:
                    queue.append(fn_index[name])

        # Determine entry type
        entry_type = "http"
        entry_method = ""
        entry_path = ""
        if entry.consumes:
            entry_type = "mq_consumer"
        for r in entry.reads:
            if r.startswith("request.body"):
                entry_method = "POST"
                break
            elif r.startswith("request.query") or r.startswith("request.path"):
                entry_method = "GET"
                break

        # Build flow name from entry function
        flow_name = _to_snake_case(entry.function_name)

        # Collect error handling from all steps
        error_handling = []
        for step in steps:
            for fail in step.on_fail:
                error_handling.append({
                    "condition": fail.split("→")[0].strip() if "→" in fail else fail,
                    "step": step.fn,
                    "action": fail.split("→", 1)[1].strip() if "→" in fail else fail,
                })

        flows.append(Flow(
            name=flow_name,
            description=entry.intent or f"Flow starting from {entry.qualified_name}",
            entry_type=entry_type,
            entry_method=entry_method,
            entry_path=entry_path,
            steps=steps,
            error_handling=error_handling,
            entities=sorted(entities),
            events=sorted(events),
        ))

    return flows


def derive_events(functions: list[FunctionDSL]) -> list[Event]:
    """Derive events by pairing @bodhi.emits with @bodhi.consumes."""
    # Collect all events
    event_data: dict[str, dict] = {}

    for fn in functions:
        for emit_val in fn.emits:
            name, fields, dest = _parse_emits_value(emit_val)
            if name not in event_data:
                event_data[name] = {
                    "fields": set(),
                    "channel": None,
                    "producers": [],
                    "consumers": [],
                }
            event_data[name]["fields"].update(fields)
            if dest:
                event_data[name]["channel"] = dest
            event_data[name]["producers"].append(fn.qualified_name)

        for consume_val in fn.consumes:
            name, fields, source = _parse_consumes_value(consume_val)
            if name not in event_data:
                event_data[name] = {
                    "fields": set(),
                    "channel": None,
                    "producers": [],
                    "consumers": [],
                }
            event_data[name]["fields"].update(fields)
            if source and not event_data[name]["channel"]:
                event_data[name]["channel"] = source
            event_data[name]["consumers"].append(fn.qualified_name)

    events: list[Event] = []
    for name, data in sorted(event_data.items()):
        schema = [
            EventSchemaField(field=f, type="string", description="")
            for f in sorted(data["fields"])
        ]
        producers = [EventEndpoint(fn=p) for p in data["producers"]]
        consumers = [EventEndpoint(fn=c) for c in data["consumers"]]

        events.append(Event(
            name=name,
            description=f"Event: {name}",
            channel=data["channel"],
            schema=schema,
            producers=producers,
            consumers=consumers,
        ))

    return events


def derive_services(functions: list[FunctionDSL]) -> list[ServiceDependency]:
    """Derive service dependencies from @bodhi.calls ... via remote calls."""
    deps: dict[str, dict] = {}

    for fn in functions:
        for call_val in fn.get_tags("calls"):
            for single_call in call_val.split(","):
                single_call = single_call.strip()
                name, via = _parse_calls_value(single_call)
                if not via:
                    continue

                # Extract service name from ClassName.method
                service_name = name.split(".")[0] if "." in name else name

                if service_name not in deps:
                    deps[service_name] = {
                        "protocol": None,
                        "apis": set(),
                    }

                # Parse protocol
                if via.startswith("http:"):
                    deps[service_name]["protocol"] = "http"
                    # e.g. "http:POST /api/payments/hold"
                    api_part = via[len("http:"):].strip()
                    deps[service_name]["apis"].add(api_part)
                elif via.startswith("grpc"):
                    deps[service_name]["protocol"] = "grpc"
                    if ":" in via:
                        api_part = via.split(":", 1)[1].strip()
                        deps[service_name]["apis"].add(api_part)
                else:
                    deps[service_name]["protocol"] = via

    result: list[ServiceDependency] = []
    for service_name, data in sorted(deps.items()):
        result.append(ServiceDependency(
            service=service_name,
            protocol=data["protocol"],
            apis=sorted(data["apis"]),
        ))

    return result


def _to_snake_case(name: str) -> str:
    """Convert camelCase/PascalCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# --- YAML output ---

def _flow_to_dict(flow: Flow) -> dict:
    d: dict = {
        "name": flow.name,
        "description": flow.description,
        "entry": {
            "type": flow.entry_type,
        },
    }
    if flow.entry_method:
        d["entry"]["method"] = flow.entry_method
    if flow.entry_path:
        d["entry"]["path"] = flow.entry_path
    if flow.entry_auth:
        d["entry"]["auth"] = flow.entry_auth

    steps = []
    for s in flow.steps:
        step: dict = {"fn": s.fn, "intent": s.intent}
        if s.reads:
            step["reads"] = s.reads
        if s.writes:
            step["writes"] = s.writes
        if s.calls:
            step["calls"] = s.calls
        if s.emits:
            step["emits"] = s.emits
        if s.consumes:
            step["consumes"] = s.consumes
        if s.on_fail:
            step["on_fail"] = s.on_fail
        steps.append(step)
    d["steps"] = steps

    if flow.error_handling:
        d["error_handling"] = flow.error_handling
    if flow.entities:
        d["entities"] = flow.entities
    if flow.events:
        d["events"] = flow.events

    return d


def _event_to_dict(event: Event) -> dict:
    d: dict = {
        "name": event.name,
        "description": event.description,
    }
    if event.channel:
        d["channel"] = event.channel
    if event.schema:
        d["schema"] = [{"field": s.field, "type": s.type} for s in event.schema]
    if event.producers:
        d["producers"] = [{"fn": p.fn} for p in event.producers]
    if event.consumers:
        d["consumers"] = [{"fn": c.fn} for c in event.consumers]
    return d


def _service_dep_to_dict(dep: ServiceDependency) -> dict:
    d: dict = {"service": dep.service}
    if dep.protocol:
        d["protocol"] = dep.protocol
    if dep.apis:
        d["apis"] = dep.apis
    return d


def derive_and_write(project_root: Path, output_dir: Optional[Path] = None) -> dict:
    """Derive all Layer 2 files and write them to .bodhi/ directory.

    Returns a summary dict with counts.
    """
    functions = parse_directory(project_root)
    if output_dir is None:
        output_dir = project_root / ".bodhi"

    summary = {"flows": 0, "events": 0, "services": 0}

    # Derive flows
    flows = derive_flows(functions)
    if flows:
        flows_dir = output_dir / "flows"
        flows_dir.mkdir(parents=True, exist_ok=True)
        for flow in flows:
            path = flows_dir / f"{flow.name}.yaml"
            with open(path, "w") as f:
                yaml.dump(_flow_to_dict(flow), f, default_flow_style=False,
                          allow_unicode=True, sort_keys=False)
            summary["flows"] += 1

    # Derive events
    events = derive_events(functions)
    if events:
        events_dir = output_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        for event in events:
            path = events_dir / f"{event.name}.yaml"
            with open(path, "w") as f:
                yaml.dump(_event_to_dict(event), f, default_flow_style=False,
                          allow_unicode=True, sort_keys=False)
            summary["events"] += 1

    # Derive service dependencies
    service_deps = derive_services(functions)
    if service_deps:
        services_dir = output_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)
        # Write as a single dependencies file
        deps_data = {
            "name": project_root.name,
            "description": f"Service dependencies for {project_root.name}",
            "depends_on": [_service_dep_to_dict(d) for d in service_deps],
        }
        path = services_dir / f"{project_root.name}.yaml"
        with open(path, "w") as f:
            yaml.dump(deps_data, f, default_flow_style=False,
                      allow_unicode=True, sort_keys=False)
        summary["services"] = len(service_deps)

    return summary
