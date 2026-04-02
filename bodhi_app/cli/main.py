"""
Bodhi CLI — validate Bodhi DSL completeness and consistency.

Usage:
    bodhi validate [<path>]    Check DSL completeness and consistency
    bodhi check [<path>]       Check inline tags vs YAML consistency
    bodhi stats [<path>]       Show coverage statistics
    bodhi derive [<path>]      Derive Layer 2 YAML files from inline tags (scaffold)
    bodhi graph [<path>]       Generate Mermaid diagrams from flows
    bodhi serve [<path>]       Start MCP server for AI coding assistants
"""

import argparse
import json
import sys
from pathlib import Path

from bodhi_engine.parser import parse_directory, load_bodhi_dir
from bodhi_engine.validator.checker import validate, format_report
from bodhi_engine.deriver import scaffold, validate_consistency
from bodhi_app.cli.graph import cmd_graph


def cmd_validate(project_root: Path, exclude_dirs: set[str] | None = None):
    issues = validate(project_root, exclude_dirs=exclude_dirs)
    print(format_report(issues))
    sys.exit(1 if any(i.severity.value == "error" for i in issues) else 0)


def cmd_check(project_root: Path, exclude_dirs: set[str] | None = None):
    """Check consistency between inline tags and .bodhi/ YAML files."""
    report = validate_consistency(project_root, exclude_dirs=exclude_dirs)
    print(report.summary())
    sys.exit(0 if report.is_consistent else 1)


def cmd_stats(project_root: Path, exclude_dirs: set[str] | None = None):
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)

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
        stats["channels"] = len(dsl.get("channels", []))
        stats["topologies"] = len(dsl.get("topologies", []))

    print(json.dumps(stats, indent=2))


def cmd_derive(project_root: Path, exclude_dirs: set[str] | None = None):
    summary = scaffold(project_root, exclude_dirs=exclude_dirs)
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
    parser.add_argument(
        "--exclude", nargs="+", metavar="DIR",
        help="Directory names to exclude from scanning (e.g. --exclude frontend admin-ui)",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_validate = subparsers.add_parser("validate", help="Check DSL completeness and consistency")
    p_validate.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_check = subparsers.add_parser("check", help="Check inline tags vs YAML consistency")
    p_check.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_stats = subparsers.add_parser("stats", help="Show coverage statistics")
    p_stats.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_derive = subparsers.add_parser("derive", help="Scaffold Layer 2 YAML files from inline tags")
    p_derive.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_graph = subparsers.add_parser("graph", help="Generate Mermaid diagrams from flows")
    p_graph.add_argument("path", nargs="?", default=".", help="Project root directory")
    p_graph.add_argument("--flow", metavar="NAME", help="Only graph a specific flow")
    p_graph.add_argument("-o", "--output", metavar="FILE", help="Render to file (svg/png/pdf) via mmdc")

    p_serve = subparsers.add_parser("serve", help="Start MCP server for AI coding assistants")
    p_serve.add_argument("path", nargs="?", default=".", help="Project root directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    project_root = Path(args.path).resolve()
    exclude_dirs = set(args.exclude) if args.exclude else None

    if args.command == "validate":
        cmd_validate(project_root, exclude_dirs)
    elif args.command == "check":
        cmd_check(project_root, exclude_dirs)
    elif args.command == "stats":
        cmd_stats(project_root, exclude_dirs)
    elif args.command == "derive":
        cmd_derive(project_root, exclude_dirs)
    elif args.command == "graph":
        cmd_graph(project_root, flow_name=args.flow, output=args.output)
    elif args.command == "serve":
        from bodhi_app.mcp.server import mcp, init_knowledge
        init_knowledge(project_root, exclude_dirs=exclude_dirs)
        print(f"Bodhi MCP server starting for {project_root}", file=sys.stderr)
        mcp.run()


if __name__ == "__main__":
    main()
