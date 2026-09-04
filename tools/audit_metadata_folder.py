"""Read-only audit of Twano metadata lookups for one folder.

The audit is deliberately nonrecursive by default.  It extracts embedded
metadata and calls the same active-provider search used by Metadata & Covers,
but it never previews/applies changes or writes to the ebook files/catalogue.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import get_ident, local
from time import monotonic


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.metadata import extract_metadata  # noqa: E402
from database.database import DatabaseManager  # noqa: E402
from services.metadata_studio_service import (  # noqa: E402
    MetadataStudioService,
)
from services.plugin_service import PluginService  # noqa: E402


SUPPORTED_SUFFIXES = {
    ".azw",
    ".azw3",
    ".cb7",
    ".cbr",
    ".cbz",
    ".epub",
    ".fb2",
    ".mobi",
    ".pdf",
}


@dataclass(frozen=True)
class AuditResult:
    file_name: str
    file_path: str
    embedded_title: str
    embedded_author: str
    extraction_status: str
    result_count: int
    top_provider: str
    top_title: str
    top_author: str
    confidence: int
    has_cover: bool
    series: str
    series_number: str
    searched_providers: tuple[str, ...]
    failed_providers: tuple[str, ...]
    elapsed_seconds: float
    error: str


_thread_state = local()


def _service() -> MetadataStudioService:
    service = getattr(_thread_state, "service", None)
    if service is not None:
        return service

    audit_root = Path(tempfile.gettempdir()) / "twano-metadata-audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    thread_number = get_ident()
    database = DatabaseManager(audit_root / f"audit-{thread_number}.db")
    service = MetadataStudioService(
        database,
        plugin_service=PluginService(),
        cache_path=audit_root / f"cache-{thread_number}.json",
        timeout=12.0,
    )
    _thread_state.service = service
    return service


def _audit_file(path: Path) -> AuditResult:
    started = monotonic()
    embedded = extract_metadata(path)
    service = _service()
    try:
        candidates = service.search_enabled_candidates(
            title=embedded.title,
            author=embedded.author,
            isbn=embedded.isbn,
            file_name=path.name,
            cache_days=0,
        )
        top = candidates[0] if candidates else None
        report = service.last_search_report
        return AuditResult(
            file_name=path.name,
            file_path=str(path),
            embedded_title=embedded.title,
            embedded_author=embedded.author,
            extraction_status=embedded.extraction_status,
            result_count=len(candidates),
            top_provider=top.provider_name if top else "",
            top_title=top.title if top else "",
            top_author=top.author if top else "",
            confidence=int(top.confidence) if top else 0,
            has_cover=any(bool(candidate.cover_url) for candidate in candidates),
            series=top.series if top else "",
            series_number=top.series_number if top else "",
            searched_providers=tuple(report.searched_providers),
            failed_providers=tuple(report.failed_providers),
            elapsed_seconds=round(monotonic() - started, 2),
            error="",
        )
    except Exception as error:  # Audit must record one bad provider/book and continue.
        report = service.last_search_report
        return AuditResult(
            file_name=path.name,
            file_path=str(path),
            embedded_title=embedded.title,
            embedded_author=embedded.author,
            extraction_status=embedded.extraction_status,
            result_count=0,
            top_provider="",
            top_title="",
            top_author="",
            confidence=0,
            has_cover=False,
            series="",
            series_number="",
            searched_providers=tuple(report.searched_providers),
            failed_providers=tuple(report.failed_providers),
            elapsed_seconds=round(monotonic() - started, 2),
            error=f"{type(error).__name__}: {error}",
        )


def _root_files(folder: Path) -> tuple[Path, ...]:
    """Return supported files directly in folder; never enter subfolders."""

    return tuple(
        sorted(
            (
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
            ),
            key=lambda path: path.name.casefold(),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--workers",
        type=int,
        choices=(1,),
        default=1,
        help="Audit sequentially so provider-health state remains deterministic.",
    )
    args = parser.parse_args()

    folder = args.folder.resolve()
    files = _root_files(folder)
    print(f"Auditing {len(files)} direct ebook files in {folder}", flush=True)
    print("Subfolders are excluded.", flush=True)

    results: list[AuditResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(_audit_file, path): path for path in files}
        for completed, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            state = "ERROR" if result.error else (
                "NO MATCH" if not result.result_count else f"{result.confidence}%"
            )
            print(
                f"[{completed:02d}/{len(files):02d}] {state:<8} {result.file_name}",
                flush=True,
            )

    results.sort(key=lambda result: result.file_name.casefold())
    payload = {
        "folder": str(folder),
        "recursive": False,
        "file_count": len(files),
        "results": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Report written to {args.output.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
