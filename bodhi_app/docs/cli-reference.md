# Bodhi App — CLI Reference

bodhi_app is the application layer built on top of bodhi_engine. It provides higher-level capabilities that leverage the
knowledge graph for runtime intelligence: MCP servers for AI assistants, log-driven diagnosis, and PR impact analysis.

bodhi_app also provides the unified CLI entry point (`bodhi` command) that assembles both engine-level and app-level
commands into a single interface.

## Commands

### `bodhi impact-pr [path]`

Analyse a git diff and produce a Markdown impact report. Traces changed functions through the knowledge graph to
identify affected flows, data reads/writes, event impacts, cross-service dependencies, and risks.

Designed to be posted as a PR comment — see [`templates/ci/bodhi-impact-pr.yml`](../templates/ci/bodhi-impact-pr.yml)
for a ready-to-use GitHub Actions workflow.

```bash
bodhi impact-pr .                                # Analyse uncommitted changes
bodhi impact-pr . --base main                    # Changes since main
bodhi impact-pr . --base main --head feature     # Specific range
git diff main...HEAD | bodhi impact-pr .         # Pipe diff via stdin
```

**How it works:**

1. `git diff` identifies changed source files and line ranges
2. Inline parser matches changed lines to `@bodhi.*`-annotated functions
3. Knowledge graph traces: changed function → flows → entities → events → services → state machines
4. Heuristic risk assessment (event schema changes affecting consumers, missing resilience config, etc.)
5. Renders a Markdown report with the full impact chain

**Example output:**

```markdown
## Bodhi Impact Analysis

### Changed functions

- `OrderService.create` (modified) — Create order, deduct inventory, publish domain event

### Affected flows

- `create_order` (POST /api/orders) — this is the entry point

### Data impact

- Writes to: `orders(id, userId, totalAmount, status=PENDING) via INSERT`
- Reads from: `request.body(userId, items, address)`

### Event impact

- Produces: `order_created` → kafka:order-events
    - Consumed by: `NotificationHandler.onOrderCreated`

### Cross-service dependencies

- Calls: `inventory-service` via grpc (InventoryService/DeductStock)

### Risks

- `order_created` event schema change will affect 1 downstream consumer(s)
```

### `bodhi serve [path]`

Start a single-service MCP server for AI coding assistants. Exposes the project's knowledge graph via
the [Model Context Protocol](https://modelcontextprotocol.io/).

```bash
bodhi serve /path/to/project
```

Available MCP tools:

| Tool              | Description                                            |
|-------------------|--------------------------------------------------------|
| `query_flow`      | Return a complete request-to-response call chain       |
| `trace_entity`    | Find all functions that read/write a given entity      |
| `find_consumers`  | Find all consumers of a given event                    |
| `impact_analysis` | Trace the blast radius of a change                     |
| `query_state`     | Return state machine transitions                       |
| `service_deps`    | Return upstream/downstream service dependencies        |
| `query_channel`   | Return a bidirectional channel definition              |
| `query_topology`  | Return a cross-service event chain                     |
| `list_*`          | List available flows, entities, events, services, etc. |

See [mcp-server-guide.md](mcp-server-guide.md) for configuration details.

### `bodhi serve-all [path]`

Start a federated MCP server for a multi-service workspace. Scans all subdirectories for `.bodhi/` folders, merges their
metadata, and exposes cross-service query tools.

```bash
bodhi serve-all /path/to/workspace
```

Additional tools beyond single-service:

| Tool                | Description                                                  |
|---------------------|--------------------------------------------------------------|
| `list_services`     | List all services in the workspace                           |
| `list_all_flows`    | List all flows across all services                           |
| `list_all_events`   | List all events across all services                          |
| `trace_event_chain` | Trace an event across service boundaries                     |
| `event_schema_diff` | Check event schema consistency between producer and consumer |

See [workspace-guide.md](workspace-guide.md) for workspace setup.

## CI Integration

Ready-to-use GitHub Actions workflow templates are in [`templates/ci/`](../templates/ci/):

- **`bodhi-validate.yml`** — runs `bodhi validate` on every PR to check DSL completeness
- **`bodhi-impact-pr.yml`** — runs `bodhi impact-pr` on every PR and posts the impact report as a comment

Copy into your project's `.github/workflows/` directory:

```bash
cp bodhi_app/templates/ci/bodhi-impact-pr.yml /path/to/your-project/.github/workflows/
```

## Module Structure

```
bodhi_app/
├── cli/
│   ├── main.py            # Unified CLI entry point (assembles all commands)
│   └── impact_pr.py       # PR impact analysis
├── mcp/
│   ├── server.py          # Single-service MCP server
│   └── workspace_server.py # Federated multi-service MCP server
├── templates/
│   └── ci/                # GitHub Actions workflow templates
│       ├── bodhi-validate.yml
│       └── bodhi-impact-pr.yml
├── diagnose.py            # Log-driven diagnosis
└── docs/
```

## Separation from bodhi_engine

bodhi_engine provides the foundation: parsing, validation, visualization, scaffolding, and the in-memory knowledge
graph. It has no dependency on bodhi_app.

bodhi_app depends on bodhi_engine and adds:

- **MCP servers** — expose the knowledge graph to AI assistants via Model Context Protocol
- **Log diagnosis** — match log snippets against `@bodhi.log.*` patterns to identify failures and trace impact
- **PR impact analysis** — analyse git diffs through the knowledge graph to produce impact reports
- **Git history DSL import** — reverse-generate `@bodhi.*` annotations from git history using AI
- **CI templates** — ready-to-use GitHub Actions workflows
- **Unified CLI** — the `bodhi` command that assembles engine and app commands into a single interface
