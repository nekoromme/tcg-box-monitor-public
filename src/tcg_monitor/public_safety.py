from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 仮想環境やテストキャッシュは公開対象ではなく、依存ライブラリ内の例示用鍵などが
# 大量に含まれることもある。リポジトリ自身が管理するテキストだけを検査する。
SKIP_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
MAX_TEXT_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    label: str


# 値そのものは検査結果へ出さない。もし本物が混入していても、Actionsログへ
# もう一度コピーしてしまわないための設計。
SECRET_RULES = (
    Rule(
        "Discord Webhook URL",
        re.compile(
            r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/"
            r"api/webhooks/\d+/[A-Za-z0-9_-]{20,}",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    Rule(
        "GitHub token",
        re.compile(r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})"),
    ),
    Rule("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    Rule("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    Rule("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{20,}")),
    Rule(
        "literal credential assignment",
        re.compile(
            r"\b(?:password|passwd|client_secret|api_key|access_token|refresh_token)"
            r"\s*[:=]\s*[\"'][^\"'\s${}]{8,}[\"']",
            re.IGNORECASE,
        ),
    ),
)

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}))"
)
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.test",
    "users.noreply.github.com",
}
MOBILE_PHONE_PATTERN = re.compile(r"(?<!\d)0[5789]0[- ]?\d{4}[- ]?\d{4}(?!\d)")
POSTAL_CODE_PATTERN = re.compile(r"〒\s*\d{3}-\d{4}")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for rule in SECRET_RULES:
        for match in rule.pattern.finditer(text):
            findings.append(Finding(path, _line_number(text, match.start()), rule.label))

    for match in EMAIL_PATTERN.finditer(text):
        domain = match.group(2).lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            findings.append(
                Finding(path, _line_number(text, match.start()), "non-example email")
            )

    for label, pattern in (
        ("Japanese mobile phone number", MOBILE_PHONE_PATTERN),
        ("Japanese postal code", POSTAL_CODE_PATTERN),
    ):
        for match in pattern.finditer(text):
            findings.append(Finding(path, _line_number(text, match.start()), label))
    return findings


def iter_repository_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRECTORIES for part in relative_parts):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        files.append(path)
    return sorted(files)


def scan_repository(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_repository_text_files(root):
        try:
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(path.relative_to(root), text))
    return findings


def main() -> int:
    root = Path.cwd()
    findings = scan_repository(root)
    if not findings:
        print("public-safety check: OK")
        return 0

    print("公開できない可能性がある値を検出しました。値そのものは安全のため表示しません。")
    for finding in findings:
        print(f"- {finding.path}:{finding.line}: {finding.label}")
    return 1
