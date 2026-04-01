"""Test Bodhi DSL validator."""

from pathlib import Path
from bodhi_engine.validator.checker import validate, Severity

FIXTURES = Path(__file__).parent / "fixtures"


class TestValidator:

    def setup_method(self):
        self.issues = validate(FIXTURES)

    def test_finds_missing_intent(self):
        """logAction has @bodhi.writes but no @bodhi.intent — should be an error."""
        errors = [i for i in self.issues if i.rule == "missing-intent"]
        assert len(errors) >= 1
        assert any("logAction" in i.message for i in errors)

    def test_finds_dangling_calls(self):
        """@bodhi.calls references that don't have their own tags."""
        warnings = [i for i in self.issues if i.rule == "dangling-call"]
        # InventoryService.deduct, PaymentService.hold, InventoryService.rollback, PaymentService.charge
        # are called but don't exist as tagged functions in the fixture
        assert len(warnings) > 0

    def test_finds_missing_entity(self):
        """@bodhi.writes audit_log but audit_log is not in .bodhi/entities/."""
        warnings = [i for i in self.issues if i.rule == "missing-entity"]
        assert any("audit_log" in i.message for i in warnings)

    def test_flow_step_missing_inline(self):
        """Flow references InventoryService.deduct which has no inline tags."""
        warnings = [i for i in self.issues if i.rule == "flow-missing-inline"]
        assert len(warnings) > 0

    def test_writes_no_error_handling(self):
        """OrderRepository.save in flow has writes but no on_fail."""
        warnings = [i for i in self.issues if i.rule == "writes-no-error-handling"]
        assert any("OrderRepository.save" in i.message for i in warnings)

    def test_flow_missing_entity(self):
        """Flow references 'inventory' entity which is not in .bodhi/entities/."""
        errors = [i for i in self.issues if i.rule == "flow-missing-entity"]
        assert any("inventory" in i.message for i in errors)

    def test_transition_fn_not_in_flow(self):
        """State machine transition fns like PaymentCallback.onSuccess are not in any flow."""
        infos = [i for i in self.issues if i.rule == "transition-fn-not-in-flow"]
        assert len(infos) > 0

    def test_consumes_missing_event(self):
        """payment_completed is consumed but not in .bodhi/events/."""
        warnings = [i for i in self.issues if i.rule == "consumes-missing-event"]
        assert any("payment_completed" in i.message for i in warnings)

    def test_emits_event_exists(self):
        """order_created is emitted and IS in .bodhi/events/ — should not warn."""
        warnings = [i for i in self.issues if i.rule == "emits-missing-event"]
        assert not any("order_created" in i.message for i in warnings)

    def test_event_consumer_missing_inline(self):
        """Event catalog consumer NotificationHandler.onOrderCreated should exist (it does)."""
        warnings = [i for i in self.issues if i.rule == "event-consumer-missing-inline"]
        assert not any("NotificationHandler.onOrderCreated" in i.message for i in warnings)

    def test_service_api_missing_flow(self):
        """Service API references 'nonexistent_flow' which does not exist."""
        warnings = [i for i in self.issues if i.rule == "service-api-missing-flow"]
        assert any("nonexistent_flow" in i.message for i in warnings)

    def test_service_api_valid_flow(self):
        """Service API references 'create_order' which exists — should not warn."""
        warnings = [i for i in self.issues if i.rule == "service-api-missing-flow"]
        assert not any("create_order" in i.message for i in warnings)

    def test_severity_levels(self):
        """Should have a mix of error, warning, and info."""
        severities = {i.severity for i in self.issues}
        assert Severity.ERROR in severities
        assert Severity.WARNING in severities

    def test_implements_valid_link(self):
        """OrderServiceImpl declares @bodhi.implements OrderService,
        and OrderService has tags — should NOT warn."""
        warnings = [i for i in self.issues if i.rule == "implements-missing-interface"]
        assert not any("OrderServiceImpl" in i.message for i in warnings)


class TestImplementsValidation:

    def test_implements_missing_interface(self, tmp_path):
        """@bodhi.implements pointing to a class with no tags should warn."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "FooImpl.java").write_text("""
package com.example;

public class FooImpl implements Foo {
    /**
     * @bodhi.implements Foo
     */
    public void doStuff() {}
}
""")
        issues = validate(tmp_path)
        warnings = [i for i in issues if i.rule == "implements-missing-interface"]
        assert len(warnings) == 1
        assert "Foo" in warnings[0].message
