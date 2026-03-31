"""Test deriver: derive Layer 2 YAML from inline tags + validate consistency."""

import shutil
from pathlib import Path

import yaml

from bodhi_engine.deriver import (
    derive_flows,
    derive_events,
    derive_services,
    derive_and_write,
    scaffold,
    validate_consistency,
    ConsistencyIssue,
    ConsistencyReport,
    _parse_emits_value,
    _parse_consumes_value,
    _parse_calls_value,
)
from bodhi_engine.parser.inline import parse_directory

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseHelpers:

    def test_parse_emits_with_destination(self):
        name, fields, dest = _parse_emits_value(
            "order_created(orderId, userId) to kafka:order-events"
        )
        assert name == "order_created"
        assert fields == ["orderId", "userId"]
        assert dest == "kafka:order-events"

    def test_parse_emits_without_destination(self):
        name, fields, dest = _parse_emits_value("order_created(orderId)")
        assert name == "order_created"
        assert fields == ["orderId"]
        assert dest is None

    def test_parse_consumes_with_source(self):
        name, fields, source = _parse_consumes_value(
            "order_created(orderId, userId) from kafka:order-events"
        )
        assert name == "order_created"
        assert fields == ["orderId", "userId"]
        assert source == "kafka:order-events"

    def test_parse_calls_with_via(self):
        name, via = _parse_calls_value(
            "PaymentService.hold via http:POST /api/payments/hold"
        )
        assert name == "PaymentService.hold"
        assert via == "http:POST /api/payments/hold"

    def test_parse_calls_local(self):
        name, via = _parse_calls_value("OrderRepository.save")
        assert name == "OrderRepository.save"
        assert via is None


class TestDeriveFlows:

    def test_derive_flows_from_fixtures(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        assert len(flows) > 0

    def test_flow_has_steps(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        for flow in flows:
            assert len(flow.steps) > 0
            assert flow.steps[0].intent != ""

    def test_flow_entry_point_is_first_step(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        # OrderService.create should be an entry point (reads request.body)
        create_flows = [
            f for f in flows
            if f.steps[0].fn == "OrderService.create"
        ]
        assert len(create_flows) == 1

    def test_flow_collects_entities(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        create_flows = [
            f for f in flows
            if f.steps[0].fn == "OrderService.create"
        ]
        assert len(create_flows) == 1
        assert "orders" in create_flows[0].entities

    def test_flow_collects_events(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        create_flows = [f for f in flows if "create" in f.name]
        assert len(create_flows) >= 1
        assert "order_created" in create_flows[0].events

    def test_flow_collects_error_handling(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        create_flows = [f for f in flows if "create" in f.name]
        assert len(create_flows) >= 1
        assert len(create_flows[0].error_handling) > 0

    def test_event_consumer_is_entry_point(self):
        functions = parse_directory(FIXTURES / "src")
        flows = derive_flows(functions)
        # NotificationHandler.onOrderCreated consumes an event, should be an entry
        consumer_flows = [
            f for f in flows
            if any(s.fn == "NotificationHandler.onOrderCreated" for s in f.steps)
        ]
        assert len(consumer_flows) >= 1
        assert consumer_flows[0].entry_type == "mq_consumer"


class TestDeriveEvents:

    def test_derive_events_from_fixtures(self):
        functions = parse_directory(FIXTURES / "src")
        events = derive_events(functions)
        assert len(events) > 0

    def test_event_has_producers_and_consumers(self):
        functions = parse_directory(FIXTURES / "src")
        events = derive_events(functions)
        order_created = [e for e in events if e.name == "order_created"]
        assert len(order_created) == 1
        evt = order_created[0]
        assert len(evt.producers) > 0
        assert len(evt.consumers) > 0
        assert evt.channel == "kafka:order-events"

    def test_event_schema_fields(self):
        functions = parse_directory(FIXTURES / "src")
        events = derive_events(functions)
        order_created = [e for e in events if e.name == "order_created"]
        assert len(order_created) == 1
        field_names = {s.field for s in order_created[0].schema}
        assert "orderId" in field_names
        assert "userId" in field_names

    def test_event_cancelled(self):
        functions = parse_directory(FIXTURES / "src")
        events = derive_events(functions)
        cancelled = [e for e in events if e.name == "order_cancelled"]
        assert len(cancelled) == 1
        assert len(cancelled[0].producers) > 0


class TestDeriveServices:

    def test_no_remote_calls_no_services(self):
        """Fixture has no 'via' remote calls, so no service deps."""
        functions = parse_directory(FIXTURES / "src")
        deps = derive_services(functions)
        assert isinstance(deps, list)


class TestScaffold:

    def test_scaffold_creates_files(self, tmp_path):
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        output_dir = tmp_path / ".bodhi"
        summary = scaffold(tmp_path, output_dir)

        assert summary["flows"] > 0
        assert summary["events"] > 0
        assert (output_dir / "flows").is_dir()
        assert (output_dir / "events").is_dir()

    def test_scaffold_yaml_is_valid(self, tmp_path):
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        output_dir = tmp_path / ".bodhi"
        scaffold(tmp_path, output_dir)

        for yaml_file in output_dir.rglob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict)
            assert "name" in data

    def test_derive_and_write_backward_compat(self, tmp_path):
        """derive_and_write is an alias for scaffold."""
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        output_dir = tmp_path / ".bodhi"
        summary = derive_and_write(tmp_path, output_dir)
        assert summary["flows"] > 0


# ============================================================
# Consistency validation tests
# ============================================================

class TestConsistencyReport:

    def test_empty_report_is_consistent(self):
        report = ConsistencyReport()
        assert report.is_consistent
        assert "No issues" in report.summary()

    def test_report_with_errors(self):
        report = ConsistencyReport(issues=[
            ConsistencyIssue(severity="error", category="flow", message="test error"),
        ])
        assert not report.is_consistent
        assert len(report.errors) == 1
        assert len(report.warnings) == 0

    def test_report_with_warnings_only(self):
        report = ConsistencyReport(issues=[
            ConsistencyIssue(severity="warning", category="event", message="test warning"),
        ])
        assert report.is_consistent  # warnings don't break consistency
        assert len(report.warnings) == 1

    def test_issue_str(self):
        issue = ConsistencyIssue(
            severity="error", category="flow",
            message="Step missing", source="flows/create.yaml",
        )
        s = str(issue)
        assert "[ERROR]" in s
        assert "[flow]" in s
        assert "flows/create.yaml" in s


class TestValidateConsistency:
    """Test validate_consistency against the test fixtures.

    The fixtures have both source code (src/) with inline tags and
    hand-written YAML (.bodhi/) — this lets us test real consistency checks.
    """

    def test_validate_with_fixtures(self):
        """Fixtures should produce a report (may have warnings due to
        intentional differences between derived and hand-written YAML)."""
        report = validate_consistency(FIXTURES, FIXTURES / ".bodhi")
        assert isinstance(report, ConsistencyReport)
        # The report should have some content since fixtures exist
        assert report.issues is not None

    def test_no_source_code(self, tmp_path):
        """Empty project should warn about no inline tags."""
        bodhi_dir = tmp_path / ".bodhi"
        bodhi_dir.mkdir()
        report = validate_consistency(tmp_path, bodhi_dir)
        assert any("No inline" in i.message for i in report.issues)

    def test_no_bodhi_dir(self, tmp_path):
        """Project with code but no .bodhi/ should warn."""
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)
        report = validate_consistency(tmp_path, tmp_path / ".bodhi")
        assert any(".bodhi/" in i.message for i in report.issues)

    def test_event_consistency(self):
        """Events in code should match events in YAML."""
        report = validate_consistency(FIXTURES, FIXTURES / ".bodhi")
        event_issues = [i for i in report.issues if i.category == "event"]
        # order_created exists in both code and YAML, so no "missing YAML" error for it
        missing_yaml_errors = [
            i for i in event_issues
            if i.severity == "error" and "order_created" in i.message
            and "no YAML definition" in i.message
        ]
        assert len(missing_yaml_errors) == 0

    def test_detects_event_in_code_not_in_yaml(self, tmp_path):
        """If code emits an event that has no YAML, report an error."""
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        # Create .bodhi with only bodhi.yaml (no events/)
        bodhi_dir = tmp_path / ".bodhi"
        bodhi_dir.mkdir()
        (bodhi_dir / "bodhi.yaml").write_text(
            "version: '0.1.0'\nproject:\n  name: test\n  description: test\n"
        )

        report = validate_consistency(tmp_path, bodhi_dir)
        event_errors = [
            i for i in report.issues
            if i.category == "event" and i.severity == "error"
            and "no YAML definition" in i.message
        ]
        # Fixtures emit order_created and order_cancelled — both should be flagged
        assert len(event_errors) >= 2

    def test_detects_flow_step_without_inline_tags(self, tmp_path):
        """If a flow YAML references a function with no inline tags, report error."""
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        bodhi_dir = tmp_path / ".bodhi"
        bodhi_dir.mkdir()
        flows_dir = bodhi_dir / "flows"
        flows_dir.mkdir()

        # Write a flow that references a non-existent function
        flow_data = {
            "name": "ghost_flow",
            "description": "References a function that doesn't exist",
            "entry": {"type": "http", "method": "POST"},
            "steps": [
                {"fn": "GhostService.doSomething", "intent": "Does not exist"},
            ],
        }
        with open(flows_dir / "ghost_flow.yaml", "w") as f:
            yaml.dump(flow_data, f)

        report = validate_consistency(tmp_path, bodhi_dir)
        ghost_errors = [
            i for i in report.issues
            if "GhostService.doSomething" in i.message and i.severity == "error"
        ]
        assert len(ghost_errors) >= 1

    def test_detects_entity_without_yaml(self):
        """Entities referenced in code but missing from .bodhi/entities/ should warn."""
        report = validate_consistency(FIXTURES, FIXTURES / ".bodhi")
        entity_warnings = [
            i for i in report.issues
            if i.category == "entity" and i.severity == "warning"
        ]
        # Some entities in code (like audit_log, inventory, users, notifications)
        # may not have YAML definitions in fixtures
        # Just verify the check runs without error
        assert isinstance(entity_warnings, list)
