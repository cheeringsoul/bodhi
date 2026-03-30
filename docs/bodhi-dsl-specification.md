# Bodhi DSL — Design & Specification

> Version: 0.1.0 — Early Preview
> Date: 2026-03-29
> Status: Early preview. DSL schema may evolve based on real-world usage. Feedback welcome.

---

## 1. The Problem: Code Knows "What", Not "Why"

Every codebase has two layers of knowledge:

- **Structural knowledge** — what the code does, how functions call each other, what data flows where. Static analysis
  tools can extract this.
- **Semantic knowledge** — *why* a function exists, what business rule it enforces, what happens when it fails, which
  downstream services depend on it. This lives in developers' heads, Slack threads, and architecture docs that went
  stale on day one.

Today's AI coding assistants (Claude Code, Copilot, Cursor) are remarkably good at writing code. But when asked to debug
a production issue, trace a cross-service flow, or assess the impact of a schema change, they hit a wall — because the
*semantic* layer isn't in the code.

**Bodhi DSL bridges this gap.** It makes the AI that writes the code also write the semantics — structured,
machine-readable annotations that capture business intent, data flows, error handling paths, service dependencies, event
chains, and state machines. Not documentation for humans to read and forget, but **structured intelligence for AI to act
on**.

### Why "Bodhi"?

Bodhi (菩提) means "awakening" or "enlightenment" in Sanskrit. A Bodhi-annotated codebase is an *awakened* codebase —
one that knows what it does and why, and can explain itself to any AI agent that asks.

---

## 2. Design Principles

1. **Completeness**: DSL carries enough information to support bug triage, impact analysis, code Q&A, test generation,
   and cross-service tracing.
2. **Generatability**: AI generates DSL as a byproduct of writing code. DSL is never "maintained" — if it becomes
   outdated, it is regenerated from the current code.
3. **Extensibility**: The `@bodhi.*` namespace allows infinite extension without schema changes.
4. **Language-agnostic**: Works with Java, Python, Go, TypeScript, Kotlin — adapting to each language's doc comment
   syntax.
5. **Two-layer complementarity**: Function-level inline tags + system-level YAML files, each serving a distinct purpose.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                  Bodhi DSL: Two-Layer Architecture            │
│                                                              │
│  Layer 1: Inline Tags (@bodhi.*)                             │
│  ─────────────────────────────────                           │
│  Location: doc comments of functions/methods                 │
│  Granularity: single function                                │
│  Maintained by: AI auto-generation                          │
│  Answers: "What does this function do?"                      │
│                                                              │
│  Layer 2: System Files (.bodhi/)                             │
│  ─────────────────────────────────                           │
│  Location: .bodhi/ directory at project root                 │
│  Granularity: cross-function / cross-module / system-wide    │
│  Maintained by: AI auto-generation                           │
│  Answers: "How does the system work?"                        │
│                                                              │
│  ┌─────────┐   aggregate   ┌──────────┐                     │
│  │ @bodhi.*│  ──────────►  │ .bodhi/  │                     │
│  │ inline  │               │  YAML    │                     │
│  └─────────┘    locate     └──────────┘                     │
│                 ◄──────────                                  │
│              (trace back to functions)                        │
└──────────────────────────────────────────────────────────────┘
```

### How the Two Layers Relate

| Dimension        | Layer 1 (Inline Tags)                | Layer 2 (System Files)                         |
|------------------|--------------------------------------|------------------------------------------------|
| Location         | Code doc comments                    | `.bodhi/` YAML files                           |
| Granularity      | Single function/method               | Cross-function flows, state machines, entities |
| Maintained by    | AI auto-generation                   | AI auto-generation                             |
| Change frequency | High (follows code changes)          | Medium (when business flows change)            |
| Core value       | Answers "what does this function do" | Answers "how does this business work"          |

---

## 4. Layer 1: Inline Tags

### 4.1 Syntax

Tags are placed in the doc comment of each function/method, using the host language's comment syntax:

**Java / Kotlin:**

```java
/**
 * @bodhi.intent Create order, deduct inventory, publish domain event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct via grpc
 * @bodhi.calls PaymentService.hold via http:POST /api/payments/hold
 * @bodhi.emits order_created(orderId, userId) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 * @bodhi.on_fail payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

**Python:**

```python
def create_order(req: CreateOrderRequest) -> OrderResponse:
    """
    @bodhi.intent Create order, deduct inventory, publish domain event
    @bodhi.reads request.body(userId, items, address)
    @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
    @bodhi.calls InventoryService.deduct via grpc
    @bodhi.emits order_created(orderId, userId) to kafka:order-events
    @bodhi.on_fail inventory_insufficient → reject 400
    """
```

**Go:**

```go
// @bodhi.intent Create order, deduct inventory, publish domain event
// @bodhi.reads request.body(userId, items, address)
// @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
// @bodhi.calls InventoryService.deduct via grpc
// @bodhi.emits order_created(orderId, userId) to kafka:order-events
// @bodhi.on_fail inventory_insufficient → reject 400
func createOrder(req CreateOrderRequest) (*OrderResponse, error) { ... }
```

**TypeScript / JavaScript:**

```typescript
/**
 * @bodhi.intent Create order, deduct inventory, publish domain event
 * @bodhi.reads request.body(userId, items, address)
 * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
 * @bodhi.calls InventoryService.deduct via grpc
 * @bodhi.emits order_created(orderId, userId) to kafka:order-events
 * @bodhi.on_fail inventory_insufficient → reject 400
 */
async function createOrder(req: CreateOrderRequest): Promise<OrderResponse> { ...
}
```

### 4.2 Tag Reference

#### 4.2.1 `@bodhi.intent` — Business Intent

**Purpose**: One-line description of the function's business purpose. The most critical tag for AI to understand *why* a
function exists.

**Syntax**: `@bodhi.intent <natural language description>`

**Examples**:

```
@bodhi.intent Create order, deduct inventory, publish domain event
@bodhi.intent Validate user credentials and issue JWT token
@bodhi.intent Scheduled task: clean up unpaid orders older than 30 days
```

**Rules**:

- Required on every annotated function
- Use business language, don't restate the code
- One line, under 100 characters

---

#### 4.2.2 `@bodhi.reads` — Data Sources Read

**Purpose**: Declares what data sources this function reads from.

**Syntax**: `@bodhi.reads <source>(<fields...>)`

**Source types**:

| Source           | Meaning              | Example                                   |
|------------------|----------------------|-------------------------------------------|
| `request.body`   | HTTP request body    | `request.body(userId, items)`             |
| `request.query`  | URL query params     | `request.query(page, size)`               |
| `request.path`   | URL path params      | `request.path(orderId)`                   |
| `request.header` | HTTP headers         | `request.header(Authorization)`           |
| `<table_name>`   | Database table       | `orders(id, status, totalAmount)`         |
| `cache:<key>`    | Cache read           | `cache:user_session(userId)`              |
| `config:<key>`   | Configuration        | `config:payment_gateway(apiKey, timeout)` |
| `env:<key>`      | Environment variable | `env:DATABASE_URL`                        |

**Rules**:

- Multiple `@bodhi.reads` allowed, or comma-separated on one line
- List key fields in parentheses (not necessarily all fields)
- Optional `WHERE` clause to describe filter conditions

---

#### 4.2.3 `@bodhi.writes` — Data Targets Written

**Purpose**: Declares what data targets this function writes to.

**Syntax**: `@bodhi.writes <target>(<fields...>) [via <operation>]`

**Target types**:

| Target         | Meaning        | Example                             |
|----------------|----------------|-------------------------------------|
| `<table_name>` | Database table | `orders(id, status=PENDING)`        |
| `cache:<key>`  | Cache write    | `cache:user_session(token, expiry)` |
| `response`     | HTTP response  | `response(201, orderId)`            |
| `file:<path>`  | File write     | `file:logs/audit.log`               |

**Operation types**: `INSERT`, `UPDATE`, `UPSERT`, `DELETE`, `SET`

**Rules**:

- `via <operation>` is optional but recommended
- Use `=` for fixed values (e.g., `status=PENDING`)
- Multiple `@bodhi.writes` allowed

---

#### 4.2.4 `@bodhi.calls` — Key Function Calls

**Purpose**: Declares which important functions or services this function calls. Only list business-critical calls, not
utility functions.

**Syntax**:

```
@bodhi.calls <QualifiedName> [via <protocol>]
@bodhi.calls <QualifiedName>, <QualifiedName>, ...
```

**Protocol types** (for remote calls):

| Protocol                  | Meaning            | Example                              |
|---------------------------|--------------------|--------------------------------------|
| `http:<METHOD> <path>`    | HTTP/REST call     | `via http:POST /api/payments/charge` |
| `grpc`                    | gRPC call          | `via grpc`                           |
| `grpc:<service>/<method>` | gRPC with method   | `via grpc:PaymentService/Charge`     |
| `dubbo`                   | Dubbo RPC          | `via dubbo`                          |
| `feign`                   | Spring Cloud Feign | `via feign`                          |
| (no `via`)                | Local call         | `OrderRepository.save`               |

**Examples**:

```
# Local calls (no via)
@bodhi.calls InventoryService.deduct, OrderRepository.save

# Remote calls (with via — protocol and path)
@bodhi.calls PaymentService.charge via http:POST /api/payments/charge
@bodhi.calls InventoryService.deduct via grpc:InventoryService/DeductStock
@bodhi.calls UserService.getProfile via http:GET /api/users/{id}

# Mixed: local + remote in the same function, written on separate lines
@bodhi.calls OrderRepository.save
@bodhi.calls PaymentService.charge via http:POST /api/payments/charge
```

**Rules**:

- Only list business-critical calls, skip utility functions (log, format, etc.)
- Use `ClassName.methodName` format
- Left-to-right order reflects actual execution order
- Remote calls must use `via <protocol>` to distinguish local/remote — this is critical for understanding network
  boundaries in microservice architectures

---

#### 4.2.5 `@bodhi.emits` — Events Published

**Purpose**: Declares what events or messages this function publishes.

**Syntax**: `@bodhi.emits <event_name>(<payload_fields...>) [to <destination>]`

**Examples**:

```
@bodhi.emits order_created(orderId, userId, totalAmount)
@bodhi.emits payment_completed(orderId, transactionId) to payment_events
@bodhi.emits user_registered(userId, email) to kafka:user-events
@bodhi.emits inventory_low(productId, currentStock) to alert_channel
```

**Rules**:

- `to <destination>` is optional; specifies the target topic/queue/channel
- List key payload fields in parentheses

---

#### 4.2.6 `@bodhi.consumes` — Events Consumed

**Purpose**: Declares what events or messages trigger this function. The counterpart to `@bodhi.emits`, enabling AI to
trace complete event chains.

**Syntax**: `@bodhi.consumes <event_name>(<payload_fields...>) [from <source>]`

**Source types**:

| Source               | Meaning              | Example                         |
|----------------------|----------------------|---------------------------------|
| `kafka:<topic>`      | Kafka topic          | `from kafka:order-events`       |
| `rabbitmq:<queue>`   | RabbitMQ queue       | `from rabbitmq:payment-queue`   |
| `eventbus:<address>` | Vert.x EventBus      | `from eventbus:index.update`    |
| `sqs:<queue>`        | AWS SQS              | `from sqs:notification-queue`   |
| `redis:<channel>`    | Redis Pub/Sub        | `from redis:cache-invalidation` |
| `internal`           | In-process event bus | `from internal`                 |

**Examples**:

```
@bodhi.consumes order_created(orderId, userId) from kafka:order-events
@bodhi.consumes payment_completed(orderId, transactionId) from rabbitmq:payment-queue
```

**Rules**:

- `from <source>` is optional but recommended
- List the fields this function actually uses (can be a subset of the event payload)
- A function can consume multiple events
- `@bodhi.consumes` and `@bodhi.emits` form event chains: a producer's `emits` target corresponds to a consumer's
  `consumes` source

**Complete event-driven example**:

```java
// Producer
/**
 * @bodhi.intent Create order and publish order created event
 * @bodhi.writes orders(id, userId, status=PENDING) via INSERT
 * @bodhi.emits order_created(orderId, userId, totalAmount) to kafka:order-events
 */
public void createOrder(CreateOrderRequest req) { ... }

// Consumer
/**
 * @bodhi.intent On order created event, send notification to user
 * @bodhi.consumes order_created(orderId, userId) from kafka:order-events
 * @bodhi.reads users(email) WHERE id = userId
 * @bodhi.calls EmailService.send
 * @bodhi.on_fail email_send_failed → retry 3 → alert ops
 */
public void onOrderCreated(OrderCreatedEvent event) { ... }
```

---

#### 4.2.7 `@bodhi.on_fail` — Error Handling Paths

**Purpose**: Declares how this function handles specific error conditions. Critical for AI bug triage.

**Syntax**: `@bodhi.on_fail <condition> → <action>`

**Action types**:

| Action                 | Meaning                   | Example                                               |
|------------------------|---------------------------|-------------------------------------------------------|
| `reject <code>`        | Return error response     | `reject 400`                                          |
| `retry <count>`        | Retry (optional strategy) | `retry 3`, `retry 3(backoff=exponential)`             |
| `rollback <what>`      | Rollback operation        | `rollback inventory`                                  |
| `fallback <fn>`        | Degrade to backup         | `fallback CachedPriceService.get`                     |
| `circuit_breaker(...)` | Circuit breaker           | `circuit_breaker(threshold=5, window=60s)`            |
| `degrade(<strategy>)`  | Service degradation       | `degrade(skip_stock_check)`, `degrade(return_cached)` |
| `alert <channel>`      | Alert notification        | `alert ops_channel`                                   |
| `ignore`               | Silently ignore           | `ignore`                                              |
| `throw`                | Rethrow upstream          | `throw`                                               |

**Examples**:

```
# Basic error handling
@bodhi.on_fail inventory_insufficient → reject 400
@bodhi.on_fail payment_timeout → retry 3 → reject 500
@bodhi.on_fail user_not_found → reject 404
@bodhi.on_fail price_service_down → fallback CachedPriceService.get

# Microservice resilience patterns
@bodhi.on_fail payment_service_timeout → circuit_breaker(threshold=5, window=60s) → fallback reject 503
@bodhi.on_fail inventory_service_down → retry 3(backoff=exponential) → degrade(skip_stock_check)
@bodhi.on_fail recommendation_unavailable → degrade(return_cached) → alert ml_team
```

**Rules**:

- Chain multiple actions with `→` (try A, if still failing try B)
- A function can have multiple `@bodhi.on_fail` for different error conditions
- Conditions use natural language (snake_case), not exception class names

---

### 4.3 Observability Tags

#### `@bodhi.log.success` — Success Log Pattern

```
@bodhi.log.success "Order {orderId} created successfully"
```

#### `@bodhi.log.error` — Error Log Pattern

```
@bodhi.log.error "Payment failed for order {orderId}: {reason}" severity=error
```

#### `@bodhi.metric` — Key Metrics

```
@bodhi.metric order_create_latency threshold=500ms
@bodhi.metric payment_success_rate threshold=99.5%
```

### 4.4 Constraint Tags

| Tag                 | Purpose              | Example                                         |
|---------------------|----------------------|-------------------------------------------------|
| `@bodhi.auth`       | Auth requirements    | `@bodhi.auth required(role=ADMIN)`              |
| `@bodhi.validate`   | Validation rules     | `@bodhi.validate amount > 0, items.length >= 1` |
| `@bodhi.idempotent` | Idempotency strategy | `@bodhi.idempotent key=userId+orderId`          |
| `@bodhi.ratelimit`  | Rate limiting        | `@bodhi.ratelimit 100/min per userId`           |

### 4.5 Tag Priority

| Level          | Tags                                    | Importance                                                                      |
|----------------|-----------------------------------------|---------------------------------------------------------------------------------|
| P0 Required    | `intent`, `reads`, `writes`             | Without these, AI cannot understand function semantics                          |
| P1 Recommended | `calls`, `emits`, `consumes`, `on_fail` | Completes call graphs, event chains, and error paths — essential for bug triage |
| P2 Optional    | `log.*`, `auth`, `validate`             | Enhances observability and constraint understanding                             |
| P3 Extended    | `metric`, `idempotent`, `ratelimit`     | Useful in specific scenarios                                                    |

AI should generate at least P0 + P1 tags for every function.

### 4.6 Complete Example

```java
/**
 * Handle adding a comment to an album.
 *
 * @bodhi.intent User adds comment to album, store in MongoDB, notify index via EventBus
 * @bodhi.reads request.path(albumId), request.body(content, rating, userId)
 * @bodhi.reads albums(id, title) WHERE id = albumId
 * @bodhi.writes comments(id, albumId, userId, content, rating, createdAt) via INSERT
 * @bodhi.calls CommentValidator.validate, AlbumRepository.exists
 * @bodhi.emits comment_added(albumId, commentId) to eventbus:index.update
 * @bodhi.on_fail album_not_found → reject 404
 * @bodhi.on_fail validation_failed → reject 400
 * @bodhi.on_fail db_write_failed → retry 2 → reject 500
 * @bodhi.auth required(role=USER)
 * @bodhi.log.success "Comment {commentId} added to album {albumId}"
 * @bodhi.log.error "Failed to add comment to album {albumId}: {reason}" severity=error
 */
public void handle(RoutingContext rc) {
    // ...
}
```

---

## 5. Layer 2: System Files

### 5.1 Directory Structure

```
.bodhi/
├── bodhi.yaml              # Project metadata
├── flows/                  # Request-to-response call chains
│   ├── create_order.yaml
│   ├── get_order_detail.yaml
│   └── cancel_order.yaml
├── states/                 # State machine definitions
│   ├── order_lifecycle.yaml
│   └── payment_state.yaml
├── entities/               # Database entity semantics
│   ├── orders.yaml
│   ├── order_items.yaml
│   └── inventory.yaml
├── services/               # Service topology (microservices)
│   ├── order-service.yaml
│   └── payment-service.yaml
├── events/                 # Event catalog
│   ├── order_created.yaml
│   └── payment_completed.yaml
├── concepts/               # Business glossary
│   └── glossary.yaml
└── schema.json             # DSL JSON Schema (for validation)
```

### 5.2 Project Metadata — `bodhi.yaml`

```yaml
version: "0.1.0"
project:
  name: "music-store"
  description: "Online music store backend"
  languages: [ java, kotlin ]
  frameworks: [ vertx, mongodb ]

# Inline tag parsing per language
inline:
  java: javadoc       # /** @bodhi.* */
  python: docstring   # """ @bodhi.* """
  go: line_comment    # // @bodhi.*
  typescript: jsdoc   # /** @bodhi.* */
```

### 5.3 Flow — `.bodhi/flows/*.yaml`

**Purpose**: Describes a complete request-to-response call chain. Answers "how does this request flow through the
system?"

```yaml
name: create_order
description: Complete order creation flow, from HTTP request to persistence and event publishing

entry:
  type: http          # http | grpc | mq_consumer | event | scheduler | websocket
  method: POST
  path: /api/orders
  auth: required(role=USER)

steps:
  - fn: OrderController.create
    intent: Receive request, validate params, orchestrate order creation
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
      - order_items(orderId, productId, quantity, price) via INSERT
    on_fail:
      - db_write_failed → retry 2 → throw

  - fn: EventPublisher.publish
    intent: Publish order created domain event
    emits:
      - order_created(orderId, userId, totalAmount) to kafka:order-events

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
  - order_items
  - inventory

events:
  - order_created
```

**Field reference**:

| Field              | Required | Description                                                           |
|--------------------|----------|-----------------------------------------------------------------------|
| `name`             | Yes      | Unique flow identifier, snake_case                                    |
| `description`      | Yes      | One-line description                                                  |
| `entry`            | Yes      | Entry point info (type, method, path)                                 |
| `entry.type`       | Yes      | `http` / `grpc` / `mq_consumer` / `event` / `scheduler` / `websocket` |
| `steps`            | Yes      | Ordered array of call chain steps                                     |
| `steps[].fn`       | Yes      | Fully qualified function name `ClassName.methodName`                  |
| `steps[].intent`   | Yes      | Business intent of this step                                          |
| `steps[].reads`    | No       | Data sources read (same as inline `@bodhi.reads`)                     |
| `steps[].writes`   | No       | Data targets written (same as inline `@bodhi.writes`)                 |
| `steps[].emits`    | No       | Events published (same as inline `@bodhi.emits`)                      |
| `steps[].consumes` | No       | Events consumed (same as inline `@bodhi.consumes`)                    |
| `steps[].calls`    | No       | Downstream function calls                                             |
| `steps[].on_fail`  | No       | Error handling                                                        |
| `error_handling`   | No       | Cross-step error handling summary                                     |
| `related_flows`    | No       | Related flows                                                         |
| `entities`         | No       | Database entities involved                                            |
| `events`           | No       | Events involved                                                       |

### 5.4 State Machine — `.bodhi/states/*.yaml`

**Purpose**: Describes the lifecycle of a business entity's state. Answers "how does this entity transition between
states?"

```yaml
name: order_lifecycle
entity: orders
field: status
description: Order lifecycle from creation to completion/cancellation

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

### 5.5 Entity — `.bodhi/entities/*.yaml`

**Purpose**: Describes database table semantics — fields, types, relationships, and business meaning. Answers "what does
this data mean?"

```yaml
table: orders
description: Core orders table
database: mysql

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
    sensitive: true          # PII flag

indexes:
  - name: idx_user_status
    fields: [ user_id, status ]
    description: User order list query

relations:
  - target: order_items
    type: one_to_many
    join: orders.id = order_items.order_id
  - target: users
    type: many_to_one
    join: orders.user_id = users.id
```

### 5.6 Event Catalog — `.bodhi/events/*.yaml`

**Purpose**: Defines event schemas, producers, and consumers. Answers "where does this event come from and where does it
go?"

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
  - fn: AnalyticsHandler.trackOrderCreated
    flow: track_order_analytics
    description: Update order analytics
```

### 5.7 Service Topology — `.bodhi/services/*.yaml`

**Purpose**: Defines the microservice topology — what APIs a service exposes, what upstream services it depends on, and
what resilience strategies are in place. Answers "what services exist and how are they connected?"

> Note: Only needed for microservice / distributed architectures. Monoliths can skip this.

```yaml
name: order-service
description: Core order service — handles order creation, query, and cancellation
port: 8080
tech_stack: [ spring-boot, mysql, kafka ]

apis:
  - method: POST
    path: /api/orders
    flow: create_order
    description: Create order
  - method: GET
    path: /api/orders/{id}
    flow: get_order_detail
    description: Get order details
  - method: POST
    path: /api/orders/{id}/cancel
    flow: cancel_order
    description: Cancel order

depends_on:
  - service: payment-service
    protocol: http
    apis:
      - POST /api/payments/hold
      - POST /api/payments/charge
      - POST /api/payments/refund
    resilience:
      timeout: 3s
      retry: 2
      circuit_breaker: threshold=5, window=60s

  - service: inventory-service
    protocol: grpc
    apis:
      - DeductStock
      - RollbackStock
    resilience:
      timeout: 2s
      retry: 3(backoff=exponential)

  - service: kafka
    type: mq
    topics:
      - order-events
      - payment-events
```

**Field reference**:

| Field                     | Required | Description                                                 |
|---------------------------|----------|-------------------------------------------------------------|
| `name`                    | Yes      | Service name, matching deployment name                      |
| `description`             | Yes      | One-line description                                        |
| `port`                    | No       | Service port                                                |
| `tech_stack`              | No       | Technology stack list                                       |
| `apis`                    | No       | APIs this service exposes                                   |
| `apis[].method`           | Yes      | HTTP method or RPC method                                   |
| `apis[].path`             | Yes      | Route path                                                  |
| `apis[].flow`             | No       | Associated flow                                             |
| `depends_on`              | No       | Upstream dependency list                                    |
| `depends_on[].service`    | Yes      | Dependent service name                                      |
| `depends_on[].protocol`   | Yes      | Communication protocol: `http`, `grpc`, `dubbo`, etc.       |
| `depends_on[].type`       | No       | Middleware type: `mq`, `cache`, `db` (for non-service deps) |
| `depends_on[].apis`       | No       | Specific APIs called                                        |
| `depends_on[].topics`     | No       | MQ topics used                                              |
| `depends_on[].resilience` | No       | Resilience strategy (timeout, retry, circuit_breaker)       |

### 5.8 Business Glossary — `.bodhi/concepts/*.yaml`

**Purpose**: Defines business terms and concepts that appear in code. Answers "what does this business term mean?"

```yaml
concepts:
  - term: Closed deal
    definition: Order status transitions from PAID to COMPLETED, meaning the transaction is fully settled
    related_states: [ PAID, COMPLETED ]
    related_flows: [ create_order, confirm_delivery ]

  - term: Stock lock
    definition: Pre-deduct inventory on order creation to prevent overselling. Roll back on payment failure.
    related_fields: [ inventory.stock, inventory.locked_stock ]
    related_flows: [ create_order, cancel_order ]
```

---

## 6. Extension Mechanism

### 6.1 Namespace Rules

All tags live under the `@bodhi` namespace, separated by `.`:

```
@bodhi.<domain>.<sub>
```

| Namespace          | Layer         | Example Tags               |
|--------------------|---------------|----------------------------|
| `bodhi.intent`     | Core          | (no sub)                   |
| `bodhi.reads`      | Core          | (no sub)                   |
| `bodhi.writes`     | Core          | (no sub)                   |
| `bodhi.calls`      | Core          | (no sub)                   |
| `bodhi.emits`      | Core          | (no sub)                   |
| `bodhi.consumes`   | Core          | (no sub)                   |
| `bodhi.on_fail`    | Core          | (no sub)                   |
| `bodhi.log.*`      | Observability | `log.success`, `log.error` |
| `bodhi.auth`       | Constraints   | (no sub)                   |
| `bodhi.validate`   | Constraints   | (no sub)                   |
| `bodhi.idempotent` | Constraints   | (no sub)                   |
| `bodhi.ratelimit`  | Constraints   | (no sub)                   |
| `bodhi.metric`     | Observability | (no sub)                   |

### 6.2 Custom Extensions

Teams can define their own tags by registering them in `bodhi.yaml`:

```yaml
extensions:
  - namespace: bodhi.security
    description: Security audit tags
    tags:
      - name: bodhi.security.risk
        description: Security risk flag
        example: "@bodhi.security.risk sql_injection if input not sanitized"
      - name: bodhi.security.encrypt
        description: Encryption requirement
        example: "@bodhi.security.encrypt field=password algo=bcrypt"

  - namespace: bodhi.test
    description: Testing tags
    tags:
      - name: bodhi.test.cases
        description: Key test scenarios
        example: "@bodhi.test.cases happy_path, insufficient_stock, payment_timeout"
```

---

## 7. How AI Agents Consume the DSL

The DSL is not just documentation — it's a **machine-readable knowledge graph** that AI agents can query, traverse, and
reason about.

### 7.1 Knowledge Graph Construction

```
.bodhi/ directory
  │
  ├── flows/*.yaml    → Call chain graphs (entry → steps → terminal)
  ├── states/*.yaml   → State transition graphs
  ├── entities/*.yaml → Entity relationship graphs
  ├── events/*.yaml   → Event chain graphs (producer → event → consumer)
  ├── services/*.yaml → Service dependency graphs
  └── concepts/*.yaml → Business concept index

Source code @bodhi.* tags
  │
  ├── Function-level semantic nodes
  ├── Call relationship edges
  └── Data read/write relationship edges

Combined Knowledge Graph
  ├── Function nodes (with intent, reads, writes, on_fail)
  ├── Entity nodes (with fields, enum, relations)
  ├── State nodes (with transitions)
  ├── Service nodes (with APIs, dependencies, resilience)
  ├── Flow edges (linking function call chains)
  ├── Data edges (function ↔ entity read/write)
  └── Event edges (function → event → function)
```

### 7.2 Agent Capability Matrix

Which DSL data enables which AI agent capabilities:

| Agent Capability                 | DSL Information Used                                       |
|----------------------------------|------------------------------------------------------------|
| **Bug Triage**                   | `intent` + `on_fail` + `reads/writes` + `log.*` + `states` |
| **Impact Analysis**              | `writes` + `entities.relations` + `related_flows`          |
| **Code Q&A**                     | `intent` + `calls` + `reads/writes`                        |
| **Flow Tracing**                 | `flows` + `calls` + `emits/consumes`                       |
| **Test Generation**              | `reads` + `writes` + `on_fail` + `validate`                |
| **Security Audit**               | `auth` + `sensitive` + `reads/writes`                      |
| **Performance Diagnosis**        | `metric` + `calls` (N+1 detection)                         |
| **Migration Impact**             | `entities` + `writes` + `related_flows`                    |
| **Log Correlation**              | `log.success` + `log.error`                                |
| **Service Dependency Analysis**  | `services` + `calls(via)` + `emits/consumes`               |
| **Failure Propagation Analysis** | `services.depends_on` + `on_fail(circuit_breaker/degrade)` |

### 7.3 Example: AI Bug Triage

**User asks**: "Why didn't order ORD-99 complete?"

**Agent reasoning path**:

```
1. Read .bodhi/concepts/glossary.yaml
   → "Closed deal" = status transitions from PAID to COMPLETED

2. Read .bodhi/states/order_lifecycle.yaml
   → PAID → COMPLETED requires trigger: event(delivery_confirmed)
   → Also has timeout(15d) auto-complete path

3. Read .bodhi/entities/orders.yaml
   → status field enum: ORD-99 status=2 → FAILED
   → Order never reached PAID state — problem is in payment

4. Read .bodhi/flows/create_order.yaml
   → step: PaymentService.charge
   → on_fail: payment_timeout → retry 3 → reject 500

5. Read PaymentService.charge @bodhi.* tags
   → @bodhi.log.error "Payment failed for order {orderId}: {reason}"

6. Search logs
   → Found "Payment failed for order ORD-99: insufficient_balance"

7. Answer:
   "Order ORD-99 failed during payment due to insufficient balance.
    Status is FAILED(2), never reached PAID.
    Failure occurred at PaymentService.charge,
    retried 3 times then returned 500."
```

---

## 8. Validation Rules

### 8.1 Inline Tag Validation

| Rule                                                           | Severity | Description                          |
|----------------------------------------------------------------|----------|--------------------------------------|
| Has `@bodhi.writes` but no `@bodhi.intent`                     | Error    | Intent is required                   |
| `@bodhi.calls` references a function with no tags              | Warning  | Possible typo or not yet implemented |
| `@bodhi.writes` references an entity not in `.bodhi/entities/` | Warning  | Possible missing entity definition   |
| `@bodhi.emits` event has no consumers                          | Info     | May be a cross-service event         |
| Has database operations but no `@bodhi.writes`                 | Error    | Missing write annotation             |

### 8.2 Flow Validation

| Rule                                                 | Severity | Description                          |
|------------------------------------------------------|----------|--------------------------------------|
| Flow step.fn has no corresponding `@bodhi.*` tags    | Warning  | Function missing inline tags         |
| Flow has `writes` but no `on_fail` in the step chain | Warning  | Write operations lack error handling |
| Flow references an entity not in `.bodhi/entities/`  | Error    | Entity definition missing            |
| State transition.fn not in any flow                  | Info     | May be internally triggered          |
| Entity has enum field but no linked state machine    | Info     | May need a state machine definition  |

### 8.3 Microservice Validation

| Rule                                                            | Severity | Description                                  |
|-----------------------------------------------------------------|----------|----------------------------------------------|
| `@bodhi.calls via` remote call has no `@bodhi.on_fail`          | Warning  | Remote calls should have resilience handling |
| `services.depends_on` references a service with no service file | Info     | Upstream service may be in another repo      |
| `services.apis` flow reference does not exist                   | Warning  | API and flow are out of sync                 |
| `@bodhi.calls via` target service not in `depends_on`           | Warning  | Service dependency is incomplete             |

---

## 9. Versioning

`bodhi.yaml` contains the `version` field to identify the DSL schema version:

```yaml
version: "0.1.0"
```

Version follows semantic versioning:

- **patch (0.1.x)**: New optional tags, backward compatible
- **minor (0.x.0)**: New required tags or changed tag semantics, migration scripts provided
- **major (x.0.0)**: Breaking changes

The `.bodhi/` directory is committed to version control alongside code. Since DSL is always regenerated (not manually
maintained), version control serves as a snapshot of the DSL state at each commit:

- DSL changes are traceable via `git blame`
- Code reviews include DSL review
- Branch merges detect DSL conflicts

---

## 10. Vision: What Becomes Possible

Bodhi DSL today is an annotation protocol. But the structured semantic data it produces unlocks capabilities that grow
with adoption:

### Near-term (single repo)

- **AI Bug Triage**: Agent reads flows, states, and error paths to diagnose production issues without human explanation
  of business logic.
- **Impact Analysis**: Change a database field → AI traces every function that reads/writes it, every flow that touches
  it, every downstream service.
- **Test Generation**: `reads` + `writes` + `on_fail` fully describes a function's inputs, outputs, and failure modes —
  enough to generate test skeletons.
- **Architecture-aware Code Review**: PR changes a function → AI checks if new writes have error handling, remote calls
  have resilience, entity references exist.

### Mid-term (cross-repo / cross-service)

- **Global Service Dependency Graph**: Every microservice repo has `.bodhi/services/`. Aggregate them → complete system
  topology. "What breaks if payment-service goes down?" becomes answerable.
- **Cross-service Flow Tracing**: order-service flow hits `PaymentService.charge via http` → jump to payment-service
  repo and continue tracing. Full request path from gateway to database, statically — no Jaeger needed.
- **Event Chain Panorama**: `emits` + `consumes` + `events/` across all repos → complete event lineage. "What ultimately
  happens when `order_created` fires?" → recursive trace to notifications, analytics, inventory sync.

### Long-term (generative)

- **Intent-to-Code Generation**: Write `.bodhi/flows/`, `.bodhi/entities/`, `.bodhi/events/` first → AI generates code
  from the DSL. The DSL becomes a high-level "intent programming" language.
- **Automated Architecture Compliance**: Define rules ("all writes must have on_fail", "all remote calls must have
  circuit_breaker", "PII fields must be marked sensitive") → CI enforces them automatically.
- **Living Architecture Diagrams**: Auto-generate C4 models, sequence diagrams, ER diagrams, state machine diagrams from
  services → flows → entities → states. Always in sync with code because the data source *is* the code.
- **Failure Simulation**: "What if payment-service times out for 5 seconds?" → Agent reads `depends_on.resilience` for
  timeout/circuit breaker config, reads `on_fail` for fallback behavior, reads downstream consumers for cascading
  impact. Chaos engineering without the chaos.
- **AI Onboarding Agent**: New developer asks "how does the order flow work?" → Agent walks through the flow step by
  step. "What does this field mean?" → reads entity + concepts. "What does this service depend on?" → reads services. An
  always-on, always-accurate system explainer.

---

## Appendix: Entity Generation Sources

| Source                | Method                                          | Accuracy                                   |
|-----------------------|-------------------------------------------------|--------------------------------------------|
| ORM model definitions | Auto-extract field names, types, relations      | High (structure accurate, lacks semantics) |
| Migration / DDL       | Parse SQL changes                               | Medium (structure only)                    |
| AI analysis           | Infer field meaning from code context           | High (AI understands business context from requirements) |

Recommended flow: **AI generates complete entity definitions (structure + semantics) during code generation**
