"""
Parse @bodhi.* inline tags from source code files.
Supports Java, Python, Go, TypeScript, Kotlin.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BodhiTag:
    """A single @bodhi.* tag parsed from a doc comment."""
    tag: str          # e.g. "intent", "reads", "writes"
    value: str        # e.g. "request.body(userId, items)"
    line_number: int  # line in source file


@dataclass
class FunctionDSL:
    """All Bodhi DSL tags for a single function."""
    file_path: str
    function_name: str
    class_name: Optional[str]
    line_number: int
    tags: list[BodhiTag] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        if self.class_name:
            return f"{self.class_name}.{self.function_name}"
        return self.function_name

    @property
    def intent(self) -> Optional[str]:
        for tag in self.tags:
            if tag.tag == "intent":
                return tag.value
        return None

    def get_tags(self, name: str) -> list[str]:
        return [t.value for t in self.tags if t.tag == name]

    @property
    def reads(self) -> list[str]:
        return self.get_tags("reads")

    @property
    def writes(self) -> list[str]:
        return self.get_tags("writes")

    @property
    def calls(self) -> list[str]:
        results = []
        for val in self.get_tags("calls"):
            results.extend([c.strip() for c in val.split(",")])
        return results

    @property
    def emits(self) -> list[str]:
        return self.get_tags("emits")

    @property
    def consumes(self) -> list[str]:
        return self.get_tags("consumes")

    @property
    def on_fail(self) -> list[str]:
        return self.get_tags("on_fail")

    @property
    def implements(self) -> Optional[str]:
        """Return the interface name from @bodhi.implements, or None."""
        vals = self.get_tags("implements")
        return vals[0] if vals else None


# Pattern to match @bodhi.<tag> <value>
TAG_PATTERN = re.compile(r"@bodhi\.(\S+)\s+(.*)")

# Patterns to detect function declarations per language
FUNCTION_PATTERNS = {
    ".java": re.compile(
        r"(?:public|private|protected|static|\s)+"
        r"\S+\s+(\w+)\s*\("
    ),
    ".kt": re.compile(
        r"(?:fun)\s+(\w+)\s*\("
    ),
    ".py": re.compile(
        r"def\s+(\w+)\s*\("
    ),
    ".go": re.compile(
        r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\("
    ),
    ".ts": re.compile(
        r"(?:async\s+)?(?:function\s+)?(\w+)\s*\(|(\w+)\s*(?:=|:)\s*(?:async\s+)?\("
    ),
    ".js": re.compile(
        r"(?:async\s+)?(?:function\s+)?(\w+)\s*\(|(\w+)\s*(?:=|:)\s*(?:async\s+)?\("
    ),
}

# Patterns to detect class declarations
CLASS_PATTERNS = {
    ".java": re.compile(r"class\s+(\w+)"),
    ".kt": re.compile(r"class\s+(\w+)"),
    ".py": re.compile(r"class\s+(\w+)"),
    ".go": None,  # Go doesn't have classes
    ".ts": re.compile(r"class\s+(\w+)"),
    ".js": re.compile(r"class\s+(\w+)"),
}


def parse_tags_from_comment(comment_lines: list[tuple[int, str]]) -> list[BodhiTag]:
    """Extract @bodhi.* tags from a list of comment lines."""
    tags = []
    for line_num, line in comment_lines:
        # Strip comment prefixes: //, *, #, """
        stripped = line.strip()
        for prefix in ("*", "//", "#", "/**", "*/", '"""', "'''"):
            stripped = stripped.strip(prefix).strip()

        match = TAG_PATTERN.match(stripped)
        if match:
            tags.append(BodhiTag(
                tag=match.group(1),
                value=match.group(2).strip(),
                line_number=line_num,
            ))
    return tags


def _parse_python(file_path: Path, lines: list[str]) -> list[FunctionDSL]:
    """Parse Python files: docstrings come AFTER the def line."""
    func_pattern = FUNCTION_PATTERNS[".py"]
    class_pattern = CLASS_PATTERNS[".py"]
    results = []
    current_class = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        line_num = i + 1

        # Track class context
        if class_pattern:
            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)

        # Check for def
        func_match = func_pattern.search(line)
        if func_match:
            func_name = func_match.group(1)
            func_line = line_num

            # Look ahead for docstring on next non-empty line(s)
            j = i + 1
            # Skip continuation lines (multi-line def)
            while j < len(lines) and not lines[j].strip().endswith(":"):
                if lines[j].strip().startswith(('"""', "'''")):
                    break
                j += 1
                if j - i > 5:  # safety limit
                    break

            # Now look for docstring
            if j < len(lines):
                # The def line itself might end with :, check next line
                check_line = j + 1 if lines[j].strip().endswith(":") and j == i else j
                # Actually, just scan forward from def line for docstring
                for k in range(i + 1, min(i + 4, len(lines))):
                    check_stripped = lines[k].strip()
                    if not check_stripped:
                        continue
                    if check_stripped.startswith(('"""', "'''")):
                        # Found docstring start
                        quote = '"""' if check_stripped.startswith('"""') else "'''"
                        comment_buffer: list[tuple[int, str]] = []

                        # Single-line docstring: """..."""
                        if check_stripped.count(quote) >= 2:
                            comment_buffer.append((k + 1, lines[k]))
                        else:
                            # Multi-line docstring
                            comment_buffer.append((k + 1, lines[k]))
                            for m in range(k + 1, len(lines)):
                                comment_buffer.append((m + 1, lines[m]))
                                if quote in lines[m].strip():
                                    break

                        tags = parse_tags_from_comment(comment_buffer)
                        if tags:
                            results.append(FunctionDSL(
                                file_path=str(file_path),
                                function_name=func_name,
                                class_name=current_class,
                                line_number=func_line,
                                tags=tags,
                            ))
                        break
                    else:
                        break  # Not a docstring, stop looking
        i += 1

    return results


def parse_file(file_path: Path) -> list[FunctionDSL]:
    """Parse all @bodhi.* annotated functions from a source file."""
    suffix = file_path.suffix
    if suffix not in FUNCTION_PATTERNS:
        return []

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    # Python needs special handling: docstring comes after def
    if suffix == ".py":
        return _parse_python(file_path, lines)

    func_pattern = FUNCTION_PATTERNS[suffix]
    class_pattern = CLASS_PATTERNS.get(suffix)

    results = []
    current_class = None
    class_tags: list[BodhiTag] = []  # Tags from class-level doc comment
    comment_buffer: list[tuple[int, str]] = []
    in_comment = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track class context
        if class_pattern:
            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)
                # Check if the preceding comment had class-level @bodhi.* tags
                if comment_buffer:
                    class_tags = parse_tags_from_comment(comment_buffer)
                comment_buffer = []
                continue

        # Track block comments (/** ... */)
        if suffix in (".java", ".kt", ".ts", ".js"):
            if "/**" in stripped:
                in_comment = True
                comment_buffer = [(i, line)]
                continue
            if in_comment:
                comment_buffer.append((i, line))
                if "*/" in stripped:
                    in_comment = False
                continue
        elif suffix == ".go":
            if stripped.startswith("//"):
                comment_buffer.append((i, line))
                continue

        # Check if this line declares a function
        func_match = func_pattern.search(line)
        if func_match:
            func_name = func_match.group(1)
            if not func_name and func_match.lastindex and func_match.lastindex >= 2:
                func_name = func_match.group(2)

            if func_name and comment_buffer:
                tags = parse_tags_from_comment(comment_buffer)
                if tags:
                    # Merge class-level tags (e.g. @bodhi.implements)
                    merged = list(tags)
                    if class_tags:
                        existing = {t.tag for t in merged}
                        for ct in class_tags:
                            if ct.tag not in existing:
                                merged.append(ct)
                    results.append(FunctionDSL(
                        file_path=str(file_path),
                        function_name=func_name,
                        class_name=current_class,
                        line_number=i,
                        tags=merged,
                    ))
            elif func_name and class_tags:
                # Function has no own doc comment but class has tags
                results.append(FunctionDSL(
                    file_path=str(file_path),
                    function_name=func_name,
                    class_name=current_class,
                    line_number=i,
                    tags=list(class_tags),
                ))

        # Reset comment buffer on non-comment, non-function lines
        if not stripped.startswith("//") and not in_comment:
            comment_buffer = []

    return results


def parse_directory(directory: Path, extensions: set[str] | None = None,
                    exclude_dirs: set[str] | None = None) -> list[FunctionDSL]:
    """Recursively parse all source files in a directory.

    Args:
        directory: Root directory to scan.
        extensions: File extensions to include (default: common source files).
        exclude_dirs: Additional directory names to skip (merged with built-in list).
    """
    if extensions is None:
        extensions = {".java", ".py", ".go", ".ts", ".js", ".kt"}

    results = []
    for file_path in directory.rglob("*"):
        if file_path.suffix in extensions and not _is_excluded(file_path, exclude_dirs):
            results.extend(parse_file(file_path))
    return results


def _is_excluded(path: Path, extra: set[str] | None = None) -> bool:
    """Skip common non-source directories."""
    excluded = {
        "node_modules", ".git", "__pycache__", "venv", ".venv",
        "build", "dist", "target", ".idea", ".vscode",
    }
    if extra:
        excluded |= extra
    return any(part in excluded for part in path.parts)
