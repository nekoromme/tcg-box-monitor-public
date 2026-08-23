from __future__ import annotations

from pathlib import Path

from tcg_monitor.public_safety import scan_repository, scan_text


def test_public_safety_detects_credentials_without_echoing_values() -> None:
    secret_text = "\n".join(
        (
            "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/"
            + "1234567890/abcdefghijklmnopqrstuvwxyz012345",
            "private_key=-----BEGIN " + "PRIVATE KEY-----",
            "contact=personal.user" + "@" + "real-mail.invalid",
            "phone=090" + "-1234-5678",
        )
    )

    findings = scan_text(Path("unsafe.env"), secret_text)

    assert {finding.label for finding in findings} == {
        "Discord Webhook URL",
        "private key",
        "non-example email",
        "Japanese mobile phone number",
    }
    assert all("abcdefghijklmnopqrstuvwxyz" not in repr(finding) for finding in findings)


def test_public_safety_allows_placeholders_and_public_repository_url() -> None:
    safe_text = "\n".join(
        (
            "DISCORD_WEBHOOK_URL=",
            "GOOGLE_SERVICE_ACCOUNT_JSON=",
            "GOOGLE_CALENDAR_ID=calendar@example.com",
            "MONITOR_USER_AGENT_CONTACT=https://github.com/OWNER/REPOSITORY",
            "bot=41898282+github-actions[bot]@users.noreply.github.com",
        )
    )

    assert scan_text(Path(".env.example"), safe_text) == []


def test_current_repository_is_public_safe() -> None:
    assert scan_repository(Path.cwd()) == []


def test_public_safety_detects_legacy_account_identity() -> None:
    findings = scan_text(Path("README.md"), "former-owner=" + "neko" + "pone")

    assert [finding.label for finding in findings] == ["legacy account identity"]
