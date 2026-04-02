"""Tests for bodhi_engine.runtime: log adapters, debug engine, and config parsing."""

import pytest
from datetime import datetime
from pathlib import Path

from bodhi_engine.runtime.log_adapter import (
    LogEntry, FileLogAdapter, _parse_timestamp, _parse_level,
)
from bodhi_engine.runtime.debug_engine import (
    DebugEngine, StepStatus, StepResult, DebugReport,
    _bodhi_pattern_to_regex,
)
from bodhi_engine.parser.yaml_parser import (
    Flow, FlowStep, parse_project_meta, parse_flow,
)
from bodhi_engine.parser.inline import FunctionDSL, BodhiTag


FIXTURES = Path(__file__).parent / "fixtures"
TEXT_LOG = FIXTURES / "logs" / "order-service.log"
JSON_LOG = FIXTURES / "logs" / "order-service.json.log"


# -- timestamp / level parsing --

class TestParseTimestamp:
    def test_iso_format(self):
        ts = _parse_timestamp("2026-04-02T10:30:01Z some message")
        assert ts is not None
        assert ts.year == 2026
        assert ts.hour == 10
        assert ts.second == 1

    def test_common_format(self):
        ts = _parse_timestamp("2026-04-02 10:30:01 INFO message")
        assert ts is not None
        assert ts.minute == 30

    def test_no_timestamp(self):
        assert _parse_timestamp("just a log message") is None


class TestParseLevel:
    def test_info(self):
        assert _parse_level("2026 INFO message") == "INFO"

    def test_error(self):
        assert _parse_level("2026 ERROR message") == "ERROR"

    def test_warning_normalized(self):
        assert _parse_level("WARNING: something") == "WARN"

    def test_no_level(self):
        assert _parse_level("some random line") == "INFO"


# -- FileLogAdapter (text) --

class TestFileLogAdapterText:
    @pytest.fixture
    def adapter(self):
        return FileLogAdapter(paths=[TEXT_LOG], format="text")

    def test_search_all(self, adapter):
        entries = adapter.search(pattern=".*")
        assert len(entries) == 5

    def test_search_by_pattern(self, adapter):
        entries = adapter.search(pattern="Payment failed")
        assert len(entries) == 1
        assert "timeout" in entries[0].message

    def test_search_by_correlation(self, adapter):
        entries = adapter.search(pattern=".*", correlation={"orderId": "12345"})
        assert len(entries) >= 3  # lines containing "12345"

    def test_search_by_time_window(self, adapter):
        t_from = datetime(2026, 4, 2, 10, 30, 3)
        t_to = datetime(2026, 4, 2, 10, 30, 6)
        entries = adapter.search(pattern=".*", time_from=t_from, time_to=t_to)
        assert all(e.timestamp >= t_from for e in entries if e.timestamp)
        assert all(e.timestamp <= t_to for e in entries if e.timestamp)

    def test_timestamp_parsed(self, adapter):
        entries = adapter.search(pattern="Order 12345 created")
        assert len(entries) == 1
        assert entries[0].timestamp is not None
        assert entries[0].timestamp.year == 2026

    def test_level_parsed(self, adapter):
        entries = adapter.search(pattern="Payment failed")
        assert entries[0].level == "ERROR"

    def test_limit(self, adapter):
        entries = adapter.search(pattern=".*", limit=2)
        assert len(entries) == 2

    def test_nonexistent_file(self):
        adapter = FileLogAdapter(paths=[Path("/nonexistent/file.log")])
        entries = adapter.search(pattern=".*")
        assert entries == []


# -- FileLogAdapter (JSON) --

class TestFileLogAdapterJSON:
    @pytest.fixture
    def adapter(self):
        return FileLogAdapter(
            paths=[JSON_LOG], format="json",
            timestamp_field="@timestamp", message_field="message",
        )

    def test_search_all(self, adapter):
        entries = adapter.search(pattern=".*")
        assert len(entries) == 4

    def test_json_field_correlation(self, adapter):
        entries = adapter.search(
            pattern=".*",
            correlation={"orderId": "12345"},
        )
        assert len(entries) == 3  # 3 entries have orderId=12345

    def test_json_level(self, adapter):
        entries = adapter.search(pattern="Payment failed")
        assert len(entries) == 1
        assert entries[0].level == "ERROR"

    def test_json_raw_fields(self, adapter):
        entries = adapter.search(pattern="Order 12345 created")
        assert len(entries) == 1
        assert entries[0].raw.get("orderId") == "12345"


# -- bodhi pattern to regex --

class TestBodhiPatternToRegex:
    def test_simple_pattern(self):
        regex = _bodhi_pattern_to_regex("Order {orderId} created successfully")
        import re
        assert re.search(regex, "Order 12345 created successfully")
        assert not re.search(regex, "Order created")

    def test_multiple_placeholders(self):
        regex = _bodhi_pattern_to_regex("Payment failed for {orderId}: {reason}")
        import re
        assert re.search(regex, "Payment failed for 12345: timeout")

    def test_no_placeholders(self):
        regex = _bodhi_pattern_to_regex("static message")
        import re
        assert re.search(regex, "static message")


# -- DebugEngine --

def _make_function_dsl(name: str, success_patterns=None, error_patterns=None):
    """Helper to create a FunctionDSL with log patterns."""
    tags = []
    class_name = None
    fn_name = name
    if "." in name:
        class_name, fn_name = name.split(".", 1)
    if success_patterns:
        for p in success_patterns:
            tags.append(BodhiTag(tag="log.success", value=p, line_number=0))
    if error_patterns:
        for p in error_patterns:
            tags.append(BodhiTag(tag="log.error", value=p, line_number=0))
    return FunctionDSL(
        file_path="test.java",
        function_name=fn_name,
        class_name=class_name,
        line_number=1,
        tags=tags,
    )


class TestDebugEngine:
    @pytest.fixture
    def adapter(self):
        return FileLogAdapter(paths=[TEXT_LOG], format="text")

    @pytest.fixture
    def flow(self):
        return Flow(
            name="create_order",
            description="Order creation flow",
            entry_type="http",
            entry_method="POST",
            entry_path="/api/orders",
            trace_key="orderId",
            steps=[
                FlowStep(
                    fn="OrderService.create",
                    intent="Receive request, orchestrate order creation",
                ),
                FlowStep(
                    fn="InventoryService.deduct",
                    intent="Deduct inventory",
                    remote="inventory-service",
                    protocol="grpc",
                ),
                FlowStep(
                    fn="PaymentService.hold",
                    intent="Hold payment",
                    remote="payment-service",
                    protocol="http",
                    on_fail=["payment_timeout → circuit_breaker → reject 503"],
                ),
                FlowStep(
                    fn="EventPublisher.publish",
                    intent="Publish order_created event",
                    emits=["order_created"],
                ),
            ],
        )

    @pytest.fixture
    def functions(self):
        return {
            "OrderService.create": _make_function_dsl(
                "OrderService.create",
                success_patterns=["Order {orderId} created successfully"],
                error_patterns=["Order creation failed for user {userId}: {reason}"],
            ),
            "InventoryService.deduct": _make_function_dsl(
                "InventoryService.deduct",
                success_patterns=["Inventory deducted for product {productId}"],
                error_patterns=["Insufficient inventory for {productId}"],
            ),
            "PaymentService.hold": _make_function_dsl(
                "PaymentService.hold",
                success_patterns=["Payment held: {transactionId}"],
                error_patterns=["Payment failed for order {orderId}: {reason}"],
            ),
            "EventPublisher.publish": _make_function_dsl(
                "EventPublisher.publish",
                success_patterns=["Event {eventName} published"],
            ),
        }

    @pytest.fixture
    def engine(self, adapter, flow, functions):
        return DebugEngine(
            adapter=adapter,
            flows={"create_order": flow},
            functions=functions,
        )

    def test_debug_flow_basic(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert report.flow == "create_order"
        assert report.trace_key == "orderId"
        assert report.trace_value == "12345"
        assert len(report.steps) == 4

    def test_step_success(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # OrderService.create should be SUCCESS (log matches success pattern)
        assert report.steps[0].fn == "OrderService.create"
        assert report.steps[0].status == StepStatus.SUCCESS

    def test_step_success_inventory(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # InventoryService.deduct should be SUCCESS
        assert report.steps[1].fn == "InventoryService.deduct"
        assert report.steps[1].status == StepStatus.SUCCESS

    def test_step_failed(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # PaymentService.hold should be FAILED (error pattern matches)
        assert report.steps[2].fn == "PaymentService.hold"
        assert report.steps[2].status == StepStatus.FAILED
        assert "timeout" in report.steps[2].log

    def test_step_no_evidence(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # EventPublisher.publish should be NO_EVIDENCE
        assert report.steps[3].fn == "EventPublisher.publish"
        assert report.steps[3].status == StepStatus.NO_EVIDENCE

    def test_break_point(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert report.break_point == "PaymentService.hold"

    def test_consequences(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert len(report.consequences) > 0
        # Should mention unpublished events
        assert any("order_created" in c for c in report.consequences)

    def test_suggestions_remote(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert any("payment-service" in s for s in report.suggested_actions)

    def test_remote_note(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # InventoryService.deduct should have remote note
        assert "inventory-service" in report.steps[1].note
        assert "grpc" in report.steps[1].note

    def test_error_handling_on_failed_step(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # PaymentService.hold should have error_handling populated
        assert report.steps[2].error_handling is not None
        assert "circuit_breaker" in report.steps[2].error_handling

    def test_flow_not_found(self, engine):
        report = engine.debug_flow(
            flow_name="nonexistent",
            trace_value="12345",
        )
        assert "not found" in report.consequences[0]

    def test_to_dict(self, engine):
        report = engine.debug_flow(
            flow_name="create_order",
            trace_value="12345",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        d = report.to_dict()
        assert d["flow"] == "create_order"
        assert d["trace_key"] == "orderId"
        assert len(d["steps"]) == 4
        assert d["steps"][0]["status"] == "SUCCESS"
        assert d["break_point"] == "PaymentService.hold"


# -- search_logs --

class TestSearchLogs:
    @pytest.fixture
    def engine(self):
        adapter = FileLogAdapter(paths=[TEXT_LOG], format="text")
        flow = Flow(
            name="create_order",
            description="test",
            entry_type="http",
            entry_method="POST",
            entry_path="/api/orders",
            steps=[
                FlowStep(fn="OrderService.create", intent="create"),
                FlowStep(fn="InventoryService.deduct", intent="deduct"),
            ],
        )
        functions = {
            "OrderService.create": _make_function_dsl("OrderService.create"),
        }
        return DebugEngine(
            adapter=adapter,
            flows={"create_order": flow},
            functions=functions,
        )

    def test_search_by_fn(self, engine):
        results = engine.search_logs(
            fn="OrderService.create",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert len(results) >= 1
        assert all("OrderService.create" in r["message"] for r in results)

    def test_search_by_flow(self, engine):
        results = engine.search_logs(
            flow="create_order",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert len(results) >= 1

    def test_search_by_level(self, engine):
        results = engine.search_logs(
            level="ERROR",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        assert all(r["level"] == "ERROR" for r in results)

    def test_annotated_with_fn(self, engine):
        results = engine.search_logs(
            fn="OrderService.create",
            time_from=datetime(2026, 4, 2, 10, 0, 0),
            time_to=datetime(2026, 4, 2, 11, 0, 0),
        )
        # Results that match a known function should be annotated
        for r in results:
            if "OrderService.create" in r["message"]:
                assert r.get("fn") == "OrderService.create"


# -- Runtime config parsing --

class TestRuntimeConfigParsing:
    def test_parse_runtime_config(self):
        data = {
            "version": "0.1.0",
            "project": {"name": "test"},
            "runtime": {
                "logs": [
                    {
                        "name": "app-log",
                        "type": "file",
                        "path": "/var/log/app.log",
                        "format": "json",
                        "timestamp_field": "@timestamp",
                        "message_field": "msg",
                    },
                ],
                "time_window": "60s",
                "default_trace_field": "traceId",
            },
        }
        meta = parse_project_meta(data)
        assert meta.runtime is not None
        assert len(meta.runtime.logs) == 1
        assert meta.runtime.logs[0].name == "app-log"
        assert meta.runtime.logs[0].type == "file"
        assert meta.runtime.logs[0].path == "/var/log/app.log"
        assert meta.runtime.logs[0].format == "json"
        assert meta.runtime.time_window == "60s"
        assert meta.runtime.default_trace_field == "traceId"

    def test_no_runtime_config(self):
        data = {
            "version": "0.1.0",
            "project": {"name": "test"},
        }
        meta = parse_project_meta(data)
        assert meta.runtime is None

    def test_flow_trace_key(self):
        data = {
            "name": "test_flow",
            "description": "test",
            "trace_key": "orderId",
            "entry": {"type": "http", "method": "POST", "path": "/test"},
            "steps": [],
        }
        flow = parse_flow(data)
        assert flow.trace_key == "orderId"

    def test_flow_no_trace_key(self):
        data = {
            "name": "test_flow",
            "description": "test",
            "entry": {"type": "http", "method": "POST", "path": "/test"},
            "steps": [],
        }
        flow = parse_flow(data)
        assert flow.trace_key is None
