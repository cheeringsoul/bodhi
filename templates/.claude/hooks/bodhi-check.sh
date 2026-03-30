#!/bin/bash
# Bodhi DSL PostToolUse hook
# Runs after every Edit/Write/MultiEdit to catch missing @bodhi tags immediately.
# Claude Code passes tool info as JSON via stdin.

INPUT=$(cat)

# Extract the file path from tool input
FILE_PATH=$(python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
fp = d.get('tool_input', {}).get('file_path', '')
print(fp)
" 2>/dev/null <<< "$INPUT")

# Skip if no file path extracted
[ -z "$FILE_PATH" ] && exit 0
[ ! -f "$FILE_PATH" ] && exit 0

# --- Check 1: Inline tag check for source code files ---
if [[ "$FILE_PATH" =~ \.(java|kt)$ ]]; then
    # Find public methods missing @bodhi.intent in Java/Kotlin files
    # Strategy: find public method signatures and check if the preceding doc comment has @bodhi.intent
    MISSING=$(python3 -c "
import re, sys

with open('$FILE_PATH', 'r') as f:
    content = f.read()
    lines = content.split('\n')

# Patterns to skip (getters, setters, toString, hashCode, equals, constructors, main)
SKIP_PATTERNS = [
    r'^\s*public\s+\w+\s+get[A-Z]',
    r'^\s*public\s+\w+\s+set[A-Z]',
    r'^\s*public\s+\w+\s+is[A-Z]',
    r'^\s*public\s+(String\s+)?toString\s*\(',
    r'^\s*public\s+(int\s+)?hashCode\s*\(',
    r'^\s*public\s+(boolean\s+)?equals\s*\(',
    r'^\s*public\s+static\s+void\s+main\s*\(',
    r'^\s*public\s+\w+\s*\(',  # constructor (no return type)
]

# Find public method declarations
METHOD_RE = re.compile(r'^\s*(?:@\w+\s+)*public\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:<[^>]+>\s+)?\w+(?:<[^>]+>)?\s+(\w+)\s*\(')
CONSTRUCTOR_RE = re.compile(r'^\s*(?:@\w+\s+)*public\s+[A-Z]\w*\s*\(')

missing = []
for i, line in enumerate(lines):
    # Skip constructors
    if CONSTRUCTOR_RE.match(line):
        continue

    m = METHOD_RE.match(line)
    if not m:
        continue

    method_name = m.group(1)

    # Skip known trivial methods
    skip = False
    for pat in SKIP_PATTERNS:
        if re.match(pat, line):
            skip = True
            break
    if skip:
        continue

    # Look backwards for @bodhi.intent in the preceding doc comment
    found_intent = False
    j = i - 1
    while j >= 0:
        prev = lines[j].strip()
        if prev.startswith('*/') or prev.startswith('*') or prev.startswith('/**'):
            if '@bodhi.intent' in lines[j]:
                found_intent = True
                break
            if prev.startswith('/**'):
                break  # reached start of doc comment
            j -= 1
            continue
        elif prev.startswith('//'):
            if '@bodhi.intent' in lines[j]:
                found_intent = True
                break
            j -= 1
            continue
        elif prev.startswith('@'):
            j -= 1  # skip annotations
            continue
        else:
            break  # no doc comment found
        j -= 1

    if not found_intent:
        missing.append(f'  Line {i+1}: {method_name}()')

if missing:
    print('\n'.join(missing))
" 2>/dev/null)

    if [ -n "$MISSING" ]; then
        echo "⚠ Bodhi DSL: public methods missing @bodhi.intent in $(basename "$FILE_PATH"):"
        echo "$MISSING"
        echo ""
        echo "Add @bodhi.intent to each method's doc comment before continuing."
        exit 1
    fi

elif [[ "$FILE_PATH" =~ \.(py)$ ]]; then
    # Find public functions/methods missing @bodhi.intent in Python files
    MISSING=$(python3 -c "
import re, sys

with open('$FILE_PATH', 'r') as f:
    lines = f.readlines()

SKIP = {'__init__', '__str__', '__repr__', '__eq__', '__hash__', 'main', 'setup', 'teardown'}

missing = []
for i, line in enumerate(lines):
    # Match function/method definitions (not private _xxx)
    m = re.match(r'^(\s*)def\s+([a-zA-Z][a-zA-Z0-9_]*)\s*\(', line)
    if not m:
        continue

    indent = m.group(1)
    func_name = m.group(2)

    # Skip private/protected and known trivial methods
    if func_name.startswith('_') or func_name in SKIP:
        continue

    # Check if the docstring below contains @bodhi.intent
    found_intent = False
    j = i + 1
    while j < len(lines):
        stripped = lines[j].strip()
        if stripped == '':
            j += 1
            continue
        if stripped.startswith('\"\"\"') or stripped.startswith(\"'''\"):
            # Found docstring, scan it for @bodhi.intent
            k = j
            while k < len(lines):
                if '@bodhi.intent' in lines[k]:
                    found_intent = True
                    break
                if k > j and ('\"\"\"' in lines[k] or \"'''\" in lines[k]):
                    break
                k += 1
        break

    if not found_intent:
        missing.append(f'  Line {i+1}: {func_name}()')

if missing:
    print('\n'.join(missing))
" 2>/dev/null)

    if [ -n "$MISSING" ]; then
        echo "⚠ Bodhi DSL: public functions missing @bodhi.intent in $(basename "$FILE_PATH"):"
        echo "$MISSING"
        echo ""
        echo "Add @bodhi.intent to each function's docstring before continuing."
        exit 1
    fi

elif [[ "$FILE_PATH" =~ \.(ts|tsx|js|jsx)$ ]]; then
    # Find exported functions missing @bodhi.intent in TS/JS files
    MISSING=$(python3 -c "
import re, sys

with open('$FILE_PATH', 'r') as f:
    lines = f.readlines()

missing = []
for i, line in enumerate(lines):
    # Match exported function/method declarations
    m = re.match(r'^\s*export\s+(?:async\s+)?function\s+(\w+)\s*[\(<]', line)
    if not m:
        m = re.match(r'^\s*(?:public|async\s+public|public\s+async)\s+(\w+)\s*[\(<]', line)
    if not m:
        continue

    func_name = m.group(1)

    # Skip trivial
    if func_name in ('constructor', 'toString', 'toJSON'):
        continue
    if func_name.startswith('get') or func_name.startswith('set'):
        # Check if it's a simple getter/setter (single line or very short)
        pass  # keep checking for now

    # Look backwards for @bodhi.intent in JSDoc
    found_intent = False
    j = i - 1
    while j >= 0:
        prev = lines[j].strip()
        if prev.startswith('*/') or prev.startswith('*') or prev.startswith('/**'):
            if '@bodhi.intent' in lines[j]:
                found_intent = True
                break
            if prev.startswith('/**'):
                break
            j -= 1
            continue
        elif prev.startswith('//'):
            if '@bodhi.intent' in lines[j]:
                found_intent = True
                break
            j -= 1
            continue
        elif prev.startswith('@'):
            j -= 1
            continue
        else:
            break
        j -= 1

    if not found_intent:
        missing.append(f'  Line {i+1}: {func_name}()')

if missing:
    print('\n'.join(missing))
" 2>/dev/null)

    if [ -n "$MISSING" ]; then
        echo "⚠ Bodhi DSL: exported functions missing @bodhi.intent in $(basename "$FILE_PATH"):"
        echo "$MISSING"
        echo ""
        echo "Add @bodhi.intent to each function's JSDoc comment before continuing."
        exit 1
    fi

elif [[ "$FILE_PATH" =~ \.(go)$ ]]; then
    # Find exported functions missing @bodhi.intent in Go files
    MISSING=$(python3 -c "
import re, sys

with open('$FILE_PATH', 'r') as f:
    lines = f.readlines()

missing = []
for i, line in enumerate(lines):
    m = re.match(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?([A-Z]\w*)\s*\(', line)
    if not m:
        continue

    func_name = m.group(1)

    # Skip trivial
    if func_name in ('String', 'Error', 'MarshalJSON', 'UnmarshalJSON'):
        continue

    # Look backwards for @bodhi.intent in line comments
    found_intent = False
    j = i - 1
    while j >= 0:
        prev = lines[j].strip()
        if prev.startswith('//'):
            if '@bodhi.intent' in lines[j]:
                found_intent = True
                break
            j -= 1
            continue
        else:
            break

    if not found_intent:
        missing.append(f'  Line {i+1}: {func_name}()')

if missing:
    print('\n'.join(missing))
" 2>/dev/null)

    if [ -n "$MISSING" ]; then
        echo "⚠ Bodhi DSL: exported functions missing @bodhi.intent in $(basename "$FILE_PATH"):"
        echo "$MISSING"
        echo ""
        echo "Add @bodhi.intent to each function's comment before continuing."
        exit 1
    fi
fi

# --- Check 2: YAML validation (if .bodhi/ exists) ---
if [[ "$FILE_PATH" =~ \.(java|py|go|ts|js|tsx|kt)$ ]] || [[ "$FILE_PATH" =~ /\.bodhi/ ]]; then
    PROJECT_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || pwd)

    if [ -d "$PROJECT_ROOT/.bodhi" ] && command -v bodhi &>/dev/null; then
        OUTPUT=$(bodhi validate "$PROJECT_ROOT" 2>&1)
        EXIT_CODE=$?

        if [ $EXIT_CODE -ne 0 ]; then
            echo "⚠ Bodhi DSL validation failed — fix before continuing:"
            echo "$OUTPUT"
            exit 1
        fi
    fi
fi
