"""
Bodhi CLI — validate Bodhi DSL completeness and consistency.

Usage:
    bodhi validate [<path>]    Check DSL completeness and consistency
    bodhi stats [<path>]       Show coverage statistics
    bodhi derive [<path>]      Derive Layer 2 YAML files from inline tags
"""

import argparse
import json
import sys
from pathlib import Path

from ..parser import parse_directory, load_bodhi_dir
from ..validator.checker import validate, format_report
from ..deriver import derive_and_write


def cmd_validate(project_root: Path):
    issues = validate(project_root)
    print(format_report(issues))
    sys.exit(1 if any(i.severity.value == "error" for i in issues) else 0)


def cmd_stats(project_root: Path):
    functions = parse_directory(project_root)

    bodhi_dir = project_root / ".bodhi"
    dsl = load_bodhi_dir(bodhi_dir) if bodhi_dir.is_dir() else None

    stats = {
        "functions_with_bodhi_tags": len(functions),
        "functions_with_intent": sum(1 for f in functions if f.intent),
        "functions_with_reads": sum(1 for f in functions if f.reads),
        "functions_with_writes": sum(1 for f in functions if f.writes),
        "functions_with_calls": sum(1 for f in functions if f.calls),
        "functions_with_emits": sum(1 for f in functions if f.emits),
        "functions_with_on_fail": sum(1 for f in functions if f.on_fail),
    }

    if dsl:
        stats["flows"] = len(dsl["flows"])
        stats["entities"] = len(dsl["entities"])
        stats["state_machines"] = len(dsl["states"])
        stats["concepts"] = len(dsl["concepts"])

    print(json.dumps(stats, indent=2))


def cmd_derive(project_root: Path):
    summary = derive_and_write(project_root)
    total = summary["flows"] + summary["events"] + summary["services"]
    if total == 0:
        print("No inline tags found to derive from.")
        sys.exit(0)
    print(f"Derived {summary['flows']} flows, {summary['events']} events, {summary['services']} service dependencies")
    print(f"Output: {project_root / '.bodhi'}")


def main():
    parser = argparse.ArgumentParser(
        prog="bodhi",
        description="Bodhi DSL — validate and inspect your code's semantic annotations.",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_validate = subparsers.add_parser("validate", help="Check DSL completeness and consistency")
    p_validate.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_stats = subparsers.add_parser("stats", help="Show coverage statistics")
    p_stats.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_derive = subparsers.add_parser("derive", help="Derive Layer 2 YAML files from inline tags")
    p_derive.add_argument("path", nargs="?", default=".", help="Project root directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    project_root = Path(args.path).resolve()

    if args.command == "validate":
        cmd_validate(project_root)
    elif args.command == "stats":
        cmd_stats(project_root)
    elif args.command == "derive":
        cmd_derive(project_root)


if __name__ == "__main__":
    main()
