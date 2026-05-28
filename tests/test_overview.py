"""Tests for `bodhi overview` terminal visualization."""

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from bodhi_engine.cli import overview


FIXTURES = Path(__file__).parent / "fixtures"


def _capture_overview(project_root: Path) -> str:
    buf = StringIO()
    overview.console = Console(file=buf, force_terminal=False, width=140)
    try:
        overview.cmd_overview(project_root)
    finally:
        overview.console = Console()
    return buf.getvalue()


class TestOverviewOutput:
    def test_renders_header_with_counts(self):
        out = _capture_overview(FIXTURES)
        assert "Project Overview" in out
        assert "flows" in out and "entities" in out

    def test_renders_entry_points_from_services(self):
        out = _capture_overview(FIXTURES)
        assert "Entry Points" in out
        assert "POST /api/orders" in out
        assert "OrderService/CreateOrder" in out  # grpc
        assert "channel:order_status_ws" in out   # ws

    def test_renders_flow_names(self):
        out = _capture_overview(FIXTURES)
        assert "Flows" in out
        assert "create_order" in out

    def test_renders_storage_grouped_by_datasource(self):
        out = _capture_overview(FIXTURES)
        assert "Storage" in out
        assert "orders" in out

    def test_renders_events_grouped_by_channel(self):
        out = _capture_overview(FIXTURES)
        assert "Events" in out
        assert "order_created" in out

    def test_renders_externals_excluding_known_services(self):
        out = _capture_overview(FIXTURES)
        assert "Externals" in out
        assert "payment-service" in out


class TestOverviewErrors:
    def test_missing_bodhi_dir(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            _capture_overview(tmp_path)
        assert exc.value.code == 1

    def test_empty_bodhi_dir(self, tmp_path):
        (tmp_path / ".bodhi").mkdir()
        with pytest.raises(SystemExit) as exc:
            _capture_overview(tmp_path)
        assert exc.value.code == 1

    def test_malformed_yaml_renders_warning_and_partial(self, tmp_path):
        """Broken YAML in one file shouldn't crash the command."""
        flows_dir = tmp_path / ".bodhi" / "flows"
        flows_dir.mkdir(parents=True)
        # broken file
        (flows_dir / "broken.yaml").write_text(
            "name: broken\nsteps:\n  - fn: foo\n  ? bad\n"
        )
        # good file
        (flows_dir / "good.yaml").write_text(
            "name: good_flow\ndescription: ok\n"
            "entry:\n  type: http\n  method: GET\n  path: /api/x\n"
            "steps:\n  - fn: Handler.x\n    intent: x\n"
        )
        out = _capture_overview(tmp_path)
        assert "failed to parse" in out
        assert "broken.yaml" in out
        # Good flow should still render
        assert "good_flow" in out
