from pathlib import Path


def test_monitor_workflow_is_manual_only_during_migration_and_ocr_ready() -> None:
    workflow = Path(".github/workflows/monitor.yml").read_text(encoding="utf-8")

    # 公開リポジトリへの移行中は、旧リポジトリとの二重実行を避けるため
    # 手動実行だけを許可する。Secretsと状態リポジトリ接続の確認後に、
    # このテストとworkflowを一緒に定期実行向けへ戻す。
    assert "  schedule:" not in workflow
    assert "  push:" not in workflow
    assert "workflow_dispatch:" in workflow
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
