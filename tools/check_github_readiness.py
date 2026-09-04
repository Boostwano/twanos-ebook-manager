"""Fail safely when local-only or sensitive files could enter GitHub."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    ".gitattributes",
    ".github/dependabot.yml",
    ".github/workflows/tests.yml",
    ".gitignore",
    "LICENSE.md",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
}
FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    ".pytest-runtime",
    ".pytest-runtime-cache",
    ".pytest-runtime-tmp",
    ".runtime-smoke",
    ".test-temp",
    ".venv",
    "__pycache__",
    "build",
    "build-output",
    "dist",
    "htmlcov",
    "zip",
}
FORBIDDEN_SUFFIXES = {
    ".azw",
    ".azw3",
    ".cbr",
    ".cbz",
    ".db",
    ".env",
    ".epub",
    ".key",
    ".log",
    ".mobi",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".zip",
}
FORBIDDEN_NAMES = {
    "credentials.json",
    "plugin-state.json",
    "provider-health.json",
}
SECRET_PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "GitHub token": re.compile(
        rb"(?:gh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,})"
    ),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}
MAX_FILE_BYTES = 10 * 1024 * 1024


def _git_candidates() -> tuple[Path, ...]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        PROJECT_ROOT / line
        for line in result.stdout.splitlines()
        if line.strip()
    )


def _is_generated_runtime_part(part: str) -> bool:
    lowered = part.casefold()
    return (
        lowered in FORBIDDEN_PARTS
        or lowered.startswith(".pytest-runtime")
        or lowered.startswith(".env")
        or lowered.startswith(".test-temp")
        or lowered.startswith("test-runtime-")
    )


def audit() -> tuple[str, ...]:
    """Return publication blockers without changing repository state."""
    blockers: list[str] = []
    candidates = _git_candidates()
    relative_candidates = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in candidates
    }

    for required in sorted(REQUIRED_FILES):
        if required not in relative_candidates:
            blockers.append(f"Required publication file is missing: {required}")

    for path in candidates:
        relative = path.relative_to(PROJECT_ROOT)
        parts = tuple(part.casefold() for part in relative.parts)
        suffix = path.suffix.casefold()
        if any(_is_generated_runtime_part(part) for part in parts):
            blockers.append(f"Local/generated path is publishable: {relative}")
            continue
        if path.name.casefold() in FORBIDDEN_NAMES:
            blockers.append(f"Credential/state file is publishable: {relative}")
            continue
        if suffix in FORBIDDEN_SUFFIXES:
            blockers.append(f"Forbidden file type is publishable: {relative}")
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            blockers.append(
                f"File exceeds the 10 MiB source limit: {relative}"
            )
            continue
        try:
            content = path.read_bytes()
        except OSError as error:
            blockers.append(f"Could not inspect {relative}: {error}")
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                blockers.append(f"Possible {label} in {relative}")

    config = PROJECT_ROOT / "src" / "config.py"
    readme = PROJECT_ROOT / "README.md"
    if config.is_file() and "R4 RC1" not in config.read_text(
        encoding="utf-8"
    ):
        blockers.append("src/config.py is not aligned to R4 RC1.")
    if readme.is_file() and "R4 RC1" not in readme.read_text(
        encoding="utf-8"
    ):
        blockers.append("README.md is not aligned to R4 RC1.")

    return tuple(dict.fromkeys(blockers))


def main() -> int:
    blockers = audit()
    if blockers:
        print("GitHub publication audit failed:")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    print("GitHub publication audit passed.")
    print(
        "Generated data, ebook files, release ZIPs, downloaded plugins, "
        "private keys, and recognised credential formats are excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
