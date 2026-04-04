# Multi-Service Workspace — Usage Guide

Bodhi supports querying across multiple microservice repos at once. Place all your service repos in a single directory,
and Bodhi will scan each one's `.bodhi/` metadata, merge them into a unified knowledge graph, and validate cross-service
consistency.

## Directory Structure

```
workspace/
  order-service/
    .bodhi/
      bodhi.yaml
      flows/
      entities/
      events/
      services/
    src/
  payment-service/
    .bodhi/
      bodhi.yaml
      flows/
      events/
      services/
    src/
  inventory-service/
    .bodhi/
      ...
    src/
```

Each subdirectory with a `.bodhi/` folder is treated as a service. The service name is resolved from (in priority
order):

1. `distributed.service` in `bodhi.yaml`
2. `project.name` in `bodhi.yaml`
3. The directory name

## Quick Start

### Validate cross-service consistency

```bash
bodhi workspace-validate ./workspace
```

Output:

```
Services found: order-service, payment-service, inventory-service
Flows: 5
Events: 3
Services: 3

Errors (1):
  [error] event-schema-mismatch (payment-service): Event 'order_created' has
    inconsistent schema between order-service and payment-service.
    fields in order-service but not payment-service: ['userId'];
    fields in payment-service but not order-service: ['buyerId']
Warnings (2):
  [warning] event-no-consumer: Event 'payment_completed' has producers but no consumers
  [warning] unknown-dependency (order-service): Service 'order-service' depends on
    'kafka' which is not found in workspace
```

### Start federated MCP server

```bash
bodhi serve-all ./workspace
```

This starts an MCP server with the merged knowledge graph from all services. If there are validation errors (
severity=error), the server refuses to start — fix the issues first.

### Configure with Claude Code

```json
{
  "mcpServers": {
    "bodhi-workspace": {
      "command": "bodhi",
      "args": [
        "serve-all",
        "/path/to/workspace"
      ]
    }
  }
}
```

## Available MCP Tools

### Cross-Service Query Tools

| Tool                   | What it does                                           | Example question                                                 |
|------------------------|--------------------------------------------------------|------------------------------------------------------------------|
| `trace_event_chain`    | Follow an event across all services                    | "What happens system-wide when order_created fires?"             |
| `cross_service_impact` | Blast radius of a change across all services           | "What breaks across the system if I change OrderService.create?" |
| `event_schema_diff`    | Compare event schema across producer/consumer services | "Is the order_created schema consistent?"                        |
| `service_deps`         | Full dependency graph for a service                    | "What does order-service depend on?"                             |
| `workspace_issues`     | Show all cross-service validation issues               | "Are there any consistency problems?"                            |

### Standard Query Tools (workspace-scoped)

| Tool              | What it does                                  |
|-------------------|-----------------------------------------------|
| `query_flow`      | Query a flow by `"service:flow_name"` key     |
| `list_services`   | List all services with descriptions           |
| `list_all_flows`  | List all flows across all services            |
| `list_all_events` | List all events with producer/consumer counts |

## Usage Examples

### Tracing an event chain

> "What happens when order_created fires?"

AI calls `trace_event_chain("order_created")`:

```json
{
  "event": "order_created",
  "channel": "kafka:order-events",
  "producers": [
    {
      "fn": "OrderService.create",
      "flow": "create_order"
    }
  ],
  "consumers": [
    {
      "fn": "PaymentHandler.onOrderCreated",
      "flow": "hold_payment"
    },
    {
      "fn": "NotificationHandler.onOrderCreated"
    }
  ]
}
```

### Cross-service impact analysis

> "What breaks if I change the orders table schema?"

AI calls `cross_service_impact("orders")`:

```json
{
  "target": "orders",
  "affected_flows": [
    "order-service:create_order",
    "order-service:cancel_order"
  ],
  "affected_events": [
    "order_created"
  ],
  "affected_state_machines": [
    "order-service:order_lifecycle"
  ]
}
```

### Detecting schema mismatches

> "Is the order_created event consistent across services?"

AI calls `event_schema_diff("order_created")`:

```json
{
  "event": "order_created",
  "consistent": false,
  "schemas": {
    "order-service": [
      {
        "field": "orderId",
        "type": "string"
      },
      {
        "field": "userId",
        "type": "string"
      },
      {
        "field": "totalAmount",
        "type": "decimal"
      }
    ],
    "payment-service": [
      {
        "field": "orderId",
        "type": "string"
      },
      {
        "field": "buyerId",
        "type": "string"
      },
      {
        "field": "totalAmount",
        "type": "decimal"
      }
    ]
  },
  "mismatches": [
    {
      "field": "userId",
      "present_in": [
        "order-service"
      ],
      "missing_from": [
        "payment-service"
      ]
    },
    {
      "field": "buyerId",
      "present_in": [
        "payment-service"
      ],
      "missing_from": [
        "order-service"
      ]
    }
  ]
}
```

Root cause: order-service uses `userId`, payment-service expects `buyerId`.

## Validation Rules

These are checked automatically when loading the workspace:

| Code                     | Severity | What it checks                                          |
|--------------------------|----------|---------------------------------------------------------|
| `event-schema-mismatch`  | ERROR    | Same event has different fields across services         |
| `broken-flow-ref`        | ERROR    | `flow_ref` points to a service:flow that doesn't exist  |
| `duplicate-service`      | ERROR    | Two directories resolve to the same service name        |
| `unknown-remote-service` | WARNING  | Flow step calls a remote service not in the workspace   |
| `unknown-dependency`     | WARNING  | Service depends on another service not in the workspace |
| `event-no-consumer`      | WARNING  | Event has producers but no consumers                    |
| `topology-unknown-event` | WARNING  | Topology references an event not defined in any service |

Errors block `serve-all` from starting. Warnings are printed but don't block.

## Comparison: `serve` vs `serve-all`

|               | `bodhi serve`                         | `bodhi serve-all`                                   |
|---------------|---------------------------------------|-----------------------------------------------------|
| Scope         | Single service repo                   | All services in a workspace                         |
| Input         | One `.bodhi/` directory               | Multiple `.bodhi/` directories                      |
| Flow keys     | `"create_order"`                      | `"order-service:create_order"`                      |
| Cross-service | Limited (only what one service knows) | Full (merged from all services)                     |
| Validation    | Single-service rules                  | Cross-service consistency checks                    |
| Use case      | Day-to-day development                | Architecture review, debugging cross-service issues |
