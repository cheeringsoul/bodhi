"""Tests for bodhi import-history: git walker, prompt builder, tag accumulator, and output writer."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from bodhi_engine.git_walker import (
    CommitInfo, CommitWalker, DiffParser, MethodChange,
    _is_meaningful_commit,
)
from bodhi_app.cli.import_history import (
    GeneratedTags, PromptBuilder, LLMClient, TagAccumulator,
    OutputWriter, ImportState, ContextCollector, BudgetTracker,
    SYSTEM_PROMPT,
)


# ── CommitInfo / filtering ────────────────────────────────────────

class TestCommitFiltering:
    def test_skip_merge_commit(self):
        c = CommitInfo(hash="abc", message="Merge branch 'feature'", author="a", date="2024-01-01",
                       files_changed=["src/Foo.java"])
        assert not _is_meaningful_commit(c)

    def test_skip_docs_commit(self):
        c = CommitInfo(hash="abc", message="docs: update README", author="a", date="2024-01-01",
                       files_changed=["README.md"])
        assert not _is_meaningful_commit(c)

    def test_skip_chore_commit(self):
        c = CommitInfo(hash="abc", message="chore: bump version", author="a", date="2024-01-01",
                       files_changed=["version.txt"])
        assert not _is_meaningful_commit(c)

    def test_skip_no_source_files(self):
        c = CommitInfo(hash="abc", message="feat: add config", author="a", date="2024-01-01",
                       files_changed=["config.yml", "data.json"])
        assert not _is_meaningful_commit(c)

    def test_keep_feat_with_source(self):
        c = CommitInfo(hash="abc", message="feat: add order creation", author="a", date="2024-01-01",
                       files_changed=["src/OrderService.java"])
        assert _is_meaningful_commit(c)

    def test_keep_fix_with_python(self):
        c = CommitInfo(hash="abc", message="fix: handle null pointer", author="a", date="2024-01-01",
                       files_changed=["app/service.py"])
        assert _is_meaningful_commit(c)

    def test_keep_refactor_with_ts(self):
        c = CommitInfo(hash="abc", message="refactor: extract helper", author="a", date="2024-01-01",
                       files_changed=["src/utils.ts"])
        assert _is_meaningful_commit(c)


# ── CommitWalker._parse_log ───────────────────────────────────────

class TestCommitWalkerParseLog:
    def test_parse_single_commit(self):
        raw = "abc123\x00feat: add order\x00Alice\x002024-01-15T10:00:00+08:00\nsrc/Order.java\n"
        walker = CommitWalker(Path("."))
        commits = walker._parse_log(raw)
        assert len(commits) == 1
        assert commits[0].hash == "abc123"
        assert commits[0].message == "feat: add order"
        assert commits[0].author == "Alice"
        assert commits[0].files_changed == ["src/Order.java"]

    def test_parse_multiple_commits(self):
        raw = (
            "aaa\x00feat: first\x00A\x002024-01-01\nsrc/A.java\n"
            "bbb\x00fix: second\x00B\x002024-01-02\nsrc/B.py\nsrc/C.py\n"
        )
        walker = CommitWalker(Path("."))
        commits = walker._parse_log(raw)
        assert len(commits) == 2
        assert commits[1].files_changed == ["src/B.py", "src/C.py"]

    def test_parse_empty(self):
        walker = CommitWalker(Path("."))
        assert walker._parse_log("") == []


# ── PromptBuilder ─────────────────────────────────────────────────

class TestPromptBuilder:
    def test_basic_prompt(self):
        builder = PromptBuilder()
        method = MethodChange(
            file_path="src/OrderService.java",
            class_name="OrderService",
            method_name="create",
            method_body="public void create() { }",
            change_type="added",
            language="java",
        )
        commit = CommitInfo(hash="abc", message="feat: add order creation",
                            author="a", date="2024-01-01")
        prompt = builder.build_batch_prompt([method], commit)
        assert "feat: add order creation" in prompt
        assert "OrderService.create" in prompt
        assert "public void create()" in prompt

    def test_prompt_with_context(self):
        builder = PromptBuilder()
        method = MethodChange("f.java", "Svc", "run", "void run(){}", "added", "java")
        commit = CommitInfo(hash="abc", message="feat: x", author="a", date="d")
        prompt = builder.build_batch_prompt(
            [method], commit,
            known_entities=["Order", "User"],
            known_services=["PaymentService"],
            extra_context="PR: Added retry logic for payments",
        )
        assert "Order, User" in prompt
        assert "PaymentService" in prompt
        assert "PR: Added retry logic" in prompt

    def test_multiple_methods(self):
        builder = PromptBuilder()
        m1 = MethodChange("f.java", "A", "foo", "void foo(){}", "added", "java")
        m2 = MethodChange("f.java", "A", "bar", "void bar(){}", "modified", "java")
        commit = CommitInfo(hash="abc", message="feat: x", author="a", date="d")
        prompt = builder.build_batch_prompt([m1, m2], commit)
        assert "Method 1: A.foo (added)" in prompt
        assert "Method 2: A.bar (modified)" in prompt


# ── TagAccumulator ────────────────────────────────────────────────

class TestTagAccumulator:
    def test_add_new(self):
        acc = TagAccumulator()
        t = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                          intent="Do something", commit_hash="abc")
        acc.add(t)
        assert len(acc.get_all()) == 1
        assert acc.get_all()[0].intent == "Do something"

    def test_later_commit_overrides_intent(self):
        acc = TagAccumulator()
        t1 = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                           intent="First intent", reads=["orders(id)"], commit_hash="aaa")
        t2 = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                           intent="Updated intent", reads=["orders(id, status)"], commit_hash="bbb")
        acc.add(t1)
        acc.add(t2)
        assert len(acc.get_all()) == 1
        assert acc.get_all()[0].intent == "Updated intent"
        assert acc.get_all()[0].reads == ["orders(id, status)"]

    def test_on_fail_accumulates(self):
        acc = TagAccumulator()
        t1 = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                           intent="x", on_fail=["timeout → retry"], commit_hash="aaa")
        t2 = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                           intent="x", on_fail=["not_found → 404"], commit_hash="bbb")
        acc.add(t1)
        acc.add(t2)
        result = acc.get_all()[0]
        assert "timeout → retry" in result.on_fail
        assert "not_found → 404" in result.on_fail

    def test_remove_deleted(self):
        acc = TagAccumulator()
        t = GeneratedTags(file_path="f.java", class_name="Svc", method_name="run",
                          intent="x", commit_hash="abc")
        acc.add(t)
        acc.remove_deleted("Svc.run")
        assert len(acc.get_all()) == 0

    def test_get_by_class(self):
        acc = TagAccumulator()
        acc.add(GeneratedTags("f.java", "OrderSvc", "create", intent="x", commit_hash="a"))
        acc.add(GeneratedTags("f.java", "OrderSvc", "cancel", intent="y", commit_hash="a"))
        acc.add(GeneratedTags("g.java", "PaySvc", "charge", intent="z", commit_hash="a"))
        by_class = acc.get_by_class()
        assert len(by_class["OrderSvc"]) == 2
        assert len(by_class["PaySvc"]) == 1


# ── BudgetTracker ─────────────────────────────────────────────────

class TestBudgetTracker:
    def test_no_budget_never_exceeded(self):
        bt = BudgetTracker(budget=None)
        bt.record(100000, 50000)
        assert not bt.exceeded()

    def test_budget_exceeded(self):
        bt = BudgetTracker(budget=0.001)
        bt.record(100000, 100000)
        assert bt.exceeded()

    def test_budget_not_exceeded(self):
        bt = BudgetTracker(budget=100.0)
        bt.record(1000, 500)
        assert not bt.exceeded()

    def test_cost_accumulates(self):
        bt = BudgetTracker(budget=1.0, provider="anthropic")
        bt.record(4000, 4000)  # ~1k tokens each
        first = bt.spent
        bt.record(4000, 4000)
        assert bt.spent > first


# ── LLMClient._parse_response ────────────────────────────────────

class TestLLMClientParseResponse:
    def setup_method(self):
        self.client = LLMClient.__new__(LLMClient)

    def test_parse_json_array(self):
        text = '[{"method": "Svc.run", "intent": "Do X"}]'
        result = self.client._parse_response(text)
        assert len(result) == 1
        assert result[0]["intent"] == "Do X"

    def test_parse_single_object(self):
        text = '{"method": "Svc.run", "intent": "Do X"}'
        result = self.client._parse_response(text)
        assert len(result) == 1

    def test_parse_wrapped_methods(self):
        text = '{"methods": [{"intent": "A"}, {"intent": "B"}]}'
        result = self.client._parse_response(text)
        assert len(result) == 2

    def test_strip_markdown_fences(self):
        text = '```json\n[{"intent": "X"}]\n```'
        result = self.client._parse_response(text)
        assert result[0]["intent"] == "X"


# ── OutputWriter ──────────────────────────────────────────────────

class TestOutputWriter:
    def test_write_creates_files(self, tmp_path):
        acc = TagAccumulator()
        acc.add(GeneratedTags("src/Order.java", "OrderService", "create",
                              intent="Create order", writes=["orders(id)"], commit_hash="abc"))
        acc.add(GeneratedTags("src/Pay.java", "PayService", "charge",
                              intent="Charge payment", calls=["Stripe.charge"], commit_hash="def"))

        writer = OutputWriter(tmp_path)
        writer.write(acc, {"commits_analyzed": 5, "api_calls": 3, "errors": 0})

        tags_dir = tmp_path / ".bodhi-import" / "tags"
        assert tags_dir.exists()
        assert (tags_dir / "OrderService.yaml").exists()
        assert (tags_dir / "PayService.yaml").exists()
        assert (tmp_path / ".bodhi-import" / "summary.md").exists()

    def test_yaml_content(self, tmp_path):
        acc = TagAccumulator()
        acc.add(GeneratedTags("src/Order.java", "OrderService", "create",
                              intent="Create order", reads=["request.body(items)"],
                              writes=["orders(id, status) via INSERT"], commit_hash="abc"))

        writer = OutputWriter(tmp_path)
        writer.write(acc, {"commits_analyzed": 1, "api_calls": 1, "errors": 0})

        import yaml
        data = yaml.safe_load((tmp_path / ".bodhi-import" / "tags" / "OrderService.yaml").read_text())
        assert data["class"] == "OrderService"
        assert len(data["methods"]) == 1
        assert data["methods"][0]["tags"]["intent"] == "Create order"
        assert "orders(id, status) via INSERT" in data["methods"][0]["tags"]["writes"]


# ── ImportState ───────────────────────────────────────────────────

class TestImportState:
    def test_save_and_load(self, tmp_path):
        state = ImportState(tmp_path)
        state.save(["abc", "def"], {"commits_analyzed": 2})
        loaded = state.load()
        assert loaded["processed_commits"] == ["abc", "def"]
        assert loaded["stats"]["commits_analyzed"] == 2

    def test_load_empty(self, tmp_path):
        state = ImportState(tmp_path)
        loaded = state.load()
        assert loaded["processed_commits"] == []


# ── ContextCollector ──────────────────────────────────────────────

class TestContextCollector:
    def test_no_github_returns_none(self):
        cc = ContextCollector(github_repo=None)
        commit = CommitInfo(hash="abc", message="feat: x", author="a", date="d")
        assert cc.collect(commit) is None

    def test_extract_issue_refs(self):
        refs = ContextCollector._extract_issue_refs("fix: handle timeout (#42, see #100)")
        assert 42 in refs
        assert 100 in refs

    def test_extract_no_refs(self):
        refs = ContextCollector._extract_issue_refs("feat: add feature")
        assert refs == []

    def test_caches_results(self):
        cc = ContextCollector(github_repo="owner/repo")
        cc._cache["abc"] = "cached context"
        commit = CommitInfo(hash="abc", message="feat: x", author="a", date="d")
        assert cc.collect(commit) == "cached context"


# ── GeneratedTags ─────────────────────────────────────────────────

class TestGeneratedTags:
    def test_qualified_name_with_class(self):
        t = GeneratedTags("f.java", "OrderService", "create")
        assert t.qualified_name == "OrderService.create"

    def test_qualified_name_without_class(self):
        t = GeneratedTags("f.py", None, "process_order")
        assert t.qualified_name == "process_order"
