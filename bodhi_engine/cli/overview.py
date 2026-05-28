"""
bodhi overview — high-level project architecture in the terminal.

Aggregates .bodhi/ data into a layered bird's-eye view:
    Entry Points  →  Flows  →  Storage / Events / Externals

Designed for "what does this project look like at a glance", not for service-
level detail (use `bodhi arch` for that).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from bodhi_engine.parser import load_bodhi_dir
from bodhi_engine.parser.yaml_parser import (
    Entity, Event, Flow, Service, ServiceApi,
)


console = Console()


_MAX_ITEMS_PER_PANEL = 12  # truncate long lists with "+ N more"


_PROTO_COLOR = {
    "http": "cyan", "https": "cyan",
    "grpc": "green",
    "websocket": "magenta", "ws": "magenta",
    "tcp": "yellow",
    "jsonrpc": "blue",
    "mq": "bright_magenta", "kafka": "bright_magenta",
    "scheduler": "white", "event": "bright_magenta",
    "mq_consumer": "bright_magenta",
}


_PROTO_DISPLAY = {
    "websocket": "ws",
    "mq_consumer": "mq",
    "scheduler": "cron",
    "https": "http",
}


def _proto_label(proto: str) -> Text:
    short = _PROTO_DISPLAY.get(proto.lower(), proto.lower())
    return Text(f"{short:<5}", style=f"bold {_PROTO_COLOR.get(proto.lower(), 'white')}")


def _api_endpoint_label(api: ServiceApi) -> str:
    p = api.protocol
    if p in ("http", "https") and api.method:
        return f"{api.method} {api.path or ''}"
    if p == "grpc":
        return f"{api.service or '?'}/{api.method or '?'}"
    if p in ("websocket", "ws"):
        return f"channel:{api.channel}" if api.channel else (api.path or "?")
    if p == "tcp":
        return f"tcp:{api.port}" if api.port else "tcp"
    if p == "jsonrpc":
        return f"{api.transport or '?'} {api.method or ''}"
    return api.method or api.path or "?"


def _flow_entry_label(flow: Flow) -> str:
    if flow.entry_type in ("http", "https") and flow.entry_method:
        return f"{flow.entry_method} {flow.entry_path or ''}".strip()
    if flow.entry_type in ("mq_consumer", "event") and flow.entry_path:
        return flow.entry_path
    return flow.entry_path or flow.entry_method or flow.entry_type


def _collect_entries(flows: list[Flow], services: list[Service]) -> list[tuple[str, str, str]]:
    """Return list of (protocol, label, flow_name). Dedup by (label, flow_name)."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str]] = []

    for svc in services:
        for api in svc.apis:
            label = _api_endpoint_label(api)
            flow_name = api.flow or ""
            key = (label, flow_name)
            if key in seen:
                continue
            seen.add(key)
            out.append((api.protocol, label, flow_name))

    for flow in flows:
        if not flow.entry_type:
            continue
        label = _flow_entry_label(flow)
        key = (label, flow.name)
        if key in seen:
            continue
        seen.add(key)
        out.append((flow.entry_type, label, flow.name))

    return out


def _entries_panel(entries: list[tuple[str, str, str]]) -> Panel:
    body = Text()
    label_width = max((len(label) for _, label, _ in entries[:_MAX_ITEMS_PER_PANEL]), default=0)
    label_width = min(label_width, 40)

    for proto, label, flow in entries[:_MAX_ITEMS_PER_PANEL]:
        body.append_text(_proto_label(proto))
        body.append("  ")
        body.append(f"{label:<{label_width}}", style="bold")
        if flow:
            body.append("  → ", style="dim")
            body.append(flow, style="cyan")
        body.append("\n")

    extra = len(entries) - _MAX_ITEMS_PER_PANEL
    if extra > 0:
        body.append(f"... + {extra} more", style="dim italic")

    return Panel(
        body,
        title=f"[bold]Entry Points ({len(entries)})[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    )


def _flows_panel(flows: list[Flow]) -> Panel:
    body = Text()
    names = [f.name for f in flows]
    shown = names[:_MAX_ITEMS_PER_PANEL]
    body.append(", ".join(shown), style="cyan")
    extra = len(names) - _MAX_ITEMS_PER_PANEL
    if extra > 0:
        body.append(f"\n... + {extra} more", style="dim italic")
    return Panel(
        body,
        title=f"[bold]Flows ({len(flows)})[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    )


def _group_entities(entities: list[Entity]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        key = e.datasource or e.database or "default"
        groups[key].append(e.table)
    return groups


def _storage_panel(entities: list[Entity]) -> Panel | None:
    if not entities:
        return None
    groups = _group_entities(entities)
    body = Text()
    for ds, tables in groups.items():
        body.append(ds, style="bold yellow")
        body.append(f"  ({len(tables)})\n", style="dim")
        shown = tables[:6]
        for t in shown:
            body.append(f"  · {t}\n", style="white")
        if len(tables) > 6:
            body.append(f"  · ... + {len(tables) - 6} more\n", style="dim italic")
    return Panel(
        body,
        title=f"[bold]Storage ({len(entities)})[/bold]",
        border_style="yellow",
        padding=(0, 2),
    )


def _group_events(events: list[Event]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for e in events:
        key = e.channel or "internal"
        groups[key].append(e.name)
    return groups


def _events_panel(events: list[Event]) -> Panel | None:
    if not events:
        return None
    groups = _group_events(events)
    body = Text()
    for ch, names in groups.items():
        body.append(ch, style="bold bright_magenta")
        body.append(f"  ({len(names)})\n", style="dim")
        shown = names[:6]
        for n in shown:
            body.append(f"  · {n}\n", style="white")
        if len(names) > 6:
            body.append(f"  · ... + {len(names) - 6} more\n", style="dim italic")
    return Panel(
        body,
        title=f"[bold]Events ({len(events)})[/bold]",
        border_style="bright_magenta",
        padding=(0, 2),
    )


def _externals_panel(services: list[Service]) -> Panel | None:
    """List services that this workspace depends on but does not own."""
    known = {s.name for s in services}
    externals: dict[str, str] = {}  # name → protocol/type
    for svc in services:
        for dep in svc.depends_on:
            if dep.service in known:
                continue
            tag = dep.protocol or dep.type or "?"
            externals[dep.service] = tag

    if not externals:
        return None

    body = Text()
    for name, tag in externals.items():
        body.append(f"· {name}", style="bold")
        body.append(f"  [{tag}]\n", style="dim")

    return Panel(
        body,
        title=f"[bold]Externals ({len(externals)})[/bold]",
        border_style="red",
        padding=(0, 2),
    )


def _arrow_down(width: int = 50) -> None:
    bar = " " * (width // 2)
    console.print(f"{bar}[dim]│[/dim]")
    console.print(f"{bar}[dim]▼[/dim]")


def cmd_overview(project_root: Path, exclude_dirs: set[str] | None = None) -> None:
    bodhi_dir = project_root / ".bodhi"
    if not bodhi_dir.is_dir():
        console.print(f"[red]No .bodhi/ directory found in {project_root}[/red]")
        sys.exit(1)

    parse_errors: list[str] = []
    dsl = load_bodhi_dir(bodhi_dir, errors=parse_errors)
    flows: list[Flow] = dsl["flows"]
    entities: list[Entity] = dsl["entities"]
    events: list[Event] = dsl["events"]
    services: list[Service] = dsl["services"]

    if parse_errors:
        console.print(f"[yellow]⚠ {len(parse_errors)} file(s) failed to parse — rendering partial overview:[/yellow]")
        for err in parse_errors:
            console.print(f"  [dim]{err}[/dim]")
        console.print()

    if not (flows or entities or events or services):
        console.print(f"[red].bodhi/ exists but no flows/entities/events/services could be loaded.[/red]")
        sys.exit(1)

    meta = dsl.get("meta")
    title = meta.name if meta and getattr(meta, "name", None) else project_root.name
    counts = f"flows {len(flows)} · entities {len(entities)} · events {len(events)} · services {len(services)}"
    console.print(Panel(
        f"[bold]{title}[/bold]\n[dim]{counts}[/dim]",
        title="[bold]Project Overview[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    entries = _collect_entries(flows, services)
    if entries:
        console.print(_entries_panel(entries))
        _arrow_down()

    if flows:
        console.print(_flows_panel(flows))
        _arrow_down()

    bottom = [p for p in (
        _storage_panel(entities),
        _events_panel(events),
        _externals_panel(services),
    ) if p is not None]

    if bottom:
        console.print(Columns(bottom, equal=False, expand=False))

    console.print()
