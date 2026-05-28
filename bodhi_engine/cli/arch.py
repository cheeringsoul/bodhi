"""
bodhi arch — terminal visualization of project service topology.

Renders services from .bodhi/services/*.yaml as colored panels with their
APIs and dependencies, plus a topology summary of inter-service edges.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from bodhi_engine.parser import load_bodhi_dir
from bodhi_engine.parser.yaml_parser import Service, ServiceApi, ServiceDependency


console = Console()


_PROTOCOL_COLORS = {
    "http": "cyan",
    "https": "cyan",
    "grpc": "green",
    "websocket": "magenta",
    "ws": "magenta",
    "tcp": "yellow",
    "jsonrpc": "blue",
    "mq": "bright_magenta",
    "kafka": "bright_magenta",
    "rabbitmq": "bright_magenta",
    "redis": "red",
}


def _proto_color(protocol: str | None, dep_type: str | None = None) -> str:
    key = (protocol or dep_type or "").lower()
    return _PROTOCOL_COLORS.get(key, "white")


def _proto_tag(protocol: str | None, dep_type: str | None = None) -> Text:
    label = protocol or dep_type or "?"
    return Text(label, style=f"bold {_proto_color(protocol, dep_type)}")


def _format_api(api: ServiceApi) -> Text:
    line = Text()
    line.append_text(_proto_tag(api.protocol))
    line.append("  ")
    if api.protocol in ("http", "https") and api.method:
        line.append(f"{api.method} {api.path or ''}", style="bold")
    elif api.protocol == "grpc":
        rpc = f"{api.service or '?'}/{api.method or '?'}"
        line.append(rpc, style="bold")
    elif api.protocol in ("websocket", "ws"):
        target = api.channel or api.path or "?"
        line.append(target, style="bold")
    elif api.protocol == "tcp":
        port = f":{api.port}" if api.port else ""
        line.append(f"tcp{port} ({api.codec or 'codec?'})", style="bold")
    elif api.protocol == "jsonrpc":
        line.append(f"{api.transport or '?'} {api.method or ''}", style="bold")
    else:
        line.append(api.method or api.path or "", style="bold")

    if api.flow:
        line.append(f"  → {api.flow}", style="dim")
    if api.description:
        line.append(f"  [{api.description}]", style="dim italic")
    return line


def _format_dep(dep: ServiceDependency) -> list[Text]:
    """Render one dependency as one or more lines."""
    head = Text()
    head.append("→ ", style="bold red")
    head.append(dep.service, style="bold yellow")
    head.append("  ")
    head.append_text(_proto_tag(dep.protocol, dep.type))
    lines = [head]

    for api in dep.apis:
        lines.append(Text(f"    · {api}", style="dim"))
    for topic in dep.topics:
        t = Text("    · ", style="dim")
        t.append(topic, style="bright_magenta")
        t.append("  ")
        t.append("(topic)", style="dim")
        lines.append(t)

    if dep.resilience:
        parts = [f"{k}={v}" for k, v in dep.resilience.items()]
        r = Text("    ⚠ ", style="bold red")
        r.append(", ".join(parts), style="dim red")
        lines.append(r)

    return lines


def _render_service(svc: Service) -> Panel:
    body = Text()

    if svc.description:
        body.append(svc.description, style="italic")
        body.append("\n")
    meta_parts = []
    if svc.port:
        meta_parts.append(f"port {svc.port}")
    if svc.tech_stack:
        meta_parts.append(", ".join(svc.tech_stack))
    if meta_parts:
        body.append(" · ".join(meta_parts), style="dim")
        body.append("\n")

    if svc.apis:
        body.append("\n")
        body.append("APIs", style="bold")
        body.append("\n")
        for api in svc.apis:
            body.append("  ")
            body.append_text(_format_api(api))
            body.append("\n")

    if svc.depends_on:
        body.append("\n")
        body.append("Depends on", style="bold")
        body.append("\n")
        for dep in svc.depends_on:
            for line in _format_dep(dep):
                body.append("  ")
                body.append_text(line)
                body.append("\n")

    return Panel(
        body,
        title=f"[bold cyan]{svc.name}[/bold cyan]",
        border_style="bright_blue",
        padding=(0, 2),
    )


def _render_topology(services: list[Service]) -> None:
    """Print a flat list of service → service edges with protocol."""
    known = {s.name for s in services}
    edges: list[tuple[str, str, str]] = []
    externals: set[str] = set()
    for svc in services:
        for dep in svc.depends_on:
            proto = dep.protocol or dep.type or "?"
            edges.append((svc.name, dep.service, proto))
            if dep.service not in known:
                externals.add(dep.service)

    if not edges:
        return

    console.print()
    console.print("[bold]Topology[/bold]")
    console.print()
    src_width = max(len(s) for s, _, _ in edges)
    proto_width = max(len(p) for _, _, p in edges)
    for src, dst, proto in edges:
        line = Text()
        line.append(f"  {src:<{src_width}}", style="cyan")
        line.append(" ──")
        line.append(f"{proto:<{proto_width}}", style=_proto_color(proto))
        line.append("──▶ ")
        is_external = dst in externals
        line.append(dst, style="yellow" if is_external else "cyan")
        if is_external:
            line.append("  (external)", style="dim")
        console.print(line)

    if externals:
        console.print()
        ext_text = Text("  external: ", style="dim")
        ext_text.append(", ".join(sorted(externals)), style="yellow")
        console.print(ext_text)


def cmd_arch(project_root: Path, exclude_dirs: set[str] | None = None) -> None:
    """Visualize the project's service topology in the terminal."""
    bodhi_dir = project_root / ".bodhi"
    if not bodhi_dir.is_dir():
        console.print(f"[red]No .bodhi/ directory found in {project_root}[/red]")
        sys.exit(1)

    parse_errors: list[str] = []
    dsl = load_bodhi_dir(bodhi_dir, errors=parse_errors)
    services: list[Service] = dsl["services"]

    if parse_errors:
        console.print(f"[yellow]⚠ {len(parse_errors)} file(s) failed to parse — rendering what loaded:[/yellow]")
        for err in parse_errors:
            console.print(f"  [dim]{err}[/dim]")
        console.print()

    if not services:
        console.print("[red]No services found in .bodhi/services/[/red]")
        console.print("[dim]Tip: define services in .bodhi/services/<name>.yaml[/dim]")
        sys.exit(1)

    meta = dsl.get("meta")
    title = meta.name if meta and getattr(meta, "name", None) else project_root.name
    header = f"[bold]{title}[/bold]  [dim]{len(services)} service(s)[/dim]"
    console.print(Panel(
        header,
        title="[bold]Bodhi Service Architecture[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    for svc in services:
        console.print(_render_service(svc))
        console.print()

    _render_topology(services)
    console.print()
