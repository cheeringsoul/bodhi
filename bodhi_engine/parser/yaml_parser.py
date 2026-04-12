"""
Parse .bodhi/ directory YAML files: flows, entities, states, concepts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


# --- Data Models ---

@dataclass
class FlowStep:
    fn: str
    intent: str
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    emits: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    on_fail: list[str] = field(default_factory=list)
    # Cross-service fields
    remote: Optional[str] = None       # remote service name, None = local
    protocol: Optional[str] = None     # protocol for remote call (http, grpc, etc.)
    api: Optional[str] = None          # remote API identifier
    flow_ref: Optional[str] = None     # pointer to remote flow, e.g. "payment-service:hold_payment"


@dataclass
class Flow:
    name: str
    description: str
    entry_type: str          # http, grpc, mq_consumer, scheduler, websocket
    entry_method: str        # GET, POST, etc.
    entry_path: str          # /api/orders
    entry_auth: Optional[str] = None
    steps: list[FlowStep] = field(default_factory=list)
    error_handling: list[dict] = field(default_factory=list)
    related_flows: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    trace_key: Optional[str] = None   # correlation ID field for log-driven debug

    @property
    def all_functions(self) -> list[str]:
        return [s.fn for s in self.steps]

    @property
    def all_writes(self) -> list[str]:
        result = []
        for s in self.steps:
            result.extend(s.writes)
        return result

    @property
    def all_reads(self) -> list[str]:
        result = []
        for s in self.steps:
            result.extend(s.reads)
        return result


@dataclass
class StateTransition:
    target: str
    trigger: str
    fn: Optional[str] = None
    condition: Optional[str] = None


@dataclass
class State:
    id: str
    value: Optional[int] = None
    description: str = ""
    on_entry: Optional[str] = None
    terminal: bool = False
    transitions: list[StateTransition] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)


@dataclass
class StateMachine:
    name: str
    entity: str
    field_name: str   # "field" in YAML, renamed to avoid conflict
    description: str
    states: list[State] = field(default_factory=list)

    @property
    def all_functions(self) -> list[str]:
        """All functions involved in state transitions."""
        fns = []
        for state in self.states:
            if state.on_entry:
                fns.append(state.on_entry)
            for t in state.transitions:
                if t.fn:
                    fns.append(t.fn)
        return fns


@dataclass
class EntityField:
    name: str
    type: str
    description: str = ""
    primary_key: bool = False
    references: Optional[str] = None
    state_machine: Optional[str] = None
    sensitive: bool = False
    unit: Optional[str] = None
    enum: Optional[dict[int, str]] = None


@dataclass
class EntityRelation:
    target: str
    type: str          # one_to_many, many_to_one, one_to_one
    join: str
    description: str = ""


@dataclass
class Entity:
    table: str
    description: str
    database: Optional[str] = None
    datasource: Optional[str] = None
    fields: list[EntityField] = field(default_factory=list)
    indexes: list[dict] = field(default_factory=list)
    relations: list[EntityRelation] = field(default_factory=list)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def sensitive_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.sensitive]

    @property
    def state_machine_fields(self) -> list[EntityField]:
        return [f for f in self.fields if f.state_machine]


@dataclass
class Concept:
    term: str
    definition: str
    related_states: list[str] = field(default_factory=list)
    related_flows: list[str] = field(default_factory=list)
    related_fields: list[str] = field(default_factory=list)


@dataclass
class EventSchemaField:
    field: str
    type: str
    description: str = ""


@dataclass
class EventEndpoint:
    fn: str
    flow: Optional[str] = None
    description: str = ""


@dataclass
class Event:
    name: str
    description: str
    channel: Optional[str] = None
    schema: list[EventSchemaField] = field(default_factory=list)
    producers: list[EventEndpoint] = field(default_factory=list)
    consumers: list[EventEndpoint] = field(default_factory=list)


@dataclass
class ServiceApi:
    protocol: str = "http"             # http, grpc, websocket, jsonrpc, tcp
    method: Optional[str] = None       # HTTP method or gRPC method name
    path: Optional[str] = None         # HTTP/WebSocket path
    flow: Optional[str] = None
    description: str = ""
    # gRPC-specific
    service: Optional[str] = None      # gRPC service name
    # WebSocket-specific
    channel: Optional[str] = None      # reference to channel definition
    # JSON-RPC-specific
    transport: Optional[str] = None    # http, websocket, tcp
    # TCP-specific
    port: Optional[int] = None
    codec: Optional[str] = None        # protobuf, msgpack, json, custom
    commands: list[dict] = field(default_factory=list)  # TCP commands


@dataclass
class ServiceDependency:
    service: str
    protocol: Optional[str] = None
    type: Optional[str] = None
    apis: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    resilience: Optional[dict] = None


@dataclass
class Service:
    name: str
    description: str
    port: Optional[int] = None
    tech_stack: list[str] = field(default_factory=list)
    apis: list[ServiceApi] = field(default_factory=list)
    depends_on: list[ServiceDependency] = field(default_factory=list)


@dataclass
class ChannelEvent:
    name: str
    description: str = ""
    schema: list[dict] = field(default_factory=list)
    triggers_flow: Optional[str] = None      # for inbound events
    triggered_by: list[dict] = field(default_factory=list)  # for outbound events


@dataclass
class Channel:
    name: str
    protocol: str              # websocket, tcp, sse
    description: str = ""
    path: Optional[str] = None
    port: Optional[int] = None
    inbound_events: list[ChannelEvent] = field(default_factory=list)
    outbound_events: list[ChannelEvent] = field(default_factory=list)


@dataclass
class TopologyConsumer:
    service: str
    fn: Optional[str] = None
    action: str = ""
    emits: Optional[str] = None  # downstream event this consumer triggers


@dataclass
class TopologyChain:
    event: str
    channel: Optional[str] = None
    producer: Optional[str] = None
    consumers: list[TopologyConsumer] = field(default_factory=list)


@dataclass
class Topology:
    name: str
    description: str = ""
    chains: list[TopologyChain] = field(default_factory=list)


@dataclass
class DistributedMeta:
    system: str                     # system name shared by all services
    service: str                    # this service's name
    registry: Optional[str] = None  # registry repo URL


@dataclass
class RuntimeLogSource:
    name: str
    type: str              # file, elasticsearch, loki, cloudwatch
    path: Optional[str] = None
    format: Optional[str] = None          # json, text, logfmt
    timestamp_field: Optional[str] = None
    message_field: Optional[str] = None
    url: Optional[str] = None
    index: Optional[str] = None
    labels: dict = field(default_factory=dict)
    auth: dict = field(default_factory=dict)


@dataclass
class RuntimeConfig:
    logs: list[RuntimeLogSource] = field(default_factory=list)
    time_window: str = "30s"
    default_trace_field: Optional[str] = None


@dataclass
class ProjectMeta:
    version: str
    name: str
    description: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    distributed: Optional[DistributedMeta] = None
    runtime: Optional[RuntimeConfig] = None


# --- Parsers ---

def parse_flow(data: dict) -> Flow:
    raw_entry = data.get("entry", {})
    if isinstance(raw_entry, str):
        entry = {"type": raw_entry}
    elif isinstance(raw_entry, dict):
        entry = raw_entry
    else:
        entry = {}
    steps = []
    for s in data.get("steps", []):
        steps.append(FlowStep(
            fn=s["fn"],
            intent=s.get("intent", ""),
            reads=s.get("reads", []),
            writes=s.get("writes", []),
            calls=s.get("calls", []),
            emits=s.get("emits", []),
            consumes=s.get("consumes", []),
            on_fail=s.get("on_fail", []),
            remote=s.get("remote"),
            protocol=s.get("protocol"),
            api=s.get("api"),
            flow_ref=s.get("flow_ref"),
        ))

    return Flow(
        name=data["name"],
        description=data.get("description", ""),
        entry_type=entry.get("type", ""),
        entry_method=entry.get("method", ""),
        entry_path=entry.get("path", ""),
        entry_auth=entry.get("auth"),
        steps=steps,
        error_handling=data.get("error_handling", []),
        related_flows=data.get("related_flows", []),
        entities=data.get("entities", []),
        events=data.get("events", []),
        trace_key=data.get("trace_key"),
    )


def parse_state_machine(data: dict) -> StateMachine:
    states = []
    for s in data.get("states", []):
        transitions = []
        for t in s.get("transitions", []):
            transitions.append(StateTransition(
                target=t["target"],
                trigger=t["trigger"],
                fn=t.get("fn"),
                condition=t.get("condition"),
            ))
        states.append(State(
            id=s["id"],
            value=s.get("value"),
            description=s.get("description", ""),
            on_entry=s.get("on_entry"),
            terminal=s.get("terminal", False),
            transitions=transitions,
            side_effects=s.get("side_effects", []),
        ))

    return StateMachine(
        name=data["name"],
        entity=data["entity"],
        field_name=data.get("field", ""),
        description=data.get("description", ""),
        states=states,
    )


def parse_entity(data: dict) -> Entity:
    fields = []
    for f in data.get("fields", []):
        fields.append(EntityField(
            name=f["name"],
            type=f["type"],
            description=f.get("description", ""),
            primary_key=f.get("primary_key", False),
            references=f.get("references"),
            state_machine=f.get("state_machine"),
            sensitive=f.get("sensitive", False),
            unit=f.get("unit"),
            enum=f.get("enum"),
        ))

    relations = []
    for r in data.get("relations", []):
        relations.append(EntityRelation(
            target=r["target"],
            type=r["type"],
            join=r["join"],
            description=r.get("description", ""),
        ))

    return Entity(
        table=data["table"],
        description=data.get("description", ""),
        database=data.get("database"),
        datasource=data.get("datasource"),
        fields=fields,
        indexes=data.get("indexes", []),
        relations=relations,
    )


def parse_concepts(data: dict) -> list[Concept]:
    concepts = []
    for c in data.get("concepts", []):
        concepts.append(Concept(
            term=c["term"],
            definition=c["definition"],
            related_states=c.get("related_states", []),
            related_flows=c.get("related_flows", []),
            related_fields=c.get("related_fields", []),
        ))
    return concepts


def parse_event(data: dict) -> Event:
    schema = []
    for s in data.get("schema", []):
        schema.append(EventSchemaField(
            field=s["field"],
            type=s["type"],
            description=s.get("description", ""),
        ))

    producers = []
    for p in data.get("producers", []):
        if isinstance(p, str):
            p = {"fn": p}
        producers.append(EventEndpoint(
            fn=p.get("fn", ""),
            flow=p.get("flow"),
            description=p.get("description", ""),
        ))

    consumers = []
    for c in data.get("consumers", []):
        if isinstance(c, str):
            c = {"fn": c}
        consumers.append(EventEndpoint(
            fn=c.get("fn", ""),
            flow=c.get("flow"),
            description=c.get("description", ""),
        ))

    return Event(
        name=data["name"],
        description=data.get("description", ""),
        channel=data.get("channel"),
        schema=schema,
        producers=producers,
        consumers=consumers,
    )


def parse_service(data: dict) -> Service:
    apis = []
    for a in data.get("apis", []):
        apis.append(ServiceApi(
            protocol=a.get("protocol", "http"),
            method=a.get("method"),
            path=a.get("path"),
            flow=a.get("flow"),
            description=a.get("description", ""),
            service=a.get("service"),
            channel=a.get("channel"),
            transport=a.get("transport"),
            port=a.get("port"),
            codec=a.get("codec"),
            commands=a.get("commands", []),
        ))

    depends_on = []
    for d in data.get("depends_on", []):
        depends_on.append(ServiceDependency(
            service=d["service"],
            protocol=d.get("protocol"),
            type=d.get("type"),
            apis=d.get("apis", []),
            topics=d.get("topics", []),
            resilience=d.get("resilience"),
        ))

    return Service(
        name=data["name"],
        description=data.get("description", ""),
        port=data.get("port"),
        tech_stack=data.get("tech_stack", []),
        apis=apis,
        depends_on=depends_on,
    )


def parse_channel(data: dict) -> Channel:
    inbound = []
    for e in data.get("inbound_events", []):
        inbound.append(ChannelEvent(
            name=e["name"],
            description=e.get("description", ""),
            schema=e.get("schema", []),
            triggers_flow=e.get("triggers_flow"),
        ))

    outbound = []
    for e in data.get("outbound_events", []):
        outbound.append(ChannelEvent(
            name=e["name"],
            description=e.get("description", ""),
            schema=e.get("schema", []),
            triggered_by=e.get("triggered_by", []),
        ))

    return Channel(
        name=data["name"],
        protocol=data.get("protocol", "websocket"),
        description=data.get("description", ""),
        path=data.get("path"),
        port=data.get("port"),
        inbound_events=inbound,
        outbound_events=outbound,
    )


def parse_topology(data: dict) -> Topology:
    chains = []
    for c in data.get("chains", []):
        consumers = []
        for con in c.get("consumers", []):
            consumers.append(TopologyConsumer(
                service=con["service"],
                fn=con.get("fn"),
                action=con.get("action", ""),
                emits=con.get("emits"),
            ))
        chains.append(TopologyChain(
            event=c["event"],
            channel=c.get("channel"),
            producer=c.get("producer"),
            consumers=consumers,
        ))

    return Topology(
        name=data["name"],
        description=data.get("description", ""),
        chains=chains,
    )


def _parse_runtime_config(data: dict) -> RuntimeConfig:
    logs = []
    for src in data.get("logs", []):
        logs.append(RuntimeLogSource(
            name=src.get("name", ""),
            type=src.get("type", "file"),
            path=src.get("path"),
            format=src.get("format"),
            timestamp_field=src.get("timestamp_field"),
            message_field=src.get("message_field"),
            url=src.get("url"),
            index=src.get("index"),
            labels=src.get("labels", {}),
            auth=src.get("auth", {}),
        ))
    return RuntimeConfig(
        logs=logs,
        time_window=data.get("time_window", "30s"),
        default_trace_field=data.get("default_trace_field"),
    )


def parse_project_meta(data: dict) -> ProjectMeta:
    project = data.get("project", {})
    dist_data = data.get("distributed")
    distributed = None
    if dist_data:
        distributed = DistributedMeta(
            system=dist_data.get("system", ""),
            service=dist_data.get("service", ""),
            registry=dist_data.get("registry"),
        )
    runtime_data = data.get("runtime")
    runtime = _parse_runtime_config(runtime_data) if runtime_data else None
    return ProjectMeta(
        version=data.get("version", "0.1.1"),
        name=project.get("name", ""),
        description=project.get("description", ""),
        languages=project.get("languages", []),
        frameworks=project.get("frameworks", []),
        distributed=distributed,
        runtime=runtime,
    )


# --- Directory Loader ---

def load_bodhi_dir(bodhi_dir: Path) -> dict[str, Any]:
    """Load all YAML files from a .bodhi/ directory.

    Returns a dict with keys: meta, flows, states, entities, concepts
    """
    result: dict[str, Any] = {
        "meta": None,
        "flows": [],
        "states": [],
        "entities": [],
        "events": [],
        "services": [],
        "concepts": [],
        "channels": [],
        "topologies": [],
    }

    # bodhi.yaml
    meta_file = bodhi_dir / "bodhi.yaml"
    if meta_file.exists():
        with open(meta_file) as f:
            result["meta"] = parse_project_meta(yaml.safe_load(f))

    # flows/
    flows_dir = bodhi_dir / "flows"
    if flows_dir.is_dir():
        for f in sorted(flows_dir.glob("*.yaml")):
            with open(f) as fh:
                result["flows"].append(parse_flow(yaml.safe_load(fh)))

    # states/
    states_dir = bodhi_dir / "states"
    if states_dir.is_dir():
        for f in sorted(states_dir.glob("*.yaml")):
            with open(f) as fh:
                result["states"].append(parse_state_machine(yaml.safe_load(fh)))

    # entities/
    entities_dir = bodhi_dir / "entities"
    if entities_dir.is_dir():
        for f in sorted(entities_dir.glob("*.yaml")):
            with open(f) as fh:
                result["entities"].append(parse_entity(yaml.safe_load(fh)))

    # services/
    services_dir = bodhi_dir / "services"
    if services_dir.is_dir():
        for f in sorted(services_dir.glob("*.yaml")):
            with open(f) as fh:
                result["services"].append(parse_service(yaml.safe_load(fh)))

    # events/
    events_dir = bodhi_dir / "events"
    if events_dir.is_dir():
        for f in sorted(events_dir.glob("*.yaml")):
            with open(f) as fh:
                result["events"].append(parse_event(yaml.safe_load(fh)))

    # concepts/
    concepts_dir = bodhi_dir / "concepts"
    if concepts_dir.is_dir():
        for f in sorted(concepts_dir.glob("*.yaml")):
            with open(f) as fh:
                data = yaml.safe_load(fh)
                result["concepts"].extend(parse_concepts(data))

    # channels/
    channels_dir = bodhi_dir / "channels"
    if channels_dir.is_dir():
        for f in sorted(channels_dir.glob("*.yaml")):
            with open(f) as fh:
                result["channels"].append(parse_channel(yaml.safe_load(fh)))

    # topology/
    topology_dir = bodhi_dir / "topology"
    if topology_dir.is_dir():
        for f in sorted(topology_dir.glob("*.yaml")):
            with open(f) as fh:
                result["topologies"].append(parse_topology(yaml.safe_load(fh)))

    return result
