# Bodhi Engine — CLI Reference

bodhi_engine provides the core DSL analysis toolkit: parsing, validation, visualization, and scaffolding. These commands
work on inline `@bodhi.*` tags and `.bodhi/` YAML files directly — no knowledge graph or runtime intelligence required.

## Commands

All commands accept `--exclude DIR1 DIR2` to skip directories during scanning.

### `bodhi validate [path]`

Check DSL completeness and consistency. Exits with code 1 on errors — suitable as a CI gate.

Checks include:

- Functions with `@bodhi.reads`/`@bodhi.writes` but no `@bodhi.intent` (error)
- Dangling `@bodhi.calls` references (warning)
- Missing entity definitions in `.bodhi/entities/` (warning)
- Flow steps referencing functions without inline tags (warning)
- Event references without `.bodhi/events/` definitions (warning)
- State machine transition functions not in any flow (info)

```bash
bodhi validate .
bodhi validate /path/to/project --exclude frontend admin-ui
```

### `bodhi check [path]`

Check consistency between inline tags and `.bodhi/` YAML files. Compares what the inline tags declare (reads, writes,
calls, emits) against what the YAML flows, events, and entities describe.

```bash
bodhi check .
```

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
│   └── show.py            # Terminal visualization (Rich)
├── knowledge.py           # In-memory knowledge graph and query engine
├── deriver.py             # Scaffold YAML from inline tags
└── workspace.py           # Multi-service workspace aggregation
```

## Separation from bodhi_app

bodhi_engine is the foundation layer. It parses, validates, and visualizes Bodhi DSL data. It has no dependency on
bodhi_app.

bodhi_app builds on top of the engine to provide higher-level capabilities: MCP servers, log diagnosis, PR impact
analysis, and the unified CLI entry point that assembles all commands.
