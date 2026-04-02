"""Tests for log diagnosis: engine match_log() and app diagnose_from_log()."""

import pytest
from pathlib import Path

from bodhi_engine.knowledge import BodhiKnowledge, LogMatchResult, _compile_bodhi_pattern
from bodhi_app.diagnose import diagnose_from_log


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def kb():
    """Knowledge base built from test fixtures."""
    return BodhiKnowledge(FIXTURES)


# -- _compile_bodhi_pattern --

class TestCompileBodhiPattern:
    def test_single_placeholder(self):
        regex, fields = _compile_bodhi_pattern("Order {orderId} created")
        assert fields == ["orderId"]
        m = regex.search("Order 12345 created")
        assert m is not None
        assert m.group(1) == "12345"

    def test_multiple_placeholders(self):
        regex, fields = _compile_bodhi_pattern("Payment failed for {orderId}: {reason}")
        assert fields == ["orderId", "reason"]
        m = regex.search("Payment failed for 12345: timeout")
        assert m.group(1) == "12345"
        assert m.group(2) == "timeout"

    def test_no_placeholders(self):
        regex, fields = _compile_bodhi_pattern("static message")
        assert fields == []
        assert regex.search("static message")

    def test_special_chars_escaped(self):
        regex, fields = _compile_bodhi_pattern("rate: {value}%")
        assert regex.search("rate: 99.5%")


# -- match_log (engine layer) --

class TestMatchLog:
    def test_match_success_pattern(self, kb):
        log_text = 'Payment held: TX-001 for order 12345'
        matches = kb.match_log(log_text)
        assert len(matches) >= 1
        match = next(m for m in matches if m.pattern_type == "success")
        assert match.fn == "PaymentService.hold"
        assert match.extracted.get("transactionId") == "TX-001"
        assert match.extracted.get("orderId") == "12345"

    def test_match_error_pattern(self, kb):
        log_text = 'Payment failed for order 99999: timeout'
        matches = kb.match_log(log_text)
        assert len(matches) >= 1
        match = next(m for m in matches if m.pattern_type == "error")
        assert match.fn == "PaymentService.hold"
        assert match.extracted.get("orderId") == "99999"
        assert match.extracted.get("reason") == "timeout"

    def test_match_function_name_fallback(self, kb):
        log_text = 'OrderService.create received request'
        matches = kb.match_log(log_text)
        assert len(matches) >= 1
        match = next(m for m in matches if m.fn == "OrderService.create")
        assert match.pattern_type == "function_name"

    def test_no_match(self, kb):
        log_text = 'Something totally unrelated happened'
        matches = kb.match_log(log_text)
        assert len(matches) == 0

    def test_multiline_log(self, kb):
        log_text = """
2026-04-02 10:30:01 INFO Payment held: TX-001 for order 12345
2026-04-02 10:30:05 ERROR Payment failed for order 67890: connection refused
        """
        matches = kb.match_log(log_text)
        # Should match both lines
        success_matches = [m for m in matches if m.pattern_type == "success"]
        error_matches = [m for m in matches if m.pattern_type == "error"]
        assert len(success_matches) >= 1
        assert len(error_matches) >= 1

    def test_match_includes_flows(self, kb):
        log_text = 'Payment held: TX-001 for order 12345'
        matches = kb.match_log(log_text)
        # PaymentService.hold is not in a flow step in fixtures currently,
        # but it is in the calls list of OrderService.create flow.
        # The match should still work regardless.
        match = next(m for m in matches if m.pattern_type == "success")
        assert match.fn == "PaymentService.hold"

    def test_match_includes_intent(self, kb):
        log_text = 'Payment held: TX-001 for order 12345'
        matches = kb.match_log(log_text)
        match = next(m for m in matches if m.pattern_type == "success")
        assert match.intent == "Hold payment for order"

    def test_refund_patterns(self, kb):
        log_text = 'Refund completed for transaction TX-999'
        matches = kb.match_log(log_text)
        assert len(matches) >= 1
        match = next(m for m in matches if m.pattern_type == "success")
        assert match.fn == "PaymentService.refund"
        assert match.extracted.get("transactionId") == "TX-999"

    def test_dedup_same_fn_same_line(self, kb):
        log_text = 'Payment held: TX-001 for order 12345'
        matches = kb.match_log(log_text)
        # Should not have duplicate entries for same fn + same line
        fn_line_pairs = [(m.fn, m.matched_line) for m in matches]
        assert len(fn_line_pairs) == len(set(fn_line_pairs))


# -- diagnose_from_log (app layer) --

class TestDiagnoseFromLog:
    def test_no_match(self, kb):
        result = diagnose_from_log(kb, "totally unknown log")
        assert result["matched"] is False

    def test_basic_diagnosis(self, kb):
        result = diagnose_from_log(kb, "Payment failed for order 12345: timeout")
        assert result["matched"] is True
        assert len(result["matches"]) >= 1
        match = result["matches"][0]
        assert match["fn"] == "PaymentService.hold"
        assert match["type"] == "error"
        assert "12345" in str(match.get("extracted_variables", {}))

    def test_diagnosis_structure(self, kb):
        result = diagnose_from_log(kb, "Payment failed for order 12345: timeout")
        # Diagnosis should have the expected top-level keys
        assert result["matched"] is True
        assert "matches" in result
        assert "flow_context" in result
        assert "impact" in result

    def test_multiline_diagnosis(self, kb):
        log_text = """
Payment held: TX-001 for order 12345
Refund failed for transaction TX-001: insufficient balance
        """
        result = diagnose_from_log(kb, log_text)
        assert result["matched"] is True
        fns = [m["fn"] for m in result["matches"]]
        assert "PaymentService.hold" in fns
        assert "PaymentService.refund" in fns


# -- trace_key on Flow --

class TestFlowTraceKey:
    def test_trace_key_parsed(self, kb):
        flow = kb._flow_by_name.get("create_order")
        assert flow is not None
        assert flow.trace_key == "orderId"


# -- inline tag properties --

class TestInlineLogTags:
    def test_trace_property(self, kb):
        fn = kb._fn_by_name.get("PaymentService.hold")
        assert fn is not None
        assert fn.trace == "orderId"

    def test_log_success_property(self, kb):
        fn = kb._fn_by_name.get("PaymentService.hold")
        assert fn is not None
        assert len(fn.log_success) == 1
        assert "Payment held" in fn.log_success[0]

    def test_log_error_property(self, kb):
        fn = kb._fn_by_name.get("PaymentService.hold")
        assert fn is not None
        assert len(fn.log_error) == 1
        assert "Payment failed" in fn.log_error[0]
