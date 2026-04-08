"""
Compute an AI-friendliness score for a Bodhi project.

The score is a weighted combination of five dimensions, each scored out of 20:
  - intent_coverage:      how many tagged functions declare @bodhi.intent
  - dataflow_completeness: how many intent-bearing functions declare reads/writes
  - error_handling:       how many write/remote-call functions declare @bodhi.on_fail
  - call_chain_traceability: how many @bodhi.calls targets resolve to tagged functions
  - structural_health:    penalties for overloading, dangling impls, missing intents

Each dimension produces a (score, max, reasons) triple so the output can
explain itself. The score is meant as a product-visible indicator for how
easy the codebase is for AI to reason about — low scores point at concrete
things to fix, not vague complaints.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bodhi_engine.parser import load_bodhi_dir, parse_directory
from bodhi_engine.validator.checker import validate, Severity


DIMENSION_MAX = 20
NUM_DIMENSIONS = 5
TOTAL_MAX = DIMENSION_MAX * NUM_DIMENSIONS  # 100


@dataclass
class Dimension:
    name: str
    score: int
    max: int = DIMENSION_MAX
    reasons: list[str] = field(default_factory=list)
    # Concrete offending items (qualified_name + location), exposed in
    # --verbose and --json output so users can jump straight to the fix.
    offenders: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "max": self.max,
            "reasons": list(self.reasons),
            "offenders": list(self.offenders),
        }


@dataclass
class ScoreReport:
    total: int
    max: int
    dimensions: list[Dimension]

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "max": self.max,
            "dimensions": [d.as_dict() for d in self.dimensions],
        }


def _ratio_to_score(numerator: int, denominator: int) -> int:
    """Scale a ratio to an integer out of DIMENSION_MAX. Empty → full score."""
    if denominator == 0:
        return DIMENSION_MAX
    return round(DIMENSION_MAX * numerator / denominator)


def _is_remote_call(call_value: str) -> bool:
    return " via " in call_value


def _fn_location(fn, project_root: Path) -> str:
    """Return 'Class.method (relative/path.java:42)' for an offender line."""
    try:
        rel = Path(fn.file_path).resolve().relative_to(project_root.resolve())
    except ValueError:
        rel = Path(fn.file_path).name
    return f"{fn.qualified_name} ({rel}:{fn.line_number})"


def compute_score(project_root: Path, exclude_dirs: set[str] | None = None) -> ScoreReport:
    """Compute the AI-friendliness score for a project."""
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)
    bodhi_dir = project_root / ".bodhi"
    _dsl = load_bodhi_dir(bodhi_dir) if bodhi_dir.is_dir() else None
    issues = validate(project_root, exclude_dirs=exclude_dirs)

    # --- Dimension 1: intent coverage ---
    total_fns = len(functions)
    with_intent = sum(1 for f in functions if f.intent)
    missing_intent_fns = [f for f in functions if not f.intent]
    d1 = Dimension(
        name="Intent coverage",
        score=_ratio_to_score(with_intent, total_fns),
    )
    if missing_intent_fns:
        d1.reasons.append(f"{len(missing_intent_fns)} tagged function(s) missing @bodhi.intent")
        d1.offenders = [_fn_location(f, project_root) for f in missing_intent_fns]

    # --- Dimension 2: data-flow completeness ---
    # Functions with intent should also declare at least one of reads/writes
    # so data flow can be reconstructed.
    intent_fns = [f for f in functions if f.intent]
    intent_with_flow = sum(1 for f in intent_fns if f.reads or f.writes)
    intent_without_flow_fns = [f for f in intent_fns if not (f.reads or f.writes)]
    d2 = Dimension(
        name="Data-flow completeness",
        score=_ratio_to_score(intent_with_flow, len(intent_fns)),
    )
    if intent_without_flow_fns:
        d2.reasons.append(
            f"{len(intent_without_flow_fns)} function(s) have @bodhi.intent but no @bodhi.reads/@bodhi.writes"
        )
        d2.offenders = [_fn_location(f, project_root) for f in intent_without_flow_fns]

    # --- Dimension 3: error handling coverage ---
    # Functions that write to storage or make remote calls should declare
    # @bodhi.on_fail — silent failure modes are opaque to AI.
    risky_fns = []
    for f in functions:
        has_writes = bool(f.writes)
        has_remote = any(_is_remote_call(c) for c in f.get_tags("calls"))
        if has_writes or has_remote:
            risky_fns.append(f)
    risky_with_on_fail = sum(1 for f in risky_fns if f.on_fail)
    risky_without_fns = [f for f in risky_fns if not f.on_fail]
    d3 = Dimension(
        name="Error handling",
        score=_ratio_to_score(risky_with_on_fail, len(risky_fns)),
    )
    if risky_without_fns:
        d3.reasons.append(
            f"{len(risky_without_fns)} function(s) with writes/remote-calls missing @bodhi.on_fail"
        )
        d3.offenders = [_fn_location(f, project_root) for f in risky_without_fns]

    # --- Dimension 4: call-chain traceability ---
    # Every local @bodhi.calls target should resolve to a tagged function.
    # Remote calls (with "via <protocol>") are exempt — the via annotation
    # makes the boundary explicit and the target lives in another service.
    fn_names = {f.qualified_name for f in functions}
    total_calls = 0
    unresolved: list[tuple[str, object]] = []  # (target, caller fn)
    for f in functions:
        for raw in f.get_tags("calls"):
            for piece in raw.split(","):
                piece = piece.strip()
                if not piece:
                    continue
                total_calls += 1
                if _is_remote_call(piece):
                    continue
                if piece not in fn_names:
                    unresolved.append((piece, f))
    resolved = total_calls - len(unresolved)
    d4 = Dimension(
        name="Call-chain traceability",
        score=_ratio_to_score(resolved, total_calls),
    )
    if unresolved:
        d4.reasons.append(
            f"{len(unresolved)} @bodhi.calls target(s) have no inline tags (dangling)"
        )
        d4.offenders = [
            f"{target}  ← called from {_fn_location(caller, project_root)}"
            for target, caller in unresolved
        ]

    # --- Dimension 5: structural health ---
    # Start at max; deduct for anti-patterns surfaced by the validator.
    overloading = [i for i in issues if i.rule == "method-overloading"]
    dangling_impl = [i for i in issues if i.rule == "implements-missing-interface"]
    missing_intent_errors = [i for i in issues if i.rule == "missing-intent"]

    penalty = 0
    penalty += min(len(overloading) * 5, 15)        # overloading is the worst
    penalty += min(len(dangling_impl) * 3, 9)
    penalty += min(len(missing_intent_errors) * 2, 10)
    penalty = min(penalty, DIMENSION_MAX)

    d5 = Dimension(
        name="Structural health",
        score=DIMENSION_MAX - penalty,
    )
    if overloading:
        d5.reasons.append(f"{len(overloading)} method(s) overloaded (violates Bodhi ClassName.methodName identity)")
        # Keep the "(N tagged implementations at file.java:12, file.java:20)"
        # part — that's how users find the methods to rename.
        d5.offenders.extend(f"[overload] {i.message.split('). ')[0]})" for i in overloading)
    if dangling_impl:
        d5.reasons.append(f"{len(dangling_impl)} @bodhi.implements target(s) missing tags")
        d5.offenders.extend(f"[dangling-impl] {i.location}" for i in dangling_impl)
    if missing_intent_errors:
        d5.reasons.append(f"{len(missing_intent_errors)} function(s) write/read data but lack @bodhi.intent")
        d5.offenders.extend(f"[missing-intent] {i.location}" for i in missing_intent_errors)

    dimensions = [d1, d2, d3, d4, d5]
    total = sum(d.score for d in dimensions)
    return ScoreReport(total=total, max=TOTAL_MAX, dimensions=dimensions)


# ── Terminal rendering ─────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"


def _color_for(score: int, max_score: int) -> str:
    ratio = score / max_score if max_score else 1.0
    if ratio >= 0.8:
        return _GREEN
    if ratio >= 0.5:
        return _YELLOW
    return _RED


def _progress_bar(score: int, max_score: int, width: int = 20) -> str:
    filled = round(width * score / max_score) if max_score else width
    return "█" * filled + "░" * (width - filled)


def format_report(report: ScoreReport, color: bool = True, verbose: bool = False) -> str:
    def wrap(text: str, *codes: str) -> str:
        if not color or not codes:
            return text
        return f"{''.join(codes)}{text}{_RESET}"

    lines = []
    total_color = _color_for(report.total, report.max)
    header = f"Bodhi AI Score: {report.total} / {report.max}"
    lines.append(wrap(header, _BOLD, total_color))
    lines.append("")

    name_width = max(len(d.name) for d in report.dimensions)
    for d in report.dimensions:
        col = _color_for(d.score, d.max)
        bar = _progress_bar(d.score, d.max)
        score_txt = f"{d.score:>2}/{d.max}"
        lines.append(
            f"  {d.name.ljust(name_width)}  {wrap(bar, col)}  {wrap(score_txt, col)}"
        )
        for reason in d.reasons:
            lines.append(f"  {' ' * name_width}  {wrap('↳ ' + reason, _DIM)}")
        if verbose and d.offenders:
            for off in d.offenders:
                lines.append(f"  {' ' * name_width}  {wrap('  • ' + off, _DIM)}")

    return "\n".join(lines)


def cmd_score(
    project_root: Path,
    exclude_dirs: set[str] | None = None,
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    report = compute_score(project_root, exclude_dirs=exclude_dirs)

    if json_output:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_report(report, color=sys.stdout.isatty(), verbose=verbose))

    # Exit code: 0 if passing (≥60), 1 otherwise — usable as a CI gate.
    sys.exit(0 if report.total >= 60 else 1)
