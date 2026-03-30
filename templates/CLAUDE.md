# Bodhi DSL — Code + DSL Co-generation Rules

## Core Principle: DSL is Generated, Not Maintained

**DSL is a byproduct of code generation.** When you write or modify code, generate the corresponding DSL at the same time. DSL is never "maintained" separately — if it becomes outdated, it is regenerated from the current code.

- When writing new code: generate inline `@bodhi.*` tags and `.bodhi/` YAML files alongside the code
- When modifying code: regenerate the affected DSL to match the new code
- When refactoring: regenerate all DSL touched by the refactor
- If DSL is stale or missing: regenerate it from the current code — don't try to patch it

| Code Change | DSL to Generate |
|-------------|-----------------|
| Write/modify a function | `@bodhi.*` inline tags in its doc comment |
| Add/modify an API endpoint | `.bodhi/flows/<name>.yaml` |
| Add/modify a DB table / ORM model | `.bodhi/entities/<table>.yaml` |
| Add/modify state transition logic | `.bodhi/states/<name>.yaml` |
| Add/modify event publishing or consumption | `.bodhi/events/<name>.yaml` |
| Add/modify cross-service calls | `.bodhi/services/<name>.yaml` |
| Introduce a business term | `.bodhi/concepts/glossary.yaml` |

The DSL has two layers — both are generated together with the code.

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

## Layer 2: System Files (generated on structural changes)

When code involves any of the following, generate the corresponding `.bodhi/` YAML files.

### Trigger Rules

| What You Did | What to Generate |
|--------------|------------------|
| Added an HTTP endpoint or request handling chain | `.bodhi/flows/<flow_name>.yaml` |
| Added a database table or ORM model | `.bodhi/entities/<table_name>.yaml` |
| Added a status enum or state transition logic | `.bodhi/states/<state_machine_name>.yaml` |
| Added an event (MQ, EventBus message) | `.bodhi/events/<event_name>.yaml` |
| Added cross-service calls or dependencies | `.bodhi/services/<service_name>.yaml` |
| Introduced a new business term or concept | `.bodhi/concepts/glossary.yaml` |
| Project initialization or framework change | `.bodhi/bodhi.yaml` |

### Flow File — `.bodhi/flows/<name>.yaml`

When you write an API endpoint or a complete request handling chain, generate the corresponding flow:

```yaml
name: create_order
description: Complete order creation flow

entry:
  type: http          # http | grpc | mq_consumer | event | scheduler | websocket
  method: POST
  path: /api/orders
  auth: required(role=USER)

steps:
  - fn: OrderController.create
    intent: Receive request, validate params, orchestrate creation
    reads:
      - request.body(userId, items, address)
    calls:
      - InventoryService.deduct
      - OrderRepository.save
      - EventPublisher.publish
    on_fail:
      - validation_failed → reject 400

  - fn: InventoryService.deduct
    intent: Deduct product inventory
    reads:
      - inventory(productId, stock)
    writes:
      - inventory(stock) via UPDATE
    on_fail:
      - inventory_insufficient → reject 400

  - fn: OrderRepository.save
    intent: Persist order to database
    writes:
      - orders(id, userId, totalAmount, status=PENDING) via INSERT
    on_fail:
      - db_write_failed → retry 2 → throw

  - fn: EventPublisher.publish
    intent: Publish order created domain event
    emits:
      - order_created(orderId, userId) to kafka:order-events

error_handling:
  - condition: inventory_insufficient
    step: InventoryService.deduct
    action: reject 400
  - condition: db_write_failed
    step: OrderRepository.save
    action: retry 2 → rollback inventory → reject 500

related_flows:
  - cancel_order
  - get_order_detail

entities:
  - orders
  - inventory

events:
  - order_created
```

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

### State Machine File — `.bodhi/states/<name>.yaml`

When you implement state transition logic (enum + transition methods):

```yaml
name: order_lifecycle
entity: orders
field: status
description: Order lifecycle

states:
  - id: INIT
    value: 0
    description: Awaiting payment
    transitions:
      - target: PAID
        trigger: event(payment_success)
        fn: PaymentCallback.onSuccess
      - target: CANCELLED
        trigger: timeout(30m)
        fn: OrderScheduler.cancelExpired

  - id: PAID
    value: 1
    description: Payment received
    transitions:
      - target: SHIPPED
        trigger: event(shipment_created)
        fn: ShipmentCallback.onShipped

  - id: COMPLETED
    value: 4
    description: Order completed
    terminal: true

  - id: CANCELLED
    value: 5
    description: Order cancelled
    terminal: true
    side_effects:
      - rollback inventory
      - refund if paid
```

### Service File — `.bodhi/services/<service_name>.yaml`

Only for microservice / distributed architectures. When you add cross-service calls or modify service dependencies:

```yaml
name: order-service
description: Core order service
port: 8080
tech_stack: [spring-boot, mysql, kafka]

apis:
  - method: POST
    path: /api/orders
    flow: create_order
    description: Create order

depends_on:
  - service: payment-service
    protocol: http
    apis:
      - POST /api/payments/hold
      - POST /api/payments/charge
    resilience:
      timeout: 3s
      retry: 2
      circuit_breaker: threshold=5, window=60s

  - service: kafka
    type: mq
    topics: [order-events]
```

### Event File — `.bodhi/events/<event_name>.yaml`

When you implement event publishing or consumption (Kafka, RabbitMQ, EventBus, etc.):

```yaml
name: order_created
description: Domain event published after order creation
channel: kafka:order-events

schema:
  - field: orderId
    type: string
    description: Order ID
  - field: userId
    type: string
    description: User ID
  - field: totalAmount
    type: decimal
    description: Order total amount

producers:
  - fn: OrderService.create
    flow: create_order

consumers:
  - fn: NotificationHandler.onOrderCreated
    flow: send_order_notification
    description: Send order notification to user
```

### Concept File — `.bodhi/concepts/glossary.yaml`

When business terms appear in code (especially in state checks or business rules):

```yaml
concepts:
  - term: Closed deal
    definition: Order status transitions from PAID to COMPLETED, meaning the transaction is fully settled
    related_states: [PAID, COMPLETED]
    related_flows: [create_order, confirm_delivery]

  - term: Stock lock
    definition: Pre-deduct inventory on order creation to prevent overselling
    related_fields: [inventory.stock, inventory.locked_stock]
    related_flows: [create_order, cancel_order]
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

1. Did you write a function? → Add Layer 1 inline tags
2. Is this function an API entry point / part of a request handling chain? → Update `.bodhi/flows/`
3. Did you create or modify a database table? → Update `.bodhi/entities/`
4. Did you implement a state enum or state transitions? → Update `.bodhi/states/`
5. Did you implement event publishing or consumption? → Update `.bodhi/events/`
6. Did you add cross-service calls or dependencies? → Update `.bodhi/services/`
7. Did you introduce a new business term? → Update `.bodhi/concepts/`

**What does NOT need DSL:**
- Pure utility functions (format, log wrapper, string utils)
- Simple getters/setters
- Test code
- Configuration / startup classes
