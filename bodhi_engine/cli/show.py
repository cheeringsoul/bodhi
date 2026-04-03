"""
bodhi show — terminal visualization for Bodhi DSL knowledge.

Subcommands:
    bodhi show flow [name]   Visualize a flow's call chain
    bodhi show stats         Coverage dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.bar import Bar
from rich import box

from bodhi_engine.parser import parse_directory, load_bodhi_dir
from bodhi_engine.parser.yaml_parser import Flow, FlowStep


console = Console()


# ── show flow ──────────────────────────────────────────────────────────

def _render_step(idx: int, step: FlowStep, total: int) -> None:
    """Render a single flow step with color-coded details."""
    # Step header
    num = f"[bold white]  {idx}[/bold white]"
    fn_label = f"[bold cyan]{step.fn}[/bold cyan]"

    if step.remote:
        remote_tag = f"  [bold red]⟵ {step.remote}[/bold red] [dim]{step.protocol or ''}[/dim]"
    else:
        remote_tag = ""

    console.print(f"{num}  {fn_label}{remote_tag}")

    # Intent
    if step.intent:
        console.print(f"       [dim italic]{step.intent}[/dim italic]")

    # Reads
    for r in step.reads:
        console.print(f"       [green]reads:[/green]  {r}")

    # Writes
    for w in step.writes:
        console.print(f"       [yellow]writes:[/yellow] {w}")

    # Calls
    if step.calls:
        calls_str = ", ".join(step.calls)
        console.print(f"       [blue]calls:[/blue]  {calls_str}")

    # Emits
    for e in step.emits:
        console.print(f"       [magenta]emits:[/magenta]  {e}")

    # Consumes
    for c in step.consumes:
        console.print(f"       [magenta]consumes:[/magenta] {c}")

    # On fail
    for f in step.on_fail:
        console.print(f"       [bold red]on_fail:[/bold red] {f}")

    # Connector to next step
    if idx < total:
        console.print("       [dim]│[/dim]")
        console.print("       [dim]▼[/dim]")


def cmd_show_flow(project_root: Path, flow_name: str | None = None,
                  exclude_dirs: set[str] | None = None) -> None:
    """Visualize one or all flows as colored call chains."""
    bodhi_dir = project_root / ".bodhi"
    if not bodhi_dir.is_dir():
        console.print(f"[red]No .bodhi/ directory found in {project_root}[/red]")
        sys.exit(1)

    dsl = load_bodhi_dir(bodhi_dir)
    flows: list[Flow] = dsl["flows"]

    if not flows:
        console.print("[red]No flows found in .bodhi/flows/[/red]")
        sys.exit(1)

    # If no flow name specified, list available flows
    if not flow_name:
        console.print("[bold]Available flows:[/bold]\n")
        for f in flows:
            entry = f"{f.entry_method} {f.entry_path}" if f.entry_method else f.entry_type
            console.print(f"  [cyan]{f.name}[/cyan]  [dim]{entry}[/dim]  {f.description}")
        console.print(f"\n[dim]Usage: bodhi show flow <name>[/dim]")
        return

    # Find the specific flow
    matched = [f for f in flows if f.name == flow_name]
    if not matched:
        available = ", ".join(f.name for f in flows)
        console.print(f"[red]Flow '{flow_name}' not found.[/red] Available: {available}")
        sys.exit(1)

    flow = matched[0]

    # Header panel
    header_lines = []
    if flow.description:
        header_lines.append(flow.description)

    entry_line = f"[bold green]{flow.entry_method} {flow.entry_path}[/bold green]"
    if flow.entry_auth:
        entry_line += f"  [dim]auth: {flow.entry_auth}[/dim]"
    header_lines.append(entry_line)

    if flow.trace_key:
        header_lines.append(f"[dim]trace: {flow.trace_key}[/dim]")

    header_text = "\n".join(header_lines)
    console.print(Panel(
        header_text,
        title=f"[bold]{flow.name}[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    # Steps
    for i, step in enumerate(flow.steps, 1):
        _render_step(i, step, len(flow.steps))

    # Footer: entities and events
    console.print()
    if flow.entities:
        entities_str = ", ".join(f"[yellow]{e}[/yellow]" for e in flow.entities)
        console.print(f"  [dim]entities:[/dim] {entities_str}")
    if flow.events:
        events_str = ", ".join(f"[magenta]{e}[/magenta]" for e in flow.events)
        console.print(f"  [dim]events:[/dim]   {events_str}")
    if flow.related_flows:
        related_str = ", ".join(f"[cyan]{r}[/cyan]" for r in flow.related_flows)
        console.print(f"  [dim]related:[/dim]  {related_str}")
    console.print()


# ── show stats ─────────────────────────────────────────────────────────

def _bar(value: int, total: int, width: int = 30) -> Text:
    """Build a colored progress bar text."""
    if total == 0:
        return Text("  no data", style="dim")

    ratio = value / total
    filled = int(ratio * width)
    empty = width - filled

    if ratio >= 0.8:
        color = "green"
    elif ratio >= 0.5:
        color = "yellow"
    else:
        color = "red"

    bar_text = Text()
    bar_text.append("█" * filled, style=color)
    bar_text.append("░" * empty, style="dim")
    bar_text.append(f" {value}/{total} ", style="bold")
    bar_text.append(f"({ratio:.0%})", style=color)
    return bar_text


def cmd_show_stats(project_root: Path, exclude_dirs: set[str] | None = None) -> None:
    """Show a coverage dashboard with colored bars."""
    functions = parse_directory(project_root, exclude_dirs=exclude_dirs)
    bodhi_dir = project_root / ".bodhi"
    dsl = load_bodhi_dir(bodhi_dir) if bodhi_dir.is_dir() else None

    total = len(functions)

    # Tag coverage
    tag_counts = {
        "intent": sum(1 for f in functions if f.intent),
        "reads": sum(1 for f in functions if f.reads),
        "writes": sum(1 for f in functions if f.writes),
        "calls": sum(1 for f in functions if f.calls),
        "emits": sum(1 for f in functions if f.emits),
        "consumes": sum(1 for f in functions if f.consumes),
        "on_fail": sum(1 for f in functions if f.on_fail),
    }

    # Header
    console.print(Panel(
        f"[bold]{project_root.name}[/bold]  [dim]{project_root}[/dim]",
        title="[bold]Bodhi Coverage Dashboard[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    # Functions summary
    console.print(f"  [bold]Functions with @bodhi tags:[/bold] [cyan]{total}[/cyan]")
    console.print()

    # Tag coverage table
    console.print("  [bold]Inline Tag Coverage[/bold]")
    console.print()
    for tag, count in tag_counts.items():
        label = f"  @bodhi.{tag:<10}"
        bar = _bar(count, total)
        line = Text()
        line.append(label, style="bold")
        line.append(" ")
        line.append_text(bar)
        console.print(line)

    # Layer 2 summary
    if dsl:
        console.print()
        console.print("  [bold]Layer 2 (.bodhi/ YAML)[/bold]")
        console.print()

        layer2 = Table(
            show_header=False,
            box=None,
            padding=(0, 2),
            pad_edge=True,
        )
        layer2.add_column("type", style="bold", min_width=14)
        layer2.add_column("count", style="cyan", justify="right", min_width=4)

        items = [
            ("Flows", len(dsl["flows"])),
            ("Entities", len(dsl["entities"])),
            ("Events", len(dsl["events"])),
            ("State Machines", len(dsl["states"])),
            ("Services", len(dsl["services"])),
            ("Concepts", len(dsl["concepts"])),
            ("Channels", len(dsl.get("channels", []))),
            ("Topologies", len(dsl.get("topologies", []))),
        ]

        for name, count in items:
            if count > 0:
                layer2.add_row(f"  {name}", str(count))

        console.print(layer2)

    # Completeness hints
    console.print()
    missing_intent = [f for f in functions if not f.intent]
    missing_on_fail = [f for f in functions if (f.reads or f.writes or f.calls) and not f.on_fail]

    if missing_intent:
        console.print(f"  [yellow]![/yellow] {len(missing_intent)} functions missing @bodhi.intent")
        for f in missing_intent[:5]:
            console.print(f"    [dim]- {f.qualified_name}[/dim]")
        if len(missing_intent) > 5:
            console.print(f"    [dim]  ... and {len(missing_intent) - 5} more[/dim]")

    if missing_on_fail:
        console.print(f"  [yellow]![/yellow] {len(missing_on_fail)} functions with I/O but no @bodhi.on_fail")
        for f in missing_on_fail[:5]:
            console.print(f"    [dim]- {f.qualified_name}[/dim]")
        if len(missing_on_fail) > 5:
            console.print(f"    [dim]  ... and {len(missing_on_fail) - 5} more[/dim]")

    console.print()
