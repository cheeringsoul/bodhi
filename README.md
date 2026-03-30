<div align="center">
  <img src="bodhi.svg" width="160" alt="Bodhi DSL Logo">
  <h1>Bodhi DSL</h1>
  <p><strong>v0.1.0 — Early Preview</strong> | Solo research project. Development pace depends on availability. Issues and ideas welcome; response time is not guaranteed.</p>
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
├── bodhi.yaml              # Project metadata
├── flows/create_order.yaml # Request-to-response call chains
├── entities/orders.yaml    # Database table semantics
├── states/order_lifecycle.yaml  # State machines
├── events/order_created.yaml   # Event catalog (producers/consumers)
├── services/order-service.yaml # Service topology (microservices)
└── concepts/glossary.yaml  # Business glossary
```

Works with **Java, Python, Go, TypeScript, Kotlin**.

## Quick Start

### 1. Enable DSL generation for new code

Copy `CLAUDE.md` and the Claude Code hook into your project. Claude Code reads `CLAUDE.md` on every conversation
and follows the DSL generation rules. The hook runs `bodhi validate` after every file edit, surfacing inconsistencies
immediately so Claude can fix them in the same session.

```bash
git clone https://github.com/anthropics/bodhi.git

# Rules file — Claude reads this on every conversation
cp bodhi/templates/CLAUDE.md /path/to/your-project/CLAUDE.md

# PostToolUse hook — validates DSL after every Edit/Write
mkdir -p /path/to/your-project/.claude/hooks
cp bodhi/templates/.claude/settings.json /path/to/your-project/.claude/settings.json
cp bodhi/templates/.claude/hooks/bodhi-check.sh /path/to/your-project/.claude/hooks/
chmod +x /path/to/your-project/.claude/hooks/bodhi-check.sh

# Install bodhi-engine so the hook can run
pip install bodhi-engine
```

### 2. Scan existing code (optional)

Copy the slash command into your project, then use it in Claude Code:

```bash
mkdir -p /path/to/your-project/.claude/commands
cp bodhi/templates/commands/bodhi-scan.md /path/to/your-project/.claude/commands/
```

```
/bodhi-scan init                                # Initialize .bodhi/ directory
/bodhi-scan src/main/java/com/example/order/    # Add inline tags per directory
/bodhi-scan flows                               # Generate flow files
/bodhi-scan concepts                            # Generate glossary
```

### 3. Validate in CI (optional)

```bash
pip install bodhi-engine
bodhi validate .
```

## CI Integration

Add to your GitHub Actions workflow:

```yaml
- name: Validate Bodhi DSL
  run: |
    pip install bodhi-engine
    bodhi validate .
```

`bodhi validate` exits with code 1 if there are errors (missing intent on write functions, entity references to
undefined tables, etc.), making it suitable as a CI gate.

`bodhi stats` outputs coverage as JSON:

```json
{
  "functions_with_bodhi_tags": 42,
  "functions_with_intent": 40,
  "functions_with_writes": 28,
  "flows": 8,
  "entities": 5,
  "state_machines": 2
}
```

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
│       └── bodhi-scan.md          # /bodhi-scan command for existing code
├── bodhi_engine/                  # pip install → bodhi validate in CI
│   ├── parser/                    # Parses @bodhi.* tags and .bodhi/*.yaml
│   ├── validator/                 # Checks DSL completeness and consistency
│   └── cli/                       # bodhi validate / bodhi stats
├── tests/                         # 38 tests
├── bodhi_dsl_specification.md     # Full DSL specification
└── pyproject.toml
```

## Full Specification

See [bodhi_dsl_specification.md](docs/bodhi_dsl_specification.md) for the complete DSL specification.

## Architecture & Vision

See [architecture-and-vision.md](docs/architecture-and-vision.md) for the target architecture (MCP server), future data sources (DB, logs, metrics, traces), and long-term vision (cross-repo tracing, intent-to-code generation, living architecture diagrams).

## License

MIT
