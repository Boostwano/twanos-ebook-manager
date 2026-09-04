"""Build and inspect a source release ZIP from the approved project files."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".gitignore",
    ".gitattributes",
    "ARCHITECTURE.md",
    "build-rc1.bat",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "launcher.bat",
    "LICENSE.md",
    "PROJECT_HANDOVER.md",
    "pytest.ini",
    "README.md",
    "requirements-build.txt",
    "requirements.txt",
    "ROADMAP.md",
    "START_HERE.txt",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "UPLOAD_TO_GITHUB.md",
}
INCLUDED_FOLDERS = {
    "design",
    "docs",
    "prompts",
    "packaging",
    "src",
    "tests",
    "tools",
}
FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    ".pytest-runtime",
    ".pytest-runtime-cache",
    ".pytest-runtime-tmp",
    ".test-temp",
    ".runtime-smoke",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".log",
    ".pyc",
    ".pyd",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".zip",
}
REQUIRED_ENTRIES = {
    "launcher.bat",
    "build-rc1.bat",
    "LICENSE.md",
    "README.md",
    "requirements.txt",
    "requirements-build.txt",
    "docs/R4-Beta2-Automated-Test-Report.md",
    "docs/R4-Beta2-Complete-Testing-Guide.md",
    "docs/RELEASE_NOTES_R4_BETA2.md",
    "docs/R4-RC1-Automated-Test-Report.md",
    "docs/R4-RC1-Testing-Guide.md",
    "docs/RELEASE_NOTES_R4_RC1.md",
    "docs/KNOWN_ISSUES_R4_RC1.md",
    "docs/USER_GUIDE.md",
    "docs/KNOWN_ISSUES_R4_BETA2.md",
    "docs/PRIVACY_AND_DIAGNOSTICS.md",
    "docs/WINDOWS_BUILD_GUIDE.md",
    "docs/approved-plugin-catalog.json",
    "src/app.py",
    "src/services/metadata_studio_service.py",
    "src/services/duplicate_service.py",
    "src/services/library_health_service.py",
    "src/services/plugin_service.py",
    "src/services/scan_service.py",
    "src/ui/metadata_studio.py",
    "src/ui/duplicate_page.py",
    "src/ui/library_health_page.py",
    "src/ui/plugin_page.py",
    "src/ui/scan_page.py",
    "src/workers/source_removal_worker.py",
    "tests/test_complete_preview.py",
    "tools/capture_complete_preview.py",
    "tools/build_windows_app.ps1",
    "tools/windows_version_info.txt",
    "tools/validate_release_zip.py",
    "packaging/Twano.iss",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "tools/check_github_readiness.py",
}
TIMESTAMP_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-")


def timestamped_output_path(output: Path) -> Path:
    """Prefix a sortable local timestamp unless the caller already did."""
    if TIMESTAMP_PREFIX.match(output.name):
        return output
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    return output.with_name(f"{timestamp}-{output.name}")


def release_files() -> tuple[Path, ...]:
    """Return the allowlisted release files in stable archive order."""
    selected: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        if len(relative.parts) == 1:
            if relative.name not in ROOT_FILES:
                continue
        elif relative.parts[0] not in INCLUDED_FOLDERS:
            continue
        selected.append(path)
    return tuple(
        sorted(
            selected,
            key=lambda item: item.relative_to(PROJECT_ROOT).as_posix(),
        )
    )


def inspect_archive(archive_path: Path) -> dict[str, int]:
    """Verify required files, readable entries, and release exclusions."""
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        name_set = set(names)
        missing = sorted(REQUIRED_ENTRIES - name_set)
        if missing:
            raise RuntimeError(
                "Release ZIP is missing required entries: "
                + ", ".join(missing)
            )
        forbidden = [
            name
            for name in names
            if (
                any(part in FORBIDDEN_PARTS for part in Path(name).parts)
                or Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
            )
        ]
        if forbidden:
            raise RuntimeError(
                "Release ZIP contains forbidden entries: "
                + ", ".join(forbidden)
            )
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"Unreadable ZIP entry: {corrupt}")
        banner_count = sum(
            name.startswith("design/banner-sources/")
            and name.lower().endswith(".png")
            for name in names
        )
        if banner_count != 8:
            raise RuntimeError(
                f"Expected 8 banner PNG files, found {banner_count}."
            )
        return {
            "entries": len(names),
            "banner_png_files": banner_count,
            "nested_zip_files": sum(
                name.lower().endswith(".zip")
                for name in names
            ),
        }


def build_archive(
    archive_path: Path,
    *,
    replace: bool,
) -> dict[str, int]:
    """Create the archive atomically, then inspect the final file."""
    archive_path = archive_path.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and not replace:
        raise FileExistsError(
            f"Release ZIP already exists: {archive_path}"
        )
    temporary_path = archive_path.with_suffix(
        archive_path.suffix + ".building"
    )
    if temporary_path.exists():
        temporary_path.unlink()
    files = release_files()
    try:
        with ZipFile(
            temporary_path,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in files:
                archive.write(
                    path,
                    path.relative_to(PROJECT_ROOT).as_posix(),
                )
        results = inspect_archive(temporary_path)
        temporary_path.replace(archive_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    output = timestamped_output_path(arguments.output)
    results = build_archive(output, replace=False)
    print(f"archive={output.resolve()}")
    for name, value in results.items():
        print(f"{name}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
