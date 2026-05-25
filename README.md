<div align="center">
  <img src="images/bodhi.svg" width="160" alt="Bodhi DSL Logo">
  <h1>Bodhi DSL</h1>
  <p><strong>v0.1.1 — Early Preview</strong> | Solo research project. Development pace depends on availability. Issues and ideas welcome; response time is not guaranteed.</p>
  <p><em>The semantic layer between code and AI — making every codebase self-describing.</em></p>
</div>

**Bodhi DSL** is an AI-native semantic annotation protocol. It makes Claude Code **simultaneously write code and
structured DSL** — capturing business intent, data flows, service dependencies, event chains, error handling paths, and
state machines **at write time**, as a natural part of coding.

Static analysis can see *what* code does, but not *why*. Comments rot, docs drift, architecture diagrams go stale on day
one. Bodhi DSL solves this by making the AI that writes the code also write the semantics — inline `@bodhi.*` tags on
every function, plus `.bodhi/` system files that describe how services, entities, events, and state machines connect
across your entire system.

**The vision**: a world where every codebase carries a living, machine-readable knowledge graph — maintained by AI,
verified in CI, and consumed by AI agents for bug triage, impact analysis, cross-service tracing, and autonomous code
reasoning. Not documentation for humans to read and forget, but structured intelligence for AI to act on.

## Best For

Bodhi is designed for **AI-first projects** — codebases where AI writes the code from scratch. In this workflow, Claude
generates code and DSL annotations simultaneously, keeping semantics accurate and complete from day one.

For **existing / legacy projects**, use `/bodhi scan` to retrofit annotations from the current code state. Coverage and
accuracy depend on code complexity and style. Projects with heavy reflection, runtime wiring, or deep inheritance
hierarchies are harder for AI to annotate reliably. Treat results as a starting point that needs human review.

## Best Practices: How to Work with AI + Bodhi

Bodhi's design-first workflow works best when you **tell AI the whole picture first, not one step at a time**.

### Tell AI *what* you want, not *how* to implement it

```
❌ Bad — feeding implementation details one by one:

  "Create an OrderController with a POST /api/orders endpoint"
  (AI writes code)
  "Now add inventory deduction, call inventory-service via gRPC"
  (AI patches code)
  "Oh and publish an order_created event to Kafka"
  (AI patches again, YAML skeleton is incomplete or missing)

✅ Good — describe the business intent upfront:

  "Users place an order: deduct inventory (gRPC to inventory-service),
   hold payment (HTTP to payment-service), persist the order,
   and publish order_created to Kafka. Return 400 if inventory
   is insufficient, circuit-break on payment timeout."
```

When AI sees the full picture, it can design the complete YAML skeleton first — flows, entities, events, cross-service
dependencies, error handling — and then implement every function in one coherent pass. When it only sees one piece at a
time, each addition is a patch, and the skeleton is either incomplete or never created.

### Recommended workflow

```
Step 1 → /bodhi design <describe the full feature>
            AI produces YAML skeleton only, no code
            You review: are the flows, entities, events correct?

Step 2 → "Looks good, proceed to implement"
            AI writes code + inline tags, guided by the skeleton
            Hook validates consistency after every edit

Step 3 → Review the code as usual
```

You don't need to write a formal PRD. A few sentences describing the business intent, key operations, external
dependencies, and error scenarios is enough. The AI will ask if anything is ambiguous.

**Even without `/bodhi design`**, describing the feature in full triggers the same workflow automatically — Claude will
produce the skeleton and ask for confirmation before writing code. But the explicit command makes the separation
between "design" and "implement" clearer and gives you a natural review checkpoint.

## Why Bodhi

| Problem                                                      | Bodhi's Answer                                                                         |
|--------------------------------------------------------------|----------------------------------------------------------------------------------------|
| Static analysis sees *what*, not *why*                       | `@bodhi.intent` captures business purpose on every function                            |
| Architecture docs go stale on day one                        | `.bodhi/` YAML files are maintained by AI as code changes                              |
| Cross-service tracing requires runtime infra                 | `@bodhi.calls via`, `.bodhi/services/`, `.bodhi/events/` map the full topology at rest |
| Bug triage needs tribal knowledge                            | AI agents read the semantic graph to reason about failures autonomously                |
| "What does this service depend on?" requires asking 3 people | `depends_on` with protocols, APIs, and resilience policies — always up to date         |

## What It Does

### Layer 1: Inline Tags (every function)

Claude writes code and simultaneously adds `@bodhi.*` annotations in doc comments:

```java
/**
 * @bodhi.intent Create order, deduct inventory, publish domain event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct, PaymentService.hold
 * @bodhi.emits order_created(orderId, userId) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

### Layer 2: System Files (structural changes)

When Claude creates an API, a database model, or a state machine, it also writes the corresponding `.bodhi/` YAML:

```
.bodhi/
├── bodhi.yaml              # Project metadata (+ distributed block for microservices)
├── flows/create_order.yaml # Request-to-response call chains (supports cross-service steps)
├── entities/orders.yaml    # Database table semantics
├── states/order_lifecycle.yaml  # State machines
├── events/order_created.yaml   # Event catalog (producers/consumers)
├── services/order-service.yaml # Service topology — multi-protocol APIs (http, grpc, ws, etc.)
├── channels/order_ws.yaml  # Bidirectional channels (WebSocket, TCP, etc.)
├── topology/order_flow.yaml # Cross-service event chains
└── concepts/glossary.yaml  # Business glossary
```

Works with **Java, Python, Go, TypeScript, Kotlin, Rust, C#, C, C++**.

## Quick Start

### 1. Install into your project

Copy `CLAUDE.md`, the `/bodhi` slash command, and the validation hook into your project:

```bash
git clone https://github.com/anthropics/bodhi.git

# Rules file — Claude reads this on every conversation
cp bodhi/templates/CLAUDE.md /path/to/your-project/CLAUDE.md

# /bodhi slash command (design, init, scan, flows, concepts)
mkdir -p /path/to/your-project/.claude/commands
cp bodhi/templates/commands/bodhi.md /path/to/your-project/.claude/commands/

# PostToolUse hook — validates DSL after every Edit/Write
mkdir -p /path/to/your-project/.claude/hooks
cp bodhi/templates/.claude/settings.json /path/to/your-project/.claude/settings.json
cp bodhi/templates/.claude/hooks/bodhi-check.sh /path/to/your-project/.claude/hooks/
chmod +x /path/to/your-project/.claude/hooks/bodhi-check.sh

# Install bodhi-engine so the hook can run
pip install bodhi-engine
```

### 2. Use `/bodhi` commands

```
/bodhi design <description or file>             # Design YAML skeleton before coding (recommended)
/bodhi init                                     # Initialize .bodhi/ directory
/bodhi scan src/main/java/com/example/order/    # Add inline tags per directory
/bodhi flows                                    # Generate flow files
/bodhi concepts                                 # Generate glossary
```

**`/bodhi design` is the recommended way to start a new feature.** Describe what you want in natural language, and
Claude will produce the complete YAML skeleton (flows, entities, events, channels, topology) for your review before
writing any code. Even if you skip `/bodhi design` and describe the feature directly, Claude will automatically run the
design-first workflow — but the explicit command makes the intent clearer.

### 3. Validate in CI (optional)

```bash
pip install bodhi-engine
bodhi validate .
```

## CLI Reference

All commands accept `--exclude DIR1 DIR2` to skip scanning certain directories.

### Validation & Analysis

```bash
bodhi validate [path]              # Check DSL completeness and consistency (CI gate, exit 1 on errors)
bodhi check [path]                 # Check inline tags vs .bodhi/ YAML consistency
bodhi stats [path]                 # Output coverage statistics as JSON
bodhi score [path]                 # Compute AI-friendliness score (0-100, exits 1 if <60)
bodhi score [path] --json          # Same, JSON output for CI dashboards
bodhi derive [path]                # Scaffold .bodhi/ YAML from inline tags (cold-start)
```

`bodhi score` produces a weighted score across five dimensions (intent coverage, data-flow completeness, error handling, call-chain traceability, structural health), each with concrete reasons for any lost points. Suitable as a PR comment or README badge to track how AI-friendly a codebase is.

### PR Impact Analysis

```bash
bodhi impact-pr [path]                        # Analyse uncommitted changes
bodhi impact-pr [path] --base main            # Analyse changes since main
bodhi impact-pr [path] --base main --head dev # Analyse a specific range
git diff main...HEAD | bodhi impact-pr [path] # Pipe diff via stdin
```

Traces changed functions through the knowledge graph and outputs a Markdown impact report: affected flows, data
reads/writes, event impacts, cross-service dependencies, and risks. Designed to be posted as a PR comment — see [
`bodhi_app/templates/ci/bodhi-impact-pr.yml`](bodhi_app/templates/ci/bodhi-impact-pr.yml) for a ready-to-use GitHub
Actions workflow.

### Visualization

```bash
bodhi show -p <path> flow          # List all available flows
bodhi show -p <path> flow <name>   # Visualize a flow's call chain (colored terminal output)
bodhi show -p <path> stats         # Coverage dashboard with progress bars and completeness hints
bodhi arch [path]                  # Service topology — services, APIs, dependencies (colored terminal)
bodhi graph [path]                 # Generate Mermaid diagram for all flows (stdout)
bodhi graph [path] --flow <name>   # Generate Mermaid diagram for a single flow
bodhi graph [path] -o diagram.html # Render to HTML (zero dependencies, open in browser)
bodhi graph [path] -o diagram.svg  # Render to SVG/PNG/PDF (requires mmdc)
```

`bodhi show flow` renders a color-coded call chain in the terminal — each step shows function name, intent,
reads/writes, emits, on_fail, and cross-service calls. `bodhi show stats` displays a coverage dashboard with colored
progress bars for each tag type and hints about missing annotations.

`bodhi arch` renders the project's service topology in the terminal — one panel per service showing its APIs (with
protocol tags: http/grpc/websocket/tcp) and `depends_on` edges (including resilience policies and Kafka topics),
followed by a flat list of service-to-service edges with internal vs. external services color-coded.

`bodhi graph` generates Mermaid diagrams with color-coded nodes: green for entry points, blue for functions, orange for
database tables, purple for events, red dashed for remote calls. Rendering to SVG/PNG
requires [mermaid-cli](https://github.com/mermaid-js/mermaid-cli): `npm install -g @mermaid-js/mermaid-cli`

### MCP Server

```bash
bodhi serve [path]                 # Start MCP server for a single service
bodhi serve-all [path]             # Start federated MCP server for a multi-service workspace
```

Configure in Claude Code (`~/.claude/settings.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "bodhi": {
      "command": "bodhi",
      "args": [
        "serve",
        "/path/to/your-project"
      ]
    }
  }
}
```

Available MCP tools:

| Tool              | What It Does                                                                           | Example Question                                  |
|-------------------|----------------------------------------------------------------------------------------|---------------------------------------------------|
| `query_flow`      | Return a complete request-to-response call chain                                       | "How does the create order API work?"             |
| `trace_entity`    | Find all functions that read/write a given entity                                      | "What touches the `orders` table?"                |
| `find_consumers`  | Find all consumers of a given event                                                    | "What happens when `order_created` fires?"        |
| `impact_analysis` | Trace the blast radius of a change                                                     | "What breaks if I change `OrderService.create`?"  |
| `query_state`     | Return state machine transitions                                                       | "What are the valid transitions from PAID?"       |
| `service_deps`    | Return upstream/downstream service dependencies                                        | "What does order-service depend on?"              |
| `query_channel`   | Return a bidirectional channel definition                                              | "What events does the order WebSocket handle?"    |
| `query_topology`  | Return a cross-service event chain                                                     | "How does the order fulfillment event flow work?" |
| `list_*`          | List available flows, entities, events, services, state machines, channels, topologies | "What flows exist in this project?"               |

### Workspace (Multi-Service)

```bash
bodhi workspace-validate [path]    # Validate cross-service consistency (event schema mismatch, broken flow_ref, etc.)
```

### CI Integration

Ready-to-use GitHub Actions workflows are in [`bodhi_app/templates/ci/`](bodhi_app/templates/ci/):

- **[`bodhi-validate.yml`](bodhi_app/templates/ci/bodhi-validate.yml)** — validates DSL completeness on every PR
- **[`bodhi-impact-pr.yml`](bodhi_app/templates/ci/bodhi-impact-pr.yml)** — posts a Bodhi impact analysis comment on
  every PR (uses `bodhi impact-pr`)

Copy the one you need into your project's `.github/workflows/` directory.

```bash
cp bodhi/bodhi_app/templates/ci/bodhi-impact-pr.yml /path/to/your-project/.github/workflows/
```

`bodhi validate` exits with code 1 on errors, suitable as a CI gate. `bodhi stats` outputs JSON for dashboards or
coverage tracking.

## AI-Friendly Code Style

Bodhi doesn't just annotate code — it promotes a coding style that is **statically traceable from source text**. If AI
cannot determine the execution path by reading the source, the code is not AI-friendly.

**Core principles:**

- **Functions + modules over classes + inheritance** — direct calls are grepable; vtable dispatch is not
- **Explicit routing over polymorphism** — `if`/`switch`/`match` at the call site, every branch visible
- **Data structures over objects with behavior** — records / dataclasses / structs, not getter/setter mazes
- **Explicit dependencies over injection** — pass as parameters, not auto-wired by a container
- **`@bodhi.*` tags are remediation, not default** — write traceable code first; tag only unavoidable indirection

**Refactoring principle: extract into modules and functions, not into class hierarchies.**

- Extract function / module → good (preserves traceability)
- Extract interface for a single implementation → bad (adds indirection for no benefit)
- Replace `if`/`switch` with polymorphic dispatch → bad (hides routing)

Per-language rules for Java, Go, Python, Kotlin, TypeScript, Rust, C#, C, and C++ are in [
`templates/CLAUDE.md`](templates/CLAUDE.md).

## Tag Reference

### Core Tags (P0 — always add)

| Tag             | Purpose              | Example                                            |
|-----------------|----------------------|----------------------------------------------------|
| `@bodhi.intent` | Business purpose     | `@bodhi.intent Create order and deduct inventory`  |
| `@bodhi.reads`  | Data sources read    | `@bodhi.reads orders(id, status) WHERE userId = ?` |
| `@bodhi.writes` | Data targets written | `@bodhi.writes orders(status=PAID) via UPDATE`     |

### Relationship Tags (P1 — add when applicable)

| Tag              | Purpose            | Example                                               |
|------------------|--------------------|-------------------------------------------------------|
| `@bodhi.calls`   | Key function calls | `@bodhi.calls PaymentService.charge`                  |
| `@bodhi.emits`   | Events published   | `@bodhi.emits order_created(orderId) to kafka:orders` |
| `@bodhi.on_fail` | Error handling     | `@bodhi.on_fail timeout → retry 3 → reject 500`       |

### Constraint Tags (P2 — add if obvious)

| Tag                  | Purpose             | Example                                       |
|----------------------|---------------------|-----------------------------------------------|
| `@bodhi.auth`        | Auth requirements   | `@bodhi.auth required(role=ADMIN)`            |
| `@bodhi.validate`    | Validation rules    | `@bodhi.validate amount > 0`                  |
| `@bodhi.log.success` | Success log pattern | `@bodhi.log.success "Order {id} created"`     |
| `@bodhi.log.error`   | Error log pattern   | `@bodhi.log.error "Payment failed: {reason}"` |

## Project Structure

```
bodhi/
├── templates/
│   ├── CLAUDE.md                  # Put in your project → Claude writes DSL with code
│   └── commands/
│       └── bodhi.md               # /bodhi command (design, init, scan, flows, concepts)
├── bodhi_engine/                  # Core engine — parser, knowledge graph, validator
│   ├── parser/                    # Parses @bodhi.* tags and .bodhi/*.yaml
│   ├── validator/                 # Checks DSL completeness and consistency
│   ├── knowledge.py               # In-memory knowledge graph for queries
│   ├── deriver.py                 # Scaffold Layer 2 YAML from inline tags
│   └── workspace.py               # Multi-service workspace aggregation
├── bodhi_app/                     # Application layer — CLI, MCP, visualization
│   ├── cli/                       # CLI commands (validate, show, graph, impact-pr, etc.)
│   ├── mcp/                       # MCP server (single + federated workspace)
│   └── diagnose.py                # Log diagnosis
├── tests/                         # 228 tests
└── pyproject.toml
```

## Examples

### Flow Visualization (`bodhi show flow`)

Render a color-coded call chain in the terminal — each step shows function name, intent, data access, error handling,
and cross-service calls.

![bodhi show flow](images/flow.png)

### Coverage Dashboard (`bodhi show stats`)

See how well your codebase is annotated at a glance — progress bars per tag type, Layer 2 asset counts, and actionable
hints about missing annotations.

![bodhi show stats](images/status.png)

### Flow Graph (`bodhi graph`)

Generate visual call graphs from flow definitions — color-coded nodes for entry points, functions, database tables,
events, and remote calls. Tables sharing the same datasource are grouped together.

![bodhi graph](images/graph.png)

## Full Specification

See [bodhi-dsl-specification.md](bodhi_engine/docs/bodhi-dsl-specification.md) for the complete DSL specification.

## Roadmap

- [x] **PR Impact Report** — Auto-generate impact analysis on pull requests via GitHub Action ([details](roadmap/01-pr-impact-report.md))
- [x] **Cross-Service Validation** — Multi-repo workspace scanning with event schema diff, broken ref detection, and federated MCP server ([details](roadmap/02-cross-repo-registry.md))
- [x] **Git History DSL Import** — Reverse-generate Bodhi DSL from git history using AI, enabling Bodhi for existing projects ([details](roadmap/04-git-history-dsl-import.md))
- [ ] **Runtime Intelligence** — Connect Bodhi's knowledge graph to logs, databases, and traces for live operational analysis ([details](roadmap/03-runtime-intelligence.md))

## Architecture & Vision

See [architecture-and-vision.md](bodhi_engine/docs/architecture-and-vision.md) for the target architecture (MCP server),
future data sources (DB, logs, metrics, traces), and long-term vision (cross-repo tracing, intent-to-code generation,
living architecture diagrams).

## License

MIT
