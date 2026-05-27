# Bodhi MCP Server — Usage Guide

Bodhi includes a local [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes your project's knowledge graph to AI coding assistants. This lets AI tools like Claude Code query your flows, entities, events, services, channels, and topologies in real time while you work.

## Prerequisites

```bash
pip install bodhi-engine
```

Your project must have a `.bodhi/` directory with YAML files (run `/bodhi init` or create them manually).

## Starting the Server

### Standalone (for testing)

```bash
bodhi serve /path/to/your-project
```

This starts the MCP server on stdio. It's mainly useful for verifying the server works — in practice, you'll configure it as an MCP server in your AI tool.

### With Claude Code

Add to your project's `.claude/settings.json` (project-level) or `~/.claude/settings.json` (global):

```json
{
  "mcpServers": {
    "bodhi": {
      "command": "bodhi",
      "args": ["serve", "/path/to/your-project"]
    }
  }
}
```

Replace `/path/to/your-project` with the absolute path to your project root (the directory containing `.bodhi/`).

After saving, restart Claude Code. You should see "bodhi" listed when you check available MCP servers.

### With Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "bodhi": {
      "command": "bodhi",
      "args": ["serve", "/path/to/your-project"]
    }
  }
}
```

Restart Claude Desktop after saving.

### Excluding directories

If your project has directories that should be skipped during inline tag parsing (e.g., vendored code, generated code):

```json
{
  "mcpServers": {
    "bodhi": {
      "command": "bodhi",
      "args": ["serve", "/path/to/your-project", "--exclude", "vendor", "generated"]
    }
  }
}
```

## Available Tools

Once connected, AI has access to the following tools:

### Query Tools

| Tool | What it does | Example question |
|------|-------------|-----------------|
| `query_flow` | Return the complete call chain for a flow | "How does the create order API work?" |
| `trace_entity` | Find all functions that read/write a table | "What touches the `orders` table?" |
| `find_consumers` | Find all producers and consumers of an event | "What happens when `order_created` fires?" |
| `impact_analysis` | Trace the blast radius of a change | "What breaks if I change `OrderService.create`?" |
| `query_state` | Return state machine transitions | "What are the valid transitions from PAID?" |
| `service_deps` | Return upstream/downstream service dependencies | "What does order-service depend on?" |
| `query_channel` | Return a bidirectional channel definition | "What events does the order WebSocket handle?" |
| `query_topology` | Return a cross-service event chain | "How does the order fulfillment event flow work?" |

### List Tools

| Tool | What it returns |
|------|----------------|
| `list_flows` | All flow names |
| `list_entities` | All entity/table names |
| `list_events` | All event names |
| `list_services` | All service names |
| `list_state_machines` | All state machine names |
| `list_channels` | All channel names |
| `list_topologies` | All topology names |

## Usage Examples

Once the MCP server is connected, you can ask AI natural language questions and it will use the appropriate tools automatically.

### Understanding a flow

> "How does order creation work?"

AI calls `query_flow("create_order")` and gets back:

```json
{
  "name": "create_order",
  "description": "Order creation flow",
  "entry": {
    "type": "http",
    "method": "POST",
    "path": "/api/orders",
    "auth": "required(role=USER)"
  },
  "steps": [
    {
      "fn": "OrderService.create",
      "intent": "Receive request, orchestrate order creation",
      "reads": ["request.body(userId, items, address)"],
      "calls": ["InventoryService.deduct", "OrderRepository.save"]
    },
    {
      "fn": "InventoryService.deduct",
      "intent": "Deduct inventory",
      "remote": "inventory-service",
      "protocol": "grpc",
      "api": "InventoryService/DeductStock"
    },
    {
      "fn": "OrderRepository.save",
      "intent": "Persist order",
      "writes": ["orders(id, userId, totalAmount, status=PENDING) via INSERT"]
    }
  ],
  "entities": ["orders", "inventory"],
  "events": ["order_created"]
}
```

### Impact analysis before making a change

> "What will be affected if I change the orders table schema?"

AI calls `impact_analysis("orders")` and gets back all flows, functions, events, and state machines that reference the `orders` entity.

### Tracing an event chain

> "What happens system-wide when order_created fires?"

AI calls `find_consumers("order_created")` to see direct producers/consumers, then `query_topology("order_fulfillment")` to see the full cross-service event chain:

```json
{
  "name": "order_fulfillment",
  "chains": [
    {
      "event": "order_created",
      "channel": "kafka:order-events",
      "producer": "order-service",
      "consumers": [
        {
          "service": "payment-service",
          "action": "Initiate payment collection",
          "emits": "payment_completed"
        },
        {
          "service": "notification-service",
          "action": "Send order confirmation email"
        }
      ]
    },
    {
      "event": "payment_completed",
      "channel": "kafka:payment-events",
      "producer": "payment-service",
      "consumers": [
        {
          "service": "order-service",
          "action": "Update order status to PAID",
          "emits": "order_paid"
        }
      ]
    }
  ]
}
```

### Understanding a state machine

> "What are the valid transitions from PENDING?"

AI calls `query_state("order_lifecycle", "INIT")`:

```json
{
  "state_machine": "order_lifecycle",
  "entity": "orders",
  "state": "INIT",
  "transitions": [
    {
      "target": "PAID",
      "trigger": "event(payment_success)",
      "fn": "PaymentCallback.onSuccess"
    },
    {
      "target": "CANCELLED",
      "trigger": "timeout(30m)",
      "fn": "OrderService.cancel"
    }
  ]
}
```

### Checking service dependencies

> "What does order-service depend on?"

AI calls `service_deps("order-service")` and gets the full dependency graph including protocols, APIs, and resilience policies.

## Troubleshooting

### "bodhi: command not found"

The `bodhi` CLI is installed via `pip install bodhi-engine`. Make sure it's in your PATH:

```bash
which bodhi
# If not found, try:
pip install bodhi-engine
# Or use the full path:
python -m bodhi_engine.cli.main serve /path/to/your-project
```

### "BodhiKnowledge not initialized"

The server can't find or parse the `.bodhi/` directory. Check that:
1. The path you passed to `bodhi serve` contains a `.bodhi/` directory
2. The YAML files in `.bodhi/` are valid (run `bodhi lint /path/to/your-project` to check)

### Tools return empty results

The knowledge graph is built from both `.bodhi/` YAML files and inline `@bodhi.*` tags in source code. If results are sparse:
- Run `bodhi stats /path/to/your-project` to check coverage
- Run `/bodhi scan` to add inline tags to existing code
- Check that source files use a supported language (Java, Python, Go, TypeScript, Kotlin, Rust, C#, C, C++)

### MCP server not showing up in Claude Code

1. Verify the config path: `.claude/settings.json` in the project root, or `~/.claude/settings.json` for global config
2. Verify JSON syntax is valid
3. Restart Claude Code after changing the config
4. Check that `bodhi serve /path/to/your-project` runs without errors when executed manually
