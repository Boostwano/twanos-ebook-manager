"""Safe Calibre detection and network-library diagnostics."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CalibreInstallation:
    calibre_path: str
    viewer_path: str
    database_tool_path: str
    version: str

    @property
    def available(self) -> bool:
        return bool(self.calibre_path)


@dataclass(frozen=True)
class CalibreLibrary:
    folder: str
    metadata_database: str
    valid: bool
    message: str


class IntegrationService:
    """Use only documented Calibre commands and read-only library checks."""

    def detect_calibre(self) -> CalibreInstallation:
        roots = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Calibre2",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
            / "Calibre2",
        )
        calibre = self._find_executable("calibre.exe", roots)
        viewer = self._find_executable("ebook-viewer.exe", roots)
        database_tool = self._find_executable("calibredb.exe", roots)
        version = ""
        if calibre:
            try:
                result = subprocess.run(
                    [calibre, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0,
                    ),
                )
                version = (result.stdout or result.stderr).strip()
            except (OSError, subprocess.SubprocessError):
                version = ""
        return CalibreInstallation(
            calibre_path=calibre,
            viewer_path=viewer,
            database_tool_path=database_tool,
            version=version,
        )

    @staticmethod
    def inspect_calibre_library(folder: str | Path) -> CalibreLibrary:
        path = Path(folder).expanduser()
        metadata = path / "metadata.db"
        if not path.is_absolute():
            return CalibreLibrary(
                str(path),
                str(metadata),
                False,
                "Choose an absolute Calibre library folder.",
            )
        if not path.is_dir():
            return CalibreLibrary(
                str(path),
                str(metadata),
                False,
                "That folder is not currently available.",
            )
        if not metadata.is_file():
            return CalibreLibrary(
                str(path),
                str(metadata),
                False,
                "No Calibre metadata.db file was found in that folder.",
            )
        return CalibreLibrary(
            str(path.resolve()),
            str(metadata.resolve()),
            True,
            "Calibre library detected. Twano will scan ebook files but will "
            "not write directly to Calibre's database.",
        )

    def open_calibre_library(self, folder: str | Path) -> None:
        installation = self.detect_calibre()
        if not installation.calibre_path:
            raise FileNotFoundError("Calibre is not installed or could not be found.")
        library = self.inspect_calibre_library(folder)
        if not library.valid:
            raise ValueError(library.message)
        subprocess.Popen(
            [
                installation.calibre_path,
                "--with-library",
                library.folder,
            ],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @staticmethod
    def network_path_shape(path: str) -> tuple[bool, str]:
        """Explain a local, mapped-drive, or UNC-shaped path."""
        cleaned = str(path).strip()
        if cleaned.startswith("\\\\"):
            return True, "Windows network (UNC) location"
        drive, _tail = os.path.splitdrive(cleaned)
        if drive:
            return True, "Local or mapped Windows drive"
        return False, "Choose an absolute local, mapped-drive, or UNC path."

    @staticmethod
    def _find_executable(name: str, roots: tuple[Path, ...]) -> str:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
        for root in roots:
            candidate = root / name
            if candidate.is_file():
                return str(candidate.resolve())
        return ""
