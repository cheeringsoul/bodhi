# Runtime Intelligence: Logs, Debug, and Database-Driven Business Analysis

**Priority**: P2 — Do third
**Effort**: Large
**Value**: Very High — transforms Bodhi from a static annotation tool into a live operational intelligence layer

## Problem

Bodhi's knowledge graph captures the *design-time* truth: what the code does, why, how data flows, what events connect which services. But when something goes wrong in production — a stuck order, a failed payment, a mysterious data anomaly — developers still fall back to manual investigation: grep logs, write ad-hoc SQL queries, trace through code, and piece together the story from scattered data points.

The knowledge graph already knows the causal structure. Logs, database records, and metrics are the raw facts. Connecting the two is what turns hours of debugging into minutes of AI-assisted reasoning.

## Core Idea

Bodhi's static knowledge graph becomes the **reasoning skeleton** for runtime data analysis. AI doesn't just search — it follows the graph's causal structure to ask the right questions in the right order.

```
Static graph (Bodhi)          Runtime data (logs, DB, metrics)
─────────────────────         ─────────────────────────────────
flow: create_order       +    log: "Payment timeout for order 12345"
  step 1: deduct inventory    DB: orders WHERE id=12345 → status=PENDING
  step 2: hold payment        DB: inventory WHERE product_id=99 → stock decreased
  step 3: publish event       log: no order_created event emitted
                          =
AI conclusion: inventory was deducted (step 1 succeeded),
payment timed out (step 2 failed), event was never published
(step 3 never reached). Need to rollback inventory for order 12345.
```

## Use Case 1: Log-Driven Debug

### Scenario

User reports: "Order 12345 is stuck in PENDING status."

### Without Bodhi

1. Search logs for order 12345 — find several log lines across multiple services
2. Read code to understand what PENDING means and what should trigger the next transition
3. Check if payment service received the request
4. Check if the callback was received
5. Manually correlate timestamps across services
6. 30-60 minutes to root cause

### With Bodhi

```
User: "Why is order 12345 stuck in PENDING?"

AI reasoning (using knowledge graph):
1. Query state machine: order_lifecycle → PENDING transitions to PAID via event(payment_success),
   triggered by PaymentCallback.onSuccess
2. Query flow: create_order → step 2 is PaymentService.hold (remote: payment-service, protocol: http)
3. Search logs for order 12345:
   - [order-service] "Calling PaymentService.hold for order 12345" ✓
   - [order-service] "Payment timeout for order 12345, circuit breaker triggered" ✗
   - No PaymentCallback.onSuccess log found
4. Query: @bodhi.on_fail payment_timeout → circuit_breaker(threshold=5, window=60s) → reject 503

AI answer: "Order 12345 is stuck because payment-service timed out. The circuit breaker
was triggered (5 failures in 60s window). No payment_success callback was received, so
the state never transitioned from PENDING to PAID. The order also has deducted inventory
(step 1 completed) that needs rollback."
```

### Implementation

- Connect to log sources (file, Elasticsearch, CloudWatch, Loki) via configurable adapters
- `@bodhi.log.success` and `@bodhi.log.error` patterns become structured log queries — AI knows exactly what log pattern to search for each function
- Correlate logs to flow steps using function names and log patterns from the graph
- Trace the execution path: which steps produced logs (succeeded) and which didn't (failed or never reached)

## Use Case 2: Database-Driven Business Analysis

### Scenario

User asks: "Why does this user have 3 duplicate orders?"

### With Bodhi

```
AI reasoning:
1. Query entity schema: orders table — fields: id, userId, totalAmount, status, createdAt
   Unique constraint? None on (userId + items) — no dedup at DB level
2. Query flow: create_order → check @bodhi.idempotent? Not present on OrderService.create
3. Query DB: SELECT * FROM orders WHERE user_id = 'U123' ORDER BY created_at
   → 3 orders created within 2 seconds, same items, same amount
4. Query logs around that timestamp: 3 POST /api/orders requests from the same client

AI answer: "User U123 submitted 3 identical requests within 2 seconds (likely double-click
or retry without idempotency). OrderService.create has no @bodhi.idempotent tag — there's
no dedup mechanism. The 3 orders are genuine duplicates.

Suggested fix: add idempotency key on (userId + itemsHash + timeWindow). This would be
tagged as @bodhi.idempotent key=userId+itemsHash,window=5s"
```

### Implementation

- Connect to databases via read-only connections (configured per datasource in entity YAML)
- Entity YAML provides the schema context — AI knows field meanings, relations, state machines, sensitive fields
- AI constructs queries guided by the graph: it knows which table to check, what fields matter, and how entities relate
- Sensitive fields (`sensitive: true`) are automatically masked or excluded from output

## Use Case 3: Real-Time Log Stream Analysis

### Scenario

Ops team wants continuous monitoring with business-aware alerting.

### With Bodhi

```
Log stream → Bodhi engine matches log patterns to @bodhi.log.* tags
  → Correlate to flows and functions
  → Detect anomalies in the context of the knowledge graph

Example alerts:
- "order_created event rate dropped 80% in last 5 minutes, but POST /api/orders
   request rate is unchanged → OrderService.create is likely failing before the
   emit step. Check InventoryService.deduct (remote: inventory-service via gRPC)"

- "PaymentCallback.onSuccess has not been called for any order in 10 minutes,
   but PaymentService.hold calls are succeeding → payment-service webhook
   callback is broken, orders will pile up in PENDING state"
```

### Implementation

- Log stream consumer (tail file, subscribe to Kafka/Redis log topic, poll Elasticsearch)
- Pattern matcher: maps incoming logs to `@bodhi.log.success` / `@bodhi.log.error` patterns
- Flow-aware anomaly detection: if step N succeeds but step N+1 never logs, something is wrong between them
- Alert rules derived from the graph: the graph knows what *should* happen next, so it can detect when it doesn't

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Bodhi Runtime                      │
│                                                       │
│  ┌─────────────┐    ┌──────────────┐                 │
│  │ Knowledge    │    │ Data Source   │                 │
│  │ Graph        │◄──►│ Connectors   │                 │
│  │ (static)     │    │              │                 │
│  │ flows,       │    │ - Log files  │                 │
│  │ entities,    │    │ - MySQL/PG   │                 │
│  │ events,      │    │ - ES/Loki    │                 │
│  │ state machines│   │ - CloudWatch │                 │
│  └──────┬───────┘    └──────┬───────┘                 │
│         │                   │                         │
│         ▼                   ▼                         │
│  ┌──────────────────────────────────┐                 │
│  │        Reasoning Engine          │                 │
│  │  graph structure + runtime data  │                 │
│  │  = contextual analysis           │                 │
│  └──────────────┬───────────────────┘                 │
│                 │                                     │
│         ┌───────┴────────┐                            │
│         ▼                ▼                            │
│  ┌─────────────┐  ┌──────────────┐                   │
│  │ MCP Tools   │  │ Alerts /     │                   │
│  │ (AI query)  │  │ Dashboards   │                   │
│  └─────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────┘
```

## New MCP Tools

| Tool | What it does |
|------|-------------|
| `debug_flow` | Given a flow name + correlation ID (e.g., order ID), trace which steps succeeded/failed by correlating logs |
| `explain_record` | Given a table + record ID, explain how this record got into its current state using flow and state machine knowledge |
| `query_logs` | Search logs with knowledge-graph context — AI knows which log patterns belong to which functions |
| `analyze_anomaly` | Given a symptom (e.g., "orders stuck in PENDING"), use the graph to reason about probable causes |

## Data Source Configuration

Extend `bodhi.yaml` with runtime data sources:

```yaml
runtime:
  logs:
    - type: file
      path: /var/log/order-service/*.log
      format: json
    - type: elasticsearch
      url: http://es-cluster:9200
      index: "order-service-logs-*"

  databases:
    - datasource: order-db
      type: mysql
      url: jdbc:mysql://localhost:3306/orders
      readonly: true
    - datasource: session-cache
      type: redis
      url: redis://localhost:6379

  metrics:
    - type: prometheus
      url: http://prometheus:9090
```

## Why This Direction

- **Static analysis tools are a crowded market.** Code intelligence, linting, type checking — well-served by existing tools. Bodhi can't win by being another static analyzer.
- **Runtime + static is the gap.** No tool today connects "what the code is designed to do" (static) with "what actually happened" (runtime) in a machine-readable way. Distributed tracing (Jaeger, Zipkin) shows the *mechanical* call chain but not the *semantic* chain (business intent, expected error handling, state machine implications).
- **Bodhi's unique advantage** is that it already has the semantic layer. Adding runtime data connectors turns it from "documentation AI can read" into "operational intelligence AI can reason with."
