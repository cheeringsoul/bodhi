"""Tests for workspace loading, merging, and cross-service validation."""

import pytest
from pathlib import Path

from bodhi_engine.workspace import load_workspace, WorkspaceResult, IssueSeverity


WORKSPACE = Path(__file__).parent / "fixtures" / "workspace"


@pytest.fixture
def ws() -> WorkspaceResult:
    return load_workspace(WORKSPACE)


# -- loading --

class TestWorkspaceLoading:
    def test_discovers_services(self, ws):
        assert "order-service" in ws.service_data
        assert "payment-service" in ws.service_data

    def test_service_count(self, ws):
        assert len(ws.service_data) == 2

    def test_service_name_from_distributed_meta(self, ws):
        # Name should come from distributed.service, not directory name
        assert "order-service" in ws.service_data

    def test_service_path(self, ws):
        sd = ws.service_data["order-service"]
        assert sd.path.name == "order-service"

    def test_service_flows(self, ws):
        sd = ws.service_data["order-service"]
        assert len(sd.flows) == 1
        assert sd.flows[0].name == "create_order"

    def test_service_events(self, ws):
        sd = ws.service_data["payment-service"]
        assert len(sd.events) == 2  # order_created + payment_completed


# -- merging --

class TestWorkspaceMerge:
    def test_all_flows_namespaced(self, ws):
        assert "order-service:create_order" in ws.all_flows
        assert "payment-service:hold_payment" in ws.all_flows

    def test_events_merged(self, ws):
        # order_created should be merged from both services
        assert "order_created" in ws.all_events
        evt = ws.all_events["order_created"]
        assert len(evt.producers) >= 1  # from order-service
        assert len(evt.consumers) >= 1  # from payment-service

    def test_event_producers_merged(self, ws):
        evt = ws.all_events["order_created"]
        producer_fns = [p.fn for p in evt.producers]
        assert "OrderService.create" in producer_fns

    def test_event_consumers_merged(self, ws):
        evt = ws.all_events["order_created"]
        consumer_fns = [c.fn for c in evt.consumers]
        assert "PaymentHandler.onOrderCreated" in consumer_fns

    def test_payment_completed_only_producer(self, ws):
        evt = ws.all_events["payment_completed"]
        assert len(evt.producers) >= 1
        assert len(evt.consumers) == 0  # no consumer defined

    def test_all_services(self, ws):
        assert "order-service" in ws.all_services
        assert "payment-service" in ws.all_services

    def test_all_entities_namespaced(self, ws):
        assert "order-service:orders" in ws.all_entities

    def test_all_states_empty(self, ws):
        # No state machines in fixtures
        assert len(ws.all_states) == 0


# -- cross-service validation --

class TestWorkspaceValidation:
    def test_detects_event_schema_mismatch(self, ws):
        # order-service has userId, payment-service has buyerId
        schema_issues = [i for i in ws.issues if i.code == "event-schema-mismatch"]
        assert len(schema_issues) >= 1
        issue = schema_issues[0]
        assert "order_created" in issue.message
        assert issue.severity == IssueSeverity.ERROR

    def test_detects_broken_flow_ref(self, ws):
        # order-service references payment-service:hold_payment which exists
        broken_refs = [i for i in ws.issues if i.code == "broken-flow-ref"]
        # flow_ref "payment-service:hold_payment" should resolve
        assert len(broken_refs) == 0

    def test_detects_event_no_consumer(self, ws):
        # payment_completed has producer but no consumer
        no_consumer = [i for i in ws.issues if i.code == "event-no-consumer"]
        assert len(no_consumer) >= 1
        assert any("payment_completed" in i.message for i in no_consumer)

    def test_unknown_dependency_kafka(self, ws):
        # Both services depend on kafka which is not a service in workspace
        unknown_deps = [i for i in ws.issues if i.code == "unknown-dependency"]
        assert len(unknown_deps) >= 1
        assert any("kafka" in i.message for i in unknown_deps)

    def test_has_errors(self, ws):
        # Schema mismatch is an error
        assert ws.has_errors()

    def test_format_issues(self, ws):
        output = ws.format_issues()
        assert "Errors" in output
        assert "event-schema-mismatch" in output


# -- empty workspace --

class TestEmptyWorkspace:
    def test_empty_dir(self, tmp_path):
        ws = load_workspace(tmp_path)
        assert len(ws.service_data) == 0
        assert len(ws.issues) == 1
        assert ws.issues[0].code == "empty-workspace"
