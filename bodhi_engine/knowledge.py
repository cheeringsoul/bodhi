"""
In-memory knowledge graph built from Bodhi DSL data.

Loads all inline tags and .bodhi/ YAML, builds indexes,
and exposes query methods for MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import parse_directory, load_bodhi_dir
from .parser.yaml_parser import (
    Flow, FlowStep, Entity, Event, Service, StateMachine, State, Concept,
)
from .parser.inline import FunctionDSL


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
    def __init__(self, project_root: Path, exclude_dirs: set[str] | None = None):
        self.project_root = project_root
        bodhi_dir = project_root / ".bodhi"

        self.functions: list[FunctionDSL] = parse_directory(
            project_root, exclude_dirs=exclude_dirs,
        )
        self.dsl: dict[str, Any] = (
            load_bodhi_dir(bodhi_dir) if bodhi_dir.is_dir() else {
                "meta": None, "flows": [], "states": [],
                "entities": [], "events": [], "services": [], "concepts": [],
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
                {
                    "fn": s.fn,
                    "intent": s.intent,
                    "reads": s.reads,
                    "writes": s.writes,
                    "calls": s.calls,
                    "emits": s.emits,
                    "on_fail": s.on_fail,
                }
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
            "apis": [{"method": a.method, "path": a.path, "flow": a.flow} for a in svc.apis],
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

    # -- private helpers --

    def _entity_schema(self, entity: str) -> dict | None:
        e = self._entity_by_table.get(entity)
        if not e:
            return None
        return {
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
