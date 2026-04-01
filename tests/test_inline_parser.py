"""Test inline @bodhi.* tag parser."""

from pathlib import Path
from bodhi_engine.parser.inline import parse_file, parse_directory

FIXTURES = Path(__file__).parent / "fixtures"


class TestJavaParser:

    def test_parse_java_file(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        # Should find create, cancel, logAction (3 functions with tags)
        # getName has no tags, should be skipped
        assert len(functions) == 3

    def test_function_names(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        names = [f.function_name for f in functions]
        assert "create" in names
        assert "cancel" in names
        assert "logAction" in names
        assert "getName" not in names

    def test_class_context(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        for fn in functions:
            assert fn.class_name == "OrderService"

    def test_qualified_name(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        names = [f.qualified_name for f in functions]
        assert "OrderService.create" in names
        assert "OrderService.cancel" in names

    def test_intent(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert create.intent == "Create order, deduct inventory, publish domain event"

    def test_reads(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert "request.body(userId, items, address)" in create.reads

    def test_writes(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert any("orders" in w for w in create.writes)

    def test_calls(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert "InventoryService.deduct" in create.calls
        assert "PaymentService.hold" in create.calls

    def test_emits(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert any("order_created" in e for e in create.emits)

    def test_on_fail(self):
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        create = next(f for f in functions if f.function_name == "create")
        assert len(create.on_fail) == 2
        assert any("inventory_insufficient" in f for f in create.on_fail)
        assert any("payment_timeout" in f for f in create.on_fail)

    def test_missing_intent(self):
        """logAction has writes but no intent."""
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        log_fn = next(f for f in functions if f.function_name == "logAction")
        assert log_fn.intent is None
        assert len(log_fn.writes) > 0


class TestPythonParser:

    def test_parse_python_file(self):
        functions = parse_file(FIXTURES / "src" / "order_service.py")
        assert len(functions) == 2

    def test_python_intent(self):
        functions = parse_file(FIXTURES / "src" / "order_service.py")
        create = next(f for f in functions if f.function_name == "create_order")
        assert create.intent == "Create order"

    def test_python_calls(self):
        functions = parse_file(FIXTURES / "src" / "order_service.py")
        create = next(f for f in functions if f.function_name == "create_order")
        assert "PaymentService.charge" in create.calls


class TestConsumesParser:

    def test_parse_consumer_file(self):
        functions = parse_file(FIXTURES / "src" / "NotificationHandler.java")
        assert len(functions) == 2

    def test_consumes_tag(self):
        functions = parse_file(FIXTURES / "src" / "NotificationHandler.java")
        handler = next(f for f in functions if f.function_name == "onOrderCreated")
        assert len(handler.consumes) == 1
        assert "order_created" in handler.consumes[0]
        assert "kafka:order-events" in handler.consumes[0]

    def test_consumes_with_intent(self):
        functions = parse_file(FIXTURES / "src" / "NotificationHandler.java")
        handler = next(f for f in functions if f.function_name == "onOrderCreated")
        assert handler.intent is not None

    def test_multiple_consumers(self):
        functions = parse_file(FIXTURES / "src" / "NotificationHandler.java")
        names = [f.function_name for f in functions]
        assert "onOrderCreated" in names
        assert "onPaymentCompleted" in names


class TestImplementsParser:

    def test_parse_implements_tag(self):
        functions = parse_file(FIXTURES / "src" / "OrderServiceImpl.java")
        # Both create and cancel inherit @bodhi.implements from class
        assert len(functions) == 2

    def test_implements_value(self):
        functions = parse_file(FIXTURES / "src" / "OrderServiceImpl.java")
        for fn in functions:
            assert fn.implements == "OrderService"
            assert fn.class_name == "OrderServiceImpl"

    def test_implements_no_intent(self):
        """Impl class only has @bodhi.implements, no @bodhi.intent."""
        functions = parse_file(FIXTURES / "src" / "OrderServiceImpl.java")
        for fn in functions:
            assert fn.intent is None

    def test_no_implements_on_interface(self):
        """Interface class should not have @bodhi.implements."""
        functions = parse_file(FIXTURES / "src" / "OrderService.java")
        for fn in functions:
            assert fn.implements is None


class TestDirectoryParser:

    def test_parse_directory(self):
        functions = parse_directory(FIXTURES / "src")
        # 3 from OrderService.java + 2 from OrderServiceImpl.java
        # + 2 from NotificationHandler.java + 2 from Python = 9
        assert len(functions) == 9

    def test_skips_non_source_files(self):
        # Should not crash on non-source files in directory
        functions = parse_directory(FIXTURES)
        assert len(functions) >= 7
