"""
Derive and validate Layer 2 YAML files against Layer 1 inline tags.

This module has two roles:

1. **Derivation** (cold-start / scaffold): deterministically derive flows,
   events, and service dependencies from inline @bodhi.* tags.

2. **Validation** (primary use): compare what inline tags imply against
   the hand-written .bodhi/ YAML files and report inconsistencies.

Derivation functions (no AI involved):
- flows: trace @bodhi.calls chains from entry points
- events: pair @bodhi.emits with @bodhi.consumes
- services: group @bodhi.calls ... via by target service
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .parser.inline import FunctionDSL, parse_directory
from .parser.yaml_parser import (
    Flow, FlowStep, Event, EventEndpoint, EventSchemaField,
    Service, ServiceApi, ServiceDependency,
    load_bodhi_dir,
)


# ============================================================
# Consistency issue model
# ============================================================

@dataclass
class ConsistencyIssue:
    """A single inconsistency between inline tags and YAML files."""
    severity: str          # "error" | "warning"
    category: str          # "flow" | "event" | "service" | "entity"
    message: str
    source: str = ""       # e.g. "OrderService.create" or "flows/create_order.yaml"

    def __str__(self) -> str:
        prefix = f"[{self.severity.upper()}]"
        src = f" ({self.source})" if self.source else ""
        return f"{prefix} [{self.category}]{src} {self.message}"


@dataclass
class ConsistencyReport:
    """Result of validate_consistency()."""
    issues: list[ConsistencyIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_consistent(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        if not self.issues:
            return "All consistent. No issues found."
        lines = [f"{len(self.errors)} error(s), {len(self.warnings)} warning(s):"]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)


# ============================================================
# Parse helpers
# ============================================================

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

    Returns the entity (table) name, or None for non-entity references.

    Rules:
    - DSL keywords (request.*, response*, env:*, config:*, cache:*) → None
    - Contains ':' → prefixed external store (redis:key, kafka:topic) → None
    - Contains '.' → external data source (eth.log, ws.message) → None
    - Contains '{' or '/' → template or URL path → None
    """
    v = val.strip()
    for prefix in ("request.", "response", "env:", "config:", "cache:"):
        if v.startswith(prefix):
            return None
    if "(" in v:
        name = v[:v.index("(")].strip()
    else:
        name = v.split()[0] if v else None
    if not name:
        return None
    if ":" in name or "." in name or "{" in name or "/" in name:
        return None
    return name


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


def _fn_matches(yaml_fn: str, code_fn: str) -> bool:
    """Check if a YAML fn name matches a code fn name, allowing suffix match.

    e.g. 'cex.BinanceWS.handleTicker' matches 'BinanceWS.handleTicker'
    """
    if yaml_fn == code_fn:
        return True
    if yaml_fn.endswith("." + code_fn) or code_fn.endswith("." + yaml_fn):
        return True
    return False


def _fn_in_index(fn_name: str, fn_index: dict[str, FunctionDSL]) -> bool:
    """Check if fn_name matches any key in fn_index (exact or suffix)."""
    if fn_name in fn_index:
        return True
    for code_fn in fn_index:
        if _fn_matches(fn_name, code_fn):
            return True
    return False


def _fn_set_matches(fn_name: str, fn_set: set[str]) -> bool:
    """Check if fn_name matches any element in fn_set (exact or suffix)."""
    if fn_name in fn_set:
        return True
    for s in fn_set:
        if _fn_matches(fn_name, s):
            return True
    return False


def _to_snake_case(name: str) -> str:
    """Convert camelCase/PascalCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# ============================================================
# Derivation functions
# ============================================================

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
            called_fns.add(name)

    # Entry points: functions with request reads or consumes, or not called by anyone
    entry_points: list[FunctionDSL] = []
    for fn in functions:
        if not fn.intent:
            continue
        is_http_entry = any(r.startswith("request.") for r in fn.reads)
        is_event_entry = bool(fn.consumes)
        is_uncalled = not _fn_set_matches(fn.qualified_name, called_fns)

        if is_http_entry or is_event_entry:
            entry_points.append(fn)
        elif is_uncalled and fn.calls:
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

                service_name = name.split(".")[0] if "." in name else name

                if service_name not in deps:
                    deps[service_name] = {
                        "protocol": None,
                        "apis": set(),
                    }

                if via.startswith("http:"):
                    deps[service_name]["protocol"] = "http"
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


# ============================================================
# Validation: compare derived data against hand-written YAML
# ============================================================

def validate_consistency(project_root: Path, bodhi_dir: Optional[Path] = None,
                         exclude_dirs: set[str] | None = None) -> ConsistencyReport:
    """Compare inline tags against .bodhi/ YAML files and report inconsistencies.

    This is the primary use of the deriver in a DSL-first workflow:
    the YAML files are written first (by human or AI), then code is
    implemented with inline tags. This function checks that the two
    sides agree.

    Returns a ConsistencyReport with all issues found.
    """
    if bodhi_dir is None:
        bodhi_dir = project_root / ".bodhi"

    report = ConsistencyReport()

    # Parse inline tags from source code
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)
    if not functions:
        report.issues.append(ConsistencyIssue(
            severity="warning",
            category="general",
            message="No inline @bodhi.* tags found in source code.",
        ))
        return report

    # Load hand-written YAML
    if not bodhi_dir.is_dir():
        report.issues.append(ConsistencyIssue(
            severity="warning",
            category="general",
            message=f".bodhi/ directory not found at {bodhi_dir}",
        ))
        return report

    parse_errors: list[str] = []
    yaml_data = load_bodhi_dir(bodhi_dir, errors=parse_errors)

    for err_msg in parse_errors:
        report.issues.append(ConsistencyIssue(
            severity="error",
            category="yaml-parse",
            message=err_msg,
        ))

    # --- Flow validation ---
    _validate_flows(functions, yaml_data.get("flows", []), report)

    # --- Event validation ---
    _validate_events(functions, yaml_data.get("events", []), report)

    # --- Service dependency validation ---
    _validate_services(functions, yaml_data.get("services", []), report)

    # --- Entity validation ---
    _validate_entities(functions, yaml_data.get("entities", []), report)

    return report


def _validate_flows(
    functions: list[FunctionDSL],
    yaml_flows: list[Flow],
    report: ConsistencyReport,
) -> None:
    """Check that inline tags and flow YAML files are consistent."""
    derived_flows = derive_flows(functions)

    yaml_flow_names = {f.name for f in yaml_flows}
    derived_flow_names = {f.name for f in derived_flows}

    # Build indexes
    yaml_flow_index = {f.name: f for f in yaml_flows}
    derived_flow_index = {f.name: f for f in derived_flows}

    # Functions referenced in YAML flows
    yaml_flow_fns: dict[str, set[str]] = {}
    for f in yaml_flows:
        yaml_flow_fns[f.name] = {s.fn for s in f.steps}

    derived_flow_fns: dict[str, set[str]] = {}
    for f in derived_flows:
        derived_flow_fns[f.name] = {s.fn for s in f.steps}

    # Check: functions in YAML flow steps that have no inline tags
    fn_index = _build_fn_index(functions)
    for flow in yaml_flows:
        for step in flow.steps:
            if not _fn_in_index(step.fn, fn_index):
                report.issues.append(ConsistencyIssue(
                    severity="error",
                    category="flow",
                    message=f"Step '{step.fn}' in flow YAML has no matching inline tags in source code.",
                    source=f"flows/{flow.name}.yaml",
                ))

    # Check: entities referenced in YAML flow but not found in inline tags
    for flow in yaml_flows:
        derived = derived_flow_index.get(flow.name)
        if not derived:
            # Try matching by entry function
            for df in derived_flows:
                if df.steps and flow.steps and _fn_matches(df.steps[0].fn, flow.steps[0].fn):
                    derived = df
                    break

        if derived:
            # Entities in YAML but not derived from tags
            yaml_entities = set(flow.entities)
            derived_entities = set(derived.entities)
            for entity in yaml_entities - derived_entities:
                report.issues.append(ConsistencyIssue(
                    severity="warning",
                    category="flow",
                    message=f"Entity '{entity}' listed in flow YAML but not found in inline tags.",
                    source=f"flows/{flow.name}.yaml",
                ))

            # Events in YAML but not derived from tags
            yaml_events = set(flow.events)
            derived_events = set(derived.events)
            for event in yaml_events - derived_events:
                report.issues.append(ConsistencyIssue(
                    severity="warning",
                    category="flow",
                    message=f"Event '{event}' listed in flow YAML but not found in inline tags.",
                    source=f"flows/{flow.name}.yaml",
                ))

    # Check: derived flows that have no corresponding YAML file
    # Match by entry function since names may differ
    yaml_entry_fns = set()
    for f in yaml_flows:
        if f.steps:
            yaml_entry_fns.add(f.steps[0].fn)

    # Collect all fns that appear as steps in any YAML flow
    yaml_all_step_fns = set()
    for f in yaml_flows:
        for s in f.steps:
            yaml_all_step_fns.add(s.fn)

    for df in derived_flows:
        if df.steps:
            entry_fn = df.steps[0].fn
            if not _fn_set_matches(entry_fn, yaml_entry_fns) and \
               not _fn_set_matches(entry_fn, yaml_all_step_fns):
                report.issues.append(ConsistencyIssue(
                    severity="warning",
                    category="flow",
                    message=f"Entry point '{entry_fn}' found in code but has no corresponding flow YAML.",
                    source=entry_fn,
                ))


def _validate_events(
    functions: list[FunctionDSL],
    yaml_events: list[Event],
    report: ConsistencyReport,
) -> None:
    """Check that inline event tags and event YAML files are consistent."""
    derived_events = derive_events(functions)

    yaml_event_names = {e.name for e in yaml_events}
    derived_event_names = {e.name for e in derived_events}
    yaml_event_index = {e.name: e for e in yaml_events}
    derived_event_index = {e.name: e for e in derived_events}

    # Events in code but not in YAML
    for name in derived_event_names - yaml_event_names:
        report.issues.append(ConsistencyIssue(
            severity="error",
            category="event",
            message=f"Event '{name}' found in inline tags but has no YAML definition.",
            source=name,
        ))

    # Events in YAML but not in code
    for name in yaml_event_names - derived_event_names:
        report.issues.append(ConsistencyIssue(
            severity="warning",
            category="event",
            message=f"Event '{name}' defined in YAML but not found in any inline tags.",
            source=f"events/{name}.yaml",
        ))

    # For events in both, check producer/consumer consistency
    for name in yaml_event_names & derived_event_names:
        ye = yaml_event_index[name]
        de = derived_event_index[name]

        # Check producers
        yaml_producer_fns = {p.fn for p in ye.producers}
        derived_producer_fns = {p.fn for p in de.producers}
        for fn in derived_producer_fns:
            if not _fn_set_matches(fn, yaml_producer_fns):
                report.issues.append(ConsistencyIssue(
                    severity="error",
                    category="event",
                    message=f"'{fn}' emits '{name}' in code but is not listed as a producer in YAML.",
                    source=f"events/{name}.yaml",
                ))
        for fn in yaml_producer_fns:
            if not _fn_set_matches(fn, derived_producer_fns):
                report.issues.append(ConsistencyIssue(
                    severity="warning",
                    category="event",
                    message=f"'{fn}' listed as producer of '{name}' in YAML but no @bodhi.emits found in code.",
                    source=f"events/{name}.yaml",
                ))

        # Check consumers
        yaml_consumer_fns = {c.fn for c in ye.consumers}
        derived_consumer_fns = {c.fn for c in de.consumers}
        for fn in derived_consumer_fns:
            if not _fn_set_matches(fn, yaml_consumer_fns):
                report.issues.append(ConsistencyIssue(
                    severity="error",
                    category="event",
                    message=f"'{fn}' consumes '{name}' in code but is not listed as a consumer in YAML.",
                source=f"events/{name}.yaml",
            ))
        for fn in yaml_consumer_fns:
            if not _fn_set_matches(fn, derived_consumer_fns):
                report.issues.append(ConsistencyIssue(
                    severity="warning",
                    category="event",
                    message=f"'{fn}' listed as consumer of '{name}' in YAML but no @bodhi.consumes found in code.",
                    source=f"events/{name}.yaml",
                ))

        # Check channel consistency
        if ye.channel and de.channel and ye.channel != de.channel:
            report.issues.append(ConsistencyIssue(
                severity="error",
                category="event",
                message=f"Event '{name}' channel mismatch: YAML='{ye.channel}', code='{de.channel}'.",
                source=f"events/{name}.yaml",
            ))

        # Check schema fields
        yaml_fields = {s.field for s in ye.schema}
        derived_fields = {s.field for s in de.schema}
        for f in derived_fields - yaml_fields:
            report.issues.append(ConsistencyIssue(
                severity="warning",
                category="event",
                message=f"Field '{f}' found in inline tags for event '{name}' but missing from YAML schema.",
                source=f"events/{name}.yaml",
            ))


def _validate_services(
    functions: list[FunctionDSL],
    yaml_services: list[Service],
    report: ConsistencyReport,
) -> None:
    """Check that inline @bodhi.calls via tags match service YAML depends_on."""
    derived_deps = derive_services(functions)

    # Collect all service dependencies from YAML
    yaml_dep_services: set[str] = set()
    for svc in yaml_services:
        for dep in svc.depends_on:
            yaml_dep_services.add(dep.service)

    derived_dep_services = {d.service for d in derived_deps}

    # Remote calls in code but not in YAML
    for name in derived_dep_services - yaml_dep_services:
        report.issues.append(ConsistencyIssue(
            severity="error",
            category="service",
            message=f"Remote dependency on '{name}' found in code (@bodhi.calls via) but not in any service YAML depends_on.",
            source=name,
        ))

    # Dependencies in YAML but not in code
    # Only warn for deps that declare explicit APIs — those are the ones
    # where @bodhi.calls via is expected. Deps without apis (infra, MQ,
    # long-lived connections) are accessed via reads/writes/consumes, not calls.
    for name in yaml_dep_services - derived_dep_services:
        has_apis = False
        for svc in yaml_services:
            for dep in svc.depends_on:
                if dep.service == name and dep.apis:
                    has_apis = True
        if has_apis:
            report.issues.append(ConsistencyIssue(
                severity="warning",
                category="service",
                message=f"Service '{name}' listed in YAML depends_on with APIs but no @bodhi.calls via found in code.",
                source=name,
            ))


def _validate_entities(
    functions: list[FunctionDSL],
    yaml_entities: list,
    report: ConsistencyReport,
) -> None:
    """Check that entities referenced in inline tags have YAML definitions."""
    # Collect all entity names from inline tags
    code_entities: set[str] = set()
    for fn in functions:
        for rw in fn.reads + fn.writes:
            entity = _extract_entity_from_rw(rw)
            if entity:
                code_entities.add(entity)

    yaml_entity_names = {e.table for e in yaml_entities}

    # Entities in code but no YAML definition
    for name in code_entities - yaml_entity_names:
        report.issues.append(ConsistencyIssue(
            severity="warning",
            category="entity",
            message=f"Entity '{name}' referenced in inline tags but has no .bodhi/entities/ YAML definition.",
            source=name,
        ))


# ============================================================
# YAML output (scaffold mode)
# ============================================================

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


def scaffold(project_root: Path, output_dir: Optional[Path] = None,
             exclude_dirs: set[str] | None = None) -> dict:
    """Generate scaffold Layer 2 YAML files from inline tags.

    Use this for cold-start: when adopting Bodhi on an existing project
    that already has code but no .bodhi/ YAML files. The generated files
    are a starting point — they need manual enrichment (path, auth,
    resilience, descriptions, etc.).

    Returns a summary dict with counts.
    """
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)
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


# Keep backward compatibility
derive_and_write = scaffold
