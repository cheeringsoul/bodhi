"""
bodhi import-history — reverse-generate Bodhi DSL from git history.

Walks through git commits, extracts method changes, calls AI to generate
@bodhi.* annotations, accumulates results, and writes .bodhi-import/ output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

from bodhi_engine.git_walker import CommitWalker, DiffParser, CommitInfo, MethodChange


# ── data models ────────────────────────────────────────────────────

@dataclass
class GeneratedTags:
    file_path: str
    class_name: Optional[str]
    method_name: str
    intent: str = ""
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    emits: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    on_fail: list[str] = field(default_factory=list)
    commit_hash: str = ""

    @property
    def qualified_name(self) -> str:
        if self.class_name:
            return f"{self.class_name}.{self.method_name}"
        return self.method_name


# ── PromptBuilder ──────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Bodhi DSL annotation expert. Generate @bodhi.* tags for methods based on commit context and code.

Bodhi DSL tags:
- @bodhi.intent: Business motivation (NOT code description). One sentence.
- @bodhi.reads: Data sources read, format: "entity(fields)" or "request.body(fields)"
- @bodhi.writes: Data targets written, format: "entity(fields) via INSERT/UPDATE/DELETE"
- @bodhi.calls: Functions/services called, format: "Service.method" or "Service.method via http/grpc"
- @bodhi.emits: Events emitted, format: "event_name(payload_fields) to channel:topic"
- @bodhi.consumes: Events consumed, format: "event_name(fields) from channel:topic"
- @bodhi.on_fail: Error handling, format: "condition → action"

Rules:
1. intent is REQUIRED. Describe the business WHY, not the code WHAT.
2. Only include tags that are clearly supported by the code.
3. Be precise with entity names and field lists.
4. Output valid JSON only, no markdown fences."""


class PromptBuilder:
    """Build AI prompts for DSL generation from commit context + method code."""

    def build_batch_prompt(self, methods: list[MethodChange],
                           commit: CommitInfo,
                           known_entities: list[str] | None = None,
                           known_services: list[str] | None = None,
                           extra_context: str | None = None,
                           ) -> str:
        methods_section = []
        for i, m in enumerate(methods, 1):
            qname = f"{m.class_name}.{m.method_name}" if m.class_name else m.method_name
            methods_section.append(
                f"### Method {i}: {qname} ({m.change_type})\n"
                f"```{m.language}\n{m.method_body}\n```"
            )

        context_parts = [f"- Commit message: {commit.message}"]
        if extra_context:
            context_parts.append(f"- PR/Issue context: {extra_context}")
        if known_entities:
            context_parts.append(f"- Known entities: {', '.join(known_entities)}")
        if known_services:
            context_parts.append(f"- Known services: {', '.join(known_services)}")

        return (
            f"## Commit Context\n"
            f"{chr(10).join(context_parts)}\n\n"
            f"## Methods to Annotate\n"
            f"{chr(10).join(methods_section)}\n\n"
            f"## Output\n"
            f"Return a JSON array with one object per method, in order:\n"
            f'{{"method": "ClassName.methodName", "intent": "...", '
            f'"reads": [...], "writes": [...], "calls": [...], '
            f'"emits": [...], "consumes": [...], "on_fail": [...]}}\n'
            f"Only include non-empty arrays. intent is required."
        )


# ── LLMClient ──────────────────────────────────────────────────────

class LLMClient:
    """Call an LLM to generate Bodhi DSL annotations."""

    def __init__(self, provider: str = "anthropic", model: str | None = None):
        self.provider = provider
        self.model = model or self._default_model()

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4o"
        return "claude-sonnet-4-6-20250514"

    def generate(self, system: str, user_prompt: str) -> list[dict[str, Any]]:
        if self.provider == "anthropic":
            return self._call_anthropic(system, user_prompt)
        elif self.provider == "openai":
            return self._call_openai(system, user_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _call_anthropic(self, system: str, user_prompt: str) -> list[dict[str, Any]]:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return self._parse_response(response.content[0].text)

    def _call_openai(self, system: str, user_prompt: str) -> list[dict[str, Any]]:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return self._parse_response(response.choices[0].message.content)

    def _parse_response(self, text: str) -> list[dict[str, Any]]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        if isinstance(data, dict):
            if "methods" in data:
                return data["methods"]
            return [data]
        return data


# ── ContextCollector ──────────────────────────────────────────────

class ContextCollector:
    """Collect PR/issue context for a commit via GitHub CLI."""

    def __init__(self, github_repo: str | None = None):
        self.github_repo = github_repo
        self._cache: dict[str, str] = {}

    def collect(self, commit: CommitInfo) -> str | None:
        if not self.github_repo:
            return None
        if commit.hash in self._cache:
            return self._cache[commit.hash]

        context_parts = []

        pr_body = self._get_pr_body(commit.hash)
        if pr_body:
            context_parts.append(f"PR description: {pr_body[:500]}")

        issue_refs = self._extract_issue_refs(commit.message)
        for issue_num in issue_refs[:2]:
            issue_body = self._get_issue_body(issue_num)
            if issue_body:
                context_parts.append(f"Issue #{issue_num}: {issue_body[:300]}")

        result = "\n".join(context_parts) if context_parts else None
        self._cache[commit.hash] = result
        return result

    def _get_pr_body(self, commit_hash: str) -> str | None:
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{self.github_repo}/commits/{commit_hash}/pulls",
                 "--jq", ".[0].body // empty"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _get_issue_body(self, issue_num: int) -> str | None:
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{self.github_repo}/issues/{issue_num}",
                 "--jq", ".body // empty"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    @staticmethod
    def _extract_issue_refs(message: str) -> list[int]:
        import re
        return [int(m) for m in re.findall(r"#(\d+)", message)]


# ── BudgetTracker ─────────────────────────────────────────────────

_COST_PER_1K_INPUT = {"anthropic": 0.003, "openai": 0.005}
_COST_PER_1K_OUTPUT = {"anthropic": 0.015, "openai": 0.015}


class BudgetTracker:
    """Track estimated API cost and enforce budget cap."""

    def __init__(self, budget: float | None = None, provider: str = "anthropic"):
        self.budget = budget
        self.spent = 0.0
        self._cost_in = _COST_PER_1K_INPUT.get(provider, 0.003)
        self._cost_out = _COST_PER_1K_OUTPUT.get(provider, 0.015)

    def record(self, input_chars: int, output_chars: int):
        input_tokens = input_chars / 4
        output_tokens = output_chars / 4
        self.spent += (input_tokens / 1000) * self._cost_in
        self.spent += (output_tokens / 1000) * self._cost_out

    def exceeded(self) -> bool:
        if self.budget is None:
            return False
        return self.spent >= self.budget


# ── TagAccumulator ─────────────────────────────────────────────────

class TagAccumulator:
    """Accumulate tags per method across commits. Later commits win."""

    def __init__(self):
        self.tags: dict[str, GeneratedTags] = {}  # qualified_name -> tags

    def add(self, tags: GeneratedTags):
        key = tags.qualified_name
        existing = self.tags.get(key)
        if existing is None:
            self.tags[key] = tags
            return

        # Later commit overrides intent, reads, writes, calls, emits, consumes
        if tags.intent:
            existing.intent = tags.intent
        if tags.reads:
            existing.reads = tags.reads
        if tags.writes:
            existing.writes = tags.writes
        if tags.calls:
            existing.calls = tags.calls
        if tags.emits:
            existing.emits = tags.emits
        if tags.consumes:
            existing.consumes = tags.consumes
        # on_fail is accumulative
        for of in tags.on_fail:
            if of not in existing.on_fail:
                existing.on_fail.append(of)
        existing.commit_hash = tags.commit_hash

    def remove_deleted(self, qualified_name: str):
        self.tags.pop(qualified_name, None)

    def get_all(self) -> list[GeneratedTags]:
        return list(self.tags.values())

    def get_by_class(self) -> dict[str, list[GeneratedTags]]:
        by_class: dict[str, list[GeneratedTags]] = {}
        for t in self.tags.values():
            key = t.class_name or Path(t.file_path).stem
            by_class.setdefault(key, []).append(t)
        return by_class


# ── OutputWriter ───────────────────────────────────────────────────

class OutputWriter:
    """Write accumulated tags to .bodhi-import/ directory."""

    def __init__(self, project_root: Path):
        self.output_dir = project_root / ".bodhi-import"
        self.tags_dir = self.output_dir / "tags"

    def write(self, accumulator: TagAccumulator, stats: dict[str, Any]):
        self.tags_dir.mkdir(parents=True, exist_ok=True)

        by_class = accumulator.get_by_class()
        for class_name, tags_list in by_class.items():
            self._write_class_file(class_name, tags_list)

        self._write_summary(stats, len(by_class), len(accumulator.get_all()))

    def _write_class_file(self, class_name: str, tags_list: list[GeneratedTags]):
        methods = []
        for t in tags_list:
            method: dict[str, Any] = {"name": t.method_name}
            tags: dict[str, Any] = {}
            if t.intent:
                tags["intent"] = t.intent
            if t.reads:
                tags["reads"] = t.reads
            if t.writes:
                tags["writes"] = t.writes
            if t.calls:
                tags["calls"] = t.calls
            if t.emits:
                tags["emits"] = t.emits
            if t.consumes:
                tags["consumes"] = t.consumes
            if t.on_fail:
                tags["on_fail"] = t.on_fail
            method["tags"] = tags
            methods.append(method)

        file_path = tags_list[0].file_path if tags_list else ""
        data = {
            "class": class_name,
            "source_file": file_path,
            "methods": methods,
        }

        out_file = self.tags_dir / f"{class_name}.yaml"
        out_file.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True,
                                       sort_keys=False),
                            encoding="utf-8")

    def _write_summary(self, stats: dict[str, Any], class_count: int, method_count: int):
        lines = [
            "# Bodhi Import History — Summary",
            "",
            f"- Commits analyzed: {stats.get('commits_analyzed', 0)}",
            f"- Commits skipped: {stats.get('commits_skipped', 0)}",
            f"- Methods annotated: {method_count}",
            f"- Classes/files: {class_count}",
            f"- API calls made: {stats.get('api_calls', 0)}",
            f"- Errors: {stats.get('errors', 0)}",
            "",
            f"Output: `{self.tags_dir}/`",
        ]
        (self.output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# ── State persistence (resume support) ─────────────────────────────

class ImportState:
    """Track progress for resume support."""

    def __init__(self, project_root: Path):
        self.state_file = project_root / ".bodhi-import" / ".state.json"

    def load(self) -> dict[str, Any]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"processed_commits": [], "stats": {}}

    def save(self, processed: list[str], stats: dict[str, Any]):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "processed_commits": processed,
            "stats": stats,
        }, indent=2))


# ── Main pipeline ──────────────────────────────────────────────────

def cmd_import_history(
    project_root: Path,
    branch: str = "main",
    since: str | None = None,
    until: str | None = None,
    last: int | None = None,
    output_mode: str = "tags",
    provider: str = "anthropic",
    model: str | None = None,
    concurrency: int = 1,
    budget: float | None = None,
    dry_run: bool = False,
    resume: bool = False,
    github: str | None = None,
    exclude_dirs: set[str] | None = None,
):
    console = Console()

    # Phase 1: Walk commits
    console.print(f"[bold]Scanning git history on branch '{branch}'...[/bold]")
    walker = CommitWalker(project_root, branch=branch, since=since,
                          until=until, last=last)
    try:
        commits = walker.walk()
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    total_commits_before_filter = len(commits)
    console.print(f"Found {total_commits_before_filter} meaningful commits")

    if not commits:
        console.print("[yellow]No meaningful commits found.[/yellow]")
        sys.exit(0)

    # Resume support
    state = ImportState(project_root)
    processed_hashes: list[str] = []
    if resume:
        saved = state.load()
        processed_hashes = saved.get("processed_commits", [])
        if processed_hashes:
            before = len(commits)
            commits = [c for c in commits if c.hash not in set(processed_hashes)]
            console.print(f"Resuming: skipping {before - len(commits)} already-processed commits")

    if dry_run:
        console.print(f"\n[bold]Dry run — would process {len(commits)} commits:[/bold]")
        for c in commits[:20]:
            source_files = [f for f in c.files_changed if Path(f).suffix in {".java", ".py", ".go", ".ts", ".js", ".kt"}]
            console.print(f"  {c.hash[:8]} {c.message[:60]}  ({len(source_files)} source files)")
        if len(commits) > 20:
            console.print(f"  ... and {len(commits) - 20} more")
        return

    # Phase 2: Process each commit
    diff_parser = DiffParser(project_root)
    prompt_builder = PromptBuilder()
    llm = LLMClient(provider=provider, model=model)
    accumulator = TagAccumulator()
    context_collector = ContextCollector(github_repo=github)
    budget_tracker = BudgetTracker(budget=budget, provider=provider)

    stats = {"commits_analyzed": 0, "commits_skipped": 0, "api_calls": 0, "errors": 0,
             "methods_found": 0, "estimated_cost": 0.0}

    if github:
        console.print(f"[dim]GitHub context enabled: {github}[/dim]")
    if budget:
        console.print(f"[dim]Budget cap: ${budget:.2f}[/dim]")

    # Reverse to process oldest first (chronological order)
    commits.reverse()

    def _process_commit(commit: CommitInfo) -> tuple[CommitInfo, list[MethodChange], list[dict] | None, str | None]:
        """Extract methods and call AI for a single commit. Returns (commit, methods, results, error)."""
        try:
            method_changes = diff_parser.extract_method_changes(commit)
        except Exception as e:
            return commit, [], None, str(e)

        deleted = [m for m in method_changes if m.change_type == "deleted"]
        active = [m for m in method_changes if m.change_type != "deleted"]

        if not active:
            return commit, deleted, [], None

        extra_context = context_collector.collect(commit)
        user_prompt = prompt_builder.build_batch_prompt(active, commit, extra_context=extra_context)

        try:
            results = llm.generate(SYSTEM_PROMPT, user_prompt)
            budget_tracker.record(len(SYSTEM_PROMPT) + len(user_prompt),
                                  sum(len(json.dumps(r)) for r in results))
            return commit, method_changes, results, None
        except Exception as e:
            return commit, method_changes, None, str(e)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing commits", total=len(commits))

        if concurrency > 1:
            # Concurrent processing: batch commits and process in parallel
            for batch_start in range(0, len(commits), concurrency):
                if budget_tracker.exceeded():
                    console.print(f"\n[yellow]Budget cap reached (${budget_tracker.spent:.2f}). Stopping.[/yellow]")
                    break

                batch = commits[batch_start:batch_start + concurrency]
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = {executor.submit(_process_commit, c): c for c in batch}
                    for future in as_completed(futures):
                        commit_obj, method_changes, results, error = future.result()
                        _apply_commit_result(
                            commit_obj, method_changes, results, error,
                            accumulator, stats, processed_hashes, progress, task, console,
                        )

                state.save(processed_hashes, stats)
        else:
            # Sequential processing
            for commit in commits:
                if budget_tracker.exceeded():
                    console.print(f"\n[yellow]Budget cap reached (${budget_tracker.spent:.2f}). Stopping.[/yellow]")
                    break

                progress.update(task, description=f"[cyan]{commit.hash[:8]}[/cyan] {commit.message[:40]}")
                _, method_changes, results, error = _process_commit(commit)
                _apply_commit_result(
                    commit, method_changes, results, error,
                    accumulator, stats, processed_hashes, progress, task, console,
                )

                if stats["commits_analyzed"] % 10 == 0:
                    state.save(processed_hashes, stats)

    stats["estimated_cost"] = round(budget_tracker.spent, 4)

    # Phase 3: Write output
    state.save(processed_hashes, stats)

    if output_mode == "tags":
        writer = OutputWriter(project_root)
        writer.write(accumulator, stats)
        console.print(f"\n[bold green]Done![/bold green]")
        console.print(f"  Commits analyzed: {stats['commits_analyzed']}")
        console.print(f"  Methods annotated: {len(accumulator.get_all())}")
        console.print(f"  API calls: {stats['api_calls']}")
        console.print(f"  Estimated cost: ${stats['estimated_cost']:.4f}")
        if stats["errors"]:
            console.print(f"  Errors: {stats['errors']}")
        console.print(f"  Output: {project_root / '.bodhi-import' / 'tags/'}")
    else:
        console.print("[yellow]inject mode not yet implemented — use --output tags[/yellow]")


def _apply_commit_result(
    commit: CommitInfo,
    method_changes: list[MethodChange],
    results: list[dict] | None,
    error: str | None,
    accumulator: TagAccumulator,
    stats: dict[str, Any],
    processed_hashes: list[str],
    progress: Progress,
    task: TaskID,
    console: Console,
):
    if error and results is None:
        stats["errors"] += 1
        stats["commits_skipped"] += 1
        processed_hashes.append(commit.hash)
        progress.advance(task)
        return

    deleted = [m for m in method_changes if m.change_type == "deleted"]
    active = [m for m in method_changes if m.change_type != "deleted"]

    for d in deleted:
        qname = f"{d.class_name}.{d.method_name}" if d.class_name else d.method_name
        accumulator.remove_deleted(qname)

    if not active or results is None:
        stats["commits_skipped"] += 1
        processed_hashes.append(commit.hash)
        progress.advance(task)
        return

    if error:
        console.print(f"  [red]AI error on {commit.hash[:8]}: {error}[/red]")
        stats["errors"] += 1
        processed_hashes.append(commit.hash)
        progress.advance(task)
        return

    stats["methods_found"] += len(active)
    stats["api_calls"] += 1

    for i, method in enumerate(active):
        if i < len(results):
            r = results[i]
            tags = GeneratedTags(
                file_path=method.file_path,
                class_name=method.class_name,
                method_name=method.method_name,
                intent=r.get("intent", ""),
                reads=r.get("reads", []),
                writes=r.get("writes", []),
                calls=r.get("calls", []),
                emits=r.get("emits", []),
                consumes=r.get("consumes", []),
                on_fail=r.get("on_fail", []),
                commit_hash=commit.hash,
            )
            accumulator.add(tags)

    stats["commits_analyzed"] += 1
    processed_hashes.append(commit.hash)
    progress.advance(task)
