"""
CommitWalker — walk git history and filter meaningful commits.

DiffParser — extract method-level changes from commit diffs.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bodhi_engine.parser.inline import FUNCTION_PATTERNS, CLASS_PATTERNS


# ── data models ────────────────────────────────────────────────────

@dataclass
class CommitInfo:
    hash: str
    message: str
    author: str
    date: str
    files_changed: list[str] = field(default_factory=list)


@dataclass
class MethodChange:
    file_path: str
    class_name: Optional[str]
    method_name: str
    method_body: str
    change_type: str  # "added" | "modified" | "deleted"
    language: str


# ── commit filtering ───────────────────────────────────────────────

_SKIP_PREFIXES = ("docs:", "docs(", "style:", "style(", "chore:", "chore(",
                   "ci:", "ci(", "build:", "build(", "test:", "test(")

_SOURCE_EXTENSIONS = {".java", ".py", ".go", ".ts", ".js", ".kt"}


def _is_meaningful_commit(commit: CommitInfo) -> bool:
    msg_lower = commit.message.lower().strip()
    if msg_lower.startswith("merge "):
        return False
    if any(msg_lower.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if not any(f.endswith(tuple(_SOURCE_EXTENSIONS)) for f in commit.files_changed):
        return False
    return True


# ── CommitWalker ───────────────────────────────────────────────────

class CommitWalker:
    """Walk git history and yield meaningful commits."""

    def __init__(self, repo_path: Path, branch: str = "main",
                 since: Optional[str] = None, until: Optional[str] = None,
                 last: Optional[int] = None):
        self.repo_path = repo_path
        self.branch = branch
        self.since = since
        self.until = until
        self.last = last

    def walk(self) -> list[CommitInfo]:
        cmd = [
            "git", "log", self.branch,
            "--no-merges",
            "--format=%H%x00%s%x00%an%x00%aI",
            "--name-only",
        ]
        if self.last:
            cmd.extend(["-n", str(self.last)])
        if self.since:
            cmd.extend(["--since", self.since])
        if self.until:
            cmd.extend(["--until", self.until])

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git log failed: {result.stderr.strip()}")

        commits = self._parse_log(result.stdout)
        return [c for c in commits if _is_meaningful_commit(c)]

    def _parse_log(self, raw: str) -> list[CommitInfo]:
        commits: list[CommitInfo] = []
        current: Optional[CommitInfo] = None

        for line in raw.splitlines():
            if "\x00" in line:
                parts = line.split("\x00")
                if len(parts) >= 4:
                    if current:
                        commits.append(current)
                    current = CommitInfo(
                        hash=parts[0], message=parts[1],
                        author=parts[2], date=parts[3],
                    )
            elif line.strip() and current:
                current.files_changed.append(line.strip())

        if current:
            commits.append(current)
        return commits


# ── DiffParser ─────────────────────────────────────────────────────

_FUNC_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _get_func_pattern(ext: str) -> Optional[re.Pattern]:
    return FUNCTION_PATTERNS.get(ext)


def _get_class_pattern(ext: str) -> Optional[re.Pattern]:
    return CLASS_PATTERNS.get(ext)


class DiffParser:
    """Extract method-level changes from a commit's diff."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def extract_method_changes(self, commit: CommitInfo) -> list[MethodChange]:
        source_files = [
            f for f in commit.files_changed
            if Path(f).suffix in _SOURCE_EXTENSIONS
        ]
        if not source_files:
            return []

        diff_text = self._get_commit_diff(commit.hash)
        added_files, modified_files, deleted_files = self._classify_files(diff_text, source_files)

        changes: list[MethodChange] = []

        for fpath in added_files:
            content = self._get_file_at_commit(commit.hash, fpath)
            if content:
                changes.extend(self._extract_methods_from_content(
                    fpath, content, "added",
                ))

        for fpath in modified_files:
            new_content = self._get_file_at_commit(commit.hash, fpath)
            old_content = self._get_file_at_commit(f"{commit.hash}~1", fpath)
            if new_content:
                file_diff = self._get_file_diff(commit.hash, fpath)
                changed_lines = self._extract_changed_line_ranges(file_diff)
                changes.extend(self._extract_changed_methods(
                    fpath, new_content, old_content or "", changed_lines,
                ))

        for fpath in deleted_files:
            content = self._get_file_at_commit(f"{commit.hash}~1", fpath)
            if content:
                changes.extend(self._extract_methods_from_content(
                    fpath, content, "deleted",
                ))

        return changes

    def _get_commit_diff(self, commit_hash: str) -> str:
        result = subprocess.run(
            ["git", "diff", f"{commit_hash}~1", commit_hash, "--name-status"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        return result.stdout

    def _get_file_diff(self, commit_hash: str, file_path: str) -> str:
        result = subprocess.run(
            ["git", "diff", f"{commit_hash}~1", commit_hash, "--", file_path],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        return result.stdout

    def _get_file_at_commit(self, ref: str, file_path: str) -> Optional[str]:
        result = subprocess.run(
            ["git", "show", f"{ref}:{file_path}"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _classify_files(self, name_status: str, source_files: list[str]
                        ) -> tuple[list[str], list[str], list[str]]:
        added, modified, deleted = [], [], []
        status_map: dict[str, str] = {}
        for line in name_status.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                status_map[parts[-1]] = parts[0][0]

        for f in source_files:
            s = status_map.get(f, "M")
            if s == "A":
                added.append(f)
            elif s == "D":
                deleted.append(f)
            else:
                modified.append(f)
        return added, modified, deleted

    def _extract_changed_line_ranges(self, diff_text: str) -> list[tuple[int, int]]:
        hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
        ranges = []
        for line in diff_text.splitlines():
            m = hunk_re.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                ranges.append((start, start + max(count - 1, 0)))
        return ranges

    def _extract_methods_from_content(self, file_path: str, content: str,
                                       change_type: str) -> list[MethodChange]:
        ext = Path(file_path).suffix
        func_pat = _get_func_pattern(ext)
        class_pat = _get_class_pattern(ext)
        if not func_pat:
            return []

        lang = ext.lstrip(".")
        lines = content.splitlines()
        methods: list[MethodChange] = []
        current_class = None

        for i, line in enumerate(lines):
            if class_pat:
                cm = class_pat.search(line)
                if cm:
                    current_class = cm.group(1)

            fm = func_pat.search(line)
            if fm:
                func_name = fm.group(1)
                if not func_name and fm.lastindex and fm.lastindex >= 2:
                    func_name = fm.group(2)
                if func_name:
                    body = self._extract_method_body(lines, i, ext)
                    methods.append(MethodChange(
                        file_path=file_path,
                        class_name=current_class,
                        method_name=func_name,
                        method_body=body,
                        change_type=change_type,
                        language=lang,
                    ))
        return methods

    def _extract_changed_methods(self, file_path: str, new_content: str,
                                  old_content: str,
                                  changed_ranges: list[tuple[int, int]],
                                  ) -> list[MethodChange]:
        ext = Path(file_path).suffix
        func_pat = _get_func_pattern(ext)
        class_pat = _get_class_pattern(ext)
        if not func_pat:
            return []

        lang = ext.lstrip(".")
        lines = new_content.splitlines()
        methods: list[MethodChange] = []
        current_class = None
        seen: set[str] = set()

        for i, line in enumerate(lines):
            line_num = i + 1
            if class_pat:
                cm = class_pat.search(line)
                if cm:
                    current_class = cm.group(1)

            fm = func_pat.search(line)
            if fm:
                func_name = fm.group(1)
                if not func_name and fm.lastindex and fm.lastindex >= 2:
                    func_name = fm.group(2)
                if not func_name:
                    continue

                qname = f"{current_class}.{func_name}" if current_class else func_name
                if qname in seen:
                    continue

                body = self._extract_method_body(lines, i, ext)
                body_end = i + body.count("\n") + 1

                for r_start, r_end in changed_ranges:
                    if _ranges_overlap(line_num, line_num + body_end - i,
                                       max(1, r_start - 3), r_end + 3):
                        seen.add(qname)
                        methods.append(MethodChange(
                            file_path=file_path,
                            class_name=current_class,
                            method_name=func_name,
                            method_body=body,
                            change_type="modified",
                            language=lang,
                        ))
                        break
        return methods

    def _extract_method_body(self, lines: list[str], start_idx: int, ext: str) -> str:
        if ext == ".py":
            return self._extract_python_method(lines, start_idx)
        return self._extract_brace_method(lines, start_idx)

    def _extract_python_method(self, lines: list[str], start_idx: int) -> str:
        result = [lines[start_idx]]
        if start_idx + 1 >= len(lines):
            return result[0]
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        for i in range(start_idx + 1, min(start_idx + 80, len(lines))):
            line = lines[i]
            if line.strip() == "":
                result.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent:
                break
            result.append(line)
        return "\n".join(result)

    def _extract_brace_method(self, lines: list[str], start_idx: int) -> str:
        result = []
        depth = 0
        started = False
        for i in range(start_idx, min(start_idx + 100, len(lines))):
            line = lines[i]
            result.append(line)
            depth += line.count("{") - line.count("}")
            if "{" in line:
                started = True
            if started and depth <= 0:
                break
        return "\n".join(result)


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end
