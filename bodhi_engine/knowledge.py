"""
In-memory knowledge graph built from Bodhi DSL data.

Loads all inline tags and .bodhi/ YAML, builds indexes,
and exposes query methods for MCP tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import parse_directory, load_bodhi_dir
from .parser.yaml_parser import (
    Flow, FlowStep, Entity, Event, Service, StateMachine, State, Concept,
    Channel, Topology,
)
from .parser.inline import FunctionDSL


@dataclass
class _LogPattern:
    """A compiled log pattern from @bodhi.log.success or @bodhi.log.error."""
    fn: str                # qualified function name
    pattern_type: str      # "success" or "error"
    raw_pattern: str       # original pattern string
    regex: re.Pattern      # compiled regex
    fields: list[str]      # placeholder field names in order


@dataclass
class LogMatchResult:
    """Result of matching a log line against the pattern registry."""
    fn: str                # matched function name
    pattern_type: str      # "success", "error", or "function_name"
    raw_pattern: str       # the pattern or function name that matched
    matched_line: str      # the actual log line that matched
    extracted: dict[str, str]  # extracted placeholder values, e.g. {"orderId": "12345"}
    flows: list[str]       # flow names that contain this function
    intent: str | None     # function intent from @bodhi.intent


def _compile_bodhi_pattern(pattern: str) -> tuple[re.Pattern, list[str]]:
    """Compile a @bodhi.log.* pattern into a regex + field name list.

    Example: "Order {orderId} created successfully"
           → (re.compile("Order (.+?) created successfully"), ["orderId"])

    Strips surrounding quotes from the pattern (common in @bodhi.log.* values).
    The last placeholder uses greedy (.+) since there's no trailing text to bound it.
    """
    # Strip surrounding quotes
    pattern = pattern.strip().strip('"').strip("'")

    fields: list[str] = []
    parts = re.split(r"\{(\w+)\}", pattern)
    # Count total placeholders
    total_placeholders = sum(1 for i in range(len(parts)) if i % 2 == 1)
    placeholder_index = 0

    regex_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            regex_parts.append(re.escape(part))
        else:
            fields.append(part)
            placeholder_index += 1
            # Last placeholder: greedy, everything else: non-greedy
            if placeholder_index == total_placeholders:
                regex_parts.append(r"(.+)")
            else:
                regex_parts.append(r"(.+?)")
    compiled = re.compile("".join(regex_parts), re.IGNORECASE)
    return compiled, fields


@dataclass
class EntityTrace:
    reads: list[dict[str, str]] = field(default_factory=list)
    writes: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ImpactResult:
    flows: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    state_machines: list[str] = field(default_factory=list)


class BodhiKnowledge:
    def __init__(self, project_root: Path, exclude_dirs: set[str] | None = None,
                 lenient: bool = False):
        self.project_root = project_root
        self.load_errors: list[str] = []
        bodhi_dir = project_root / ".bodhi"

        self.functions: list[FunctionDSL] = parse_directory(
            project_root, exclude_dirs=exclude_dirs,
        )
        self.dsl: dict[str, Any] = (
            load_bodhi_dir(
                bodhi_dir,
                errors=self.load_errors if lenient else None,
            ) if bodhi_dir.is_dir() else {
                "meta": None, "flows": [], "states": [],
                "entities": [], "events": [], "services": [], "concepts": [],
                "channels": [], "topologies": [],
            }
        )

        # build indexes
        self._fn_by_name: dict[str, FunctionDSL] = {
            f.qualified_name: f for f in self.functions
        }
        self._flow_by_name: dict[str, Flow] = {
            f.name: f for f in self.dsl["flows"]
        }
        self._entity_by_table: dict[str, Entity] = {
            e.table: e for e in self.dsl["entities"]
        }
        self._event_by_name: dict[str, Event] = {
            e.name: e for e in self.dsl["events"]
        }
        self._service_by_name: dict[str, Service] = {
            s.name: s for s in self.dsl["services"]
        }
        self._state_by_name: dict[str, StateMachine] = {
            s.name: s for s in self.dsl["states"]
        }
        self._concept_by_term: dict[str, Concept] = {
            c.term: c for c in self.dsl["concepts"]
        }
        self._channel_by_name: dict[str, Channel] = {
            c.name: c for c in self.dsl.get("channels", [])
        }
        self._topology_by_name: dict[str, Topology] = {
            t.name: t for t in self.dsl.get("topologies", [])
        }

        # Log pattern registry: compiled regexes from @bodhi.log.* tags
        self._log_registry: list[_LogPattern] = self._build_log_registry()

    def _build_log_registry(self) -> list[_LogPattern]:
        """Build a registry of compiled log patterns from all @bodhi.log.* tags."""
        registry: list[_LogPattern] = []
        for fn in self.functions:
            for pattern_str in fn.log_success:
                regex, fields = _compile_bodhi_pattern(pattern_str)
                registry.append(_LogPattern(
                    fn=fn.qualified_name,
                    pattern_type="success",
                    raw_pattern=pattern_str,
                    regex=regex,
                    fields=fields,
                ))
            for pattern_str in fn.log_error:
                regex, fields = _compile_bodhi_pattern(pattern_str)
                registry.append(_LogPattern(
                    fn=fn.qualified_name,
                    pattern_type="error",
                    raw_pattern=pattern_str,
                    regex=regex,
                    fields=fields,
                ))
        return registry

    # -- match_log: core engine capability --

    def match_log(self, log_text: str) -> list[LogMatchResult]:
        """Match a user-provided log snippet against the @bodhi.log.* pattern registry.

        For each line in the log text, try all registered patterns.
        Returns matched functions, pattern type (success/error),
        extracted variables, and associated flow context.

        This is a pure engine capability — no log file access needed.
        The application layer decides what to do with the matches
        (e.g. build a diagnosis, show context, trace impact).
        """
        results: list[LogMatchResult] = []
        seen: set[tuple[str, str]] = set()  # (fn, line) dedup

        for line in log_text.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            for lp in self._log_registry:
                m = lp.regex.search(line)
                if not m:
                    continue

                dedup_key = (lp.fn, line)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # Extract named fields from the match
                extracted = {}
                for i, field_name in enumerate(lp.fields):
                    try:
                        extracted[field_name] = m.group(i + 1)
                    except IndexError:
                        pass

                # Find which flows this function belongs to
                flows_containing = []
                for flow_name, flow in self._flow_by_name.items():
                    for step in flow.steps:
                        if step.fn == lp.fn:
                            flows_containing.append(flow_name)
                            break

                # Get the FunctionDSL for richer context
                fn_dsl = self._fn_by_name.get(lp.fn)

                results.append(LogMatchResult(
                    fn=lp.fn,
                    pattern_type=lp.pattern_type,
                    raw_pattern=lp.raw_pattern,
                    matched_line=line,
                    extracted=extracted,
                    flows=flows_containing,
                    intent=fn_dsl.intent if fn_dsl else None,
                ))

        # Also try matching function names directly (fallback for untagged logs)
        for line in log_text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            for fn_name, fn_dsl in self._fn_by_name.items():
                if fn_name in line:
                    dedup_key = (fn_name, line)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    flows_containing = []
                    for flow_name, flow in self._flow_by_name.items():
                        for step in flow.steps:
                            if step.fn == fn_name:
                                flows_containing.append(flow_name)
                                break

                    results.append(LogMatchResult(
                        fn=fn_name,
                        pattern_type="function_name",
                        raw_pattern=fn_name,
                        matched_line=line,
                        extracted={},
                        flows=flows_containing,
                        intent=fn_dsl.intent if fn_dsl else None,
                    ))

        return results

    # -- list helpers --

    def list_flows(self) -> list[str]:
        return list(self._flow_by_name.keys())

    def list_entities(self) -> list[str]:
        return list(self._entity_by_table.keys())

    def list_events(self) -> list[str]:
        return list(self._event_by_name.keys())

    def list_services(self) -> list[str]:
        return list(self._service_by_name.keys())

    def list_state_machines(self) -> list[str]:
        return list(self._state_by_name.keys())

    def list_channels(self) -> list[str]:
        return list(self._channel_by_name.keys())

    def list_topologies(self) -> list[str]:
        return list(self._topology_by_name.keys())

    # -- query methods --

    def query_flow(self, name: str) -> dict | None:
        flow = self._flow_by_name.get(name)
        if not flow:
            return None
        return {
            "name": flow.name,
            "description": flow.description,
            "entry": {
                "type": flow.entry_type,
                "method": flow.entry_method,
                "path": flow.entry_path,
                "auth": flow.entry_auth,
            },
            "steps": [
                self._flow_step_to_dict(s)
                for s in flow.steps
            ],
            "entities": flow.entities,
            "events": flow.events,
            "related_flows": flow.related_flows,
        }

    def trace_entity(self, entity: str) -> dict:
        trace = EntityTrace()

        # from flow steps
        for flow in self.dsl["flows"]:
            for step in flow.steps:
                for r in step.reads:
                    if entity in r:
                        trace.reads.append({"fn": step.fn, "flow": flow.name, "detail": r})
                for w in step.writes:
                    if entity in w:
                        trace.writes.append({"fn": step.fn, "flow": flow.name, "detail": w})

        # from inline tags
        for fn in self.functions:
            for r in fn.reads:
                if entity in r:
                    trace.reads.append({"fn": fn.qualified_name, "file": fn.file_path, "detail": r})
            for w in fn.writes:
                if entity in w:
                    trace.writes.append({"fn": fn.qualified_name, "file": fn.file_path, "detail": w})

        return {
            "entity": entity,
            "schema": self._entity_schema(entity),
            "reads": trace.reads,
            "writes": trace.writes,
        }

    def find_consumers(self, event: str) -> dict:
        evt = self._event_by_name.get(event)
        result: dict[str, Any] = {"event": event, "consumers": [], "producers": []}

        if evt:
            result["description"] = evt.description
            result["channel"] = evt.channel
            result["consumers"] = [
                {"fn": c.fn, "flow": c.flow} for c in evt.consumers
            ]
            result["producers"] = [
                {"fn": p.fn, "flow": p.flow} for p in evt.producers
            ]

        # also check inline tags
        for fn in self.functions:
            for e in fn.emits:
                if event in e and not any(
                    p["fn"] == fn.qualified_name for p in result["producers"]
                ):
                    result["producers"].append({"fn": fn.qualified_name, "file": fn.file_path})
            for c in fn.consumes:
                if event in c and not any(
                    con["fn"] == fn.qualified_name for con in result["consumers"]
                ):
                    result["consumers"].append({"fn": fn.qualified_name, "file": fn.file_path})

        return result

    def impact_analysis(self, target: str) -> dict:
        result = ImpactResult()

        # check flows
        for flow in self.dsl["flows"]:
            for step in flow.steps:
                if target in step.fn or target in step.calls:
                    if flow.name not in result.flows:
                        result.flows.append(flow.name)
                    if step.fn not in result.functions:
                        result.functions.append(step.fn)
                # check entity references
                for rw in step.reads + step.writes:
                    if target in rw:
                        if flow.name not in result.flows:
                            result.flows.append(flow.name)
                        if step.fn not in result.functions:
                            result.functions.append(step.fn)

        # check events
        for evt in self.dsl["events"]:
            for p in evt.producers:
                if target in p.fn:
                    if evt.name not in result.events:
                        result.events.append(evt.name)
            for c in evt.consumers:
                if target in c.fn:
                    if evt.name not in result.events:
                        result.events.append(evt.name)

        # check state machines
        for sm in self.dsl["states"]:
            if target == sm.entity or target == sm.name:
                result.state_machines.append(sm.name)
            for state in sm.states:
                for t in state.transitions:
                    if t.fn and target in t.fn:
                        if sm.name not in result.state_machines:
                            result.state_machines.append(sm.name)

        return {
            "target": target,
            "affected_flows": result.flows,
            "affected_functions": result.functions,
            "affected_events": result.events,
            "affected_state_machines": result.state_machines,
        }

    def query_state(self, state_machine: str, state: str | None = None) -> dict | None:
        sm = self._state_by_name.get(state_machine)
        if not sm:
            return None

        if state:
            for s in sm.states:
                if s.id == state:
                    return {
                        "state_machine": sm.name,
                        "entity": sm.entity,
                        "state": s.id,
                        "value": s.value,
                        "description": s.description,
                        "terminal": s.terminal,
                        "transitions": [
                            {
                                "target": t.target,
                                "trigger": t.trigger,
                                "fn": t.fn,
                                "condition": t.condition,
                            }
                            for t in s.transitions
                        ],
                    }
            return None

        return {
            "name": sm.name,
            "entity": sm.entity,
            "field": sm.field_name,
            "description": sm.description,
            "states": [
                {
                    "id": s.id,
                    "value": s.value,
                    "description": s.description,
                    "terminal": s.terminal,
                    "transitions": len(s.transitions),
                }
                for s in sm.states
            ],
        }

    def service_deps(self, service: str) -> dict | None:
        svc = self._service_by_name.get(service)
        if not svc:
            return None

        # find who depends on this service
        depended_by = []
        for other in self.dsl["services"]:
            if other.name == service:
                continue
            for dep in other.depends_on:
                if dep.service == service:
                    depended_by.append({
                        "service": other.name,
                        "protocol": dep.protocol,
                        "apis": dep.apis,
                    })

        return {
            "name": svc.name,
            "description": svc.description,
            "tech_stack": svc.tech_stack,
            "apis": [self._service_api_to_dict(a) for a in svc.apis],
            "depends_on": [
                {
                    "service": d.service,
                    "protocol": d.protocol or d.type,
                    "apis": d.apis,
                    "topics": d.topics,
                    "resilience": d.resilience,
                }
                for d in svc.depends_on
            ],
            "depended_by": depended_by,
        }

    def query_concept(self, term: str) -> dict | None:
        c = self._concept_by_term.get(term)
        if not c:
            return None
        return {
            "term": c.term,
            "definition": c.definition,
            "related_states": c.related_states,
            "related_flows": c.related_flows,
            "related_fields": c.related_fields,
        }

    def query_channel(self, name: str) -> dict | None:
        ch = self._channel_by_name.get(name)
        if not ch:
            return None
        return {
            "name": ch.name,
            "protocol": ch.protocol,
            "description": ch.description,
            "path": ch.path,
            "inbound_events": [
                {
                    "name": e.name,
                    "description": e.description,
                    "schema": e.schema,
                    "triggers_flow": e.triggers_flow,
                }
                for e in ch.inbound_events
            ],
            "outbound_events": [
                {
                    "name": e.name,
                    "description": e.description,
                    "schema": e.schema,
                    "triggered_by": e.triggered_by,
                }
                for e in ch.outbound_events
            ],
        }

    def query_topology(self, name: str) -> dict | None:
        topo = self._topology_by_name.get(name)
        if not topo:
            return None
        return {
            "name": topo.name,
            "description": topo.description,
            "chains": [
                {
                    "event": c.event,
                    "channel": c.channel,
                    "producer": c.producer,
                    "consumers": [
                        {
                            "service": con.service,
                            "fn": con.fn,
                            "action": con.action,
                            "emits": con.emits,
                        }
                        for con in c.consumers
                    ],
                }
                for c in topo.chains
            ],
        }

    # -- private helpers --

    def _flow_step_to_dict(self, s: FlowStep) -> dict:
        d: dict[str, Any] = {
            "fn": s.fn,
            "intent": s.intent,
            "reads": s.reads,
            "writes": s.writes,
            "calls": s.calls,
            "emits": s.emits,
            "on_fail": s.on_fail,
        }
        if s.remote:
            d["remote"] = s.remote
        if s.protocol:
            d["protocol"] = s.protocol
        if s.api:
            d["api"] = s.api
        if s.flow_ref:
            d["flow_ref"] = s.flow_ref
        return d

    def _service_api_to_dict(self, a) -> dict:
        d: dict[str, Any] = {"protocol": a.protocol}
        if a.method:
            d["method"] = a.method
        if a.path:
            d["path"] = a.path
        if a.flow:
            d["flow"] = a.flow
        if a.service:
            d["service"] = a.service
        if a.channel:
            d["channel"] = a.channel
        if a.description:
            d["description"] = a.description
        return d

    def _entity_schema(self, entity: str) -> dict | None:
        e = self._entity_by_table.get(entity)
        if not e:
            return None
        result = {
            "table": e.table,
            "description": e.description,
            "fields": [
                {"name": f.name, "type": f.type, "sensitive": f.sensitive}
                for f in e.fields
            ],
            "relations": [
                {"target": r.target, "type": r.type}
                for r in e.relations
            ],
        }
        if e.database:
            result["database"] = e.database
        if e.datasource:
            result["datasource"] = e.datasource
        return result
