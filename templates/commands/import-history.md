Reverse-generate Bodhi DSL annotations from git history using Claude Code as the AI engine (no API key needed).

Parse `$ARGUMENTS` for options. Supported arguments:

- `<path>` — project root directory (default: `.`)
- `--branch <name>` — git branch to analyze (default: `main`)
- `--since <date>` — only commits after this date (e.g. `2024-01-01`)
- `--until <date>` — only commits before this date
- `--last <N>` — only analyze the last N commits
- `--github <OWNER/REPO>` — enable GitHub PR/issue context

Examples:
- `/import-history`
- `/import-history ./my-project --last 50`
- `/import-history --branch develop --since 2024-06-01`
- `/import-history --github spring-projects/spring-petclinic`

---

## Step 1: Prepare — extract methods from git history

Build the `bodhi import-history --prepare` command from the parsed arguments and run it:

```
bodhi import-history --prepare <path> [--branch ...] [--since ...] [--until ...] [--last ...] [--github ...]
```

This walks git history, extracts method-level changes from diffs, and writes prompt files to `.bodhi-import/prepare/`. No API key is needed for this step.

If the command fails, report the error and stop.

## Step 2: Read manifest and system prompt

Read `.bodhi-import/prepare/_manifest.json` to get the list of prompt files and total counts.
Read `.bodhi-import/prepare/_system_prompt.txt` to get the system prompt for DSL generation.

If the manifest shows 0 commits, report "No methods to annotate" and stop.

Create the responses directory: `mkdir -p .bodhi-import/responses`

## Step 3: Process each prompt file

For each prompt file listed in the manifest's `prompt_files` array:

1. Read the prompt file from `.bodhi-import/prepare/<filename>`
2. If `active_methods` is empty, skip this file
3. Read the `user_prompt` field — this contains commit context and method code to annotate
4. Following the system prompt rules, generate Bodhi DSL annotations for each method. Output a JSON array with one object per method (in the same order as `active_methods`), each containing:
   - `"method"`: `"ClassName.methodName"` (or just `"methodName"` if no class)
   - `"intent"`: business motivation (REQUIRED — describe the WHY, not the WHAT)
   - `"reads"`: array of data sources read (only if applicable)
   - `"writes"`: array of data targets written (only if applicable)
   - `"calls"`: array of functions/services called (only if applicable)
   - `"emits"`: array of events emitted (only if applicable)
   - `"consumes"`: array of events consumed (only if applicable)
   - `"on_fail"`: array of error handling rules (only if applicable)
5. Write the JSON array to `.bodhi-import/responses/<filename>` (same filename as the prompt file)

**Important rules for generating annotations:**
- `intent` is REQUIRED for every method. Describe the business motivation, not the code logic.
- Only include tags that are clearly supported by the code shown in the prompt.
- Be precise with entity names and field lists.
- Output valid JSON arrays only.
- Process files in order. Give a brief progress update every 5 files.

## Step 4: Finalize — generate YAML output

Run:
```
bodhi import-history --finalize <path>
```

This reads all response files, accumulates tags per method (later commits win), and writes the final `.bodhi-import/tags/*.yaml` output.

## Step 5: Report

After finalize completes, summarize:
- How many commits were analyzed
- How many methods were annotated
- Where the output files are located
- Suggest the user review `.bodhi-import/tags/` and optionally use `/bodhi scan` to inject tags into source code
