"""Tests for `bodhi arch` terminal visualization."""

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from bodhi_engine.cli import arch


FIXTURES = Path(__file__).parent / "fixtures"


def _capture_arch(project_root: Path) -> str:
    buf = StringIO()
    arch.console = Console(file=buf, force_terminal=False, width=120)
    try:
        arch.cmd_arch(project_root)
    finally:
        # Reset module-level console to avoid leaking into other tests.
        arch.console = Console()
    return buf.getvalue()


class TestArchOutput:
    def test_renders_service_panel(self):
        out = _capture_arch(FIXTURES)
        assert "Bodhi Service Architecture" in out
        assert "order-service" in out
        assert "spring-boot" in out

    def test_renders_apis(self):
        out = _capture_arch(FIXTURES)
        # http API line
        assert "POST /api/orders" in out
        # grpc API line uses service/method
        assert "OrderService/CreateOrder" in out

    def test_renders_dependencies(self):
        out = _capture_arch(FIXTURES)
        assert "payment-service" in out
        assert "inventory-service" in out
        # kafka topic from depends_on
        assert "order-events" in out

    def test_renders_topology_edges(self):
        out = _capture_arch(FIXTURES)
        assert "Topology" in out
        # arrow with protocol
        assert "──http──" in out or "──http " in out
        # all deps appear as externals (only one service in this fixture)
        assert "external" in out


class TestArchErrors:
    def test_no_bodhi_dir(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            _capture_arch(tmp_path)
        assert exc.value.code == 1

    def test_no_services(self, tmp_path):
        (tmp_path / ".bodhi").mkdir()
        with pytest.raises(SystemExit) as exc:
            _capture_arch(tmp_path)
        assert exc.value.code == 1
