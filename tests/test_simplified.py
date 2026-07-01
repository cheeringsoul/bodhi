"""Tests for the simplified (data-centric) Mermaid generator."""

from pathlib import Path

from bodhi_engine.parser import load_bodhi_dir
from bodhi_engine.cli.simplified import flows_to_simple_mermaid


FIXTURES = Path(__file__).parent / "fixtures"


def _mermaid() -> str:
    dsl = load_bodhi_dir(FIXTURES / ".bodhi")
    return flows_to_simple_mermaid(dsl["flows"], dsl["entities"])


class TestSimplifiedGraph:
    def test_uses_left_right_layout(self):
        assert _mermaid().splitlines()[0] == "graph LR"

    def test_entry_node_present(self):
        m = _mermaid()
        assert 'e_create_order(["POST /api/orders"])' in m

    def test_collapses_internal_calls(self):
        # The detailed graph would emit handler/service function nodes; the
        # simplified one must not — only entry + data/event/external nodes.
        m = _mermaid()
        assert "OrderService" not in m
        assert "InventoryService" not in m

    def test_links_entry_to_tables(self):
        m = _mermaid()
        assert "db_orders" in m
        assert "-->|write| db_orders" in m
        assert "-.->|read| e_create_order" in m

    def test_links_to_external_service(self):
        m = _mermaid()
        assert 'x_inventory_service[["inventory-service"]]' in m
        assert "==>|calls| x_inventory_service" in m

    def test_excludes_request_response_pseudo_targets(self):
        m = _mermaid()
        assert "db_request" not in m
        assert "db_response" not in m

    def test_no_raw_newline_in_labels(self):
        # A literal newline inside a quoted label breaks Mermaid parsing.
        for line in _mermaid().splitlines():
            if '"' in line:
                assert line.count('"') % 2 == 0

    def test_empty_flows(self):
        m = flows_to_simple_mermaid([], [])
        assert m.startswith("graph LR")
        # No nodes or edges, only the header and classDef declarations.
        assert "-->" not in m and "-.->" not in m and "==>" not in m
        assert "class " not in m  # no `class <id> ...Style` assignment lines
