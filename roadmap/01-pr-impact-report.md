# PR Impact Report (GitHub Action)

**Priority**: P0 — Do first
**Effort**: Small
**Value**: High — visible on every PR without user action

## Problem

Bodhi builds a rich knowledge graph at write time, but developers only benefit when they actively query it. Most won't. The graph needs to surface value passively, where developers already are: **pull request reviews**.

Without Bodhi, reviewers rely on experience to judge blast radius. They frequently miss downstream impacts — especially cross-service event consumers, state machine side effects, and implicit entity dependencies.

## Solution

A GitHub Action that runs on every PR and posts an **impact analysis comment** derived from the Bodhi knowledge graph.

### Example output

```markdown
## Bodhi Impact Analysis

### Changed functions
- `OrderService.create` (modified)

### Affected flows
- `create_order` (POST /api/orders) — this is the entry point

### Data impact
- Writes to: `orders` table (status=PENDING) via INSERT
- Reads from: `inventory` table (productId, stock)

### Event impact
- Produces: `order_created` → kafka:order-events
  - Consumed by: `payment-service` (PaymentHandler.onOrderCreated)
  - Consumed by: `notification-service` (NotificationHandler.onOrderCreated)

### Cross-service dependencies
- Calls: `inventory-service` via gRPC (InventoryService/DeductStock)
- Calls: `payment-service` via HTTP (POST /api/payments/hold)

### Risks
- order_created event schema change will affect 2 downstream services
- inventory deduction is a remote gRPC call with circuit_breaker — verify timeout handling
```

### How it works

1. `git diff` identifies changed source files
2. `bodhi` inline parser extracts which functions were modified
3. Knowledge graph traces: modified function → flows → entities → events → services → state machines
4. Render a markdown comment with the full impact chain
5. Post to the PR via GitHub API

### Implementation

- New CLI command: `bodhi impact-pr` — takes a git diff (or base..head range), outputs markdown
- GitHub Action wrapper: runs `bodhi impact-pr`, posts result as PR comment
- Should work without `.bodhi/` YAML (inline tags alone provide partial impact), but richer with YAML

### What makes this valuable

- **Zero effort for the developer** — runs automatically on every PR
- **Immediate ROI** — the first time a reviewer catches a missed downstream impact, Bodhi pays for itself
- **Builds habit** — developers see Bodhi output on every PR, understand the graph's value without being told
- **CI gate potential** — can fail the PR if critical impacts are detected (e.g., event schema change without consumer update)
