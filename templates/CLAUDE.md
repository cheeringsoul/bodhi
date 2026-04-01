# Bodhi DSL — Code + DSL Co-generation Rules

## CRITICAL: DSL-First Workflow

When implementing a new feature, API endpoint, or event-driven workflow, you MUST design before coding:

1. **Design the flow** — create/update `.bodhi/flows/<name>.yaml` with entry point, steps, entities, events
2. **Define entities** — create/update `.bodhi/entities/<table>.yaml` for any new tables
3. **Define events** — create/update `.bodhi/events/<name>.yaml` for any new events
4. **Implement** — write each method with inline tags + code together (see Co-generation below)
5. **Validate** — the post-edit hook will verify completeness automatically

Do NOT jump straight to writing code. The flow YAML is your contract.

**When to use DSL-first:** new features, new API endpoints, new event workflows, new service integrations.
**When to skip (just co-generate):** bug fixes, refactoring without behavior change, adding a field, performance optimization.

---

## MANDATORY: Every Public Method MUST Have @bodhi.intent

**This is a hard rule, not a suggestion.** When you write or modify any public/exported function or method, you MUST add `@bodhi.intent` in its doc comment BEFORE moving on to the next task. Do NOT batch this — tag each method immediately as you write it.

**Exceptions (no tags needed):**
- Simple getters / setters / toString / hashCode / equals
- Constructors
- Pure utility functions (string formatting, logging wrappers)
- Test code
- Configuration / startup boilerplate (e.g., `main()`, `@Configuration` classes)

**If you forget:** A post-edit hook will block you and list the methods missing tags. Fix them before continuing.

---

## Self-Check: 6 Questions Before Moving to Next Method

After writing each method, answer these questions. If the answer is "yes" but the tag is missing, add it NOW:

1. Does this method read external input (request, DB, cache)? → Need `@bodhi.reads`
2. Does this method write to storage (DB, cache, file)? → Need `@bodhi.writes`
3. Does this method call another service or key internal method? → Need `@bodhi.calls`
4. Does this method publish an event (MQ, EventBus, WebSocket)? → Need `@bodhi.emits`
5. Does this method consume an event? → Need `@bodhi.consumes`
6. Can this method fail in a business-meaningful way? → Need `@bodhi.on_fail`

---

## What Complete DSL Looks Like (vs Incomplete)

❌ **WRONG — intent only, everything else missing:**

```java
/**
 * @bodhi.intent Create order
 */
public OrderResponse create(CreateOrderRequest req) {
    Order order = new Order(req.getUserId(), req.getItems());
    orderRepository.save(order);
    inventoryService.deduct(order.getItems());
    paymentService.hold(order.getTotalAmount());
    kafkaTemplate.send("order-events", new OrderCreatedEvent(order));
    return new OrderResponse(order.getId());
}
```

This method reads request body, writes to DB, calls two services, emits an event, and can fail — but only has `@bodhi.intent`. The deriver gets almost nothing useful.

✅ **CORRECT — all relevant tags present:**

```java
/**
 * @bodhi.intent Create order, deduct inventory, hold payment, publish event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct via grpc:InventoryService/Deduct
 * @bodhi.calls PaymentService.hold via http:POST /api/payments/hold
 * @bodhi.emits order_created(orderId, userId, totalAmount) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 * @bodhi.on_fail payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503
 */
public OrderResponse create(CreateOrderRequest req) {
    // implementation...
}
```

---

## Layer 1: Inline Tags

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
- `@bodhi.implements <InterfaceName>` — on implementation classes, back-link to the interface
- `@bodhi.log.success "<pattern>"`
- `@bodhi.log.error "<pattern>" [severity=level]`
- `@bodhi.metric <name> [threshold]`
- `@bodhi.idempotent key=<fields>`
- `@bodhi.ratelimit <rate> per <scope>`

### Language Adaptation

**Java/Kotlin/TypeScript**: Place in `/** */` JSDoc/Javadoc
**Python**: Place in `"""` docstring
**Go**: Place in `//` line comments

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
    state_machine: order_lifecycle
    enum:
      0: INIT
      1: PAID
      3: SHIPPED
      4: COMPLETED
      5: CANCELLED
  - name: phone
    type: string
    description: User contact phone
    sensitive: true

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

## DSL-Friendly Code Conventions

### No Method Overloading

Do not use method overloading. Bodhi DSL uses `ClassName.methodName` as the unique identifier — overloaded methods cause ambiguity.

- Bad: `create(Order)`, `create(BatchOrder)`
- Good: `createOrder(Order)`, `createBatchOrder(BatchOrder)`

### Keep Call Chains Traceable

The goal: anyone (human or AI) reading the code can follow the full flow from entry point to every downstream call without guessing which implementation runs.

**Rule: Do not hide business-critical branching behind interface polymorphism.**

If a method dispatches to different implementations based on runtime conditions (strategy pattern, multi-tenant adapters, payment channels, etc.), make the routing explicit in the caller:

❌ Bad — AI sees `payService.pay()` but can't tell which implementation runs:

```java
// payService is injected as PayService interface — 3 implementations exist
public OrderResponse create(CreateOrderRequest req) {
    payService.pay(req.getPayment());
}
```

✅ Good — routing logic is visible, each branch is a concrete call:

```java
/**
 * @bodhi.calls WechatPayService.pay via http:POST /v3/pay/transactions
 * @bodhi.calls AlipayPayService.pay via http:POST /gateway.do
 */
public OrderResponse create(CreateOrderRequest req) {
    switch (req.getChannel()) {
        case WECHAT -> wechatPayService.pay(req.getPayment());
        case ALIPAY -> alipayPayService.pay(req.getPayment());
    }
}
```

**When interface polymorphism is acceptable:**
- Repository / DAO interfaces (Spring Data, MyBatis) — only one implementation, framework-generated
- Pure infrastructure (logging, metrics, caching) — not part of business flow
- Single implementation behind an interface for testability

For these cases:
- Place `@bodhi.*` tags on the interface method
- Add `@bodhi.implements` on the implementation class to create a back-link
- Name implementation classes as `XxxImpl` or `DefaultXxx` (consistent naming convention)

```java
// OrderService.java (interface — tags go here)
/**
 * @bodhi.intent Create order, deduct inventory, publish event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct
 */
OrderResponse create(CreateOrderRequest req);

// OrderServiceImpl.java (implementation — back-link only)
/**
 * @bodhi.implements OrderService
 */
@Service
public class OrderServiceImpl implements OrderService {
    @Override
    public OrderResponse create(CreateOrderRequest req) {
        // actual logic here, no @bodhi.* tags needed on methods
    }
}
```

This gives bidirectional traceability: interface → Impl via naming convention, Impl → interface via `@bodhi.implements`.

**In short: if there's only one implementation, interface is fine — tag the interface, back-link the Impl. If there are multiple, make the routing explicit.**

### Make Event Chains Explicit

Framework-managed event dispatch breaks static call chains. Always use `@bodhi.emits` and `@bodhi.consumes`:

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

## Decision Tree

1. Did you write or modify a function? → Add Layer 1 inline tags (`@bodhi.intent` + relevant tags)
2. Did you create or modify a database table / ORM model? → Update `.bodhi/entities/`
3. Did you introduce a new business term? → Update `.bodhi/concepts/`

**What does NOT need DSL:**
- Pure utility functions (format, log wrapper, string utils)
- Simple getters/setters
- Test code
- Configuration / startup classes
