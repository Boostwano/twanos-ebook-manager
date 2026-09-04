"""Validate a Twano source release from a clean temporary extraction."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile


def _run(command: list[str], *, cwd: Path, environment=None) -> None:
    subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
    )


def _safe_extract(archive_path: Path, destination: Path) -> int:
    destination = destination.resolve()
    with ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(
                    f"Unsafe archive entry path: {entry.filename}"
                )
        archive.extractall(destination)
        return len(archive.infolist())


def validate(archive_path: Path, python_path: Path) -> None:
    archive_path = archive_path.resolve(strict=True)
    python_path = python_path.resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="Twano-RC1-package-validation-",
        ignore_cleanup_errors=True,
    ) as temporary_folder:
        extracted = Path(temporary_folder)
        entry_count = _safe_extract(archive_path, extracted)
        _run(
            [
                str(python_path),
                "-m",
                "compileall",
                "-q",
                "src",
                "tests",
                "tools",
            ],
            cwd=extracted,
        )
        _run(
            [str(python_path), "-m", "pytest", "-q"],
            cwd=extracted,
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        _run(
            [
                str(python_path),
                "tools/capture_complete_preview.py",
                str(extracted / "package-smoke"),
            ],
            cwd=extracted,
            environment=environment,
        )
        _run(
            [
                str(python_path),
                "-c",
                (
                    "import sys; "
                    "sys.path.insert(0, 'src'); "
                    "import config; "
                    "assert config.APP_VERSION == 'R4 RC1'; "
                    "assert config.RELEASE_NAME == "
                    "'Production Release Candidate'; "
                    "print('package_version=' + config.APP_VERSION); "
                    "print('release_name=' + config.RELEASE_NAME)"
                ),
            ],
            cwd=extracted,
        )
        captures = tuple((extracted / "package-smoke").glob("*.png"))
        if len(captures) != 7:
            raise RuntimeError(
                f"Expected 7 UI smoke captures, found {len(captures)}."
            )
        print(f"archive={archive_path}")
        print(f"entries={entry_count}")
        print("compile=passed")
        print("pytest=passed")
        print(f"ui_smoke_captures={len(captures)}")
        print("clean_extraction_validation=passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--python", required=True, type=Path)
    arguments = parser.parse_args()
    validate(arguments.archive, arguments.python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
