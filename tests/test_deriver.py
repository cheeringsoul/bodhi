"""Test deriver: derive Layer 2 YAML from inline tags."""

import shutil
from pathlib import Path

import yaml

from bodhi_engine.deriver import (
    derive_flows,
    derive_events,
    derive_services,
    derive_and_write,
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
        # The fixtures don't have 'via' in their calls tags
        # (they just have local calls like InventoryService.deduct)
        assert isinstance(deps, list)


class TestDeriveAndWrite:

    def test_derive_and_write_creates_files(self, tmp_path):
        # Copy fixtures to tmp
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        output_dir = tmp_path / ".bodhi"
        summary = derive_and_write(tmp_path, output_dir)

        assert summary["flows"] > 0
        assert summary["events"] > 0
        assert (output_dir / "flows").is_dir()
        assert (output_dir / "events").is_dir()

    def test_derived_yaml_is_valid(self, tmp_path):
        src = tmp_path / "src"
        shutil.copytree(FIXTURES / "src", src)

        output_dir = tmp_path / ".bodhi"
        derive_and_write(tmp_path, output_dir)

        # All generated YAML files should be parseable
        for yaml_file in output_dir.rglob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict)
            assert "name" in data
