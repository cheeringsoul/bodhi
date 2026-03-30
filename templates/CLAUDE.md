# Bodhi DSL — Code + DSL Co-generation Rules

## Atomic Update Rule

**Code and DSL are a single unit. Every edit to a function must include its DSL update in the same response.**

| Action | Required DSL update |
|--------|---------------------|
| Write a new function | Add `@bodhi.*` inline tags |
| Modify a function body | Re-read current `@bodhi.*` tags, update any that no longer match |
| Add an API endpoint | Create/update `.bodhi/flows/<name>.yaml` |
| Modify DB table / ORM model | Update `.bodhi/entities/<table>.yaml` |
| Add/change state transition logic | Update `.bodhi/states/<name>.yaml` |
| Add/change event publishing or consumption | Update `.bodhi/events/<name>.yaml` |
| Add/change cross-service call | Update `.bodhi/services/<name>.yaml` |

**Never split code and DSL across separate responses.** If you realize DSL is missing after writing code, fix it immediately in the same session before doing anything else.

---

When writing code in this project, you **must maintain Bodhi DSL simultaneously**. The DSL has two layers — both are required.

---

## Layer 1: Inline Tags (every function you write or modify)

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

## Layer 2: System Files (on structural changes)

When code changes involve any of the following, you must update the corresponding `.bodhi/` YAML files.

### Trigger Rules

| What You Did | What to Update |
|--------------|----------------|
| Added/modified an HTTP endpoint or request handling chain | `.bodhi/flows/<flow_name>.yaml` |
| Added/modified a database table or ORM model | `.bodhi/entities/<table_name>.yaml` |
| Added/modified a status enum or state transition logic | `.bodhi/states/<state_machine_name>.yaml` |
| Added/modified an event (MQ, EventBus message) | `.bodhi/events/<event_name>.yaml` |
| Added/modified cross-service calls or dependencies | `.bodhi/services/<service_name>.yaml` |
| Introduced a new business term or concept | `.bodhi/concepts/glossary.yaml` |
| Project initialization or framework change | `.bodhi/bodhi.yaml` |

### Flow File — `.bodhi/flows/<name>.yaml`

When you write an API endpoint or a complete request handling chain, create or update the corresponding flow:

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

When you create or modify a database table / ORM model:

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
