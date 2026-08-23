from pathlib import Path


def test_monitor_workflow_has_expected_automatic_runs_and_ocr_support() -> None:
    workflow = Path(".github/workflows/monitor.yml").read_text(encoding="utf-8")

    # cronはUTC。日本時間では06:04、11:04、16:04、18:04、20:04、22:04。
    assert "  schedule:" in workflow
    assert "    - cron: '4 2,7,9,11,13,21 * * *'" in workflow
    assert "  push:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "timeout-minutes: 60" in workflow
    assert "tesseract-ocr tesseract-ocr-jpn" in workflow
    assert "command -v tesseract" in workflow
    assert "tesseract --list-langs | grep -Fx jpn" in workflow


def test_monitor_workflow_uses_only_same_repo_plaintext_state() -> None:
    workflow = Path(".github/workflows/monitor.yml").read_text(encoding="utf-8")

    assert "ref: monitor-state" in workflow
    assert "monitor_state.json" in workflow
    assert "monitor_state.json.cms" not in workflow
    assert "private-config.yaml.cms" not in workflow
    assert "MONITOR_DECRYPTION_KEY" not in workflow
    assert "STATE_REPO_TOKEN" not in workflow
    assert "repository:" not in workflow
    assert not Path(".github/workflows/fast-opportunity-monitor.yml").exists()
