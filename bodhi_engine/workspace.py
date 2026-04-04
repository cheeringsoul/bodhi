"""
Workspace loader — scan a directory containing multiple service repos,
load each service's .bodhi/ metadata, and merge into a unified global
knowledge graph with cross-service validation.

Usage:
    result = load_workspace(Path("./workspace"))
    # result.services  — merged service data keyed by service name
    # result.issues    — cross-service validation issues found during merge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .parser.yaml_parser import (
    load_bodhi_dir, Flow, Entity, Event, EventSchemaField,
    Service, StateMachine, Channel, Topology, ProjectMeta,
)


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class WorkspaceIssue:
    """A cross-service validation issue found during workspace merge."""
    severity: IssueSeverity
    code: str
    message: str
    service: str = ""        # which service triggered this issue
    related_service: str = ""  # the other service involved

    def __str__(self) -> str:
        prefix = f"[{self.severity.value}] {self.code}"
        if self.service:
            prefix += f" ({self.service})"
        return f"{prefix}: {self.message}"


@dataclass
class ServiceData:
    """All DSL data for a single service, with its directory path."""
    name: str
    path: Path
    meta: ProjectMeta | None
    flows: list[Flow]
    entities: list[Entity]
    events: list[Event]
    services: list[Service]
    states: list[StateMachine]
    channels: list[Channel]
    topologies: list[Topology]
    concepts: list


@dataclass
class WorkspaceResult:
    """Result of loading and merging a workspace."""
    service_data: dict[str, ServiceData] = field(default_factory=dict)
    # Merged globals
    all_flows: dict[str, Flow] = field(default_factory=dict)         # "service:flow_name" → Flow
    all_entities: dict[str, Entity] = field(default_factory=dict)
    all_events: dict[str, Event] = field(default_factory=dict)       # event name → merged Event
    all_services: dict[str, Service] = field(default_factory=dict)
    all_states: dict[str, StateMachine] = field(default_factory=dict)
    all_channels: dict[str, Channel] = field(default_factory=dict)
    all_topologies: dict[str, Topology] = field(default_factory=dict)
    issues: list[WorkspaceIssue] = field(default_factory=list)

    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    def format_issues(self) -> str:
        if not self.issues:
            return "No issues found."
        lines = []
        errors = [i for i in self.issues if i.severity == IssueSeverity.ERROR]
        warnings = [i for i in self.issues if i.severity == IssueSeverity.WARNING]
        if errors:
            lines.append(f"Errors ({len(errors)}):")
            for i in errors:
                lines.append(f"  {i}")
        if warnings:
            lines.append(f"Warnings ({len(warnings)}):")
            for i in warnings:
                lines.append(f"  {i}")
        return "\n".join(lines)


def load_workspace(workspace_path: Path) -> WorkspaceResult:
    """Scan a workspace directory for all .bodhi/ subdirs, load and merge.

    Scans one level deep: workspace_path/*/. bodhi/
    Each subdirectory with a .bodhi/ is treated as a service.

    Returns a WorkspaceResult with merged data and validation issues.
    """
    result = WorkspaceResult()

    # 1. Discover and load all services
    for subdir in sorted(workspace_path.iterdir()):
        if not subdir.is_dir():
            continue
        bodhi_dir = subdir / ".bodhi"
        if not bodhi_dir.is_dir():
            continue

        dsl = load_bodhi_dir(bodhi_dir)
        meta: ProjectMeta | None = dsl["meta"]

        # Determine service name: from distributed.service, or project.name, or dir name
        service_name = subdir.name
        if meta:
            if meta.distributed and meta.distributed.service:
                service_name = meta.distributed.service
            elif meta.name:
                service_name = meta.name

        sd = ServiceData(
            name=service_name,
            path=subdir,
            meta=meta,
            flows=dsl["flows"],
            entities=dsl["entities"],
            events=dsl["events"],
            services=dsl["services"],
            states=dsl["states"],
            channels=dsl.get("channels", []),
            topologies=dsl.get("topologies", []),
            concepts=dsl.get("concepts", []),
        )

        if service_name in result.service_data:
            result.issues.append(WorkspaceIssue(
                severity=IssueSeverity.ERROR,
                code="duplicate-service",
                message=f"Service '{service_name}' found in both "
                        f"{result.service_data[service_name].path} and {subdir}",
                service=service_name,
            ))
            continue

        result.service_data[service_name] = sd

    if not result.service_data:
        result.issues.append(WorkspaceIssue(
            severity=IssueSeverity.WARNING,
            code="empty-workspace",
            message=f"No .bodhi/ directories found in {workspace_path}",
        ))
        return result

    # 2. Merge all data into global indexes
    _merge_all(result)

    # 3. Cross-service validation
    _validate_cross_service(result)

    return result


def _merge_all(result: WorkspaceResult) -> None:
    """Merge all service data into the global indexes."""
    _event_origin: dict[str, str] = {}  # event name → first service that defined it
    for svc_name, sd in result.service_data.items():
        # Flows: namespaced as "service:flow_name"
        for flow in sd.flows:
            key = f"{svc_name}:{flow.name}"
            result.all_flows[key] = flow

        # Entities: namespaced as "service:table"
        for entity in sd.entities:
            key = f"{svc_name}:{entity.table}"
            result.all_entities[key] = entity

        # Events: merged by event name (multiple services may reference same event)
        for event in sd.events:
            if event.name in result.all_events:
                _merge_event(result.all_events[event.name], event, svc_name,
                             _event_origin, result)
            else:
                result.all_events[event.name] = Event(
                    name=event.name,
                    description=event.description,
                    channel=event.channel,
                    schema=list(event.schema),
                    producers=list(event.producers),
                    consumers=list(event.consumers),
                )
                _event_origin[event.name] = svc_name

        # Services
        for svc in sd.services:
            result.all_services[svc.name] = svc

        # State machines
        for sm in sd.states:
            key = f"{svc_name}:{sm.name}"
            result.all_states[key] = sm

        # Channels
        for ch in sd.channels:
            key = f"{svc_name}:{ch.name}"
            result.all_channels[key] = ch

        # Topologies
        for topo in sd.topologies:
            result.all_topologies[topo.name] = topo


def _merge_event(existing: Event, new: Event, new_service: str,
                 event_origin: dict[str, str],
                 result: WorkspaceResult) -> None:
    """Merge a new event definition into an existing one.

    Combines producers and consumers, checks schema consistency.
    """
    # Merge producers (dedup by fn)
    existing_producer_fns = {p.fn for p in existing.producers}
    for p in new.producers:
        if p.fn not in existing_producer_fns:
            existing.producers.append(p)

    # Merge consumers (dedup by fn)
    existing_consumer_fns = {c.fn for c in existing.consumers}
    for c in new.consumers:
        if c.fn not in existing_consumer_fns:
            existing.consumers.append(c)

    # Schema consistency check
    if existing.schema and new.schema:
        existing_fields = {f.field for f in existing.schema}
        new_fields = {f.field for f in new.schema}

        missing_in_new = existing_fields - new_fields
        missing_in_existing = new_fields - existing_fields

        if missing_in_new or missing_in_existing:
            origin_service = event_origin.get(existing.name, "unknown")
            diff_parts = []
            if missing_in_new:
                diff_parts.append(
                    f"fields in {origin_service} but not {new_service}: "
                    f"{sorted(missing_in_new)}")
            if missing_in_existing:
                diff_parts.append(
                    f"fields in {new_service} but not {origin_service}: "
                    f"{sorted(missing_in_existing)}")
            result.issues.append(WorkspaceIssue(
                severity=IssueSeverity.ERROR,
                code="event-schema-mismatch",
                message=f"Event '{existing.name}' has inconsistent schema "
                        f"between {origin_service} and {new_service}. "
                        + "; ".join(diff_parts),
                service=new_service,
                related_service=origin_service,
            ))


def _validate_cross_service(result: WorkspaceResult) -> None:
    """Validate cross-service relationships after merge."""

    # 1. Check flow_ref references
    for svc_name, sd in result.service_data.items():
        for flow in sd.flows:
            for step in flow.steps:
                if step.flow_ref:
                    # flow_ref format: "service:flow_name"
                    if step.flow_ref not in result.all_flows:
                        result.issues.append(WorkspaceIssue(
                            severity=IssueSeverity.ERROR,
                            code="broken-flow-ref",
                            message=f"Flow step '{step.fn}' in '{svc_name}:{flow.name}' "
                                    f"references '{step.flow_ref}' which does not exist",
                            service=svc_name,
                        ))

    # 2. Check remote service references
    known_services = set(result.all_services.keys())
    for svc_name, sd in result.service_data.items():
        for flow in sd.flows:
            for step in flow.steps:
                if step.remote and step.remote not in known_services:
                    result.issues.append(WorkspaceIssue(
                        severity=IssueSeverity.WARNING,
                        code="unknown-remote-service",
                        message=f"Flow step '{step.fn}' in '{svc_name}:{flow.name}' "
                                f"calls remote service '{step.remote}' "
                                f"which is not found in workspace",
                        service=svc_name,
                        related_service=step.remote,
                    ))

    # 3. Check service dependencies
    for svc_name, sd in result.service_data.items():
        for svc in sd.services:
            for dep in svc.depends_on:
                if dep.service not in known_services:
                    result.issues.append(WorkspaceIssue(
                        severity=IssueSeverity.WARNING,
                        code="unknown-dependency",
                        message=f"Service '{svc_name}' depends on '{dep.service}' "
                                f"which is not found in workspace",
                        service=svc_name,
                        related_service=dep.service,
                    ))

    # 4. Check events have at least one consumer
    for event_name, event in result.all_events.items():
        if event.producers and not event.consumers:
            result.issues.append(WorkspaceIssue(
                severity=IssueSeverity.WARNING,
                code="event-no-consumer",
                message=f"Event '{event_name}' has producers but no consumers",
            ))

    # 5. Check topology event references
    for topo_name, topo in result.all_topologies.items():
        for chain in topo.chains:
            if chain.event not in result.all_events:
                result.issues.append(WorkspaceIssue(
                    severity=IssueSeverity.WARNING,
                    code="topology-unknown-event",
                    message=f"Topology '{topo_name}' references event "
                            f"'{chain.event}' which is not defined in any service",
                ))
