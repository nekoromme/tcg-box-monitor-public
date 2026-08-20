from pathlib import Path


def test_monitor_workflow_installs_and_verifies_tesseract_cli() -> None:
    workflow = Path(".github/workflows/monitor.yml").read_text(encoding="utf-8")

    assert "cron: '4 2,7,9,11,13,21 * * *'" in workflow
    assert "tesseract-ocr tesseract-ocr-jpn" in workflow
    assert "command -v tesseract" in workflow
    assert "tesseract --list-langs | grep -Fx jpn" in workflow


def test_fast_opportunity_workflow_is_scoped_and_ocr_ready() -> None:
    workflow = Path(".github/workflows/fast-opportunity-monitor.yml").read_text(
        encoding="utf-8"
    )

    assert "  schedule:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "python -m pip install -e ." in workflow
    assert "python -m playwright install" not in workflow
    assert "tesseract-ocr-jpn" in workflow
    assert "--source furuichi_official_lottery" in workflow
    assert "--source yahoo_realtime_furuichi" in workflow
    assert "--source yahoo_realtime_amazon_onepiece_secondary" not in workflow
    assert "--source yahoo_realtime_amazon_gamegetnavi_secondary" not in workflow
    assert "--source snkrdunk_onepiece" in workflow
    assert "group: monitor-state" in workflow
