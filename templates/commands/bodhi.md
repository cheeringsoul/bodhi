Unified Bodhi DSL command. Execute according to the subcommand provided in $ARGUMENTS.

## Subcommands

| Subcommand                     | Description                                                |
|--------------------------------|------------------------------------------------------------|
| `design <description or file>` | Design YAML skeleton for a new feature BEFORE writing code |
| `init`                         | Initialize the .bodhi/ directory                           |
| `scan <directory>`             | Scan source code and add @bodhi.* inline tags              |
| `flows`                        | Generate .bodhi/flows/*.yaml from existing inline tags     |
| `concepts`                     | Generate .bodhi/concepts/glossary.yaml                     |
| `verify [scope]`               | Self-report DSL written for recent changes + run check/validate |

Parse $ARGUMENTS to determine which subcommand to execute, then follow the corresponding rules below.

---

## Subcommand: `design <description or file>`

Design the YAML skeleton for a new feature BEFORE writing any code. This implements the DSL-First workflow.

The argument after `design` can be either:

1. **Inline description** — a natural language description of the feature
2. **File path** — a path to a requirements document (`.md`, `.txt`, etc.)

If the argument looks like a file path (contains `/` or `.` extension), read the file and use its content as the
requirement. Otherwise treat it as an inline description.

Examples:

- `design 用户下单后扣库存冻结金额发order_created事件到Kafka`
-
`design Add a payment callback endpoint that receives webhook from payment gateway, updates order status, and notifies user`
- `design docs/requirements/order-system.md`
- `design ./PRD.md`

### Step 1: Analyze the requirement

Read the requirement and identify:

- **Entry points**: What triggers this feature? (HTTP API, gRPC, MQ consumer, WebSocket, scheduler, etc.)
- **Data writes**: What tables/entities are created or modified?
- **Data reads**: What existing data is needed?
- **Cross-service calls**: Does this call other services? Via what protocol?
- **Events**: Are domain events published? Does this consume events from other services?
- **Channels**: Is there bidirectional communication (WebSocket, Socket)?
- **Error scenarios**: What can fail? How should each failure be handled?
- **State transitions**: Does this change an entity's status field?

Present this analysis to the user as a bullet list. Wait for confirmation before proceeding to Step 2.

### Step 2: Generate YAML skeleton

Based on the confirmed analysis, generate the following files (only the ones that are relevant):

#### Flow — `.bodhi/flows/<name>.yaml`

```yaml
name: <snake_case_name>
description: <one line>

entry:
  type: <http|grpc|mq_consumer|event|scheduler|websocket>
  method: <METHOD>      # if HTTP/gRPC
  path: <path>          # if HTTP/WebSocket

steps:
  - fn: <ClassName.methodName>
    intent: <what this step does>
    reads: [ ... ]
    writes: [ ... ]
    calls: [ ... ]
    emits: [ ... ]
    on_fail: [ ... ]

  # For cross-service calls, include remote fields:
  - fn: <RemoteService.method>
    remote: <service-name>
    protocol: <http|grpc|...>
    api: <API identifier>
    flow_ref: <service:flow_name>
    intent: <what this step does>
    on_fail: [ ... ]

entities: [ ... ]
events: [ ... ]
```

#### Entity — `.bodhi/entities/<table>.yaml` (only for NEW tables)

```yaml
table: <table_name>
description: <one line>
database: <mysql|postgresql|mongodb|redis>
datasource: <connection_name>    # if multiple datasources

fields:
  - name: <field>
    type: <type>
    description: <meaning>
    primary_key: true/false
    sensitive: true/false         # PII fields
    state_machine: <name>         # if this is a status field

relations: [ ... ]
```

#### Event — `.bodhi/events/<name>.yaml` (only for NEW events)

```yaml
name: <event_name>
description: <one line>
channel: <kafka:topic|rabbitmq:queue|internal|...>

schema:
  - field: <name>
    type: <type>

producers:
  - fn: <ClassName.methodName>
    flow: <flow_name>

consumers:
  - fn: <ClassName.methodName>
    description: <what the consumer does>
```

#### Channel — `.bodhi/channels/<name>.yaml` (only for WebSocket/Socket/bidirectional)

```yaml
name: <channel_name>
protocol: <websocket|tcp|sse>
path: <path>
description: <one line>

inbound_events:
  - name: <event_name>
    description: <what>
    schema: [ ... ]
    triggers_flow: <flow_name>

outbound_events:
  - name: <event_name>
    description: <what>
    schema: [ ... ]
    triggered_by:
      - event: <internal_event>
        from: <source>
```

#### Topology — `.bodhi/topology/<name>.yaml` (only if events cross service boundaries)

```yaml
name: <chain_name>
description: <one line>

chains:
  - event: <event_name>
    channel: <channel>
    producer: <service-name>
    consumers:
      - service: <service-name>
        fn: <handler_fn>
        action: <what it does>
        emits: <downstream_event>   # if it triggers another event
```

#### State Machine — `.bodhi/states/<name>.yaml` (only if a new status field is introduced)

```yaml
name: <lifecycle_name>
entity: <table_name>
field: status
description: <one line>

states:
  - id: <STATE>
    value: <int>
    description: <meaning>
    transitions:
      - target: <NEXT_STATE>
        trigger: <what causes this>
        fn: <ClassName.methodName>
```

#### Service manifest — `.bodhi/services/<name>.yaml`

If the feature adds new APIs or dependencies, update the existing service file. Do NOT regenerate the whole file — only
add the new entries under `apis` or `depends_on`.

### Step 3: Present and confirm

After generating all YAML files:

1. List all files created/updated
2. Show a summary: "This feature involves X steps, Y entities, Z events"
3. Ask the user: **"YAML skeleton is ready. Should I proceed to implement the code?"**

### IMPORTANT

- Do NOT write any source code (Java/Python/Go/TypeScript/etc.) in this subcommand
- Do NOT generate inline @bodhi.* tags — those come during implementation
- ONLY produce .bodhi/ YAML files
- If `.bodhi/bodhi.yaml` does not exist, run `/bodhi init` first
- Read existing `.bodhi/` files to avoid duplicating entities, events, or state machines that already exist
- For cross-service features, always check if topology files need updating

---

## Subcommand: `init`

Initialize the .bodhi/ directory.

1. Read project build files (pom.xml / build.gradle / package.json / go.mod / pyproject.toml) to determine languages and
   frameworks
2. Create `.bodhi/bodhi.yaml` with project name, languages, and frameworks
3. Scan ORM models / database migrations / DDL files, create `.bodhi/entities/<table>.yaml` for each table
4. Scan status enums (e.g., OrderStatus, PaymentState), create `.bodhi/states/<name>.yaml` for entities with state
   transitions
5. Prioritize core business tables (most foreign key references, most code references) — no need to cover all tables at
   once

---

## Subcommand: `scan <directory>`

Scan source code in the given directory and add @bodhi.* inline tags.

1. Find all public methods/functions in source files under that directory (skip
   getters/setters/toString/constructors/test code)
2. List the methods to be processed first, wait for user confirmation before modifying
3. Following the Bodhi DSL rules in CLAUDE.md, add @bodhi.* tags to each method's doc comment:
    - Must add: `@bodhi.intent` + `@bodhi.reads` + `@bodhi.writes`
    - Add `@bodhi.calls` if there are key calls (use `via` for remote calls)
    - Add `@bodhi.emits` if events are published
    - Add `@bodhi.consumes` if events are consumed
    - Add `@bodhi.on_fail` if there is error handling
4. If `.bodhi/entities/` already exists, cross-reference field names to ensure reads/writes tags are accurate

---

## Subcommand: `flows`

Generate flow YAML files from existing inline tags.

1. Scan all Controller / Handler / Router files to find all HTTP/gRPC/MQ entry points
2. For each entry point, trace the call chain using `@bodhi.calls` tags in the code
3. Create `.bodhi/flows/<name>.yaml` for each entry point
4. Prioritize POST/PUT/DELETE endpoints (those with write operations)
5. List the entry points first, wait for user to confirm priorities before generating

---

## Subcommand: `concepts`

Generate the business glossary.

1. Read content from `.bodhi/states/` and `.bodhi/flows/`
2. Extract key business terms (state meanings, business actions, domain concepts)
3. Create or update `.bodhi/concepts/glossary.yaml`

---

## Subcommand: `verify [scope]`

Self-report the Bodhi DSL written for the recent change, with evidence — then run `bodhi check` and `bodhi validate` so
the user can confirm nothing was skipped. **Do not auto-fix gaps in this subcommand.** This is a checkpoint, not a fix.

### When to use

Run `verify` after finishing a feature/refactor/bug-fix that involved code changes. Typical triggers:

- User says "are you sure you wrote all the DSL?"
- After `/bodhi design` → implement → before committing
- After `scan` / `flows` finishes a batch
- Before opening a PR

### Determining scope

Parse `$ARGUMENTS` after `verify` to determine which changes to inspect:

| Scope argument             | Meaning                                                            |
|----------------------------|--------------------------------------------------------------------|
| _(empty)_                  | Files you (the assistant) created/modified in the current task     |
| `staged`                   | Files in `git diff --cached` (staged for next commit)              |
| `uncommitted`              | Files in `git status` (staged + unstaged + untracked)              |
| `since <ref>`              | Files in `git diff <ref>...HEAD` (e.g. `since main`, `since HEAD~3`) |
| `<path> [<path> ...]`      | One or more explicit file/directory paths                          |

If the scope is empty and you can't recall which files you touched this turn, fall back to `uncommitted` and tell the
user which scope you used.

### Step 1: Enumerate the changed surface

List every source file and `.bodhi/*.yaml` file in scope. For source files, list every public function you
added/modified in this scope. Skip exempted methods (getters/setters/constructors/utilities/tests — see CLAUDE.md).

Output format:

```
Scope: <how scope was determined, e.g. "files modified in this turn">
Source files (N):
  - path/to/File.java
      · ClassName.methodA   (new)
      · ClassName.methodB   (modified)
  - path/to/other.py
      · module.func_x       (new)

.bodhi/ files (M):
  - .bodhi/flows/create_order.yaml      (new)
  - .bodhi/entities/orders.yaml          (modified)
  - .bodhi/events/order_created.yaml     (new)
  - .bodhi/services/order-service.yaml   (modified)
```

### Step 2: Paste the actual DSL — no paraphrasing

For each non-exempt function in scope, paste its `@bodhi.*` tag block verbatim from the file. Do NOT summarize, do NOT
say "all tags added" — paste the raw text. If a function has no `@bodhi.*` block, write `(no @bodhi tags)` underneath it.

```
ClassName.methodA (path/to/File.java:42)
    @bodhi.intent ...
    @bodhi.reads ...
    @bodhi.writes ...
    @bodhi.calls ...
    @bodhi.on_fail ...

module.func_x (path/to/other.py:15)
    (no @bodhi tags)
```

For each `.bodhi/*.yaml` file in scope, list the top-level entries you added/changed (flow name + step count, entity
table + field count, event name + producer/consumer count, etc.). Do not paste the full YAML unless the file is small
(< 30 lines).

### Step 3: Run the engine checks

Run these two commands and paste the **complete** output (do not truncate, do not summarize):

```bash
bodhi check . --errors-only
bodhi validate .
```

`bodhi check` reports inline-tag vs `.bodhi/` YAML inconsistencies. `bodhi validate` reports completeness errors. If
either command exits non-zero, that is a real failure — do not paper over it.

`--errors-only` on `bodhi check` suppresses warnings (typically "entry point not in any flow YAML"). The summary line
still shows the total warning count so you know how many were filtered. Drop `--errors-only` if you want the full list.

### Step 4: Identify gaps — do not fix them

Cross-reference what you pasted in Step 2 against the 6 self-check questions in CLAUDE.md ("Self-Check: 6 Questions
Before Moving to Next Method"). For each function, list which expected tags are missing.

Also flag:

- Functions with `@bodhi.calls X` where `X` has no matching tags or YAML definition (dangling)
- `@bodhi.emits E` / `@bodhi.consumes E` with no `.bodhi/events/E.yaml`
- `@bodhi.reads/writes T` with no `.bodhi/entities/T.yaml` (unless `T` is `request`/`response`/`cache:*`/etc.)
- For distributed projects: `@bodhi.calls ... via http/grpc` whose target service is not in `.bodhi/services/<name>.yaml`'s `depends_on`
- New cross-service events not reflected in `.bodhi/topology/*.yaml`

Output format:

```
Gaps (K):
  [missing-tag]   OrderService.cancel — has DB write but no @bodhi.writes
  [dangling-call] OrderService.create → @bodhi.calls FraudCheck.score: not tagged, not in any .bodhi/*.yaml
  [missing-event] @bodhi.emits payment_completed: no .bodhi/events/payment_completed.yaml
  [dep-missing]   @bodhi.calls FraudService.score via grpc: not in services/order-service.yaml depends_on
```

If there are zero gaps and both engine commands exited 0, say so explicitly: **"Verified — no gaps."**

### Step 5: Ask before fixing

Conclude with one of:

- **No gaps**: "Verified — no gaps. Ready to commit."
- **Has gaps**: "Found N gaps above. Want me to fix them now, or do you want to review first?"

**Do NOT auto-fix.** The whole point of `verify` is to give the user a checkpoint. Wait for explicit "yes, fix them" or
"yes, fix #1 and #3" before editing files.

### IMPORTANT

- Paste raw tag blocks and raw command output — do not paraphrase. The user is using this command precisely because
  they don't trust a summary
- If you can't determine scope, say so and ask — do not guess
- Do not invent gaps. If something looks fine, say it's fine
- Do not fix in this turn. Fixing is the next turn, after the user confirms
