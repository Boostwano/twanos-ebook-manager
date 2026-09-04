"""Tests for independent metadata evidence and conflict reporting."""

from src.services.library_service import LibraryRecord
from src.services.metadata_studio_service import (
    MetadataCandidate,
    MetadataStudioService,
)


def _record(*, title: str, author: str, file_name: str) -> LibraryRecord:
    return LibraryRecord(
        title=title,
        author=author,
        isbn="",
        publisher="",
        published_date="",
        language="en",
        file_format="EPUB",
        file_size=1,
        metadata_status="Needs Review",
        file_path=f"C:/Books/{file_name}",
    )


def _candidate(
    *,
    title: str,
    author: str,
    provider: str,
    confidence: int = 90,
    isbn: str = "9780000000001",
) -> MetadataCandidate:
    return MetadataCandidate(
        title=title,
        author=author,
        isbn=isbn,
        publisher="Example Publisher",
        language="en",
        published_date="2000",
        cover_id=None,
        work_key="",
        confidence=confidence,
        confidence_reason="test",
        provider_name=provider,
    )


def test_assessment_accepts_independent_agreement() -> None:
    service = MetadataStudioService.__new__(MetadataStudioService)
    record = _record(
        title="The Example Book",
        author="Jane Writer",
        file_name="The Example Book - Jane Writer.epub",
    )
    selected = _candidate(
        title="The Example Book",
        author="Jane Writer",
        provider="Google Books",
    )
    supporting = _candidate(
        title="The Example Book",
        author="Jane Writer",
        provider="Open Library",
    )

    assessment = service.assess_candidate_sources(
        record,
        selected,
        (selected, supporting),
    )

    assert assessment.needs_manual_review is False
    assert "Filename" in assessment.agreeing_sources
    assert "Current catalogue" in assessment.agreeing_sources
    assert "Open Library" in assessment.agreeing_sources
    assert "Evidence supports this match" in assessment.summary


def test_assessment_flags_provider_conflict_for_manual_review() -> None:
    service = MetadataStudioService.__new__(MetadataStudioService)
    record = _record(
        title="Mystery File",
        author="Jane Writer",
        file_name="Mystery File - Jane Writer.epub",
    )
    selected = _candidate(
        title="The Example Book",
        author="Jane Writer",
        provider="Google Books",
        confidence=85,
    )
    conflicting = _candidate(
        title="A Different Book",
        author="Jane Writer",
        provider="Open Library",
        confidence=90,
        isbn="9780000000002",
    )

    assessment = service.assess_candidate_sources(
        record,
        selected,
        (selected, conflicting),
    )

    assert assessment.needs_manual_review is True
    assert "Open Library" in assessment.conflict_sources
    assert "Manual review recommended" in assessment.summary
