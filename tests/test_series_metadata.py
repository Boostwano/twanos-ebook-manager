"""Regression tests for provider-independent series naming and order."""

import pytest

from services.series_metadata import canonical_series_details, match_existing_series


@pytest.mark.parametrize(
    ("provider_series", "title", "provider_number", "expected_number"),
    (
        ("Assiti Shards", "1635: The Tangled Web", "14", "14"),
        ("Ring of Fire", "1634: The Galileo Affair", "", "3"),
        ("Ring of fire series", "1635: The Cannon Law", "7", "8"),
        ("Ring of Fire Main Line Novels", "1635: The Eastern Front", "4", "10"),
    ),
)
def test_ring_of_fire_provider_aliases_share_one_series_and_order(
    provider_series: str,
    title: str,
    provider_number: str,
    expected_number: str,
) -> None:
    assert canonical_series_details(
        provider_series,
        title=title,
        number=provider_number,
    ) == ("Ring of Fire", expected_number)


def test_unrelated_series_is_not_rewritten() -> None:
    assert canonical_series_details(
        "The Farseer Trilogy",
        title="Assassin's Quest",
        number="3",
    ) == ("The Farseer Trilogy", "3")


@pytest.mark.parametrize(
    "freshly_resolved",
    (
        "alfred hitchcock and the three investigators series",
        "Alfred Hitchcock And The Three Investigators",
        "  Alfred   Hitchcock and the Three Investigators  ",
        "Alfred Hitchcock and the Three Investigators.",
    ),
)
def test_match_existing_series_snaps_to_the_catalogued_wording(
    freshly_resolved: str,
) -> None:
    """A resolver's wording/casing shouldn't create a near-duplicate series.

    Reproduces a real case: a web-search fallback returned this series as
    "Alfred Hitchcock and the three investigators series" on one book and
    plain "Alfred Hitchcock and The Three Investigators" (no trailing
    "series", correct casing) on 24 others already in the catalogue. Once
    an author's own catalogue already uses one wording, every later run
    should snap back onto it instead of organising into a second folder.
    """
    known_series = ("Alfred Hitchcock and The Three Investigators", "Eberron")
    assert (
        match_existing_series(freshly_resolved, known_series)
        == "Alfred Hitchcock and The Three Investigators"
    )


def test_match_existing_series_leaves_a_genuinely_new_series_alone() -> None:
    known_series = ("Alfred Hitchcock and The Three Investigators",)
    assert (
        match_existing_series("The Kingkiller Chronicle", known_series)
        == "The Kingkiller Chronicle"
    )


def test_match_existing_series_handles_no_catalogued_series_yet() -> None:
    assert match_existing_series("A Brand New Series", ()) == "A Brand New Series"
