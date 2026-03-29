Scan the specified directory and add Bodhi DSL annotations to existing code. Execute according to the argument provided.

## Arguments

$ARGUMENTS is the scan target, in one of the following formats:
- `init` — Initialize the .bodhi/ directory (run this first)
- Directory path — Scan source code in that directory and add @bodhi.* inline tags
- `flows` — Generate .bodhi/flows/*.yaml from existing inline tags
- `concepts` — Generate .bodhi/concepts/glossary.yaml from existing states and flows

## Execution Rules

### If argument is `init`

1. Read project build files (pom.xml / build.gradle / package.json / go.mod / pyproject.toml) to determine languages and frameworks
2. Create `.bodhi/bodhi.yaml` with project name, languages, and frameworks
3. Scan ORM models / database migrations / DDL files, create `.bodhi/entities/<table>.yaml` for each table
4. Scan status enums (e.g., OrderStatus, PaymentState), create `.bodhi/states/<name>.yaml` for entities with state transitions
5. Prioritize core business tables (most foreign key references, most code references) — no need to cover all tables at once

### If argument is a directory path

1. Find all public methods/functions in source files under that directory (skip getters/setters/toString/constructors/test code)
2. List the methods to be processed first, wait for user confirmation before modifying
3. Following the Bodhi DSL rules in CLAUDE.md, add @bodhi.* tags to each method's doc comment:
   - Must add: `@bodhi.intent` + `@bodhi.reads` + `@bodhi.writes`
   - Add `@bodhi.calls` if there are key calls (use `via` for remote calls)
   - Add `@bodhi.emits` if events are published
   - Add `@bodhi.consumes` if events are consumed
   - Add `@bodhi.on_fail` if there is error handling
4. If `.bodhi/entities/` already exists, cross-reference field names to ensure reads/writes tags are accurate

### If argument is `flows`

1. Scan all Controller / Handler / Router files to find all HTTP/gRPC/MQ entry points
2. For each entry point, trace the call chain using `@bodhi.calls` tags in the code
3. Create `.bodhi/flows/<name>.yaml` for each entry point
4. Prioritize POST/PUT/DELETE endpoints (those with write operations)
5. List the entry points first, wait for user to confirm priorities before generating

### If argument is `concepts`

1. Read content from `.bodhi/states/` and `.bodhi/flows/`
2. Extract key business terms (state meanings, business actions, domain concepts)
3. Create or update `.bodhi/concepts/glossary.yaml`
