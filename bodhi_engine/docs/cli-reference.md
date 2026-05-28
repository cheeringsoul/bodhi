# Bodhi Engine — CLI Reference

bodhi_engine provides the core DSL analysis toolkit: parsing, validation, visualization, and scaffolding. These commands
work on inline `@bodhi.*` tags and `.bodhi/` YAML files directly — no knowledge graph or runtime intelligence required.

## Commands

All commands accept `--exclude DIR1 DIR2` to skip directories during scanning.

### `bodhi lint [path]`

Run rule checks on Bodhi DSL — completeness, dangling references, missing definitions. Exits with code 1 on errors —
suitable as a CI gate. (Previously named `bodhi validate`; the old name still works as a deprecated alias.)

Checks include:

- Functions with `@bodhi.reads`/`@bodhi.writes` but no `@bodhi.intent` (error)
- Dangling `@bodhi.calls` references (warning)
- Missing entity definitions in `.bodhi/entities/` (warning)
- Flow steps referencing functions without inline tags (warning)
- Event references without `.bodhi/events/` definitions (warning)
- State machine transition functions not in any flow (info)

```bash
bodhi lint .
bodhi lint /path/to/project --exclude frontend admin-ui
```

### `bodhi reconcile [path]`

Reconcile Layer 1 (inline `@bodhi.*` tags) against Layer 2 (`.bodhi/` YAML files). Compares what the inline tags
declare (reads, writes, calls, emits) against what the YAML flows, events, and entities describe — flagging anything
that is in one layer but missing or mismatched in the other. (Previously named `bodhi check`; the old name still works
as a deprecated alias.)

```bash
bodhi reconcile .                # show errors + warnings
bodhi reconcile . --errors-only  # suppress warnings (summary line still shows totals)
```

Exits non-zero only when errors are present — warnings never fail the command. Use `--errors-only` to cut through
noisy "entry point not in any flow YAML" warnings when you only care about hard inconsistencies.

### `bodhi stats [path]`

Output coverage statistics as JSON. Reports how many functions have each tag type and counts of Layer 2 assets (flows,
entities, events, etc.).

```bash
bodhi stats .
```

Example output:

```json
{
  "functions_with_bodhi_tags": 42,
  "functions_with_intent": 40,
  "functions_with_reads": 28,
  "functions_with_writes": 22,
  "flows": 5,
  "entities": 8,
  "state_machines": 2
}
```

### `bodhi derive [path]`

Scaffold `.bodhi/` YAML files from inline tags (cold-start). Traces `@bodhi.calls` chains to infer flows, collects
`@bodhi.emits`/`@bodhi.consumes` to infer events, and detects remote calls to infer service dependencies.

Use this when retrofitting an existing codebase that already has inline tags but no YAML files yet.

```bash
bodhi derive .
```

### `bodhi show flow [name]`

Visualize a flow's call chain as a color-coded terminal display. Each step shows function name, intent, reads/writes,
emits, on_fail, and cross-service calls.

```bash
bodhi show -p /path/to/project flow              # List all flows
bodhi show -p /path/to/project flow create_order  # Show specific flow
```

### `bodhi show stats`

Coverage dashboard with colored progress bars per tag type, Layer 2 asset counts, and hints about missing annotations.

```bash
bodhi show -p /path/to/project stats
```

### `bodhi graph [path]`

Generate Mermaid diagrams from `.bodhi/flows/` definitions. Color-coded nodes: green for entry points, blue for
functions, orange for database tables, purple for events, red dashed for remote calls. Tables sharing the same
datasource are grouped into subgraphs.

```bash
bodhi graph .                              # All flows to stdout
bodhi graph . --flow create_order          # Single flow
bodhi graph . -o diagram.html              # Render to HTML (zero dependencies)
bodhi graph . -o diagram.svg               # Render to SVG (requires mmdc)
```

Rendering to SVG/PNG requires [mermaid-cli](https://github.com/mermaid-js/mermaid-cli):
`npm install -g @mermaid-js/mermaid-cli`

### `bodhi overview [path]`

High-level bird's-eye view of the project — answers "what does this project look like at a glance" without diving
into individual service detail. Aggregates `.bodhi/` data into a layered diagram:

```
Entry Points  →  Flows  →  Storage / Events / Externals
```

- **Entry Points**: every `apis` entry from `.bodhi/services/*.yaml` plus any `entry` block from flow files (protocol-tagged: http/grpc/ws/mq/cron)
- **Flows**: comma-separated list of flow names from `.bodhi/flows/`
- **Storage**: entities grouped by `datasource`/`database`
- **Events**: events grouped by channel (kafka:topic, internal, etc.)
- **Externals**: `depends_on` services not owned by this workspace

```bash
bodhi overview .
```

Use `bodhi overview` for onboarding, PR descriptions, and "where do I add this feature". Use `bodhi arch` when you
need service-level detail (APIs, resilience, dependencies).

### `bodhi arch [path]`

Visualize the project's service topology in the terminal — one panel per service from `.bodhi/services/*.yaml`,
followed by a flat list of service-to-service edges. Designed for a fast architectural overview without leaving the
shell.

Each service panel shows:

- description, port, `tech_stack`
- APIs with protocol tags (http=cyan, grpc=green, websocket=magenta, tcp=yellow, jsonrpc=blue)
- `depends_on` edges with their protocol, `apis`/`topics`, and `resilience` policies (timeout / retry / circuit breaker)

The topology section below lists every `src ──protocol──▶ dst` edge. Services defined in `.bodhi/services/` render in
cyan; unknown dependencies (e.g. `kafka`, third-party services) render in yellow with an `(external)` tag.

```bash
bodhi arch .
```

### `bodhi workspace-validate [path]`

Validate cross-service consistency in a multi-service workspace. Scans all subdirectories for `.bodhi/` folders, merges
their metadata, and checks for:

- Event schema mismatches between producer and consumer
- Broken `flow_ref` references across services
- Events with no consumers
- Unknown service dependencies

```bash
bodhi workspace-validate /path/to/workspace
```

Example output:

```
Errors (1):
  [error] event-schema-mismatch (payment-service): Event 'order_created' has
    inconsistent schema between order-service and payment-service.
    fields in order-service but not payment-service: ['userId'];
    fields in payment-service but not order-service: ['buyerId']
Warnings (2):
  [warning] event-no-consumer: Event 'payment_completed' has producers but no consumers
  [warning] unknown-dependency (order-service): Service 'order-service' depends on
    'kafka' which is not found in workspace
```

## Module Structure

```
bodhi_engine/
├── parser/
│   ├── inline.py          # Parse @bodhi.* tags from source code
│   └── yaml_parser.py     # Parse .bodhi/*.yaml files
├── validator/
│   └── checker.py         # DSL completeness and consistency checks
├── cli/
│   ├── graph.py           # Mermaid diagram generation
│   ├── show.py            # Terminal visualization for flows / coverage (Rich)
│   ├── arch.py            # Terminal visualization for service topology (Rich)
│   └── overview.py        # Terminal visualization for layered project overview (Rich)
├── knowledge.py           # In-memory knowledge graph and query engine
├── deriver.py             # Scaffold YAML from inline tags
└── workspace.py           # Multi-service workspace aggregation
```

## Separation from bodhi_app

bodhi_engine is the foundation layer. It parses, validates, and visualizes Bodhi DSL data. It has no dependency on
bodhi_app.

bodhi_app builds on top of the engine to provide higher-level capabilities: MCP servers, log diagnosis, PR impact
analysis, and the unified CLI entry point that assembles all commands.
