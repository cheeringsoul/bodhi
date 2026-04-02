"""
Log diagnosis — application layer.

Takes user-pasted log text, uses the engine's match_log() to find
the entry point in the knowledge graph, then builds a structured
diagnosis by querying flows, entities, events, and state machines.
"""

from __future__ import annotations

from typing import Any

from bodhi_engine.knowledge import BodhiKnowledge, LogMatchResult


def diagnose_from_log(kb: BodhiKnowledge, log_text: str) -> dict[str, Any]:
    """Diagnose an issue from user-pasted log text.

    1. Match log lines against @bodhi.log.* pattern registry
    2. For each matched function, gather flow context
    3. Trace upstream/downstream impact
    4. Return structured diagnosis
    """
    matches = kb.match_log(log_text)

    if not matches:
        return {
            "matched": False,
            "message": "No known patterns matched in the log text. "
                       "Ensure relevant functions have @bodhi.log.success / @bodhi.log.error tags.",
            "log_text": log_text,
        }

    diagnosis: dict[str, Any] = {
        "matched": True,
        "matches": [],
        "flow_context": {},
        "impact": {},
    }

    seen_flows: set[str] = set()
    seen_impact_targets: set[str] = set()

    for match in matches:
        match_entry = _format_match(match)
        diagnosis["matches"].append(match_entry)

        # Gather flow context for each matched flow
        for flow_name in match.flows:
            if flow_name in seen_flows:
                continue
            seen_flows.add(flow_name)

            flow_data = kb.query_flow(flow_name)
            if flow_data:
                # Annotate which step is the matched one
                flow_context = _build_flow_context(flow_data, match)
                diagnosis["flow_context"][flow_name] = flow_context

        # Impact analysis for the matched function
        if match.fn not in seen_impact_targets:
            seen_impact_targets.add(match.fn)
            impact = kb.impact_analysis(match.fn)
            if any(impact.get(k) for k in ("affected_flows", "affected_events",
                                            "affected_state_machines")):
                diagnosis["impact"][match.fn] = impact

    return diagnosis


def _format_match(match: LogMatchResult) -> dict[str, Any]:
    """Format a single LogMatchResult for the diagnosis output."""
    result: dict[str, Any] = {
        "fn": match.fn,
        "type": match.pattern_type,
        "matched_line": match.matched_line,
    }
    if match.extracted:
        result["extracted_variables"] = match.extracted
    if match.flows:
        result["flows"] = match.flows
    if match.intent:
        result["intent"] = match.intent
    return result


def _build_flow_context(flow_data: dict, match: LogMatchResult) -> dict[str, Any]:
    """Build flow context annotated with the matched step's position."""
    steps = flow_data.get("steps", [])
    matched_index = None
    for i, step in enumerate(steps):
        if step["fn"] == match.fn:
            matched_index = i
            break

    context: dict[str, Any] = {
        "name": flow_data["name"],
        "description": flow_data.get("description", ""),
        "entry": flow_data.get("entry"),
        "total_steps": len(steps),
    }

    if matched_index is not None:
        context["matched_step_index"] = matched_index

        # Steps before = already succeeded (presumably)
        if matched_index > 0:
            context["upstream_steps"] = [
                {"fn": s["fn"], "intent": s.get("intent", "")}
                for s in steps[:matched_index]
            ]

        # The matched step itself
        context["matched_step"] = steps[matched_index]

        # Steps after = not yet reached if this step failed
        if matched_index < len(steps) - 1:
            downstream = []
            for s in steps[matched_index + 1:]:
                entry: dict[str, Any] = {"fn": s["fn"], "intent": s.get("intent", "")}
                if s.get("emits"):
                    entry["emits"] = s["emits"]
                if s.get("writes"):
                    entry["writes"] = s["writes"]
                downstream.append(entry)
            context["downstream_steps"] = downstream

    # Related entities and events
    if flow_data.get("entities"):
        context["entities"] = flow_data["entities"]
    if flow_data.get("events"):
        context["events"] = flow_data["events"]

    return context
