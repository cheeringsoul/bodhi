# Cross-Repo Registry and Federated MCP

**Priority**: P1 — Do second
**Effort**: Medium
**Value**: High — the killer feature for distributed systems

## Problem

In a monolith, you can grep for everything. In a distributed system, you can't — the producer is in one repo, the consumer is in another, and the connection between them exists only in tribal knowledge or runtime traces.

Bodhi already models cross-service relationships within a single repo (events, topology, remote flow steps), but querying across repos requires a centralized view. Without it, questions like "what breaks if I change the order_created event schema?" can only be answered by checking each service repo individually.

## Solution

A **bodhi-registry** — a standalone repo that aggregates `.bodhi/` metadata from all services — plus an MCP server that queries the unified graph.

### Registry structure

```
bodhi-registry/
├── bodhi.yaml                    # System-level metadata
├── services/
│   ├── order-service.yaml        # Aggregated from order-service repo
│   ├── payment-service.yaml      # Aggregated from payment-service repo
│   └── inventory-service.yaml
├── events/
│   ├── order_created.yaml        # Merged: producer from order-service, consumers from all
│   └── payment_completed.yaml
├── topology/
│   └── order_fulfillment.yaml    # Cross-service event chains
└── channels/
    └── order_status_ws.yaml
```

### Sync mechanism

Each service repo's CI pipeline pushes its `.bodhi/` metadata to the registry:

1. CI detects changes in `.bodhi/` files (or `# REGISTRY_SYNC_NEEDED` markers)
2. CI runs `bodhi registry-push` — extracts service, event, and topology data
3. Registry repo receives a PR with the updated metadata
4. Registry CI runs `bodhi registry-validate` — checks cross-service consistency (event schema mismatches, missing consumers, broken flow_ref pointers)
5. Merge on green

### Federated MCP server

```bash
bodhi serve-registry /path/to/bodhi-registry
```

New tools beyond single-repo MCP:

| Tool | What it does |
|------|-------------|
| `trace_event_chain` | Follow an event across all services: producer → consumer → downstream event → consumer → ... |
| `cross_service_impact` | "What breaks across the entire system if I change OrderService.create?" |
| `event_schema_diff` | Compare producer schema vs consumer schema, detect mismatches |
| `system_topology` | Full service dependency graph with protocols, events, and resilience policies |

### Key use case: cross-service debugging

```
User: notification-service reports "userId not found in event payload"

AI (via registry MCP):
→ trace_event_chain("order_created")
→ Producer: order-service, schema: {orderId, buyerId, totalAmount}
→ Consumer: notification-service, expects: {orderId, userId}
→ Schema mismatch: producer has 'buyerId', consumer expects 'userId'
→ Root cause: order-service PR #142 renamed userId to buyerId without updating consumers
```

This takes 2 minutes with Bodhi vs 30 minutes of manual cross-repo investigation.

### Implementation plan

1. New CLI commands: `bodhi registry-push`, `bodhi registry-validate`, `bodhi serve-registry`
2. Registry merge logic: combine events from multiple sources (multiple producers/consumers for the same event)
3. Cross-service validation rules: event schema consistency, flow_ref resolution, service dependency cycles
4. MCP server extension: federation-aware query tools
