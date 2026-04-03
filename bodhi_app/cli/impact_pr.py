"""
bodhi impact-pr — Analyse a git diff and produce a PR impact report.

Takes a base..head range (or reads stdin for a raw diff) and traces
changed functions through the Bodhi knowledge graph to produce a
Markdown impact analysis.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bodhi_engine.knowledge import BodhiKnowledge
from bodhi_engine.parser.inline import (
    FunctionDSL, FUNCTION_PATTERNS, CLASS_PATTERNS,
    parse_file,
)


# ── diff parsing ────────────────────────────────────────────────────

@dataclass
class ChangedHunk:
    """A contiguous range of changed lines in a file."""
    start: int  # 1-based line number
    count: int

    @property
    def end(self) -> int:
        return self.start + max(self.count - 1, 0)


@dataclass
class ChangedFile:
    path: str
    hunks: list[ChangedHunk] = field(default_factory=list)


_DIFF_FILE_RE = re.compile(r"^diff --git a/.+ b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff_text: str) -> list[ChangedFile]:
    """Parse unified diff text into a list of ChangedFile objects."""
    files: list[ChangedFile] = []
    current: ChangedFile | None = None

    for line in diff_text.splitlines():
        file_match = _DIFF_FILE_RE.match(line)
        if file_match:
            current = ChangedFile(path=file_match.group(1))
            files.append(current)
            continue

        if current is None:
            continue

        hunk_match = _HUNK_RE.match(line)
        if hunk_match:
            start = int(hunk_match.group(1))
            count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
            current.hunks.append(ChangedHunk(start=start, count=count))

    return files


def get_git_diff(project_root: Path, base: str, head: str) -> str:
    """Run git diff between base and head."""
    result = subprocess.run(
        ["git", "diff", f"{base}...{head}"],
        capture_output=True, text=True,
        cwd=project_root,
    )
    if result.returncode != 0:
        # Fallback: try without triple-dot (for uncommitted changes)
        result = subprocess.run(
            ["git", "diff", base, head],
            capture_output=True, text=True,
            cwd=project_root,
        )
    return result.stdout


def get_git_diff_uncommitted(project_root: Path) -> str:
    """Get diff of uncommitted changes (staged + unstaged)."""
    result = subprocess.run(
        ["git", "diff", "HEAD"],
        capture_output=True, text=True,
        cwd=project_root,
    )
    return result.stdout


# ── function matching ───────────────────────────────────────────────

def find_changed_functions(
    project_root: Path,
    changed_files: list[ChangedFile],
    all_functions: list[FunctionDSL],
) -> list[FunctionDSL]:
    """Find bodhi-annotated functions that overlap with changed hunks."""
    changed: list[FunctionDSL] = []
    seen: set[str] = set()

    # Index functions by file path (relative)
    fn_by_file: dict[str, list[FunctionDSL]] = {}
    for fn in all_functions:
        # Normalise to relative path
        rel = fn.file_path
        try:
            rel = str(Path(fn.file_path).relative_to(project_root))
        except ValueError:
            pass
        fn_by_file.setdefault(rel, []).append(fn)

    for cf in changed_files:
        fns = fn_by_file.get(cf.path, [])
        if not fns:
            continue

        for fn in fns:
            if fn.qualified_name in seen:
                continue
            # Check if any hunk overlaps with the function's location.
            # We use a generous window: function line ± 30 lines to
            # account for the function body.
            fn_line = fn.line_number
            for hunk in cf.hunks:
                if _ranges_overlap(hunk.start, hunk.end, max(1, fn_line - 5), fn_line + 30):
                    changed.append(fn)
                    seen.add(fn.qualified_name)
                    break

    return changed


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


# ── impact tracing ──────────────────────────────────────────────────

@dataclass
class PRImpact:
    """Aggregated impact data for the entire PR."""
    changed_functions: list[FunctionDSL]
    affected_flows: list[dict[str, Any]]
    data_reads: list[dict[str, str]]
    data_writes: list[dict[str, str]]
    event_impacts: list[dict[str, Any]]
    cross_service_deps: list[dict[str, str]]
    state_machine_impacts: list[str]
    risks: list[str]


def trace_pr_impact(kb: BodhiKnowledge, changed_fns: list[FunctionDSL]) -> PRImpact:
    """Trace full impact chain from changed functions through the knowledge graph."""
    affected_flows: list[dict[str, Any]] = []
    data_reads: list[dict[str, str]] = []
    data_writes: list[dict[str, str]] = []
    event_impacts: list[dict[str, Any]] = []
    cross_service_deps: list[dict[str, str]] = []
    state_machine_impacts: list[str] = []
    risks: list[str] = []

    seen_flows: set[str] = set()
    seen_reads: set[str] = set()
    seen_writes: set[str] = set()
    seen_events: set[str] = set()
    seen_deps: set[str] = set()
    seen_sm: set[str] = set()

    for fn in changed_fns:
        # 1. Find affected flows
        for flow_name, flow in kb._flow_by_name.items():
            for step in flow.steps:
                if fn.qualified_name == step.fn or fn.function_name == step.fn.split(".")[-1]:
                    if flow_name not in seen_flows:
                        seen_flows.add(flow_name)
                        entry_desc = ""
                        if flow.entry_type and flow.entry_path:
                            method = f"{flow.entry_method} " if flow.entry_method else ""
                            entry_desc = f"{method}{flow.entry_path}"
                        affected_flows.append({
                            "name": flow_name,
                            "entry_type": flow.entry_type or "",
                            "entry_desc": entry_desc,
                        })

        # 2. Collect data reads/writes from inline tags
        for r in fn.reads:
            key = f"{fn.qualified_name}:{r}"
            if key not in seen_reads:
                seen_reads.add(key)
                data_reads.append({"fn": fn.qualified_name, "detail": r})

        for w in fn.writes:
            key = f"{fn.qualified_name}:{w}"
            if key not in seen_writes:
                seen_writes.add(key)
                data_writes.append({"fn": fn.qualified_name, "detail": w})

        # Also collect from flow steps
        for flow_name in seen_flows:
            flow = kb._flow_by_name.get(flow_name)
            if not flow:
                continue
            for step in flow.steps:
                for r in step.reads:
                    key = f"{step.fn}:{r}"
                    if key not in seen_reads:
                        seen_reads.add(key)
                        data_reads.append({"fn": step.fn, "detail": r})
                for w in step.writes:
                    key = f"{step.fn}:{w}"
                    if key not in seen_writes:
                        seen_writes.add(key)
                        data_writes.append({"fn": step.fn, "detail": w})

        # 3. Event impacts
        for emit_str in fn.emits:
            event_name = _extract_event_name(emit_str)
            if event_name and event_name not in seen_events:
                seen_events.add(event_name)
                evt_info = kb.find_consumers(event_name)
                event_impacts.append({
                    "name": event_name,
                    "raw": emit_str,
                    "channel": evt_info.get("channel", ""),
                    "consumers": evt_info.get("consumers", []),
                })

        # Also check events from flows
        for flow_name in seen_flows:
            flow = kb._flow_by_name.get(flow_name)
            if not flow:
                continue
            for evt_name in (flow.events or []):
                if evt_name not in seen_events:
                    seen_events.add(evt_name)
                    evt_info = kb.find_consumers(evt_name)
                    event_impacts.append({
                        "name": evt_name,
                        "raw": evt_name,
                        "channel": evt_info.get("channel", ""),
                        "consumers": evt_info.get("consumers", []),
                    })

        # 4. Cross-service dependencies
        for call_str in fn.calls:
            # Check if this is a remote call
            for flow_name in seen_flows:
                flow = kb._flow_by_name.get(flow_name)
                if not flow:
                    continue
                for step in flow.steps:
                    if step.remote and step.remote not in seen_deps:
                        seen_deps.add(step.remote)
                        protocol = step.protocol or "unknown"
                        api = step.api or step.fn
                        cross_service_deps.append({
                            "service": step.remote,
                            "protocol": protocol,
                            "api": api,
                        })

        # Also gather service deps from service YAML
        for svc in kb.dsl["services"]:
            for dep in svc.depends_on:
                if dep.service not in seen_deps:
                    # Check if any affected flow references this dependency
                    for flow_name in seen_flows:
                        flow = kb._flow_by_name.get(flow_name)
                        if not flow:
                            continue
                        for step in flow.steps:
                            if step.remote == dep.service:
                                seen_deps.add(dep.service)
                                cross_service_deps.append({
                                    "service": dep.service,
                                    "protocol": dep.protocol or dep.type or "unknown",
                                    "api": ", ".join(dep.apis) if dep.apis else "",
                                    "resilience": dep.resilience or "",
                                })
                                break

        # 5. State machine impacts
        impact = kb.impact_analysis(fn.qualified_name)
        for sm_name in impact.get("affected_state_machines", []):
            if sm_name not in seen_sm:
                seen_sm.add(sm_name)
                state_machine_impacts.append(sm_name)

    # 6. Generate risks
    risks = _assess_risks(event_impacts, cross_service_deps, state_machine_impacts, changed_fns)

    return PRImpact(
        changed_functions=changed_fns,
        affected_flows=affected_flows,
        data_reads=data_reads,
        data_writes=data_writes,
        event_impacts=event_impacts,
        cross_service_deps=cross_service_deps,
        state_machine_impacts=state_machine_impacts,
        risks=risks,
    )


def _extract_event_name(emit_str: str) -> str | None:
    """Extract event name from @bodhi.emits value like 'order_created(orderId) to kafka:topic'."""
    match = re.match(r"(\w+)", emit_str)
    return match.group(1) if match else None


def _assess_risks(
    event_impacts: list[dict],
    cross_service_deps: list[dict],
    state_machines: list[str],
    changed_fns: list[FunctionDSL],
) -> list[str]:
    """Heuristic risk assessment based on impact data."""
    risks: list[str] = []

    for evt in event_impacts:
        consumers = evt.get("consumers", [])
        if len(consumers) > 0:
            risks.append(
                f"`{evt['name']}` event schema change will affect "
                f"{len(consumers)} downstream consumer(s)"
            )

    for dep in cross_service_deps:
        resilience = dep.get("resilience", "")
        if resilience:
            risks.append(
                f"`{dep['service']}` call via {dep['protocol']} has resilience config "
                f"— verify timeout handling"
            )
        else:
            if dep.get("protocol") in ("grpc", "http"):
                risks.append(
                    f"`{dep['service']}` remote call via {dep['protocol']} "
                    f"— no resilience config found"
                )

    for sm in state_machines:
        risks.append(f"State machine `{sm}` may be affected — verify transition correctness")

    # Check for on_fail handlers
    for fn in changed_fns:
        if not fn.on_fail and (fn.calls or fn.emits):
            risks.append(
                f"`{fn.qualified_name}` has external calls/events but no `@bodhi.on_fail` handler"
            )

    return risks


# ── markdown rendering ──────────────────────────────────────────────

def render_markdown(impact: PRImpact) -> str:
    """Render PRImpact as a Markdown comment suitable for a GitHub PR."""
    sections: list[str] = []
    sections.append("## Bodhi Impact Analysis\n")

    # Changed functions
    if impact.changed_functions:
        sections.append("### Changed functions")
        for fn in impact.changed_functions:
            intent = f" — {fn.intent}" if fn.intent else ""
            sections.append(f"- `{fn.qualified_name}` (modified){intent}")
        sections.append("")

    # Affected flows
    if impact.affected_flows:
        sections.append("### Affected flows")
        for flow in impact.affected_flows:
            entry = f" ({flow['entry_desc']})" if flow["entry_desc"] else ""
            entry_note = " — this is the entry point" if flow["entry_type"] else ""
            sections.append(f"- `{flow['name']}`{entry}{entry_note}")
        sections.append("")

    # Data impact
    if impact.data_reads or impact.data_writes:
        sections.append("### Data impact")
        for w in impact.data_writes:
            sections.append(f"- Writes to: `{w['detail']}`")
        for r in impact.data_reads:
            sections.append(f"- Reads from: `{r['detail']}`")
        sections.append("")

    # Event impact
    if impact.event_impacts:
        sections.append("### Event impact")
        for evt in impact.event_impacts:
            channel = f" → {evt['channel']}" if evt["channel"] else ""
            sections.append(f"- Produces: `{evt['name']}`{channel}")
            for consumer in evt.get("consumers", []):
                fn_name = consumer.get("fn", "unknown")
                flow = consumer.get("flow", "")
                flow_note = f" (flow: {flow})" if flow else ""
                sections.append(f"  - Consumed by: `{fn_name}`{flow_note}")
        sections.append("")

    # Cross-service dependencies
    if impact.cross_service_deps:
        sections.append("### Cross-service dependencies")
        for dep in impact.cross_service_deps:
            api = f" ({dep['api']})" if dep.get("api") else ""
            sections.append(f"- Calls: `{dep['service']}` via {dep['protocol']}{api}")
        sections.append("")

    # State machine impacts
    if impact.state_machine_impacts:
        sections.append("### State machine impacts")
        for sm in impact.state_machine_impacts:
            sections.append(f"- `{sm}`")
        sections.append("")

    # Risks
    if impact.risks:
        sections.append("### Risks")
        for risk in impact.risks:
            sections.append(f"- {risk}")
        sections.append("")

    # If nothing was found
    if not any([
        impact.changed_functions, impact.affected_flows,
        impact.data_reads, impact.data_writes,
        impact.event_impacts, impact.cross_service_deps,
        impact.state_machine_impacts,
    ]):
        sections.append("No Bodhi-annotated functions were changed in this PR.")

    return "\n".join(sections).rstrip() + "\n"


# ── CLI entry point ─────────────────────────────────────────────────

def cmd_impact_pr(
    project_root: Path,
    base: str | None = None,
    head: str | None = None,
    diff_text: str | None = None,
    exclude_dirs: set[str] | None = None,
) -> str:
    """Run the full impact-pr pipeline. Returns markdown string."""
    # 1. Get diff
    if diff_text is not None:
        raw_diff = diff_text
    elif base and head:
        raw_diff = get_git_diff(project_root, base, head)
    elif base:
        raw_diff = get_git_diff(project_root, base, "HEAD")
    else:
        raw_diff = get_git_diff_uncommitted(project_root)

    if not raw_diff.strip():
        return "## Bodhi Impact Analysis\n\nNo changes detected.\n"

    # 2. Parse diff
    changed_files = parse_diff(raw_diff)
    if not changed_files:
        return "## Bodhi Impact Analysis\n\nNo source file changes detected.\n"

    # 3. Build knowledge graph
    kb = BodhiKnowledge(project_root, exclude_dirs=exclude_dirs)

    # 4. Match changed functions
    changed_fns = find_changed_functions(project_root, changed_files, kb.functions)

    # 5. Trace impact
    impact = trace_pr_impact(kb, changed_fns)

    # 6. Render
    return render_markdown(impact)
