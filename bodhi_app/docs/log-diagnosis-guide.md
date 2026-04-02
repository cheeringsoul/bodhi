# Log Diagnosis — Usage Guide

Bodhi can diagnose production issues from log snippets. When a user pastes error logs into an AI assistant, Bodhi matches the log text against `@bodhi.log.*` patterns in the knowledge graph, identifies which function produced the log, locates it within a flow, and provides full upstream/downstream context.

**No log file access required.** The log is user input — Bodhi's knowledge graph does the reasoning.

## How It Works

```
User pastes log snippet
       ↓
Engine matches against @bodhi.log.* pattern registry
       ↓
Identifies function + extracts business variables (orderId=12345)
       ↓
Locates the function in flow steps
       ↓
Returns: what failed, what succeeded before it, what was never reached,
         affected events/entities/state machines
```

## Prerequisites

1. Functions must have `@bodhi.log.success` and/or `@bodhi.log.error` tags
2. The MCP server must be running (`bodhi serve` or `bodhi serve-all`)

## Step 1: Tag Your Functions

Add log patterns to your function annotations. The `{placeholder}` syntax tells Bodhi how to parse the log and extract business variables.

```java
/**
 * @bodhi.intent Create order, deduct inventory, publish event
 * @bodhi.trace orderId
 * @bodhi.log.success "Order {orderId} created successfully"
 * @bodhi.log.error "Order creation failed for user {userId}: {reason}"
 */
public OrderResponse create(CreateOrderRequest req) { ... }
```

```java
/**
 * @bodhi.intent Hold payment for order
 * @bodhi.log.success "Payment held: {transactionId} for order {orderId}"
 * @bodhi.log.error "Payment failed for order {orderId}: {reason}"
 */
public PaymentResult hold(Long orderId, BigDecimal amount) { ... }
```

### Tag Reference

| Tag | Purpose | Example |
|-----|---------|---------|
| `@bodhi.log.success` | Log pattern when function succeeds | `"Order {orderId} created successfully"` |
| `@bodhi.log.error` | Log pattern when function fails | `"Payment failed for order {orderId}: {reason}"` |
| `@bodhi.trace` | Correlation ID field for this function | `orderId` |

The `{placeholder}` values serve dual purpose:
- **At write time**: tell developers what to log
- **At diagnosis time**: tell the engine how to extract business variables from logs

## Step 2: Use the MCP Tool

Once the MCP server is connected, the AI has access to the `diagnose_log` tool.

### Example: Diagnosing a payment failure

User pastes this log into the AI:

```
2026-04-02 10:30:05 ERROR Payment failed for order 12345: timeout
```

AI calls `diagnose_log` with the log text. Bodhi returns:

```json
{
  "matched": true,
  "matches": [
    {
      "fn": "PaymentService.hold",
      "type": "error",
      "matched_line": "2026-04-02 10:30:05 ERROR Payment failed for order 12345: timeout",
      "extracted_variables": {
        "orderId": "12345",
        "reason": "timeout"
      },
      "intent": "Hold payment for order"
    }
  ],
  "flow_context": {
    "create_order": {
      "name": "create_order",
      "entry": {"type": "http", "method": "POST", "path": "/api/orders"},
      "matched_step_index": 2,
      "upstream_steps": [
        {"fn": "OrderService.create", "intent": "Create order"},
        {"fn": "InventoryService.deduct", "intent": "Deduct inventory"}
      ],
      "matched_step": {
        "fn": "PaymentService.hold",
        "intent": "Hold payment",
        "remote": "payment-service",
        "protocol": "http"
      },
      "downstream_steps": [
        {"fn": "EventPublisher.publish", "intent": "Publish event", "emits": ["order_created"]}
      ]
    }
  },
  "impact": {
    "PaymentService.hold": {
      "affected_flows": ["create_order"],
      "affected_events": ["order_created"],
      "affected_state_machines": ["order_lifecycle"]
    }
  }
}
```

From this, AI can tell the user:

> PaymentService.hold failed with a timeout for order 12345. This is step 3 in the create_order flow. Steps 1-2 (create order, deduct inventory) likely succeeded, but step 4 (publish order_created event) was never reached. Downstream consumers (payment-service, notification-service) will not be triggered. The order is likely stuck in PENDING state.

### Example: Multi-line log

```
2026-04-02 10:30:01 INFO Order 12345 created successfully
2026-04-02 10:30:02 INFO Inventory deducted for product P99
2026-04-02 10:30:05 ERROR Payment failed for order 12345: timeout
```

Bodhi matches all three lines, showing which steps succeeded and which failed — without needing access to the actual log files.

### Example: Function name fallback

Even without `@bodhi.log.*` tags, if a log line contains a known function name:

```
OrderService.create received request for user U123
```

Bodhi will match by function name (with `pattern_type: "function_name"`) and still provide flow context.

## How the Pattern Registry Works

At startup, the engine scans all inline `@bodhi.log.success` and `@bodhi.log.error` tags and compiles them into regex patterns:

```
Pattern:  "Order {orderId} created successfully"
Compiled: /Order (.+?) created successfully/i

Pattern:  "Payment failed for order {orderId}: {reason}"
Compiled: /Payment failed for order (.+?): (.+)/i
```

When `diagnose_log` is called, each line of the user's log text is tested against every pattern. Matches extract the named variables (`orderId`, `reason`) and link back to the function, flow, and knowledge graph.

## Limitations

- Only functions with `@bodhi.log.*` tags are matched by pattern. Untagged functions fall back to function-name matching.
- The diagnosis is based on the knowledge graph's static structure — it shows what *should* happen, not what *did* happen at runtime.
- Log patterns must match the actual log format. If the real log format differs from the tag pattern, it won't match.
