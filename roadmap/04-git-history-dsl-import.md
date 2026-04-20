# Git History DSL Import: Reverse-Generate Bodhi DSL from Git History

**Priority**: P1 — Critical path for validation and promotion
**Effort**: Medium
**Value**: Very High — Enables Bodhi to be applied to any existing project, opening the door for open-source showcases

## Problem

Bodhi DSL was designed for AI to record its intent (the "why") in real-time while writing code. But for existing projects — especially well-known open-source projects — the code is already written. Purely reverse-engineering intent from the final codebase has inherently lower accuracy, because the final state is the result of many iterations, and it's hard to reconstruct the context in which each method was born by looking at the end state alone.

However, git history naturally preserves the full context of every method's birth and evolution: diffs, commit messages, PR descriptions, and issue discussions. The quality of this information is typically high in well-maintained open-source projects.

**Core insight: Going back to each commit's point in time to generate DSL is essentially "simulating the real-time recording behavior that AI would have during code writing."**

## Core Idea

Walk through git history, reconstruct the context at each commit (diff + message + PR), and have AI generate `@bodhi.*` annotations for methods introduced or modified in that commit. Accumulate incrementally to produce a complete DSL annotation set.

```
Git History                          Bodhi DSL Output
──────────────────                   ──────────────────────────
commit abc123                        @bodhi.intent Create order...
  msg: "feat: add order creation"    @bodhi.writes orders(...)
  diff: +OrderService.create()       @bodhi.calls InventoryService.deduct
                                     @bodhi.emits order_created(...)
         ↓
commit def456                        @bodhi.intent Add retry logic...
  msg: "fix: retry on payment fail"  @bodhi.on_fail payment_timeout → retry 3
  diff: modified PaymentService      
         ↓
commit ghi789                        @bodhi.intent Batch order export...
  msg: "feat: batch export orders"   @bodhi.reads orders(status, createdAt)
  diff: +ExportService.batchExport() @bodhi.writes export_records(...)
```

## Design

### Overall Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  bodhi import-history — Git History DSL Import Pipeline          │
│                                                                  │
│  Phase 1: Commit Analysis (bodhi_engine)                         │
│  ────────────────────────────────────────                        │
│  CommitWalker: Walk git log, filter meaningful commits           │
│  DiffParser: Parse each commit's diff, extract new/modified fns  │
│  ContextCollector: Gather commit message + PR body + issue body  │
│                                                                  │
│  Phase 2: DSL Generation (bodhi_app)                             │
│  ────────────────────────────────────                            │
│  PromptBuilder: Assemble AI prompt (diff + context + DSL spec)   │
│  LLMClient: Call AI to generate @bodhi.* annotations             │
│  ResultParser: Parse AI output into structured annotations       │
│                                                                  │
│  Phase 3: Accumulation & Merge (bodhi_engine)                    │
│  ─────────────────────────────────────────────                   │
│  TagAccumulator: Accumulate tags per method, handle renames      │
│  ConflictResolver: Merge strategy for multi-commit modifications │
│  OutputWriter: Write final inline tags or standalone DSL files   │
│                                                                  │
│  Phase 4: Layer 2 Derivation (existing bodhi derive)             │
│  ────────────────────────────────────────────────────            │
│  Reuse existing bodhi derive to generate flows/events/etc        │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 1: Commit Analysis

#### CommitWalker

```python
class CommitWalker:
    """Walk git history and filter meaningful commits."""
    
    def walk(self, repo_path, branch="main", since=None, until=None):
        """
        Filter strategy:
        - Skip merge commits (redundant information)
        - Skip pure refactor commits (rename/move without logic change)
        - Skip pure config/docs commits (no business code changes)
        - Keep feat/fix/refactor type commits
        """
```

**Filter rules:**

| Keep | Skip |
|------|------|
| feat: / fix: / refactor: | docs: / style: / chore: |
| New/modified .java/.py/.go/.ts files | Only .md/.yml/.json config changes |
| Diff contains method definition changes | Merge commits |
| | Pure rename/move (no logic change) |

#### DiffParser

Reuse existing `parse_diff()` + `find_changed_functions()` logic from `impact_pr.py`, extended to:

```python
class DiffParser:
    """Extract method-level changes from diffs."""
    
    def extract_method_changes(self, diff_text, file_content_at_commit):
        """
        Returns:
        - new_methods: Methods added in this commit (full method body)
        - modified_methods: Methods modified in this commit (before/after)
        - deleted_methods: Methods deleted in this commit
        """
```

Key point: Requires `git show <commit>:<file>` to get the full file content at that commit for accurate method body extraction.

#### ContextCollector

```python
class ContextCollector:
    """Collect full context for a commit."""
    
    def collect(self, commit_hash, repo_path, remote_url=None):
        """
        Collects:
        1. Commit message (always available)
        2. PR description (via GitHub/GitLab API, optional)
        3. PR review comments (optional, may contain design decisions)
        4. Related issue body (extracted from #123 references in commit message)
        """
```

**GitHub API integration (optional enhancement):**
- `gh api repos/{owner}/{repo}/commits/{sha}/pulls` → find associated PR
- `gh api repos/{owner}/{repo}/pulls/{number}` → PR body
- `gh api repos/{owner}/{repo}/issues/{number}` → issue body

For scenarios without GitHub access, using only the commit message still works — just with reduced accuracy.

### Phase 2: DSL Generation

#### PromptBuilder

Build an AI prompt for each method change:

```python
class PromptBuilder:
    """Build AI prompts for DSL generation."""
    
    def build(self, method_change, commit_context, project_context):
        """
        Prompt structure:
        
        1. System: Bodhi DSL spec summary (tag format + examples)
        2. Project context: project overview, tech stack, known entities/services
        3. Commit context: commit message + PR description
        4. Method code: full method body
        5. Instruction: generate @bodhi.* annotations
        """
```

**Core prompt template:**

```
You are a Bodhi DSL annotation expert. Generate @bodhi.* tags for the method based on the following information.

## Commit Context
- Message: {commit_message}
- PR: {pr_description}  (if available)

## Method Code
```{language}
{method_code}
```

## Known Context
- Project entities: {known_entities}
- Project services: {known_services}
- Project events: {known_events}

## Requirements
1. Must include @bodhi.intent (describe motivation in business language, don't restate the code)
2. Based on code logic, determine if needed: @bodhi.reads, @bodhi.writes, @bodhi.calls, @bodhi.emits, @bodhi.consumes, @bodhi.on_fail
3. Output format as JSON:
{
  "intent": "...",
  "reads": ["..."],
  "writes": ["..."],
  "calls": ["..."],
  "emits": ["..."],
  "on_fail": ["..."]
}
```

#### Batch Strategy

To control API cost and speed:
- Multiple methods in the same commit can be batched into one prompt (fewer API calls)
- Use Claude Batch API for processing large numbers of commits (50% cost reduction)
- Set concurrency limits to avoid rate limiting

### Phase 3: Accumulation & Merge

#### TagAccumulator

```python
class TagAccumulator:
    """Accumulate tags per method, handling evolution."""
    
    def accumulate(self, method_id, new_tags, commit_hash):
        """
        Rules:
        - Method first appears: adopt generated tags directly
        - Method modified: merge/override tags (later commit takes priority)
        - Method deleted: mark as deleted, don't output
        - Method renamed: track rename, migrate tags to new name
        """
```

#### ConflictResolver

Merge strategy when the same method is modified across multiple commits:

```
Commit 1: OrderService.create
  @bodhi.intent Create order
  @bodhi.writes orders(id, userId, status)

Commit 5: OrderService.create (payment logic added)
  @bodhi.intent Create order and initiate payment
  @bodhi.writes orders(id, userId, status, paymentId)
  @bodhi.calls PaymentService.hold

Final result = Commit 5's tags (latest intent overrides older)
But @bodhi.on_fail tags added in intermediate commits should be preserved
```

**Merge rules:**
- `@bodhi.intent`: take latest (from the last commit that modified the method)
- `@bodhi.reads/writes`: take latest (reflects current code state)
- `@bodhi.calls/emits/consumes`: take latest
- `@bodhi.on_fail`: accumulative merge (error handling is typically added incrementally)

### Phase 4: Output

#### Output Modes

Two output modes are provided:

**Mode A: Standalone DSL files (recommended for showcase)**

Generate a `.bodhi-import/` directory containing all annotations without modifying source code:

```
.bodhi-import/
├── tags/
│   ├── OrderService.yaml      # One file per class
│   ├── PaymentService.yaml
│   └── ...
└── summary.md                 # Import report
```

```yaml
# .bodhi-import/tags/OrderService.yaml
class: com.example.OrderService
methods:
  - name: create
    tags:
      intent: "Create order, deduct inventory, hold payment, publish event"
      reads: ["request.body(userId, items, address)"]
      writes: ["orders(id, userId, totalAmount, status=PENDING) via INSERT"]
      calls: ["InventoryService.deduct via grpc", "PaymentService.hold via http"]
      emits: ["order_created(orderId, userId) to kafka:order-events"]
      on_fail: ["inventory_insufficient → reject 400"]
```

**Mode B: Inject into source code**

Write annotations directly into source code doc comments (requires user confirmation).

### CLI Interface

```bash
# Basic usage: analyze current repo's git history
bodhi import-history .

# Specify branch and time range
bodhi import-history . --branch main --since 2024-01-01

# Only analyze the last N commits
bodhi import-history . --last 100

# Specify output mode
bodhi import-history . --output tags      # Mode A (default)
bodhi import-history . --output inject    # Mode B

# Use GitHub API for PR information (enhanced context)
bodhi import-history . --github owner/repo

# Dry run: only show which commits and methods would be processed
bodhi import-history . --dry-run

# Specify AI provider
bodhi import-history . --provider anthropic --model claude-sonnet-4-6
bodhi import-history . --provider openai --model gpt-4o

# Control concurrency and cost
bodhi import-history . --batch          # Use Batch API (cheaper but slower)
bodhi import-history . --concurrency 5  # Concurrency level
bodhi import-history . --budget 10.0    # Budget cap (USD)
```

### Incremental Mode

Support resuming after interruption:

```bash
# First run, interrupted halfway through
bodhi import-history . --last 500
# State saved in .bodhi-import/.state.json

# Resume from last progress
bodhi import-history . --resume
```

## Open-Source Project Showcase Workflow

Complete workflow for the promotion scenario:

```
Step 1: Select target project
  - Medium scale (50-200 business methods)
  - Java/Spring ecosystem preferred
  - High quality PRs/commits
  - High community visibility

Step 2: Fork + run import-history
  bodhi import-history . --github owner/repo --output tags

Step 3: Manual review
  - Check generated annotation accuracy
  - Correct obvious errors
  - Record accuracy metrics

Step 4: Generate Layer 2
  bodhi derive .

Step 5: Demonstrate value
  - Run bodhi score → show AI-readability improvement
  - Run bodhi graph → generate visual flow diagrams
  - Run bodhi impact-pr → demonstrate PR impact analysis capability
  - Compare: quality of AI answers about code with DSL vs without DSL
```

## Candidate Open-Source Projects

| Project | Scale | Advantages | Risks |
|---------|-------|------------|-------|
| spring-petclinic | Small | Everyone knows it, beginner-friendly | Too simple, can't showcase complex scenarios |
| mall (macrozheng) | Large | Well-known in Chinese community, complete e-commerce | Too large, inconsistent commit quality |
| ruoyi-vue-pro | Medium | Active Chinese community, clear modules | Heavy code generation, low annotation value |
| piggymetrics | Small-Medium | Microservice architecture, Spring Cloud | Showcases cross-service capability |
| staffjoy | Medium | Microservices, clear business logic | No longer maintained |

**Recommended first choice: piggymetrics**
- Microservice architecture demonstrates Bodhi's cross-service tracing capability
- Moderate scale (4 services, 10-20 business methods each)
- Spring Boot + Spring Cloud, matching tech stack
- Clean commit history

## Technical Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI-generated annotation accuracy insufficient | Showcase loses credibility | Small-scale validation first; manual review as fallback |
| Poor commit message quality | Lacking motivation info | Degrade to pure code analysis; mark confidence level |
| Method rename tracking difficulty | Tags lost or misaligned | Use `git log --follow`; accept partial loss |
| High API cost | Uneconomical for large projects | Batch API + budget cap + incremental mode |
| Long processing time | Poor user experience | Progress bar + incremental + concurrency |

## Implementation Priority

### MVP (Weeks 1-2)

1. CommitWalker: Basic commit traversal and filtering
2. DiffParser: Reuse impact_pr.py diff parsing
3. PromptBuilder: Prompt based on commit message + method code
4. LLMClient: Call Claude API to generate annotations
5. OutputWriter: Mode A output (standalone files)
6. CLI: `bodhi import-history` basic command

### V1 (Weeks 3-4)

7. ContextCollector: GitHub API integration (PR/issue)
8. TagAccumulator: Multi-commit merge logic
9. Incremental mode (resume)
10. Budget control
11. Progress reporting and statistics

### V2 (Future)

12. Mode B output (inject into source code)
13. Confidence scoring (mark uncertain annotations)
14. Interactive review mode
15. Deep integration with `bodhi derive`

## Success Metrics

- Run on piggymetrics, generated annotations achieve >80% accuracy on manual review
- After generating complete DSL, `bodhi score` reaches 60+
- Can generate meaningful flow diagrams and impact-pr reports
- Entire process (including manual review) completes in <1 day
