# Bodhi DSL — Code + DSL Co-generation Rules

## MANDATORY: Every Public Method MUST Have @bodhi.intent

**This is a hard rule, not a suggestion.** When you write or modify any public/exported function or method, you MUST add `@bodhi.intent` in its doc comment BEFORE moving on to the next task. Do NOT batch this — tag each method immediately as you write it.

**Checklist before finishing any code edit:**
1. Does every new or modified public method have `@bodhi.intent`? If not, add it now.
2. Does every method that reads data have `@bodhi.reads`? If not, add it now.
3. Does every method that writes data have `@bodhi.writes`? If not, add it now.

**Exceptions (no tags needed):**
- Simple getters / setters / toString / hashCode / equals
- Constructors
- Pure utility functions (string formatting, logging wrappers)
- Test code
- Configuration / startup boilerplate (e.g., `main()`, `@Configuration` classes)

**If you forget:** A post-edit hook will block you and list the methods missing tags. Fix them before continuing.

---

## Core Principle: Inline Tags Are the Source of Truth

Bodhi DSL has two layers, but only Layer 1 (inline tags) is written alongside code. Layer 2 (system YAML files) is derived from inline tags on demand — never maintained by hand during coding.

**When writing or modifying code:**
- Always add/update `@bodhi.*` inline tags in the doc comment of each function
- Do NOT manually create or update `.bodhi/flows/`, `.bodhi/states/`, `.bodhi/services/`, or `.bodhi/events/` YAML files

**When refactoring:**
- Update inline tags on affected methods — that's it

**If DSL is stale or missing:**
- Regenerate inline tags from the current code — don't try to patch them

### Layer 2 is Derived, Not Maintained

System-level views (flows, service topology, event chains, state machines) are **derived from inline tags** by running `/bodhi-scan`. You do NOT need to maintain them while writing code.

| System View | How It's Derived |
|-------------|------------------|
| Flow (request chain) | `@bodhi.calls` chain from entry point |
| Service topology | `@bodhi.calls ... via http/grpc` across services |
| Event chain | `@bodhi.emits` + `@bodhi.consumes` pairs |
| State machine | `@bodhi.writes table(status)` + transition logic |

**Only these are written alongside code:**

| Code Change | What to Write |
|-------------|---------------|
| Write/modify a function | `@bodhi.*` inline tags in its doc comment |
| Add/modify a DB table / ORM model | `.bodhi/entities/<table>.yaml` |
| Introduce a business term | `.bodhi/concepts/glossary.yaml` |
| Project initialization | `.bodhi/bodhi.yaml` |

---

## DSL-Friendly Code Conventions

To ensure generated code works well with Bodhi DSL parsing and validation, follow these rules:

### No Method Overloading

Do not use method overloading (multiple methods with the same name but different parameters). Bodhi DSL uses `ClassName.methodName` as the unique identifier — overloaded methods cause ambiguity.

- Bad: `create(Order)`, `create(BatchOrder)`
- Good: `createOrder(Order)`, `createBatchOrder(BatchOrder)`

If you absolutely must have similar methods, use distinct names with a business-meaningful suffix (e.g., `createSingle`, `createBatch`), not numeric suffixes.

### Prefer Explicit Over Framework Magic

- Avoid relying on implicit framework behaviors that are invisible in source code
- When using IoC/DI frameworks (Spring, Guice, etc.), place `@bodhi.*` tags on the **interface** method, not the implementation — callers depend on the interface
- For Spring Data / MyBatis repositories with no implementation class, tag the interface method directly:

```java
/**
 * @bodhi.intent Query orders by user ID, sorted by creation time desc
 * @bodhi.reads orders(id, userId, status, totalAmount) WHERE userId = ?
 */
List<Order> findByUserIdOrderByCreatedAtDesc(String userId);
```

### Make Event Chains Explicit

Framework-managed event dispatch (e.g., `ApplicationEventPublisher`, `@EventListener`) breaks static call chains. Always use `@bodhi.emits` and `@bodhi.consumes` to make these connections visible:

```java
// Publisher
/** @bodhi.emits order_created(orderId) to internal */
public void create(...) {
    eventPublisher.publishEvent(new OrderCreatedEvent(...));
}

// Consumer
/** @bodhi.consumes order_created(orderId) from internal */
@EventListener
public void onOrderCreated(OrderCreatedEvent event) { ... }
```

Use `to internal` / `from internal` for in-process event buses, and `to kafka:<topic>` / `from kafka:<topic>` for message queues.

---

## Layer 1: Inline Tags (every function you write)

Add `@bodhi.*` tags in the doc comment of each function/method.

### Required Tags

| Tag | When to Add | Description |
|-----|-------------|-------------|
| `@bodhi.intent` | **Every function** | One-line business intent in business language, don't restate the code |
| `@bodhi.reads` | When reading data | What is read: `request.body(fields)`, `table(fields)`, `cache:key(fields)` |
| `@bodhi.writes` | When writing data | What is written: `table(fields) via INSERT/UPDATE/DELETE`, `response(code, fields)` |
| `@bodhi.calls` | When making key calls | Only list business-critical calls. Format: `ClassName.method [via protocol]`. Remote calls must add `via http:POST /path` or `via grpc` |
| `@bodhi.emits` | When publishing events | `event_name(payload_fields) [to destination]` — don't miss MQ/EventBus/WebSocket |
| `@bodhi.consumes` | When consuming events | `event_name(payload_fields) [from source]` — declare what event triggers this function |
| `@bodhi.on_fail` | When handling errors | `condition → action`, chainable: `retry 3 → reject 500`. Supports `circuit_breaker(...)`, `degrade(...)` for microservice resilience |

### Optional Tags (add when applicable)

- `@bodhi.auth required|public|required(role=X)`
- `@bodhi.validate <rule>`
- `@bodhi.log.success "<pattern>"`
- `@bodhi.log.error "<pattern>" [severity=level]`
- `@bodhi.metric <name> [threshold]`
- `@bodhi.idempotent key=<fields>`
- `@bodhi.ratelimit <rate> per <scope>`

### Language Adaptation

**Java/Kotlin/TypeScript**: Place in `/** */` JSDoc/Javadoc
**Python**: Place in `"""` docstring
**Go**: Place in `//` line comments

### Example

```java
/**
 * @bodhi.intent Create order, deduct inventory, publish domain event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct via grpc:InventoryService/Deduct
 * @bodhi.calls PaymentService.hold via http:POST /api/payments/hold
 * @bodhi.emits order_created(orderId, userId) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 * @bodhi.on_fail payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

---

## Layer 2: System Files

Layer 2 files live in `.bodhi/` and fall into two categories:

### Written alongside code (manual)

These are created/updated when you write the corresponding code:

- `.bodhi/bodhi.yaml` — project metadata (create once on init)
- `.bodhi/entities/<table>.yaml` — database table schemas (when you add/modify ORM models or DDL)
- `.bodhi/concepts/glossary.yaml` — business term definitions (when domain terms appear in code)

### Derived from inline tags (automatic via `/bodhi-scan`)

These are NOT maintained during coding. Run `/bodhi-scan flows` or `/bodhi-scan` to generate them from inline tags:

- `.bodhi/flows/<name>.yaml` — derived from `@bodhi.calls` chains starting at entry points
- `.bodhi/states/<name>.yaml` — derived from `@bodhi.writes table(status)` + transition logic
- `.bodhi/events/<name>.yaml` — derived from `@bodhi.emits` + `@bodhi.consumes` pairs
- `.bodhi/services/<name>.yaml` — derived from `@bodhi.calls ... via http/grpc` across services

**Do NOT manually create or update flows, states, events, or services YAML files while writing code.** They will be regenerated from inline tags and will overwrite manual edits.

### Entity File — `.bodhi/entities/<table>.yaml`

When you create a database table / ORM model:

```yaml
table: orders
description: Core orders table
database: mongodb          # mysql | postgresql | mongodb | redis

fields:
  - name: id
    type: bigint
    description: Order primary key
    primary_key: true
  - name: status
    type: int
    description: Order status
    state_machine: order_lifecycle    # Link to state machine if stateful
    enum:
      0: INIT
      1: PAID
      3: SHIPPED
      4: COMPLETED
      5: CANCELLED
  - name: phone
    type: string
    description: User contact phone
    sensitive: true                   # PII sensitive data flag

indexes:
  - name: idx_user_status
    fields: [user_id, status]
    description: User order list query

relations:
  - target: order_items
    type: one_to_many
    join: orders.id = order_items.order_id
  - target: users
    type: many_to_one
    join: orders.user_id = users.id
```

### Project Metadata — `.bodhi/bodhi.yaml`

Create once on project initialization:

```yaml
version: "0.1.0"
project:
  name: "your-project-name"
  description: "Project description"
  languages: [java]
  frameworks: [spring-boot, mybatis]

inline:
  java: javadoc
  python: docstring
  go: line_comment
  typescript: jsdoc
```

---

## Decision Tree

**Not sure whether to write DSL? Use this decision tree:**

1. Did you write or modify a function? → Add Layer 1 inline tags (`@bodhi.intent` + relevant tags)
2. Did you create or modify a database table / ORM model? → Update `.bodhi/entities/`
3. Did you introduce a new business term? → Update `.bodhi/concepts/`

**What does NOT need DSL:**
- Pure utility functions (format, log wrapper, string utils)
- Simple getters/setters
- Test code
- Configuration / startup classes

**What is derived automatically (do NOT write by hand):**
- `.bodhi/flows/` — run `/bodhi-scan flows` to generate
- `.bodhi/states/` — run `/bodhi-scan` to generate
- `.bodhi/events/` — run `/bodhi-scan` to generate
- `.bodhi/services/` — run `/bodhi-scan` to generate
