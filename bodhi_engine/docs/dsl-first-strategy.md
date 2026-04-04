ban# DSL-First Strategy: Preventing AI from Forgetting DSL

## Problem Statement

When using Bodhi DSL in new projects with AI-assisted code generation (Claude Code / CLAUDE.md driven), the AI
frequently:

- Forgets to write `@bodhi.*` inline tags on new methods
- Omits critical tags like `@bodhi.reads`, `@bodhi.writes`, `@bodhi.calls` even when `@bodhi.intent` is present
- Skips Layer 2 YAML files (flows, services, events, states)
- Misses entity definitions when creating new ORM models or database tables

Root causes:

1. **Context Saturation** — as conversations grow longer, the AI's attention drifts away from DSL rules
2. **Task Decomposition** — large tasks cause the AI to optimize for "getting it done" and cut corners on metadata
3. **Soft constraints only** — CLAUDE.md rules are probabilistic, not deterministic; the AI can and will ignore them
   under pressure

## Solution: Three-Layer Defense

```
┌─────────────────────────────────────────────┐
│  Layer A: DSL-First Workflow (Design Phase)  │  ← Architect before coding
├─────────────────────────────────────────────┤
│  Layer B: Co-generation (Implementation)     │  ← Tags written WITH code
├─────────────────────────────────────────────┤
│  Layer C: Hook Validation (Hard Gate)        │  ← Block on missing DSL
└─────────────────────────────────────────────┘
```

### Layer A: DSL-First Workflow

For new features or significant changes, the AI must design the flow BEFORE writing any implementation code.

**Workflow:**

```
1. Receive task
2. Design: write/update .bodhi/flows/<name>.yaml with entry, steps, entities, events
3. Design: write/update .bodhi/entities/<table>.yaml if new tables are needed
4. Design: write/update .bodhi/events/<name>.yaml if new events are introduced
5. Implement: for each step in the flow, write inline tags + code together
6. Validate: hook checks run automatically after each file edit
```

**Why this works:** The flow YAML acts as a contract. The AI commits to the architecture before writing code, so it
can't "forget" components — they're already defined in the flow.

**When to use DSL-first:**

- New feature implementation
- New API endpoint
- New event-driven workflow
- New service integration

**When NOT to use DSL-first (just co-generate):**

- Bug fixes
- Refactoring without behavior change
- Adding a field to an existing method
- Performance optimization

### Layer B: Co-generation Rules

During implementation, inline tags are written simultaneously with code — not before, not after.

**The rule:** Every method gets its `@bodhi.*` tags in the same edit that creates or modifies the method body. No "I'll
add tags later" — there is no later.

**Complete vs Incomplete example:**

❌ **Incomplete (what the AI tends to produce):**

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

Problems: has `@bodhi.intent` but missing reads, writes, calls, emits, on_fail. The deriver gets almost nothing useful
from this.

✅ **Complete (what we require):**

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

**Self-check questions the AI must answer before moving to the next method:**

1. Does this method read external input? → Need `@bodhi.reads`
2. Does this method write to DB/cache/file? → Need `@bodhi.writes`
3. Does this method call another service or important internal method? → Need `@bodhi.calls`
4. Does this method publish an event (MQ, EventBus, WebSocket)? → Need `@bodhi.emits`
5. Does this method consume an event? → Need `@bodhi.consumes`
6. Can this method fail in a business-meaningful way? → Need `@bodhi.on_fail`

### Layer C: Hook Validation (Hard Gate)

The `bodhi-check.sh` PostToolUse hook is the last line of defense. It runs after every Edit/Write and blocks the AI if
DSL is incomplete.

**Current checks:**

- Missing `@bodhi.intent` on public methods (Java, Python, TS/JS, Go, Kotlin)

**Enhanced checks (to be added):**

| Check                   | Trigger                                                                                      | What it catches                                     |
|-------------------------|----------------------------------------------------------------------------------------------|-----------------------------------------------------|
| Missing `@bodhi.writes` | Method body contains DB write patterns (`save`, `insert`, `update`, `delete`, `repository.`) | AI wrote DB code but forgot `@bodhi.writes`         |
| Missing `@bodhi.calls`  | Method body contains remote call patterns (`restTemplate`, `httpClient`, `fetch`, `grpc`)    | AI made a remote call but forgot `@bodhi.calls`     |
| Missing `@bodhi.emits`  | Method body contains event publish patterns (`kafkaTemplate`, `emit`, `publish`, `send`)     | AI published an event but forgot `@bodhi.emits`     |
| Missing entity YAML     | New ORM model/entity class created                                                           | AI created a DB model but forgot `.bodhi/entities/` |
| Tag-code consistency    | `@bodhi.writes` says INSERT but code does UPDATE                                             | Tags don't match implementation                     |

**Why hooks are the most important layer:** They are deterministic. The AI cannot proceed past a hook failure. Unlike
CLAUDE.md rules (which are probabilistic), hooks provide a hard gate that guarantees compliance.

## CLAUDE.md Improvements

### 1. Add DSL-First Workflow Section

Add a workflow section that tells the AI to design before coding:

```markdown
## Workflow: DSL-First for New Features

When implementing a new feature, API endpoint, or event workflow:

1. **Design first**: Create/update the flow YAML in `.bodhi/flows/`
2. **Define entities**: Create/update `.bodhi/entities/` for any new tables
3. **Define events**: Create/update `.bodhi/events/` for any new events
4. **Implement**: Write each method with inline tags + code together
5. **Validate**: Let the hook verify completeness

Do NOT jump straight to writing code. The flow YAML is your contract.
```

### 2. Add Complete vs Incomplete Examples

Put the ❌/✅ comparison directly in CLAUDE.md. Pattern matching is more effective than rules for AI — seeing what "
complete" looks like is worth more than ten bullet points saying "don't forget X".

### 3. Add Self-Check Trigger

```markdown
## Before Moving to Next Method

Ask yourself these 6 questions:

1. Reads external input? → @bodhi.reads
2. Writes to storage? → @bodhi.writes
3. Calls another service/method? → @bodhi.calls
4. Publishes event? → @bodhi.emits
5. Consumes event? → @bodhi.consumes
6. Can fail meaningfully? → @bodhi.on_fail

If you answer "yes" to any question but the tag is missing, add it NOW.
```

### 4. Keep CLAUDE.md Focused

Do NOT split DSL rules into a separate file. CLAUDE.md is auto-loaded into context; external files require the AI to
actively read them, which is itself a step that can be forgotten. Keep all critical rules in CLAUDE.md, but keep it
concise — under 300 lines.

## Implementation Checklist

- [ ] Update `templates/CLAUDE.md` with DSL-first workflow, examples, and self-check
- [ ] Enhance `templates/.claude/hooks/bodhi-check.sh` with writes/calls/emits/entity checks
- [ ] Add integration tests for the enhanced hook
- [ ] Test the full workflow on a sample project: task → flow YAML → implementation → hook validation

## Effectiveness Expectations

| Defense Layer                    | Reliability | What it catches                                    |
|----------------------------------|-------------|----------------------------------------------------|
| DSL-First workflow (CLAUDE.md)   | ~70-80%     | Missing flows, missing architectural thinking      |
| Co-generation rules (CLAUDE.md)  | ~60-70%     | Missing inline tags (degrades with context length) |
| Hook validation (bodhi-check.sh) | ~95%+       | Any remaining gaps — hard gate                     |
| Combined                         | ~98%+       | Near-complete DSL coverage                         |

The key insight: no single layer is sufficient. CLAUDE.md rules degrade as context grows. Hooks catch what rules miss.
DSL-first design prevents entire categories of omission. Together, they form a reliable system.
