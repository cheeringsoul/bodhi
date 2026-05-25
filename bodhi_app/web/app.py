"""Bodhi Web Dashboard — FastAPI + Jinja2 visualization of .bodhi/ knowledge."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys

from bodhi_app.web.i18n import get_translations, SUPPORTED_LANGS, DEFAULT_LANG
from bodhi_engine.knowledge import BodhiKnowledge
from bodhi_engine.cli.score import ScoreReport, Dimension, _ratio_to_score, _is_remote_call, _fn_location, DIMENSION_MAX, TOTAL_MAX
from bodhi_engine.cli.graph import flows_to_mermaid
from bodhi_engine.parser import parse_directory
from bodhi_engine.validator.checker import validate

_HERE = Path(__file__).parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"


def create_app(project_root: Path) -> FastAPI:
    app = FastAPI(title="Bodhi Dashboard")
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    templates = Jinja2Templates(directory=str(_TEMPLATES))

    kb = BodhiKnowledge(project_root, lenient=True)
    if kb.load_errors:
        for err in kb.load_errors:
            print(f"Warning: {err}", file=sys.stderr)
    functions = kb.functions

    meta = kb.dsl.get("meta")
    project_name = meta.name if meta and getattr(meta, "name", None) else project_root.name

    def _get_lang(request: Request) -> str:
        lang = request.query_params.get("lang") or request.cookies.get("bodhi_lang", DEFAULT_LANG)
        return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    def _ctx(request: Request, **extra) -> dict:
        lang = _get_lang(request)
        return {
            "project_name": project_name,
            "lang": lang,
            "langs": SUPPORTED_LANGS,
            "t": get_translations(lang),
            "nav_counts": {
                "flows": len(kb.list_flows()),
                "entities": len(kb.list_entities()),
                "services": len(kb.list_services()),
                "events": len(kb.list_events()),
                "states": len(kb.list_state_machines()),
                "channels": len(kb.list_channels()),
            },
            **extra,
        }

    @app.get("/set-lang/{lang}")
    async def set_lang(request: Request, lang: str):
        referer = request.headers.get("referer", "/")
        response = RedirectResponse(url=referer)
        if lang in SUPPORTED_LANGS:
            response.set_cookie("bodhi_lang", lang, max_age=365 * 24 * 3600)
        return response

    # ── Dashboard ─────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        report = _compute_score(functions, project_root)

        total_fns = len(functions)
        tag_stats = {
            "intent": sum(1 for f in functions if f.intent),
            "reads": sum(1 for f in functions if f.reads),
            "writes": sum(1 for f in functions if f.writes),
            "calls": sum(1 for f in functions if f.calls),
            "emits": sum(1 for f in functions if f.emits),
            "on_fail": sum(1 for f in functions if f.on_fail),
        }

        return templates.TemplateResponse(request, "dashboard.html", {
            **_ctx(request),
            "score": report.as_dict(),
            "total_functions": total_fns,
            "tag_stats": tag_stats,
        })

    # ── Flows ─────────────────────────────────────────────────────────

    @app.get("/flows", response_class=HTMLResponse)
    async def flows_list(request: Request):
        flow_names = kb.list_flows()
        flows_data = []
        for name in flow_names:
            flow = kb.query_flow(name)
            if flow:
                flows_data.append(flow)
        return templates.TemplateResponse(request, "flows.html", {
            **_ctx(request),
            "flows": flows_data,
        })

    @app.get("/flows/{name}", response_class=HTMLResponse)
    async def flow_detail(request: Request, name: str):
        flow = kb.query_flow(name)
        if not flow:
            return HTMLResponse("Flow not found", status_code=404)

        matched_flows = [f for f in kb.dsl["flows"] if f.name == name]
        mermaid = flows_to_mermaid(matched_flows, entities=kb.dsl["entities"]) if matched_flows else ""

        return templates.TemplateResponse(request, "flow_detail.html", {
            **_ctx(request),
            "flow": flow,
            "mermaid": mermaid,
        })

    # ── Entities ──────────────────────────────────────────────────────

    @app.get("/entities", response_class=HTMLResponse)
    async def entities_list(request: Request):
        entity_names = kb.list_entities()
        entities_data = []
        for name in entity_names:
            schema = kb._entity_schema(name)
            if schema:
                entities_data.append(schema)
        return templates.TemplateResponse(request, "entities.html", {
            **_ctx(request),
            "entities": entities_data,
        })

    @app.get("/entities/{name}", response_class=HTMLResponse)
    async def entity_detail(request: Request, name: str):
        trace = kb.trace_entity(name)
        return templates.TemplateResponse(request, "entity_detail.html", {
            **_ctx(request),
            "entity": trace,
        })

    # ── Services ──────────────────────────────────────────────────────

    @app.get("/services", response_class=HTMLResponse)
    async def services_list(request: Request):
        service_names = kb.list_services()
        services_data = []
        for name in service_names:
            svc = kb.service_deps(name)
            if svc:
                services_data.append(svc)

        topo_mermaid = _build_service_topology_mermaid(services_data)

        return templates.TemplateResponse(request, "services.html", {
            **_ctx(request),
            "services": services_data,
            "topo_mermaid": topo_mermaid,
        })

    # ── Events ────────────────────────────────────────────────────────

    @app.get("/events", response_class=HTMLResponse)
    async def events_list(request: Request):
        event_names = kb.list_events()
        events_data = []
        for name in event_names:
            evt = kb.find_consumers(name)
            if evt:
                events_data.append(evt)
        return templates.TemplateResponse(request, "events.html", {
            **_ctx(request),
            "events": events_data,
        })

    # ── State Machines ────────────────────────────────────────────────

    @app.get("/states", response_class=HTMLResponse)
    async def states_list(request: Request):
        sm_names = kb.list_state_machines()
        states_data = []
        for name in sm_names:
            sm = kb.query_state(name)
            if sm:
                mermaid = _build_state_mermaid(name, sm, kb)
                sm["mermaid"] = mermaid
                states_data.append(sm)
        return templates.TemplateResponse(request, "states.html", {
            **_ctx(request),
            "state_machines": states_data,
        })

    # ── Impact Analysis API ───────────────────────────────────────────

    @app.get("/api/impact/{target}")
    async def api_impact(target: str):
        return kb.impact_analysis(target)

    # ── All-flows Mermaid ─────────────────────────────────────────────

    @app.get("/graph", response_class=HTMLResponse)
    async def graph_all(request: Request):
        mermaid = flows_to_mermaid(kb.dsl["flows"], entities=kb.dsl["entities"])
        return templates.TemplateResponse(request, "graph.html", {
            **_ctx(request),
            "mermaid": mermaid,
            "title": "All Flows",
        })

    return app


def _compute_score(functions, project_root: Path) -> ScoreReport:
    total_fns = len(functions)
    with_intent = sum(1 for f in functions if f.intent)
    missing_intent_fns = [f for f in functions if not f.intent]
    d1 = Dimension(name="Intent coverage", score=_ratio_to_score(with_intent, total_fns))
    if missing_intent_fns:
        d1.reasons.append(f"{len(missing_intent_fns)} tagged function(s) missing @bodhi.intent")

    intent_fns = [f for f in functions if f.intent]
    intent_with_flow = sum(1 for f in intent_fns if f.reads or f.writes)
    intent_without = [f for f in intent_fns if not (f.reads or f.writes)]
    d2 = Dimension(name="Data-flow completeness", score=_ratio_to_score(intent_with_flow, len(intent_fns)))
    if intent_without:
        d2.reasons.append(f"{len(intent_without)} function(s) have @bodhi.intent but no @bodhi.reads/@bodhi.writes")

    risky_fns = [f for f in functions if f.writes or any(_is_remote_call(c) for c in f.get_tags("calls"))]
    risky_with_on_fail = sum(1 for f in risky_fns if f.on_fail)
    risky_without = [f for f in risky_fns if not f.on_fail]
    d3 = Dimension(name="Error handling", score=_ratio_to_score(risky_with_on_fail, len(risky_fns)))
    if risky_without:
        d3.reasons.append(f"{len(risky_without)} function(s) with writes/remote-calls missing @bodhi.on_fail")

    fn_names = {f.qualified_name for f in functions}
    total_calls = 0
    unresolved = 0
    for f in functions:
        for raw in f.get_tags("calls"):
            for piece in raw.split(","):
                piece = piece.strip()
                if not piece:
                    continue
                total_calls += 1
                if not _is_remote_call(piece) and piece not in fn_names:
                    unresolved += 1
    d4 = Dimension(name="Call-chain traceability", score=_ratio_to_score(total_calls - unresolved, total_calls))
    if unresolved:
        d4.reasons.append(f"{unresolved} @bodhi.calls target(s) have no inline tags (dangling)")

    try:
        issues = validate(project_root)
    except Exception:
        issues = []
    overloading = sum(1 for i in issues if i.rule == "method-overloading")
    dangling_impl = sum(1 for i in issues if i.rule == "implements-missing-interface")
    missing_intent_err = sum(1 for i in issues if i.rule == "missing-intent")
    penalty = min(overloading * 5, 15) + min(dangling_impl * 3, 9) + min(missing_intent_err * 2, 10)
    d5 = Dimension(name="Structural health", score=DIMENSION_MAX - min(penalty, DIMENSION_MAX))

    dims = [d1, d2, d3, d4, d5]
    return ScoreReport(total=sum(d.score for d in dims), max=TOTAL_MAX, dimensions=dims)


def _build_service_topology_mermaid(services: list[dict]) -> str:
    lines = ["graph LR"]
    declared = set()
    for svc in services:
        name = svc["name"]
        sid = name.replace("-", "_")
        if sid not in declared:
            lines.append(f'    {sid}["{name}"]')
            declared.add(sid)
        for dep in svc.get("depends_on", []):
            dep_name = dep["service"]
            dep_id = dep_name.replace("-", "_")
            if dep_id not in declared:
                lines.append(f'    {dep_id}["{dep_name}"]')
                declared.add(dep_id)
            proto = dep.get("protocol", "?")
            lines.append(f'    {sid} -->|{proto}| {dep_id}')

    lines.append("")
    lines.append("    classDef svcStyle fill:#42A5F5,stroke:#1565C0,color:#fff,stroke-width:2px")
    lines.append("    classDef extStyle fill:#FF9800,stroke:#E65100,color:#fff,stroke-width:2px")

    internal = set()
    for svc in services:
        internal.add(svc["name"].replace("-", "_"))
    external = declared - internal

    if internal:
        lines.append(f"    class {','.join(internal)} svcStyle")
    if external:
        lines.append(f"    class {','.join(external)} extStyle")

    return "\n".join(lines)


def _build_state_mermaid(name: str, sm: dict, kb: BodhiKnowledge) -> str:
    lines = ["stateDiagram-v2"]
    for state in sm.get("states", []):
        sid = state["id"]
        desc = state.get("description", "")
        lines.append(f'    {sid} : {desc}')
        if state.get("terminal"):
            lines.append(f"    {sid} --> [*]")

    first_state = sm["states"][0]["id"] if sm.get("states") else None
    if first_state:
        lines.append(f"    [*] --> {first_state}")

    for state in sm.get("states", []):
        detail = kb.query_state(name, state["id"])
        if detail and detail.get("transitions"):
            for t in detail["transitions"]:
                label = t.get("trigger", "")
                lines.append(f'    {state["id"]} --> {t["target"]} : {label}')

    return "\n".join(lines)


def run_server(project_root: Path, host: str = "127.0.0.1", port: int = 8500):
    import uvicorn
    app = create_app(project_root)
    print(f"Bodhi Dashboard: http://{host}:{port}")
    print(f"Project: {project_root}")
    uvicorn.run(app, host=host, port=port)
