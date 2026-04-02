"""
Debug reasoning engine — traces flow execution through logs.

Given a flow name + correlation ID, walks flow steps in order,
searches logs for evidence of each step, and classifies status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from ..parser.yaml_parser import Flow, FlowStep
from ..parser.inline import FunctionDSL
from .log_adapter import LogAdapter, LogEntry


class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    NO_EVIDENCE = "NO_EVIDENCE"


@dataclass
class StepResult:
    """Debug result for a single flow step."""
    fn: str
    status: StepStatus
    log: Optional[str] = None          # matching log message
    timestamp: Optional[datetime] = None
    note: Optional[str] = None
    error_handling: Optional[str] = None


@dataclass
class DebugReport:
    """Full debug report for a flow execution."""
    flow: str
    trace_key: str
    trace_value: str
    time_range: Optional[str] = None
    steps: list[StepResult] = field(default_factory=list)
    break_point: Optional[str] = None
    consequences: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow": self.flow,
            "trace_key": self.trace_key,
            "trace_value": self.trace_value,
            "time_range": self.time_range,
            "steps": [
                {
                    "fn": s.fn,
                    "status": s.status.value,
                    "log": s.log,
                    "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                    "note": s.note,
                    "error_handling": s.error_handling,
                }
                for s in self.steps
            ],
            "break_point": self.break_point,
            "consequences": self.consequences,
            "suggested_actions": self.suggested_actions,
        }


def _bodhi_pattern_to_regex(pattern: str) -> str:
    """Convert a @bodhi.log.* pattern with {placeholders} to a regex.

    Example: "Order {orderId} created successfully"
           → "Order .+ created successfully"
    """
    # Escape regex metacharacters except for our {placeholders}
    parts = re.split(r"\{(\w+)\}", pattern)
    regex_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Literal text — escape it
            regex_parts.append(re.escape(part))
        else:
            # Placeholder name — match any non-empty sequence
            regex_parts.append(r".+?")
    return "".join(regex_parts)


class DebugEngine:
    """Traces flow execution through logs using the knowledge graph."""

    def __init__(
        self,
        adapter: LogAdapter,
        flows: dict[str, Flow],
        functions: dict[str, FunctionDSL],
    ):
        """
        Args:
            adapter: Log source adapter for searching logs.
            flows: Flow definitions indexed by name.
            functions: Inline-tagged functions indexed by qualified name.
        """
        self.adapter = adapter
        self.flows = flows
        self.functions = functions

    def debug_flow(
        self,
        flow_name: str,
        trace_value: str,
        trace_key: Optional[str] = None,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
    ) -> DebugReport:
        """Trace a specific flow execution by correlation ID.

        Args:
            flow_name: Name of the flow to debug.
            trace_value: Value of the correlation ID (e.g. "12345").
            trace_key: Correlation field name. Defaults to flow's trace_key.
            time_from: Search window start. Defaults to 1 hour ago.
            time_to: Search window end. Defaults to now.
        """
        flow = self.flows.get(flow_name)
        if not flow:
            return DebugReport(
                flow=flow_name,
                trace_key=trace_key or "",
                trace_value=trace_value,
                steps=[],
                consequences=[f"Flow '{flow_name}' not found"],
            )

        # Resolve trace key
        if not trace_key:
            trace_key = flow.trace_key or "requestId"

        # Default time window
        if not time_to:
            time_to = datetime.utcnow()
        if not time_from:
            time_from = time_to - timedelta(hours=1)

        correlation = {trace_key: trace_value}

        # Walk each step
        step_results: list[StepResult] = []
        break_point: Optional[str] = None
        found_failure = False

        for step in flow.steps:
            result = self._check_step(step, correlation, time_from, time_to)

            # Add remote note
            if step.remote:
                proto = step.protocol or "unknown"
                if result.note:
                    result.note = f"remote call to {step.remote} via {proto} — {result.note}"
                else:
                    result.note = f"remote call to {step.remote} via {proto}"

            # Add error handling info
            if result.status == StepStatus.FAILED and step.on_fail:
                result.error_handling = "; ".join(step.on_fail)

            # Mark unreached steps after a failure
            if found_failure and result.status == StepStatus.NO_EVIDENCE:
                result.note = f"never reached — upstream step {break_point} failed"

            # Track break point
            if not found_failure and result.status in (StepStatus.FAILED, StepStatus.NO_EVIDENCE):
                if result.status == StepStatus.FAILED:
                    break_point = step.fn
                    found_failure = True

            step_results.append(result)

        # Build consequences
        consequences = self._build_consequences(flow, step_results, break_point)
        suggested_actions = self._build_suggestions(flow, step_results, break_point)

        time_range = f"{time_from.isoformat()} — {time_to.isoformat()}" if time_from else None

        return DebugReport(
            flow=flow_name,
            trace_key=trace_key,
            trace_value=trace_value,
            time_range=time_range,
            steps=step_results,
            break_point=break_point,
            consequences=consequences,
            suggested_actions=suggested_actions,
        )

    def search_logs(
        self,
        fn: Optional[str] = None,
        flow: Optional[str] = None,
        level: Optional[str] = None,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        correlation: Optional[dict[str, str]] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Graph-aware log search.

        Returns matching log entries annotated with function/flow context.
        """
        if not time_to:
            time_to = datetime.utcnow()
        if not time_from:
            time_from = time_to - timedelta(hours=1)

        # Build search pattern
        if fn:
            # Search for the function name in logs
            pattern = re.escape(fn)
            # Also try success/error patterns from inline tags
            func_dsl = self.functions.get(fn)
            if func_dsl:
                patterns = []
                patterns.append(re.escape(fn))
                for p in func_dsl.log_success + func_dsl.log_error:
                    patterns.append(_bodhi_pattern_to_regex(p))
                pattern = "|".join(patterns)
        elif flow:
            flow_def = self.flows.get(flow)
            if flow_def:
                fn_names = [re.escape(s.fn) for s in flow_def.steps]
                pattern = "|".join(fn_names)
            else:
                pattern = re.escape(flow)
        else:
            pattern = ".*"

        # Add level filter to pattern
        if level:
            # We'll filter after search
            pass

        entries = self.adapter.search(
            pattern=pattern,
            time_from=time_from,
            time_to=time_to,
            correlation=correlation,
            limit=limit,
        )

        # Filter by level
        if level:
            entries = [e for e in entries if e.level == level.upper()]

        # Annotate with graph context
        results = []
        for entry in entries:
            result: dict[str, Any] = {
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "level": entry.level,
                "message": entry.message,
                "source": entry.source,
            }

            # Try to match to a function
            matched_fn = self._match_function(entry.message)
            if matched_fn:
                result["fn"] = matched_fn
                # Find which flow this function belongs to
                for fname, fdef in self.flows.items():
                    if any(s.fn == matched_fn for s in fdef.steps):
                        result["flow"] = fname
                        break

            results.append(result)

        return results

    def _check_step(
        self,
        step: FlowStep,
        correlation: dict[str, str],
        time_from: datetime,
        time_to: datetime,
    ) -> StepResult:
        """Check log evidence for a single flow step."""
        func_dsl = self.functions.get(step.fn)

        # 1. Check success patterns
        if func_dsl:
            for pattern in func_dsl.log_success:
                regex = _bodhi_pattern_to_regex(pattern)
                entries = self.adapter.search(
                    pattern=regex,
                    time_from=time_from,
                    time_to=time_to,
                    correlation=correlation,
                    limit=1,
                )
                if entries:
                    return StepResult(
                        fn=step.fn,
                        status=StepStatus.SUCCESS,
                        log=entries[0].message,
                        timestamp=entries[0].timestamp,
                    )

        # 2. Check error patterns
        if func_dsl:
            for pattern in func_dsl.log_error:
                regex = _bodhi_pattern_to_regex(pattern)
                entries = self.adapter.search(
                    pattern=regex,
                    time_from=time_from,
                    time_to=time_to,
                    correlation=correlation,
                    limit=1,
                )
                if entries:
                    return StepResult(
                        fn=step.fn,
                        status=StepStatus.FAILED,
                        log=entries[0].message,
                        timestamp=entries[0].timestamp,
                    )

        # 3. Check function name in logs
        entries = self.adapter.search(
            pattern=re.escape(step.fn),
            time_from=time_from,
            time_to=time_to,
            correlation=correlation,
            limit=1,
        )
        if entries:
            return StepResult(
                fn=step.fn,
                status=StepStatus.PARTIAL,
                log=entries[0].message,
                timestamp=entries[0].timestamp,
                note="function name found in logs but no success/error pattern matched",
            )

        # 4. No evidence
        return StepResult(
            fn=step.fn,
            status=StepStatus.NO_EVIDENCE,
        )

    def _match_function(self, message: str) -> Optional[str]:
        """Try to match a log message to a known function name."""
        for fn_name in self.functions:
            if fn_name in message:
                return fn_name
        return None

    def _build_consequences(
        self,
        flow: Flow,
        steps: list[StepResult],
        break_point: Optional[str],
    ) -> list[str]:
        """Build consequence descriptions from the debug results."""
        consequences = []

        if not break_point:
            return consequences

        # Find succeeded steps that might need rollback
        succeeded_writes = []
        for step_result in steps:
            if step_result.status == StepStatus.SUCCESS:
                flow_step = next(
                    (s for s in flow.steps if s.fn == step_result.fn), None
                )
                if flow_step and flow_step.writes:
                    succeeded_writes.append((step_result.fn, flow_step.writes))

        if succeeded_writes:
            for fn, writes in succeeded_writes:
                consequences.append(
                    f"{fn} succeeded with writes ({', '.join(writes)}) "
                    f"but {break_point} failed — rollback may be needed"
                )

        # Check for unpublished events
        unreached_events = []
        for step_result in steps:
            if step_result.status in (StepStatus.NO_EVIDENCE, StepStatus.FAILED):
                flow_step = next(
                    (s for s in flow.steps if s.fn == step_result.fn), None
                )
                if flow_step and flow_step.emits:
                    unreached_events.extend(flow_step.emits)

        if unreached_events:
            consequences.append(
                f"events never published: {', '.join(unreached_events)} "
                f"— downstream consumers will not be triggered"
            )

        return consequences

    def _build_suggestions(
        self,
        flow: Flow,
        steps: list[StepResult],
        break_point: Optional[str],
    ) -> list[str]:
        """Build suggested actions from the debug results."""
        suggestions = []

        if not break_point:
            return suggestions

        # Suggest checking the failed step
        failed_step = next((s for s in flow.steps if s.fn == break_point), None)
        if failed_step:
            if failed_step.remote:
                suggestions.append(
                    f"check {failed_step.remote} health — "
                    f"remote call via {failed_step.protocol or 'unknown'} failed"
                )
            if failed_step.on_fail:
                suggestions.append(
                    f"check error handling: {'; '.join(failed_step.on_fail)}"
                )

        return suggestions
