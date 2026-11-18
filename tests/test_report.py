from verified_updates.report import render_report


def test_external_diagnostic_text_is_escaped(tmp_path):
    marker = '<script>alert("untrusted diagnostic")</script>'
    destination = tmp_path / "report.html"
    render_report({"cases": [{"scenario": marker, "passed": False, "actual": {"detail": marker}}], "notes": [marker]}, destination)
    html = destination.read_text(encoding="utf-8")
    assert marker not in html
    assert "&lt;script&gt;" in html
    assert "Some outcomes need investigation" in html


def test_report_links_to_original_json_when_output_is_moved(tmp_path):
    destination = tmp_path / "slides" / "evidence.html"
    render_report({}, destination, source=tmp_path / "run #1.json")
    assert 'href="../run%20%231.json"' in destination.read_text(encoding="utf-8")

