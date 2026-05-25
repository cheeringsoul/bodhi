"""
Bodhi CLI — validate Bodhi DSL completeness and consistency.

Usage:
    bodhi validate [<path>]    Check DSL completeness and consistency
    bodhi check [<path>]       Check inline tags vs YAML consistency
    bodhi stats [<path>]       Show coverage statistics
    bodhi score [<path>]       Compute AI-friendliness score (weighted, 0-100)
    bodhi derive [<path>]      Derive Layer 2 YAML files from inline tags (scaffold)
    bodhi graph [<path>]       Generate Mermaid diagrams from flows
    bodhi arch [<path>]        Visualize service topology in the terminal
    bodhi show flow [<name>]   Visualize a flow's call chain (terminal)
    bodhi show stats           Coverage dashboard (terminal)
    bodhi serve [<path>]       Start MCP server for AI coding assistants
    bodhi impact-pr [<path>]   Analyse git diff and produce PR impact report
    bodhi web [<path>]         Start web dashboard (http://127.0.0.1:8500)
"""

import argparse
import json
import sys
from pathlib import Path

from bodhi_engine.parser import parse_directory, load_bodhi_dir
from bodhi_engine.validator.checker import validate, format_report
from bodhi_engine.deriver import scaffold, validate_consistency
from bodhi_engine.cli.graph import cmd_graph
from bodhi_engine.cli.score import cmd_score
from bodhi_engine.cli.show import cmd_show_flow, cmd_show_stats
from bodhi_engine.cli.arch import cmd_arch
from bodhi_app.cli.impact_pr import cmd_impact_pr


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

    p_score = subparsers.add_parser(
        "score",
        help="Compute AI-friendliness score (5 weighted dimensions, 0-100)",
    )
    p_score.add_argument("path", nargs="?", default=".", help="Project root directory")
    p_score.add_argument("--json", action="store_true", help="Output as JSON for CI integration")
    p_score.add_argument("--verbose", "-v", action="store_true", help="List offending functions under each dimension")

    p_derive = subparsers.add_parser("derive", help="Scaffold Layer 2 YAML files from inline tags")
    p_derive.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_graph = subparsers.add_parser("graph", help="Generate Mermaid diagrams from flows")
    p_graph.add_argument("path", nargs="?", default=".", help="Project root directory")
    p_graph.add_argument("--flow", metavar="NAME", help="Only graph a specific flow")
    p_graph.add_argument("-o", "--output", metavar="FILE", help="Render to file (svg/png/pdf) via mmdc")

    p_arch = subparsers.add_parser("arch", help="Visualize service topology in the terminal")
    p_arch.add_argument("path", nargs="?", default=".", help="Project root directory")

    # show subcommand with nested subparsers
    p_show = subparsers.add_parser("show", help="Terminal visualization of Bodhi DSL data")
    p_show.add_argument("-p", "--path", default=".", help="Project root directory")
    show_sub = p_show.add_subparsers(dest="show_command")

    p_show_flow = show_sub.add_parser("flow", help="Visualize a flow's call chain")
    p_show_flow.add_argument("flow_name", nargs="?", default=None, help="Flow name (omit to list all)")

    show_sub.add_parser("stats", help="Coverage dashboard")

    p_serve = subparsers.add_parser("serve", help="Start MCP server for AI coding assistants")
    p_serve.add_argument("path", nargs="?", default=".", help="Project root directory")

    p_serve_all = subparsers.add_parser(
        "serve-all",
        help="Start federated MCP server for a workspace with multiple services",
    )
    p_serve_all.add_argument("path", nargs="?", default=".", help="Workspace directory containing service repos")

    p_impact = subparsers.add_parser(
        "impact-pr",
        help="Analyse a git diff and produce a PR impact report",
    )
    p_impact.add_argument("path", nargs="?", default=".", help="Project root directory")
    p_impact.add_argument("--base", metavar="REF", help="Base git ref (e.g. main, HEAD~3)")
    p_impact.add_argument("--head", metavar="REF", help="Head git ref (default: HEAD)")

    p_web = subparsers.add_parser("web", help="Start web dashboard")
    p_web.add_argument("path", nargs="?", default=".", help="Project root directory")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind address")
    p_web.add_argument("--port", type=int, default=8500, help="Port number")

    p_workspace_validate = subparsers.add_parser(
        "workspace-validate",
        help="Validate cross-service consistency in a workspace",
    )
    p_workspace_validate.add_argument("path", nargs="?", default=".", help="Workspace directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    project_root = Path(args.path).resolve()
    exclude_dirs = set(args.exclude) if args.exclude else None

    if args.command == "show":
        if args.show_command == "flow":
            cmd_show_flow(project_root, flow_name=args.flow_name, exclude_dirs=exclude_dirs)
        elif args.show_command == "stats":
            cmd_show_stats(project_root, exclude_dirs=exclude_dirs)
        else:
            p_show.print_help()
        sys.exit(0)
    elif args.command == "validate":
        cmd_validate(project_root, exclude_dirs)
    elif args.command == "check":
        cmd_check(project_root, exclude_dirs)
    elif args.command == "stats":
        cmd_stats(project_root, exclude_dirs)
    elif args.command == "score":
        cmd_score(project_root, exclude_dirs=exclude_dirs, json_output=args.json, verbose=args.verbose)
    elif args.command == "derive":
        cmd_derive(project_root, exclude_dirs)
    elif args.command == "graph":
        cmd_graph(project_root, flow_name=args.flow, output=args.output)
    elif args.command == "arch":
        cmd_arch(project_root, exclude_dirs=exclude_dirs)
    elif args.command == "serve":
        from bodhi_app.mcp.server import mcp, init_knowledge
        init_knowledge(project_root, exclude_dirs=exclude_dirs)
        print(f"Bodhi MCP server starting for {project_root}", file=sys.stderr)
        mcp.run()
    elif args.command == "serve-all":
        from bodhi_app.mcp.workspace_server import workspace_mcp, init_workspace
        ws_result = init_workspace(project_root)
        if ws_result.has_errors():
            print("Cross-service validation errors found:", file=sys.stderr)
            print(ws_result.format_issues(), file=sys.stderr)
            sys.exit(1)
        if ws_result.issues:
            print(ws_result.format_issues(), file=sys.stderr)
        services = ", ".join(ws_result.service_data.keys())
        print(f"Bodhi workspace MCP server starting — services: {services}", file=sys.stderr)
        workspace_mcp.run()
    elif args.command == "impact-pr":
        import sys as _sys
        stdin_text = None
        if not _sys.stdin.isatty():
            stdin_text = _sys.stdin.read()
        md = cmd_impact_pr(
            project_root,
            base=args.base,
            head=args.head,
            diff_text=stdin_text if stdin_text else None,
            exclude_dirs=exclude_dirs,
        )
        print(md)
    elif args.command == "web":
        from bodhi_app.web.app import run_server
        run_server(project_root, host=args.host, port=args.port)
    elif args.command == "workspace-validate":
        from bodhi_engine.workspace import load_workspace
        ws_result = load_workspace(project_root)
        services = list(ws_result.service_data.keys())
        print(f"Services found: {', '.join(services)}")
        print(f"Flows: {len(ws_result.all_flows)}")
        print(f"Events: {len(ws_result.all_events)}")
        print(f"Services: {len(ws_result.all_services)}")
        print()
        print(ws_result.format_issues())
        sys.exit(1 if ws_result.has_errors() else 0)


if __name__ == "__main__":
    main()
