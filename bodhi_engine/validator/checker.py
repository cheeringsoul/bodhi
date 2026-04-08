"""
Validate Bodhi DSL completeness and consistency.

Checks both inline tags and .bodhi/ YAML files against the rules
defined in the specification (section 8).
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..config import load_config
from ..parser import load_bodhi_dir, parse_directory


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    severity: Severity
    rule: str
    message: str
    location: str = ""

    def __str__(self):
        icon = {"error": "E", "warning": "W", "info": "I"}[self.severity.value]
        loc = f" ({self.location})" if self.location else ""
        return f"[{icon}] {self.rule}: {self.message}{loc}"


def _extract_entity_name(tag_value: str) -> str | None:
    """Extract entity name from a @bodhi.reads or @bodhi.writes value.

    Examples:
        "orders(id, userId, status=PENDING) via INSERT" → "orders"
        "request.body(userId, items)" → None
        "cache:session(token)" → "cache:session"
        "response(200, ...)" → None
    """
    val = tag_value.strip()
    for prefix in ("request.", "response", "env:", "config:"):
        if val.startswith(prefix):
            return None
    # Take everything before the first '('
    if "(" in val:
        return val[:val.index("(")].strip()
    # No parens — take the first token
    return val.split()[0] if val else None


def validate(project_root: Path, exclude_dirs: set[str] | None = None) -> list[Issue]:
    """Run all validation checks and return a list of issues."""
    issues: list[Issue] = []

    bodhi_dir = project_root / ".bodhi"
    dsl = load_bodhi_dir(bodhi_dir) if bodhi_dir.is_dir() else None
    config = load_config(project_root)
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)

    # Build a set of all function qualified names for cross-reference
    fn_names = {fn.qualified_name for fn in functions}

    # --- Inline Tag Checks ---

    for fn in functions:
        loc = f"{fn.file_path}:{fn.line_number}"

        # Rule: has writes but no intent
        if fn.writes and not fn.intent:
            issues.append(Issue(
                severity=Severity.ERROR,
                rule="missing-intent",
                message=f"Function '{fn.qualified_name}' has @bodhi.writes but no @bodhi.intent",
                location=loc,
            ))

        # Rule: has reads but no intent
        if fn.reads and not fn.intent:
            issues.append(Issue(
                severity=Severity.ERROR,
                rule="missing-intent",
                message=f"Function '{fn.qualified_name}' has @bodhi.reads but no @bodhi.intent",
                location=loc,
            ))

        # Rule: @bodhi.calls target should exist
        for callee in fn.calls:
            if callee not in fn_names:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    rule="dangling-call",
                    message=f"@bodhi.calls references '{callee}' which has no @bodhi.* tags",
                    location=loc,
                ))

        # Rule: @bodhi.writes entity should exist in .bodhi/entities/
        if dsl:
            entity_names = {e.table for e in dsl["entities"]}
            for write_val in fn.writes:
                entity = _extract_entity_name(write_val)
                if entity and not entity.startswith("cache:") and entity_names and entity not in entity_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="missing-entity",
                        message=f"@bodhi.writes references entity '{entity}' not defined in .bodhi/entities/",
                        location=loc,
                    ))

    # --- Flow Checks ---

    if dsl:
        for flow in dsl["flows"]:
            for step in flow.steps:
                if step.fn not in fn_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="flow-missing-inline",
                        message=f"Flow '{flow.name}' step '{step.fn}' has no @bodhi.* inline tags in source code",
                        location=f".bodhi/flows/{flow.name}.yaml",
                    ))

                if step.writes and not step.on_fail:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="writes-no-error-handling",
                        message=f"Flow '{flow.name}' step '{step.fn}' writes data but has no on_fail",
                        location=f".bodhi/flows/{flow.name}.yaml",
                    ))

            entity_names = {e.table for e in dsl["entities"]}
            for entity_ref in flow.entities:
                if entity_ref not in entity_names:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        rule="flow-missing-entity",
                        message=f"Flow '{flow.name}' references entity '{entity_ref}' not defined in .bodhi/entities/",
                        location=f".bodhi/flows/{flow.name}.yaml",
                    ))

        # State transition functions not in any flow
        flow_functions = set()
        for flow in dsl["flows"]:
            for step in flow.steps:
                flow_functions.add(step.fn)

        for sm in dsl["states"]:
            for state in sm.states:
                for t in state.transitions:
                    if t.fn and t.fn not in flow_functions:
                        issues.append(Issue(
                            severity=Severity.INFO,
                            rule="transition-fn-not-in-flow",
                            message=f"State machine '{sm.name}' transition fn '{t.fn}' is not in any flow",
                            location=f".bodhi/states/{sm.name}.yaml",
                        ))

        # Event checks: emits/consumes should have matching event catalog entry
        event_names = {e.name for e in dsl.get("events", [])}
        if event_names:
            for fn in functions:
                loc = f"{fn.file_path}:{fn.line_number}"
                for emit_val in fn.emits:
                    event_name = emit_val.split("(")[0].strip() if "(" in emit_val else emit_val.split()[0]
                    if event_name not in event_names:
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            rule="emits-missing-event",
                            message=f"@bodhi.emits references event '{event_name}' not defined in .bodhi/events/",
                            location=loc,
                        ))
                for consume_val in fn.consumes:
                    event_name = consume_val.split("(")[0].strip() if "(" in consume_val else consume_val.split()[0]
                    if event_name not in event_names:
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            rule="consumes-missing-event",
                            message=f"@bodhi.consumes references event '{event_name}' not defined in .bodhi/events/",
                            location=loc,
                        ))

        # Event catalog: consumers/producers should exist as tagged functions
        for event in dsl.get("events", []):
            for producer in event.producers:
                if producer.fn not in fn_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="event-producer-missing-inline",
                        message=f"Event '{event.name}' producer '{producer.fn}' has no @bodhi.* inline tags",
                        location=f".bodhi/events/{event.name}.yaml",
                    ))
            for consumer in event.consumers:
                if consumer.fn not in fn_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="event-consumer-missing-inline",
                        message=f"Event '{event.name}' consumer '{consumer.fn}' has no @bodhi.* inline tags",
                        location=f".bodhi/events/{event.name}.yaml",
                    ))

        # Service checks: remote calls should have on_fail, API flows should exist
        channel_names = {c.name for c in dsl.get("channels", [])}
        for service in dsl.get("services", []):
            flow_names = {f.name for f in dsl["flows"]}
            for api in service.apis:
                if api.flow and api.flow not in flow_names:
                    api_label = f"{api.protocol}:{api.method or ''} {api.path or api.service or ''}".strip()
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="service-api-missing-flow",
                        message=f"Service '{service.name}' API '{api_label}' references flow '{api.flow}' which does not exist",
                        location=f".bodhi/services/{service.name}.yaml",
                    ))
                # WebSocket APIs should reference an existing channel
                if api.protocol == "websocket" and api.channel and api.channel not in channel_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="service-api-missing-channel",
                        message=f"Service '{service.name}' WebSocket API references channel '{api.channel}' which does not exist",
                        location=f".bodhi/services/{service.name}.yaml",
                    ))

        # Flow cross-service checks: remote steps should reference known services
        service_names = {s.name for s in dsl.get("services", [])}
        # Also include services from depends_on
        for svc in dsl.get("services", []):
            for dep in svc.depends_on:
                service_names.add(dep.service)
        for flow in dsl["flows"]:
            for step in flow.steps:
                if step.remote and service_names and step.remote not in service_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="flow-remote-unknown-service",
                        message=f"Flow '{flow.name}' step '{step.fn}' references remote service '{step.remote}' not found in any service definition",
                        location=f".bodhi/flows/{flow.name}.yaml",
                    ))

        # Topology checks: events in topology should exist in events/
        event_names = {e.name for e in dsl.get("events", [])}
        for topo in dsl.get("topologies", []):
            for chain in topo.chains:
                if event_names and chain.event not in event_names:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="topology-missing-event",
                        message=f"Topology '{topo.name}' references event '{chain.event}' not defined in .bodhi/events/",
                        location=f".bodhi/topology/{topo.name}.yaml",
                    ))

        # Remote calls (via) should have on_fail
        for fn in functions:
            loc = f"{fn.file_path}:{fn.line_number}"
            for call_val in fn.get_tags("calls"):
                if " via " in call_val and not fn.on_fail:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        rule="remote-call-no-error-handling",
                        message=f"Function '{fn.qualified_name}' has remote call '{call_val}' but no @bodhi.on_fail",
                        location=loc,
                    ))
                    break

        # Entity enum without state machine
        for entity in dsl["entities"]:
            for f in entity.fields:
                if f.enum and not f.state_machine:
                    issues.append(Issue(
                        severity=Severity.INFO,
                        rule="enum-no-state-machine",
                        message=f"Entity '{entity.table}.{f.name}' has enum values but no state_machine reference",
                        location=f".bodhi/entities/{entity.table}.yaml",
                    ))

    # --- @bodhi.implements checks (independent of .bodhi/ dir) ---

    # Build class-level index: class_name -> list of FunctionDSL
    class_functions: dict[str, list] = {}
    for fn in functions:
        if fn.class_name:
            class_functions.setdefault(fn.class_name, []).append(fn)

    # Collect all classes that declare @bodhi.implements
    impl_classes: dict[str, str] = {}  # class_name -> interface_name
    for fn in functions:
        if fn.implements and fn.class_name:
            impl_classes[fn.class_name] = fn.implements

    # Check: @bodhi.implements target interface should have inline tags
    classes_with_tags = set()
    for fn in functions:
        if fn.class_name and fn.intent:
            classes_with_tags.add(fn.class_name)

    for impl_class, interface_name in impl_classes.items():
        if interface_name not in classes_with_tags:
            issues.append(Issue(
                severity=Severity.WARNING,
                rule="implements-missing-interface",
                message=f"Class '{impl_class}' declares @bodhi.implements {interface_name}, but '{interface_name}' has no @bodhi.* inline tags",
                location=impl_class,
            ))

    # Rule: method overloading — multiple tagged functions sharing the same
    # ClassName.methodName identifier break Bodhi's call-graph resolution.
    # Only flag when BOTH overloads carry @bodhi.* tags (untagged siblings
    # are invisible to the parser and irrelevant).
    for class_name, fns in class_functions.items():
        by_name: dict[str, list] = {}
        for fn in fns:
            by_name.setdefault(fn.function_name, []).append(fn)
        for method_name, group in by_name.items():
            # Skip constructors (Java: method name == class name)
            if method_name == class_name:
                continue
            # Skip user-whitelisted overloads (Builder/fluent APIs, etc.)
            if f"{class_name}.{method_name}" in config.allow_overload:
                continue
            if len(group) > 1:
                locations = ", ".join(
                    f"{Path(fn.file_path).name}:{fn.line_number}" for fn in group
                )
                issues.append(Issue(
                    severity=Severity.WARNING,
                    rule="method-overloading",
                    message=(
                        f"Method '{class_name}.{method_name}' is overloaded "
                        f"({len(group)} tagged implementations at {locations}). "
                        f"Bodhi DSL uses ClassName.methodName as a unique identifier — "
                        f"rename overloads to distinct names (e.g. createOrder, createBatchOrder)."
                    ),
                    location=group[0].file_path,
                ))

    return issues


def format_report(issues: list[Issue]) -> str:
    """Format validation issues as a human-readable report."""
    if not issues:
        return "All checks passed."

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    lines = []
    lines.append(f"Found {len(issues)} issues: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info\n")

    if errors:
        lines.append("--- Errors ---")
        for issue in errors:
            lines.append(str(issue))
        lines.append("")

    if warnings:
        lines.append("--- Warnings ---")
        for issue in warnings:
            lines.append(str(issue))
        lines.append("")

    if infos:
        lines.append("--- Info ---")
        for issue in infos:
            lines.append(str(issue))

    return "\n".join(lines)
