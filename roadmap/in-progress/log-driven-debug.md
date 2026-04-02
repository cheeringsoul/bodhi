# Log-Driven Debug — Design Document

> Status: Draft
> Date: 2026-04-02

## 1. Overview

Log-Driven Debug connects Bodhi's static knowledge graph with runtime log data, enabling AI to diagnose production issues by **reasoning along the graph's causal structure** rather than blindly searching logs.

The core insight: when a developer investigates a bug, they don't read logs linearly. They follow a mental model — "this request enters at the controller, calls the inventory service, then writes to the DB, then emits an event." They check each step for evidence of success or failure. Bodhi already has this mental model as structured data (flows, steps, events, state machines). Log-Driven Debug automates this reasoning process.

### What it is NOT

- Not a log aggregation platform (use ELK, Loki, CloudWatch for that)
- Not a distributed tracing replacement (Jaeger/Zipkin trace the mechanical call chain at runtime)
- Not an APM tool (Datadog/New Relic monitor performance metrics)

### What it IS

A **semantic reasoning layer** that sits on top of existing log infrastructure, using Bodhi's knowledge graph to:
- Know which logs to look for (from `@bodhi.log.*` patterns)
- Know the order they should appear in (from flow steps)
- Know what it means when a log is missing (the step failed or was never reached)
- Know the upstream/downstream consequences (from events, state machines, entities)

---

## 2. How Logs Connect to the Knowledge Graph

### 2.1 Connection Points

There are four ways a log line connects to the knowledge graph:

```
Log line                              Graph connection
─────────────────────────────────     ──────────────────────────────
"Order 12345 created successfully"  → @bodhi.log.success on OrderService.create
"Payment failed: timeout"           → @bodhi.log.error on PaymentService.hold
"Calling InventoryService.deduct"   → function name match → flow step
"[order-service] POST /api/orders"  → flow entry point match
```

| Connection type | Source | Reliability | Coverage |
|----------------|--------|-------------|----------|
| **Explicit pattern** | `@bodhi.log.success` / `@bodhi.log.error` tags | High — exact pattern match | Low — only tagged functions |
| **Function name** | Log contains class/method name | Medium — naming conventions vary | Medium |
| **Flow entry** | Log contains HTTP method + path or gRPC service/method | High — standardized format | Entry points only |
| **Correlation ID** | Log contains a business ID (orderId, userId) that appears in `@bodhi.reads`/`@bodhi.writes` | High — exact ID match | High — most logs have business IDs |

### 2.2 Correlation ID — The Key to Tracing

A single request flows through multiple functions. To trace a specific request, we need a **correlation ID** — a business identifier that appears in logs across all steps.

Most applications already log business IDs (order ID, user ID, request ID). The challenge is knowing **which field is the correlation ID** for a given flow.

**New tag**: `@bodhi.trace`

```java
/**
 * @bodhi.intent Create order, deduct inventory, publish event
 * @bodhi.trace orderId                    ← this is the correlation key for this flow
 * @bodhi.reads request.body(userId, items)
 * @bodhi.writes orders(id, userId, status=PENDING) via INSERT
 * @bodhi.log.success "Order {orderId} created successfully"
 * @bodhi.log.error "Order creation failed for user {userId}: {reason}"
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

`@bodhi.trace orderId` tells the debug engine: "when tracing this flow, use `orderId` as the correlation ID to find related log entries across all steps."

Flow-level declaration (in YAML):

```yaml
name: create_order
trace_key: orderId            # correlation ID for this entire flow
entry:
  type: http
  method: POST
  path: /api/orders
steps: [...]
```

### 2.3 Log Pattern Registry

The debug engine builds a **pattern registry** from all `@bodhi.log.*` tags:

```
Function                    | Success pattern                          | Error patterns
────────────────────────────|──────────────────────────────────────────|──────────────────────
OrderService.create         | "Order {orderId} created successfully"   | "Order creation failed.*{reason}"
InventoryService.deduct     | "Inventory deducted for {productId}"     | "Insufficient inventory.*{productId}"
PaymentService.hold         | "Payment held: {transactionId}"          | "Payment failed.*{reason}"
EventPublisher.publish      | "Event {eventName} published"            | "Event publish failed.*{reason}"
```

These patterns are compiled into regex matchers. When searching logs for a specific flow execution, the engine looks for these patterns with the correlation ID substituted.

---

## 3. Debug Reasoning Engine

### 3.1 The Algorithm

Given: a flow name + correlation ID (e.g., `create_order` + `orderId=12345`)

```
1. Load flow definition → get ordered list of steps
2. For each step (in order):
   a. Search logs for this step's success pattern with correlation ID
   b. Search logs for this step's error pattern with correlation ID
   c. Search logs for the function name with correlation ID
   d. Classify step status:
      - SUCCESS: success pattern found
      - FAILED: error pattern found
      - NO_EVIDENCE: no logs found for this step
      - PARTIAL: function name found but no success/error pattern
3. Find the "break point" — the first step that is not SUCCESS
4. Enrich with context:
   a. If step is remote → check remote service logs (via registry, if available)
   b. If step emits event → check if event was published and consumed
   c. If step writes entity → check current DB state
   d. If step has on_fail → check if error handling was triggered
5. Build causal narrative
```

### 3.2 Step Status Classification

```
                    ┌──────────────────────────┐
                    │    Search logs for step   │
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │  Success pattern found?   │
                    └──────────┬───────────────┘
                         yes / │ \ no
                             / │  \
                  ┌─────────▼  │   ▼──────────────┐
                  │  SUCCESS   │   Error pattern?  │
                  └────────────│   ┌───┴───┐       │
                               │  yes      no      │
                               │   │        │      │
                               │   ▼        ▼      │
                               │ FAILED  Function   │
                               │         name in    │
                               │         logs?      │
                               │        ┌──┴──┐    │
                               │       yes    no   │
                               │        │      │   │
                               │        ▼      ▼   │
                               │    PARTIAL  NO_EVIDENCE
                               │                   │
                               └───────────────────┘

Interpretation:
- SUCCESS → this step completed, move to next
- FAILED → this is the break point, examine error details
- PARTIAL → step was reached but outcome unclear, flag for investigation
- NO_EVIDENCE → either step was never reached (upstream failure) or logs are missing
```

### 3.3 Causal Narrative Generation

The engine produces a structured debug report:

```json
{
  "flow": "create_order",
  "trace_key": "orderId",
  "trace_value": "12345",
  "time_range": "2026-04-02T10:30:00Z — 2026-04-02T10:30:05Z",
  "steps": [
    {
      "fn": "OrderService.create",
      "status": "SUCCESS",
      "log": "Order 12345 created successfully",
      "timestamp": "2026-04-02T10:30:01Z"
    },
    {
      "fn": "InventoryService.deduct",
      "status": "SUCCESS",
      "log": "Inventory deducted for product P99",
      "timestamp": "2026-04-02T10:30:02Z",
      "note": "remote call to inventory-service via gRPC — succeeded"
    },
    {
      "fn": "PaymentService.hold",
      "status": "FAILED",
      "log": "Payment failed for order 12345: timeout",
      "timestamp": "2026-04-02T10:30:05Z",
      "error_handling": "on_fail: payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503",
      "note": "circuit breaker triggered — payment-service may be degraded"
    },
    {
      "fn": "EventPublisher.publish",
      "status": "NO_EVIDENCE",
      "note": "never reached — upstream step PaymentService.hold failed"
    }
  ],
  "break_point": "PaymentService.hold",
  "consequences": [
    "inventory was deducted (InventoryService.deduct succeeded) but payment failed — rollback may be needed",
    "order_created event was never published — downstream consumers (payment-service, notification-service) will not be triggered",
    "order status is PENDING — state machine expects payment_success event to transition to PAID, which will not arrive"
  ],
  "suggested_actions": [
    "check payment-service health — circuit breaker was triggered",
    "verify inventory rollback — order 12345 has deducted stock that may need restoration",
    "check if order 12345 has @bodhi.on_fail rollback logic for this scenario"
  ]
}
```

---

## 4. Log Source Adapters

### 4.1 Adapter Interface

```python
class LogAdapter:
    """Base interface for log source adapters."""

    def search(
        self,
        pattern: str,              # regex pattern to match
        time_from: datetime,       # search window start
        time_to: datetime,         # search window end
        correlation: dict | None,  # e.g., {"orderId": "12345"}
        limit: int = 100,
    ) -> list[LogEntry]:
        ...

    def tail(
        self,
        pattern: str,
        callback: Callable[[LogEntry], None],
    ) -> None:
        """Stream matching log entries in real time (for live monitoring)."""
        ...


@dataclass
class LogEntry:
    timestamp: datetime
    level: str                     # INFO, WARN, ERROR
    message: str
    source: str                    # service name or file path
    raw: dict                      # original structured log fields
```

### 4.2 Adapter Implementations

| Adapter | Log source | Search method | Real-time |
|---------|-----------|---------------|-----------|
| `FileLogAdapter` | Local log files | Regex scan with `mmap` | `tail -f` equivalent |
| `ElasticsearchAdapter` | Elasticsearch / OpenSearch | Query DSL with regex | Scroll API |
| `LokiAdapter` | Grafana Loki | LogQL | WebSocket tail |
| `CloudWatchAdapter` | AWS CloudWatch Logs | Filter pattern | Subscription filter |
| `StdoutAdapter` | Application stdout (dev mode) | Pipe capture | Direct stream |

### 4.3 Configuration

Extend `bodhi.yaml`:

```yaml
runtime:
  logs:
    # Local files (development)
    - name: app-log
      type: file
      path: /var/log/order-service/app.log
      format: json                    # json | text | logfmt
      timestamp_field: "@timestamp"   # for JSON logs
      message_field: "message"

    # Elasticsearch (production)
    - name: es-logs
      type: elasticsearch
      url: http://es-cluster:9200
      index: "order-service-logs-*"
      auth:
        type: basic                   # basic | api_key | aws_iam
        username_env: ES_USER         # read from environment variable
        password_env: ES_PASS

    # Grafana Loki
    - name: loki-logs
      type: loki
      url: http://loki:3100
      labels:
        service: order-service

  # How long to search before/after a known timestamp
  time_window: 30s

  # Default correlation field (can be overridden per flow via trace_key)
  default_trace_field: requestId
```

### 4.4 Log Format Parsing

Structured logs (JSON) are ideal — fields are already extracted. For unstructured text logs, the engine uses the `@bodhi.log.*` patterns as parsing templates:

```
Pattern:  "Order {orderId} created successfully"
Log line: "2026-04-02 10:30:01 INFO Order 12345 created successfully"

Extracted: orderId=12345, level=INFO, timestamp=2026-04-02T10:30:01
```

The `{field}` placeholders in `@bodhi.log.*` tags serve dual purpose:
1. **At write time**: tell AI what to log
2. **At debug time**: tell the engine how to parse the log and extract correlation IDs

---

## 5. MCP Tools

### 5.1 `debug_flow`

The primary debug tool. Traces a specific flow execution by correlation ID.

```
Tool: debug_flow
Args:
  flow: "create_order"
  trace_key: "orderId"          # optional, defaults to flow's trace_key
  trace_value: "12345"
  time_from: "2026-04-02T10:00:00Z"  # optional, defaults to last 1 hour
  time_to: "2026-04-02T11:00:00Z"

Returns: structured debug report (see section 3.3)
```

**When to use**: "Why did order 12345 fail?" / "What happened to request X?"

### 5.2 `explain_record`

Given a database record, explain how it got into its current state by tracing backwards through the knowledge graph and logs.

```
Tool: explain_record
Args:
  entity: "orders"
  key: {"id": "12345"}
  question: "why is status PENDING?"   # optional, focuses the analysis

Returns:
  - Current record state (from DB)
  - State machine context (what transitions are expected from PENDING)
  - Log trail (what flow steps executed for this record)
  - Diagnosis (why the expected transition hasn't happened)
```

**When to use**: "Why is this record in this state?" / "How did this data get here?"

### 5.3 `search_logs`

Graph-aware log search. Unlike raw log search, this tool understands which function produced the log and where it sits in the flow.

```
Tool: search_logs
Args:
  fn: "PaymentService.hold"     # optional, search logs for a specific function
  flow: "create_order"          # optional, search logs for all steps in a flow
  level: "ERROR"                # optional, filter by level
  time_from: "2026-04-02T10:00:00Z"
  time_to: "2026-04-02T11:00:00Z"
  correlation: {"orderId": "12345"}  # optional

Returns:
  - Matching log entries
  - Each entry annotated with: which function, which flow step, which flow
```

**When to use**: "Show me all errors from PaymentService in the last hour" / "What did order 12345 log?"

### 5.4 `analyze_anomaly`

Given a symptom description, use the knowledge graph to reason about probable causes.

```
Tool: analyze_anomaly
Args:
  symptom: "orders are piling up in PENDING status"
  time_from: "2026-04-02T10:00:00Z"

Returns:
  AI reasoning chain:
  1. PENDING → PAID requires payment_success event (from order_lifecycle state machine)
  2. payment_success is emitted by PaymentCallback.onSuccess
  3. Check logs: PaymentCallback.onSuccess has 0 invocations in the last 30 minutes
  4. Check upstream: PaymentService.hold calls are succeeding (200 responses)
  5. Diagnosis: payment-service is accepting hold requests but not sending callbacks
  6. Check: payment-service webhook endpoint may be misconfigured or down
```

**When to use**: "Something seems wrong with orders" / "Users are complaining about stuck payments"

---

## 6. Database Query Integration

### 6.1 Purpose

When debugging, AI often needs to check the actual data state — "what is this order's current status?", "how many orders are stuck in PENDING?". The entity YAML provides schema context so AI can construct meaningful queries.

### 6.2 Safety

- **Read-only connections only** — the engine MUST use read-only database credentials
- **Sensitive field masking** — fields marked `sensitive: true` in entity YAML are masked in output (e.g., phone → `138****1234`)
- **Query limits** — all queries have `LIMIT` enforced, no full table scans
- **Audit log** — every query executed is logged with who requested it and why

### 6.3 Configuration

```yaml
runtime:
  databases:
    - datasource: order-db          # matches entity YAML datasource field
      type: mysql
      url: jdbc:mysql://readonly-replica:3306/orders
      readonly: true                # enforced at connection level
      max_rows: 100                 # hard limit per query
```

### 6.4 How AI Uses It

AI doesn't write raw SQL. It uses the entity schema as a guide:

```
AI needs: current state of order 12345
Entity schema: orders table, fields: id, userId, status, totalAmount, createdAt
Relation: orders.id → order_items.orderId (one_to_many)

Generated query: SELECT id, userId, status, totalAmount, createdAt
                 FROM orders WHERE id = '12345'
                 (phone field excluded — marked sensitive)
```

---

## 7. Implementation Plan

### Phase 1: Foundation (MCP tools + file adapter)

**Goal**: `debug_flow` works with local log files in development.

1. Add `@bodhi.trace` tag to inline parser
2. Add `trace_key` field to Flow dataclass and YAML parser
3. Implement `LogEntry` dataclass and `LogAdapter` interface
4. Implement `FileLogAdapter` — search local log files by regex
5. Implement debug reasoning engine (section 3.1 algorithm)
6. Add `debug_flow` MCP tool
7. Add `search_logs` MCP tool
8. Add `runtime.logs` configuration parsing in `bodhi.yaml`
9. Tests with fixture log files

### Phase 2: Database integration

**Goal**: `explain_record` works with real databases.

1. Add read-only database connector with sensitive field masking
2. Implement `explain_record` MCP tool
3. Add `runtime.databases` configuration parsing
4. Query builder guided by entity schema
5. Tests with test database

### Phase 3: Production log sources

**Goal**: Works with Elasticsearch, Loki, CloudWatch.

1. Implement `ElasticsearchAdapter`
2. Implement `LokiAdapter`
3. Implement `CloudWatchAdapter`
4. Connection pooling and timeout handling
5. Authentication (basic, API key, AWS IAM)

### Phase 4: Anomaly analysis

**Goal**: `analyze_anomaly` provides graph-guided reasoning for symptoms.

1. Implement `analyze_anomaly` MCP tool
2. Log rate comparison (expected vs actual)
3. Cross-step gap detection (step N succeeds but step N+1 never logs)
4. Integration with state machine knowledge (expected transitions vs actual)

### Phase 5: Real-time streaming (optional)

**Goal**: Continuous monitoring with graph-aware alerting.

1. Implement `tail` on each adapter
2. Pattern match stream against `@bodhi.log.*` registry
3. Alert rules derived from flow expectations
4. WebSocket push to dashboard

---

## 8. New Tags Summary

| Tag | Purpose | Example |
|-----|---------|---------|
| `@bodhi.trace` | Declare correlation ID for flow tracing | `@bodhi.trace orderId` |
| `@bodhi.log.success` | (existing) Success log pattern | `@bodhi.log.success "Order {orderId} created"` |
| `@bodhi.log.error` | (existing) Error log pattern | `@bodhi.log.error "Payment failed: {reason}"` |

Flow YAML addition:

| Field | Purpose | Example |
|-------|---------|---------|
| `trace_key` | Correlation ID field name for this flow | `trace_key: orderId` |

`bodhi.yaml` addition:

| Section | Purpose |
|---------|---------|
| `runtime.logs` | Log source adapter configurations |
| `runtime.databases` | Read-only database connections |
| `runtime.time_window` | Default search window for log correlation |
| `runtime.default_trace_field` | Fallback correlation field |
