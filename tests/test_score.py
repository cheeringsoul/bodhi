"""Test bodhi score command."""

from pathlib import Path

from bodhi_engine.cli.score import (
    compute_score,
    format_report,
    Dimension,
    ScoreReport,
    TOTAL_MAX,
    DIMENSION_MAX,
    NUM_DIMENSIONS,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestScore:
    def setup_method(self):
        self.report = compute_score(FIXTURES)

    def test_report_shape(self):
        assert isinstance(self.report, ScoreReport)
        assert self.report.max == TOTAL_MAX == 100
        assert len(self.report.dimensions) == NUM_DIMENSIONS == 5
        for d in self.report.dimensions:
            assert 0 <= d.score <= DIMENSION_MAX
            assert d.max == DIMENSION_MAX

    def test_total_equals_sum_of_dimensions(self):
        assert self.report.total == sum(d.score for d in self.report.dimensions)

    def test_dimension_names(self):
        names = [d.name for d in self.report.dimensions]
        assert names == [
            "Intent coverage",
            "Data-flow completeness",
            "Error handling",
            "Call-chain traceability",
            "Structural health",
        ]

    def test_structural_health_penalizes_overloading(self):
        """BatchProcessor fixture has an overloaded process() method, so
        Structural health should NOT be full score."""
        health = next(d for d in self.report.dimensions if d.name == "Structural health")
        assert health.score < DIMENSION_MAX
        assert any("overload" in r.lower() for r in health.reasons)

    def test_reasons_are_populated_when_score_is_not_full(self):
        """Every dimension that lost points should explain why."""
        for d in self.report.dimensions:
            if d.score < d.max:
                assert d.reasons, f"Dimension '{d.name}' lost points but has no reasons"

    def test_format_report_renders(self):
        out = format_report(self.report, color=False)
        assert "Bodhi AI Score:" in out
        assert f"{self.report.total} / {self.report.max}" in out
        for d in self.report.dimensions:
            assert d.name in out

    def test_format_report_no_ansi_when_color_disabled(self):
        out = format_report(self.report, color=False)
        assert "\033[" not in out

    def test_as_dict_is_json_safe(self):
        import json
        data = self.report.as_dict()
        serialized = json.dumps(data)
        assert "total" in serialized
        assert "dimensions" in serialized

    def test_empty_project_full_score(self, tmp_path):
        """A project with no code and no .bodhi/ should not crash and should
        return max score for every dimension (ratio 0/0 → full credit)."""
        report = compute_score(tmp_path)
        assert report.total == TOTAL_MAX
        for d in report.dimensions:
            assert d.score == DIMENSION_MAX
