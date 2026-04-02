Design the YAML skeleton for a new feature BEFORE writing any code. This command implements the DSL-First workflow.

## Input

$ARGUMENTS is a natural language description of the feature to design. Examples:
- `用户下单后扣库存冻结金额发order_created事件到Kafka`
- `Add a payment callback endpoint that receives webhook from payment gateway, updates order status, and notifies user`
- `WebSocket endpoint for real-time order status push to mobile clients`

## Execution Rules

### Step 1: Analyze the requirement

Read the requirement and identify:
- **Entry points**: What triggers this feature? (HTTP API, gRPC, MQ consumer, WebSocket, scheduler, etc.)
- **Data writes**: What tables/entities are created or modified?
- **Data reads**: What existing data is needed?
- **Cross-service calls**: Does this call other services? Via what protocol?
- **Events**: Are domain events published? Does this consume events from other services?
- **Channels**: Is there bidirectional communication (WebSocket, Socket)?
- **Error scenarios**: What can fail? How should each failure be handled?
- **State transitions**: Does this change an entity's status field?

Present this analysis to the user as a bullet list. Wait for confirmation before proceeding to Step 2.

### Step 2: Generate YAML skeleton

Based on the confirmed analysis, generate the following files (only the ones that are relevant):

#### Flow — `.bodhi/flows/<name>.yaml`

```yaml
name: <snake_case_name>
description: <one line>

entry:
  type: <http|grpc|mq_consumer|event|scheduler|websocket>
  method: <METHOD>      # if HTTP/gRPC
  path: <path>          # if HTTP/WebSocket

steps:
  - fn: <ClassName.methodName>
    intent: <what this step does>
    reads: [...]
    writes: [...]
    calls: [...]
    emits: [...]
    on_fail: [...]

  # For cross-service calls, include remote fields:
  - fn: <RemoteService.method>
    remote: <service-name>
    protocol: <http|grpc|...>
    api: <API identifier>
    flow_ref: <service:flow_name>
    intent: <what this step does>
    on_fail: [...]

entities: [...]
events: [...]
```

#### Entity — `.bodhi/entities/<table>.yaml` (only for NEW tables)

```yaml
table: <table_name>
description: <one line>
database: <mysql|postgresql|mongodb|redis>
datasource: <connection_name>    # if multiple datasources

fields:
  - name: <field>
    type: <type>
    description: <meaning>
    primary_key: true/false
    sensitive: true/false         # PII fields
    state_machine: <name>         # if this is a status field

relations: [...]
```

#### Event — `.bodhi/events/<name>.yaml` (only for NEW events)

```yaml
name: <event_name>
description: <one line>
channel: <kafka:topic|rabbitmq:queue|internal|...>

schema:
  - field: <name>
    type: <type>

producers:
  - fn: <ClassName.methodName>
    flow: <flow_name>

consumers:
  - fn: <ClassName.methodName>
    description: <what the consumer does>
```

#### Channel — `.bodhi/channels/<name>.yaml` (only for WebSocket/Socket/bidirectional)

```yaml
name: <channel_name>
protocol: <websocket|tcp|sse>
path: <path>
description: <one line>

inbound_events:
  - name: <event_name>
    description: <what>
    schema: [...]
    triggers_flow: <flow_name>

outbound_events:
  - name: <event_name>
    description: <what>
    schema: [...]
    triggered_by:
      - event: <internal_event>
        from: <source>
```

#### Topology — `.bodhi/topology/<name>.yaml` (only if events cross service boundaries)

```yaml
name: <chain_name>
description: <one line>

chains:
  - event: <event_name>
    channel: <channel>
    producer: <service-name>
    consumers:
      - service: <service-name>
        fn: <handler_fn>
        action: <what it does>
        emits: <downstream_event>   # if it triggers another event
```

#### State Machine — `.bodhi/states/<name>.yaml` (only if a new status field is introduced)

```yaml
name: <lifecycle_name>
entity: <table_name>
field: status
description: <one line>

states:
  - id: <STATE>
    value: <int>
    description: <meaning>
    transitions:
      - target: <NEXT_STATE>
        trigger: <what causes this>
        fn: <ClassName.methodName>
```

#### Service manifest — `.bodhi/services/<name>.yaml`

If the feature adds new APIs or dependencies, update the existing service file. Do NOT regenerate the whole file — only add the new entries under `apis` or `depends_on`.

### Step 3: Present and confirm

After generating all YAML files:

1. List all files created/updated
2. Show a summary: "This feature involves X steps, Y entities, Z events"
3. Ask the user: **"YAML skeleton is ready. Should I proceed to implement the code?"**

### IMPORTANT

- Do NOT write any source code (Java/Python/Go/TypeScript/etc.) in this command
- Do NOT generate inline @bodhi.* tags — those come during implementation
- ONLY produce .bodhi/ YAML files
- If `.bodhi/bodhi.yaml` does not exist, run `/bodhi-scan init` first
- Read existing `.bodhi/` files to avoid duplicating entities, events, or state machines that already exist
- For cross-service features, always check if topology files need updating
