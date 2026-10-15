from fastapi import Response
from app import main


def test_reports_and_downloads_are_not_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'RESULTS_DIR',tmp_path)
    (tmp_path/'TEST_health_report.md').write_text('报告版本：evidence-report-v2')
    response=Response()
    assert main.reports(response)['count']==1
    assert response.headers['cache-control'].startswith('no-store')
    artifact=main.report_file('TEST','markdown')
    assert artifact.headers['cache-control'].startswith('no-store')


def test_figure_response_is_not_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'RESULTS_DIR',tmp_path)
    (tmp_path/'figures').mkdir()
    (tmp_path/'figures'/'TEST_species.png').write_bytes(b'test')
    assert main.report_figure('TEST','TEST_species.png').headers['cache-control'].startswith('no-store')
