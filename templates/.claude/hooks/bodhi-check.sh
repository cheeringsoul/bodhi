#!/bin/bash
# Bodhi DSL PostToolUse hook
# Runs after every Edit/Write/MultiEdit to catch DSL inconsistencies immediately.
# Claude Code passes tool info as JSON via stdin.

INPUT=$(cat)

# Extract the file path from tool input
FILE_PATH=$(python3 -c "
import sys, json
try:
    d = json.loads('''$INPUT'''.replace(\"'\", \"'\"))
except Exception:
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
fp = d.get('tool_input', {}).get('file_path', '')
print(fp)
" 2>/dev/null <<< "$INPUT")

# Only validate for source code files and .bodhi/ YAML files
if [[ "$FILE_PATH" =~ \.(java|py|go|ts|js|tsx|kt)$ ]] || [[ "$FILE_PATH" =~ /\.bodhi/ ]]; then
    # Find project root (directory containing .bodhi/ or the git root)
    PROJECT_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || pwd)

    if [ ! -d "$PROJECT_ROOT/.bodhi" ]; then
        exit 0  # No .bodhi/ dir yet, skip
    fi

    OUTPUT=$(bodhi validate "$PROJECT_ROOT" 2>&1)
    EXIT_CODE=$?

    if [ $EXIT_CODE -ne 0 ]; then
        echo "⚠ Bodhi DSL validation failed — fix before continuing:"
        echo "$OUTPUT"
        exit 1
    else
        # Only print if there are warnings/info (not just "All checks passed")
        if [ "$OUTPUT" != "All checks passed." ]; then
            echo "Bodhi DSL: $OUTPUT"
        fi
    fi
fi
