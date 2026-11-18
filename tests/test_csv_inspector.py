import io

import pytest

from demo_app import csv_inspector


def test_malformed_csv_does_not_silently_drop_extra_fields():
    with pytest.raises(ValueError, match="line 2"):
        csv_inspector.inspect_csv(io.StringIO("name,score\nAlice,91,extra\n"))


def test_nonfinite_columns_are_omitted_from_json_summary(monkeypatch):
    monkeypatch.setattr(csv_inspector, "FEATURE_SUMMARIES", True)
    summary, _ = csv_inspector.inspect_csv(io.StringIO("score,temperature\n91,NaN\n99,42\n"))
    assert summary["numeric_summaries"] == {"score": {"min": 91.0, "max": 99.0, "mean": 95.0}}
