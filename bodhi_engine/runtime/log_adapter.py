"""
Log source adapters for Bodhi runtime debugging.

Provides a base LogAdapter interface and concrete implementations
for searching log files by pattern and correlation ID.
"""

from __future__ import annotations

import json
import mmap
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class LogEntry:
    """A single parsed log entry."""
    timestamp: Optional[datetime]
    level: str                     # INFO, WARN, ERROR, DEBUG
    message: str
    source: str                    # service name or file path
    raw: dict = field(default_factory=dict)


class LogAdapter(ABC):
    """Base interface for log source adapters."""

    @abstractmethod
    def search(
        self,
        pattern: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        correlation: Optional[dict[str, str]] = None,
        limit: int = 100,
    ) -> list[LogEntry]:
        """Search logs matching a regex pattern within a time window.

        Args:
            pattern: Regex pattern to match against log messages.
            time_from: Search window start (inclusive). None = no lower bound.
            time_to: Search window end (inclusive). None = no upper bound.
            correlation: Key-value pairs that must appear in the log line
                         (e.g. {"orderId": "12345"}).
            limit: Maximum number of entries to return.
        """
        ...


# Common timestamp patterns for unstructured logs
_TIMESTAMP_PATTERNS = [
    # ISO 8601: 2026-04-02T10:30:01Z or 2026-04-02T10:30:01.123Z
    (re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)"), "%Y-%m-%dT%H:%M:%S"),
    # Common: 2026-04-02 10:30:01
    (re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"), "%Y-%m-%d %H:%M:%S"),
]

_LEVEL_PATTERN = re.compile(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b", re.IGNORECASE)


def _parse_timestamp(text: str) -> Optional[datetime]:
    """Try to extract a timestamp from a log line."""
    for regex, fmt in _TIMESTAMP_PATTERNS:
        m = regex.search(text)
        if m:
            ts_str = m.group(1).rstrip("Z")
            # Handle fractional seconds
            if "." in ts_str:
                try:
                    return datetime.strptime(ts_str, fmt + ".%f")
                except ValueError:
                    pass
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
    return None


def _parse_level(text: str) -> str:
    """Extract log level from a log line."""
    m = _LEVEL_PATTERN.search(text)
    if m:
        level = m.group(1).upper()
        if level == "WARNING":
            return "WARN"
        return level
    return "INFO"


class FileLogAdapter(LogAdapter):
    """Search local log files by regex pattern.

    Supports both JSON-structured logs and plain text logs.
    """

    def __init__(
        self,
        paths: list[str | Path],
        format: str = "text",
        timestamp_field: str = "@timestamp",
        message_field: str = "message",
    ):
        """
        Args:
            paths: List of file paths or glob patterns to search.
            format: Log format — "json" or "text".
            timestamp_field: JSON field name for timestamp (json format only).
            message_field: JSON field name for message (json format only).
        """
        self.paths = [Path(p) for p in paths]
        self.format = format
        self.timestamp_field = timestamp_field
        self.message_field = message_field

    def _resolve_paths(self) -> list[Path]:
        """Expand glob patterns and return existing files."""
        resolved = []
        for p in self.paths:
            if "*" in str(p):
                resolved.extend(sorted(p.parent.glob(p.name)))
            elif p.is_file():
                resolved.append(p)
        return resolved

    def search(
        self,
        pattern: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        correlation: Optional[dict[str, str]] = None,
        limit: int = 100,
    ) -> list[LogEntry]:
        results: list[LogEntry] = []
        regex = re.compile(pattern, re.IGNORECASE)

        for file_path in self._resolve_paths():
            if len(results) >= limit:
                break
            entries = self._search_file(file_path, regex, time_from, time_to, correlation)
            results.extend(entries)

        # Sort by timestamp (entries with no timestamp go last)
        results.sort(key=lambda e: e.timestamp or datetime.max)
        return results[:limit]

    def _search_file(
        self,
        file_path: Path,
        regex: re.Pattern,
        time_from: Optional[datetime],
        time_to: Optional[datetime],
        correlation: Optional[dict[str, str]],
    ) -> list[LogEntry]:
        entries: list[LogEntry] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue

                    entry = self._parse_line(line, str(file_path))
                    if entry is None:
                        continue

                    # Time filter
                    if entry.timestamp:
                        if time_from and entry.timestamp < time_from:
                            continue
                        if time_to and entry.timestamp > time_to:
                            continue

                    # Pattern match
                    if not regex.search(entry.message):
                        continue

                    # Correlation filter: all values must appear in the message or raw fields
                    if correlation:
                        if not self._matches_correlation(entry, correlation):
                            continue

                    entries.append(entry)
        except (OSError, IOError):
            pass
        return entries

    def _parse_line(self, line: str, source: str) -> Optional[LogEntry]:
        if self.format == "json":
            return self._parse_json_line(line, source)
        return self._parse_text_line(line, source)

    def _parse_json_line(self, line: str, source: str) -> Optional[LogEntry]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        ts_raw = data.get(self.timestamp_field)
        timestamp = None
        if ts_raw:
            if isinstance(ts_raw, str):
                timestamp = _parse_timestamp(ts_raw)

        message = str(data.get(self.message_field, ""))
        level = str(data.get("level", data.get("severity", "INFO"))).upper()
        if level == "WARNING":
            level = "WARN"

        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            source=source,
            raw=data,
        )

    def _parse_text_line(self, line: str, source: str) -> Optional[LogEntry]:
        return LogEntry(
            timestamp=_parse_timestamp(line),
            level=_parse_level(line),
            message=line,
            source=source,
            raw={},
        )

    def _matches_correlation(self, entry: LogEntry, correlation: dict[str, str]) -> bool:
        """Check if all correlation values appear in the entry."""
        for key, value in correlation.items():
            # Check in raw fields first (structured logs)
            if entry.raw.get(key) == value:
                continue
            # Fallback: check if value appears in message
            if value in entry.message:
                continue
            return False
        return True
