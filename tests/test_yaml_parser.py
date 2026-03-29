"""Test .bodhi/ YAML file parser."""

from pathlib import Path
from bodhi_engine.parser.yaml_parser import load_bodhi_dir

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadBodhiDir:

    def setup_method(self):
        self.dsl = load_bodhi_dir(FIXTURES / ".bodhi")

    def test_meta(self):
        assert self.dsl["meta"] is not None
        assert self.dsl["meta"].name == "test-project"
        assert "java" in self.dsl["meta"].languages

    def test_entities(self):
        assert len(self.dsl["entities"]) == 1
        orders = self.dsl["entities"][0]
        assert orders.table == "orders"
        assert orders.description == "核心订单表"
        assert orders.database == "mysql"

    def test_entity_fields(self):
        orders = self.dsl["entities"][0]
        field_names = orders.field_names
        assert "id" in field_names
        assert "status" in field_names
        assert "total_amount" in field_names

    def test_entity_state_machine_field(self):
        orders = self.dsl["entities"][0]
        sm_fields = orders.state_machine_fields
        assert len(sm_fields) == 1
        assert sm_fields[0].name == "status"
        assert sm_fields[0].state_machine == "order_lifecycle"

    def test_entity_enum(self):
        orders = self.dsl["entities"][0]
        status = next(f for f in orders.fields if f.name == "status")
        assert status.enum is not None
        assert status.enum[0] == "INIT"
        assert status.enum[5] == "CANCELLED"

    def test_entity_relations(self):
        orders = self.dsl["entities"][0]
        assert len(orders.relations) == 1
        assert orders.relations[0].target == "order_items"
        assert orders.relations[0].type == "one_to_many"

    def test_flows(self):
        assert len(self.dsl["flows"]) == 1
        flow = self.dsl["flows"][0]
        assert flow.name == "create_order"
        assert flow.entry_method == "POST"
        assert flow.entry_path == "/api/orders"

    def test_flow_steps(self):
        flow = self.dsl["flows"][0]
        assert len(flow.steps) == 3
        assert flow.steps[0].fn == "OrderService.create"
        assert flow.steps[1].fn == "InventoryService.deduct"

    def test_flow_entities(self):
        flow = self.dsl["flows"][0]
        assert "orders" in flow.entities
        assert "inventory" in flow.entities

    def test_states(self):
        assert len(self.dsl["states"]) == 1
        sm = self.dsl["states"][0]
        assert sm.name == "order_lifecycle"
        assert sm.entity == "orders"
        assert sm.field_name == "status"

    def test_state_transitions(self):
        sm = self.dsl["states"][0]
        init = next(s for s in sm.states if s.id == "INIT")
        assert len(init.transitions) == 2
        targets = [t.target for t in init.transitions]
        assert "PAID" in targets
        assert "CANCELLED" in targets

    def test_terminal_states(self):
        sm = self.dsl["states"][0]
        completed = next(s for s in sm.states if s.id == "COMPLETED")
        assert completed.terminal is True

    def test_state_machine_functions(self):
        sm = self.dsl["states"][0]
        fns = sm.all_functions
        assert "PaymentCallback.onSuccess" in fns
        assert "OrderService.cancel" in fns

    def test_events(self):
        assert len(self.dsl["events"]) == 1
        event = self.dsl["events"][0]
        assert event.name == "order_created"
        assert event.channel == "kafka:order-events"

    def test_event_schema(self):
        event = self.dsl["events"][0]
        assert len(event.schema) == 2
        field_names = [f.field for f in event.schema]
        assert "orderId" in field_names
        assert "userId" in field_names

    def test_event_producers(self):
        event = self.dsl["events"][0]
        assert len(event.producers) == 1
        assert event.producers[0].fn == "OrderService.create"

    def test_event_consumers(self):
        event = self.dsl["events"][0]
        assert len(event.consumers) == 1
        assert event.consumers[0].fn == "NotificationHandler.onOrderCreated"

    def test_services(self):
        assert len(self.dsl["services"]) == 1
        svc = self.dsl["services"][0]
        assert svc.name == "order-service"
        assert svc.port == 8080
        assert "spring-boot" in svc.tech_stack

    def test_service_apis(self):
        svc = self.dsl["services"][0]
        assert len(svc.apis) == 2
        assert svc.apis[0].method == "POST"
        assert svc.apis[0].path == "/api/orders"
        assert svc.apis[0].flow == "create_order"

    def test_service_dependencies(self):
        svc = self.dsl["services"][0]
        assert len(svc.depends_on) == 2
        payment_dep = next(d for d in svc.depends_on if d.service == "payment-service")
        assert payment_dep.protocol == "http"
        assert len(payment_dep.apis) == 2
        assert payment_dep.resilience is not None

    def test_service_mq_dependency(self):
        svc = self.dsl["services"][0]
        kafka_dep = next(d for d in svc.depends_on if d.service == "kafka")
        assert kafka_dep.type == "mq"
        assert "order-events" in kafka_dep.topics

    def test_concepts(self):
        assert len(self.dsl["concepts"]) == 1
        concept = self.dsl["concepts"][0]
        assert concept.term == "成交"
        assert "PAID" in concept.related_states
