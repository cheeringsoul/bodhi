"""Tests for bodhi impact-pr: diff parsing, function matching, impact tracing, and rendering."""

import pytest
from pathlib import Path

from bodhi_engine.knowledge import BodhiKnowledge
from bodhi_engine.parser.inline import FunctionDSL, BodhiTag
from bodhi_app.cli.impact_pr import (
    parse_diff, ChangedFile, ChangedHunk,
    find_changed_functions, trace_pr_impact, render_markdown,
    _extract_event_name, _ranges_overlap, cmd_impact_pr,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def kb():
    return BodhiKnowledge(FIXTURES)


# -- diff parsing --

SAMPLE_DIFF = """\
diff --git a/src/OrderService.java b/src/OrderService.java
index abc1234..def5678 100644
--- a/src/OrderService.java
+++ b/src/OrderService.java
@@ -14,6 +14,8 @@ public class OrderService {
     public OrderResponse create(CreateOrderRequest req) {
-        // old code
+        // new code
+        // more new code
     }
@@ -30,3 +32,5 @@ public class OrderService {
     public void cancel(Long orderId) {
+        // added line
     }
"""

SAMPLE_DIFF_NEW_FILE = """\
diff --git a/src/NewService.java b/src/NewService.java
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/src/NewService.java
@@ -0,0 +1,10 @@
+package com.example;
+public class NewService {
+    public void doSomething() {}
+}
"""


class TestParseDiff:
    def test_parse_basic_diff(self):
        files = parse_diff(SAMPLE_DIFF)
        assert len(files) == 1
        assert files[0].path == "src/OrderService.java"
        assert len(files[0].hunks) == 2

    def test_hunk_line_numbers(self):
        files = parse_diff(SAMPLE_DIFF)
        h1 = files[0].hunks[0]
        assert h1.start == 14
        assert h1.count == 8

        h2 = files[0].hunks[1]
        assert h2.start == 32
        assert h2.count == 5

    def test_hunk_end(self):
        h = ChangedHunk(start=10, count=5)
        assert h.end == 14

    def test_hunk_single_line(self):
        h = ChangedHunk(start=10, count=1)
        assert h.end == 10

    def test_hunk_zero_count(self):
        h = ChangedHunk(start=10, count=0)
        assert h.end == 10

    def test_parse_new_file(self):
        files = parse_diff(SAMPLE_DIFF_NEW_FILE)
        assert len(files) == 1
        assert files[0].path == "src/NewService.java"
        assert files[0].hunks[0].start == 1
        assert files[0].hunks[0].count == 10

    def test_parse_multiple_files(self):
        multi_diff = SAMPLE_DIFF + SAMPLE_DIFF_NEW_FILE
        files = parse_diff(multi_diff)
        assert len(files) == 2

    def test_parse_empty_diff(self):
        assert parse_diff("") == []
        assert parse_diff("\n\n") == []


# -- range overlap --

class TestRangesOverlap:
    def test_overlap(self):
        assert _ranges_overlap(1, 10, 5, 15) is True

    def test_no_overlap(self):
        assert _ranges_overlap(1, 5, 10, 15) is False

    def test_adjacent(self):
        assert _ranges_overlap(1, 5, 5, 10) is True

    def test_contained(self):
        assert _ranges_overlap(1, 20, 5, 10) is True


# -- extract event name --

class TestExtractEventName:
    def test_simple(self):
        assert _extract_event_name("order_created") == "order_created"

    def test_with_params_and_channel(self):
        assert _extract_event_name("order_created(orderId) to kafka:topic") == "order_created"

    def test_empty(self):
        assert _extract_event_name("") is None


# -- find changed functions --

class TestFindChangedFunctions:
    def test_match_function_in_hunk(self, kb):
        changed_files = [
            ChangedFile(
                path="src/OrderService.java",
                hunks=[ChangedHunk(start=14, count=4)],
            )
        ]
        fns = find_changed_functions(FIXTURES, changed_files, kb.functions)
        names = [f.qualified_name for f in fns]
        assert "OrderService.create" in names

    def test_no_match_outside_hunk(self, kb):
        changed_files = [
            ChangedFile(
                path="src/OrderService.java",
                hunks=[ChangedHunk(start=200, count=2)],
            )
        ]
        fns = find_changed_functions(FIXTURES, changed_files, kb.functions)
        assert len(fns) == 0

    def test_no_match_wrong_file(self, kb):
        changed_files = [
            ChangedFile(
                path="src/NonExistent.java",
                hunks=[ChangedHunk(start=1, count=100)],
            )
        ]
        fns = find_changed_functions(FIXTURES, changed_files, kb.functions)
        assert len(fns) == 0


# -- trace_pr_impact --

class TestTracePRImpact:
    def test_traces_flows(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        assert fn is not None
        impact = trace_pr_impact(kb, [fn])
        flow_names = [f["name"] for f in impact.affected_flows]
        assert "create_order" in flow_names

    def test_traces_events(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        event_names = [e["name"] for e in impact.event_impacts]
        assert "order_created" in event_names

    def test_traces_data_writes(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        write_details = [w["detail"] for w in impact.data_writes]
        assert any("orders" in w for w in write_details)

    def test_traces_cross_service_deps(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        dep_services = [d["service"] for d in impact.cross_service_deps]
        assert "inventory-service" in dep_services

    def test_generates_risks(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        assert len(impact.risks) > 0

    def test_empty_functions(self, kb):
        impact = trace_pr_impact(kb, [])
        assert len(impact.affected_flows) == 0
        assert len(impact.event_impacts) == 0


# -- render_markdown --

class TestRenderMarkdown:
    def test_renders_changed_functions(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        md = render_markdown(impact)
        assert "## Bodhi Impact Analysis" in md
        assert "`OrderService.create`" in md

    def test_renders_flows(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        md = render_markdown(impact)
        assert "### Affected flows" in md
        assert "`create_order`" in md

    def test_renders_events(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        md = render_markdown(impact)
        assert "### Event impact" in md
        assert "`order_created`" in md

    def test_renders_data_impact(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        md = render_markdown(impact)
        assert "### Data impact" in md

    def test_renders_risks(self, kb):
        fn = kb._fn_by_name.get("OrderService.create")
        impact = trace_pr_impact(kb, [fn])
        md = render_markdown(impact)
        assert "### Risks" in md

    def test_empty_impact(self):
        from bodhi_app.cli.impact_pr import PRImpact
        impact = PRImpact(
            changed_functions=[], affected_flows=[],
            data_reads=[], data_writes=[],
            event_impacts=[], cross_service_deps=[],
            state_machine_impacts=[], risks=[],
        )
        md = render_markdown(impact)
        assert "No Bodhi-annotated functions were changed" in md


# -- cmd_impact_pr with diff text --

class TestCmdImpactPR:
    def test_with_matching_diff(self):
        diff = """\
diff --git a/src/OrderService.java b/src/OrderService.java
index abc..def 100644
--- a/src/OrderService.java
+++ b/src/OrderService.java
@@ -13,3 +13,5 @@ public class OrderService {
     public OrderResponse create(CreateOrderRequest req) {
+        // changed
     }
"""
        md = cmd_impact_pr(FIXTURES, diff_text=diff)
        assert "## Bodhi Impact Analysis" in md
        assert "`OrderService.create`" in md

    def test_with_empty_diff(self):
        md = cmd_impact_pr(FIXTURES, diff_text="")
        assert "No changes detected" in md

    def test_with_no_source_changes(self):
        diff = """\
diff --git a/README.md b/README.md
index abc..def 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,5 @@
 # README
+new line
"""
        md = cmd_impact_pr(FIXTURES, diff_text=diff)
        # README.md is not a source file, so no functions matched
        assert "No Bodhi-annotated functions were changed" in md
