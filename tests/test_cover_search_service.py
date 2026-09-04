"""Standalone cover search must never require Calibre."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from urllib.error import HTTPError

from database.database import DatabaseManager
from services.cover_search_service import (
    CoverSearchService,
    DirectCoverResult,
)
from services.metadata_studio_service import (
    MetadataCandidate,
    MetadataStudioService,
)
from workers.metadata_lookup_worker import MetadataLookupWorker
import services.cover_search_service as cover_module
import services.metadata_studio_service as metadata_module


class _Response:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_cover_sources_run_inside_twano_without_opening_a_browser() -> None:
    service = CoverSearchService()

    sources = service.sources()

    assert {source.source_id for source in sources} == {
        "automatic",
        "open_library",
        "google_books",
        "hardcover",
        "comic_vine",
        "apple_books",
        "amazon",
        "goodreads",
        "isbndb",
        "gutenberg",
        "big_book",
        "openweb_ninja",
    }
    assert all(source.automatic for source in sources)
    assert all("website" not in source.description.casefold() for source in sources)


def test_apple_books_maps_description_and_larger_cover(monkeypatch) -> None:
    payload = {
        "resultCount": 1,
        "results": [
            {
                "trackName": "Wizard Squared",
                "artistName": "K. E. Mills",
                "sellerName": "Hachette UK",
                "releaseDate": "2011-07-02T07:00:00Z",
                "description": "<p>An alternate reality threatens every "
                "world.</p>",
                "averageUserRating": 4.25,
                "userRatingCount": 80,
                "artworkUrl100": (
                    "https://is1-ssl.mzstatic.com/image/thumb/book/"
                    "100x100bb.jpg"
                ),
                "trackViewUrl": "https://books.apple.com/au/book/id123",
            }
        ],
    }
    monkeypatch.setattr(
        cover_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    results = CoverSearchService().search_apple_books(
        title="Wizard Squared",
        author="Mills, K. E.",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Apple Books"
    assert results[0].confidence == 90
    assert results[0].description == (
        "An alternate reality threatens every world."
    )
    assert "/600x600bb.jpg" in results[0].cover_url
    assert results[0].published_date == "2011-07-02"
    assert results[0].provider_rating == 4.25
    assert results[0].rating_count == 80


def test_apple_books_discards_unrelated_search_results(monkeypatch) -> None:
    payload = {
        "resultCount": 1,
        "results": [
            {
                "trackName": "The Secular Wizard",
                "artistName": "Christopher Stasheff",
                "artworkUrl100": "https://is1-ssl.mzstatic.com/100x100bb.jpg",
                "trackViewUrl": "https://books.apple.com/au/book/id456",
            }
        ],
    }
    monkeypatch.setattr(
        cover_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    results = CoverSearchService().search_apple_books(
        title="Wizard Squared",
        author="K. E. Mills",
    )

    assert results == ()


def test_isbndb_maps_isbn_description_and_cover_without_exposing_key(
    monkeypatch,
) -> None:
    captured = {"urls": []}
    payload = {
        "book": {
            "title": "Wizard Squared",
            "authors": ["K. E. Mills"],
            "isbn": "0316035432",
            "isbn13": "9780316035439",
            "publisher": "Orbit",
            "date_published": "2010-07-01",
            "language": "en",
            "image": "https://images.isbndb.com/covers/wizard.jpg",
            "synopsis": "<p>The third Rogue Agent novel.</p>",
        }
    }

    def fake_urlopen(request, **_kwargs):
        captured["urls"].append(request.full_url)
        captured["authorization"] = request.get_header("Authorization")
        return _Response(payload)

    monkeypatch.setattr(cover_module, "urlopen", fake_urlopen)

    results = CoverSearchService().search_isbndb(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9780316035439",
        api_key="private-isbndb-key",
    )

    assert len(results) == 1
    assert results[0].provider_name == "ISBNdb"
    assert results[0].confidence == 100
    assert results[0].isbn == "9780316035439"
    assert results[0].description == "The third Rogue Agent novel."
    assert captured["authorization"] == "private-isbndb-key"
    assert len(captured["urls"]) == 2
    assert any("/book/9780316035439" in url for url in captured["urls"])
    assert any("/books/Wizard%20Squared%20K.%20E.%20Mills" in url for url in captured["urls"])
    assert all(
        "private-isbndb-key" not in url for url in captured["urls"]
    )


def test_metadata_search_uses_clean_title_and_author_from_filename() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="03 Wizard Squared",
        author="Mills, K.E.",
        file_name="Wizard Squared - K. E. Mills.epub",
    )

    assert terms.title == "Wizard Squared"
    assert terms.author == "K. E. Mills"
    assert terms.from_filename


def test_numbered_three_part_filename_keeps_title_and_author() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="01 - Thieves of Blood - Tim Waggoner",
        author="",
        file_name="01 - Thieves of Blood - Tim Waggoner.epub",
    )

    assert terms.title == "Thieves of Blood"
    assert terms.author == "Tim Waggoner"
    assert terms.from_filename


def test_separated_publication_year_is_removed_from_filename_search() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="2006 - The Smelliest Day at the Zoo",
        author="Alan Rusbridger",
        file_name=(
            "2006 - The Smelliest Day at the Zoo - Alan Rusbridger.epub"
        ),
    )

    assert terms.title == "The Smelliest Day at the Zoo"
    assert terms.author == "Alan Rusbridger"
    assert terms.from_filename


def test_year_at_start_of_real_title_is_not_removed() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="2066 Election Day",
        author="Michael Shaara",
        file_name="2066 Election Day - Michael Shaara.epub",
    )

    assert terms.title == "2066 Election Day"
    assert terms.author == "Michael Shaara"


def test_numbered_filename_typo_does_not_replace_correct_embedded_title() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="21 The Secret of the Haunted Mirror",
        author="M. V. Carey",
        isbn="8390493443",
        file_name="21 - The Secret of the Haunted Mirrror.epub",
    )

    assert terms.title == "The Secret of the Haunted Mirror"
    assert terms.author == "M. V. Carey"
    assert terms.isbn == ""
    assert terms.from_filename


def test_repeated_letter_typo_is_repaired_when_title_and_filename_match() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="21 The Secret of the Haunted Mirrror",
        author="M. V. Carey",
        isbn="8390493443",
        file_name="21 - The Secret of the Haunted Mirrror.epub",
    )

    assert terms.title == "The Secret of the Haunted Mirror"
    assert terms.author == "M. V. Carey"
    assert terms.isbn == ""
    assert terms.from_filename


def test_legitimate_double_letters_are_not_changed_in_search_title() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="The Bookkeeper",
        author="Alice Cooper",
    )

    assert terms.title == "The Bookkeeper"


def test_real_numeric_title_without_order_separator_is_not_removed() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="101 Things to Do with Ramen Noodles",
        author="Toni Patrick",
        file_name="101 Things to Do with Ramen Noodles - Toni Patrick.epub",
    )

    assert terms.title == "101 Things to Do with Ramen Noodles"
    assert terms.author == "Toni Patrick"


def test_invalid_sentinel_published_year_is_removed() -> None:
    candidate = MetadataCandidate(
        title="The Secret of the Haunted Mirror",
        author="M. V. Carey",
        isbn="",
        publisher="",
        language="en",
        published_date="0101-01-01T00:00:00+00:00",
        cover_id=None,
        work_key="haunted-mirror",
        confidence=90,
        confidence_reason="Exact title and author match",
    )

    cleaned = metadata_module._enrich_matching_candidates([candidate])

    assert cleaned[0].published_date == ""


def test_numeric_filename_does_not_replace_date_title_and_embedded_author() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="11/22/63",
        author="King, Stephen",
        file_name="101 - 22 - 63.epub",
    )

    assert terms.title == "11/22/63"
    assert terms.author == "King, Stephen"
    assert not terms.from_filename


def test_embedded_series_prefix_cleans_search_and_fills_provider_gap(
    monkeypatch,
    tmp_path,
) -> None:
    service = MetadataStudioService(DatabaseManager(tmp_path / "library.db"))
    terms = service.prepare_search_terms(
        title="Womans Murder Club 1 - 1st To Die",
        author="Patterson, James",
        isbn="0446696617",
        file_name="1st to Die - James Patterson.epub",
    )
    provider_result = MetadataCandidate(
        title="1st To Die",
        author="James Patterson",
        isbn="9780446696616",
        publisher="Little, Brown",
        language="eng",
        published_date="2001",
        cover_id=1,
        work_key="/works/first-to-die",
        confidence=100,
        confidence_reason="Exact ISBN match",
    )
    monkeypatch.setattr(
        service,
        "search_candidates",
        lambda **_values: (provider_result,),
    )

    results = service.search_enabled_candidates(
        title="Womans Murder Club 1 - 1st To Die",
        author="Patterson, James",
        isbn="0446696617",
        file_name="1st to Die - James Patterson.epub",
    )

    assert terms.title == "1st To Die"
    assert terms.author == "Patterson, James"
    assert terms.isbn == "0446696617"
    assert results[0].title == "1st To Die"
    assert results[0].series == "Womans Murder Club"
    assert results[0].series_number == "1"


def test_comic_filename_extracts_series_issue_and_publisher() -> None:
    frew = MetadataStudioService.prepare_search_terms(
        title="(Frew) Phantom 1048",
        author="Unknown",
        file_name="(Frew) Phantom 1048.cbr",
    )
    other_series = MetadataStudioService.prepare_search_terms(
        title="[Image] Saga 0054",
        author="Unknown",
        file_name="[Image] Saga 0054.cbz",
    )

    assert frew.title == "The Phantom"
    assert frew.author == ""
    assert frew.comic_issue_number == "1048"
    assert frew.comic_publisher == "Frew Publications"
    assert frew.from_filename
    assert other_series.title == "Saga"
    assert other_series.comic_issue_number == "0054"
    assert other_series.comic_publisher == "Image"


def test_filename_search_recognises_author_then_title_layout() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="The Haunted Bridge",
        author="Carolyn Keene",
        file_name="Carolyn Keene - The Haunted Bridge.epub",
    )

    assert terms.title == "The Haunted Bridge"
    assert terms.author == "Carolyn Keene"
    assert terms.from_filename


def test_filename_search_corrects_swapped_embedded_fields() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="Banks, Ian M.",
        author="Consider Phlebas",
        file_name="Consider Phlebas - Banks, Ian M.epub",
    )

    assert terms.title == "Consider Phlebas"
    assert terms.author == "Banks, Ian M"
    assert terms.from_filename


def test_filename_search_uses_name_shape_when_embedded_fields_are_swapped() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="Cassandra Clare",
        author="City Of Glass",
        file_name="Cassandra Clare - City Of Glass.epub",
    )

    assert terms.title == "City Of Glass"
    assert terms.author == "Cassandra Clare"


def test_filename_search_ignores_trailing_series_information() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title="Butcher, Jim - Codex Alera 04",
        author="Captain's Fury",
        file_name="Captain's Fury - Butcher, Jim - Codex Alera 04.epub",
    )

    assert terms.title == "Captain's Fury"
    assert terms.author == "Butcher, Jim"
    assert terms.from_filename


def test_filename_search_accepts_missing_optional_metadata() -> None:
    terms = MetadataStudioService.prepare_search_terms(
        title=None,
        author=None,
        isbn=None,
        file_name="Wizard Squared - K. E. Mills.epub",
    )

    assert terms.title == "Wizard Squared"
    assert terms.author == "K. E. Mills"


def test_google_books_maps_direct_cover_results(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": "volume-1",
                "volumeInfo": {
                    "title": "The Hobbit",
                    "authors": ["J. R. R. Tolkien"],
                    "publisher": "HarperCollins",
                    "publishedDate": "1937",
                    "language": "en",
                    "description": (
                        "<p>A quiet hobbit is drawn into an adventure.</p>"
                    ),
                    "averageRating": 4.4,
                    "ratingsCount": 1250,
                    "industryIdentifiers": [
                        {
                            "type": "ISBN_13",
                            "identifier": "9780261103344",
                        }
                    ],
                    "imageLinks": {
                        "large": (
                            "http://books.google.com/books/content"
                            "?id=volume-1&printsec=frontcover"
                        )
                    },
                    "canonicalVolumeLink": (
                        "https://books.google.com/books?id=volume-1"
                    ),
                },
            }
        ]
    }
    monkeypatch.setattr(
        cover_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    results = CoverSearchService().search_google_books(
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Google Books"
    assert results[0].confidence == 100
    assert results[0].cover_url.startswith("https://books.google.com/")
    assert results[0].description == (
        "A quiet hobbit is drawn into an adventure."
    )
    assert results[0].provider_rating == 4.4
    assert results[0].rating_count == 1250


def test_google_books_prefers_australian_editions_and_language(monkeypatch) -> None:
    def item(volume_id: str, country: str) -> dict:
        return {
            "id": volume_id,
            "saleInfo": {"country": country},
            "volumeInfo": {
                "title": "Hounded",
                "authors": ["Kevin Hearne"],
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9780345522474"}
                ],
                "imageLinks": {
                    "large": f"https://books.google.com/{volume_id}.jpg"
                },
            },
        }

    seen_headers: list[dict] = []

    def respond(request, **_kwargs):
        seen_headers.append(dict(request.headers))
        return _Response({"items": [item("us", "US"), item("au", "AU")]})

    monkeypatch.setattr(cover_module, "urlopen", respond)

    results = CoverSearchService().search_google_books(isbn="9780345522474")

    assert [result.cover_url for result in results] == [
        "https://books.google.com/au.jpg",
        "https://books.google.com/us.jpg",
    ]
    assert seen_headers[0]["Accept-language"] == "en-AU,en;q=0.9"


def test_google_books_retries_after_weak_isbn_results(monkeypatch) -> None:
    weak_payload = {
        "items": [
            {
                "volumeInfo": {
                    "title": "An Unrelated Attic Book",
                    "authors": ["Another Writer"],
                    "industryIdentifiers": [
                        {"type": "ISBN_13", "identifier": "9780000000001"}
                    ],
                    "imageLinks": {
                        "thumbnail": "https://books.google.com/weak.jpg"
                    },
                }
            }
        ]
    }
    exact_payload = {
        "items": [
            {
                "volumeInfo": {
                    "title": "1 Dead in Attic: After Katrina",
                    "authors": ["Chris Rose"],
                    "industryIdentifiers": [
                        {"type": "ISBN_13", "identifier": "9781439126240"}
                    ],
                    "imageLinks": {
                        "large": "https://books.google.com/dead-in-attic.jpg"
                    },
                }
            }
        ]
    }
    alternate_cover_payload = {
        "items": [
            {
                "volumeInfo": {
                    "title": "1 Dead in Attic: After Katrina",
                    "authors": ["Chris Rose"],
                    "industryIdentifiers": [
                        {"type": "ISBN_13", "identifier": "9781439126240"}
                    ],
                    "imageLinks": {
                        "large": "https://books.google.com/dead-in-attic-alt.jpg"
                    },
                }
            }
        ]
    }
    responses = iter((weak_payload, exact_payload, alternate_cover_payload))
    requested_urls: list[str] = []

    def respond(request, **_kwargs):
        requested_urls.append(request.full_url)
        return _Response(next(responses))

    monkeypatch.setattr(cover_module, "urlopen", respond)

    results = CoverSearchService().search_google_books(
        title="1 Dead in Attic",
        author="Chris Rose",
        isbn="9781439126240",
    )

    assert len(requested_urls) == 3
    assert "isbn%3A9781439126240" in requested_urls[0]
    assert "intitle%3A%221+Dead+in+Attic%22" in requested_urls[1]
    usable = tuple(result for result in results if result.confidence >= 75)
    assert len(usable) == 2
    assert usable[0].title == "1 Dead in Attic: After Katrina"
    assert usable[0].confidence == 100
    assert usable[0].cover_url.endswith("dead-in-attic.jpg")
    assert usable[1].cover_url.endswith("dead-in-attic-alt.jpg")


def test_google_books_maps_title_and_structured_series(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": "inca-gold",
                "volumeInfo": {
                    "title": "Inca Gold (Dirk Pitt Adventures Book 12)",
                    "authors": ["Clive Cussler"],
                    "seriesInfo": {
                        "bookDisplayNumber": "12",
                        "volumeSeries": [{"orderNumber": 12}],
                    },
                    "imageLinks": {
                        "thumbnail": "https://books.google.com/inca-gold.jpg"
                    },
                },
            }
        ]
    }
    monkeypatch.setattr(
        cover_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    results = CoverSearchService().search_google_books(
        title="Inca Gold",
        author="Clive Cussler",
    )

    assert len(results) == 1
    assert results[0].title == "Inca Gold"
    assert results[0].series == "Dirk Pitt Adventures"
    assert results[0].series_number == "12"


def test_google_books_keeps_unnumbered_structured_collection(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": "ramen-noodles",
                "volumeInfo": {
                    "title": "101 Things to Do with Ramen Noodles",
                    "authors": ["Toni Patrick"],
                    "seriesInfo": {"title": "101 Things to do with..."},
                    "imageLinks": {
                        "thumbnail": "https://books.google.com/ramen.jpg"
                    },
                },
            }
        ]
    }
    monkeypatch.setattr(
        cover_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    results = CoverSearchService().search_google_books(
        title="101 Things to Do with Ramen Noodles",
        author="Toni Patrick",
    )

    assert len(results) == 1
    assert results[0].series == "101 Things to do with"
    assert results[0].series_number == ""

    stale_cached = MetadataCandidate(
        title="101 Things to Do with Ramen Noodles",
        author="Toni Patrick",
        isbn="9781586857356",
        publisher="Gibbs Smith",
        language="en",
        published_date="2005",
        cover_id=None,
        work_key="google-ramen",
        confidence=100,
        confidence_reason="Exact ISBN match",
        series="101 Things to do with...",
    )
    cleaned = metadata_module._enrich_matching_candidates([stale_cached])
    assert cleaned[0].series == "101 Things to do with"


def test_matching_result_recovers_explicit_series_from_description() -> None:
    candidate = MetadataCandidate(
        title="The Horse and His Boy",
        author="C. S. Lewis,C.S.",
        isbn="9781514280836",
        publisher="CreateSpace",
        language="en",
        published_date="2015-06-08",
        cover_id=None,
        work_key="narnia-horse",
        confidence=60,
        confidence_reason="Possible title or author match",
        provider_name="Google Books",
        description=(
            "The Horse and His Boy, book three in the classic fantasy "
            "series, The Chronicles of Narnia, featuring Pauline Baynes' "
            "original artwork."
        ),
    )

    results = metadata_module._enrich_matching_candidates([candidate])

    assert results[0].author == "C. S. Lewis"
    assert results[0].series == "The Chronicles of Narnia"
    assert results[0].series_number == "3"


def test_matching_result_adds_verified_parent_series_group() -> None:
    candidate = MetadataCandidate(
        title="Pawn of Prophecy",
        author="David Eddings",
        isbn="",
        publisher="",
        language="en",
        published_date="1982",
        cover_id=None,
        work_key="belgariad-1",
        confidence=100,
        confidence_reason="Exact match",
        provider_name="Google Books",
        series="The Belgariad",
        series_number="1",
    )

    results = metadata_module._enrich_matching_candidates([candidate])

    assert results[0].series_group == "Belgariad Universe"
    assert results[0].series_group_number == "1"


def test_description_series_fallback_does_not_override_structured_data() -> None:
    candidate = MetadataCandidate(
        title="Example",
        author="Example Author",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_id=None,
        work_key="example",
        confidence=90,
        confidence_reason="Exact match",
        series="Publisher Series",
        series_number="5",
        description=(
            "Book three in the classic series, Different Series, with notes."
        ),
    )

    results = metadata_module._enrich_matching_candidates([candidate])

    assert results[0].series == "Publisher Series"
    assert results[0].series_number == "5"


def test_google_books_retries_with_title_when_strict_search_is_empty(
    monkeypatch,
) -> None:
    responses = iter(
        (
            _Response({"totalItems": 0}),
            _Response(
                {
                    "items": [
                        {
                            "id": "wizard",
                            "volumeInfo": {
                                "title": "Wizard Squared",
                                "authors": ["K. E. Mills"],
                                "imageLinks": {
                                    "thumbnail": (
                                        "https://books.google.com/wizard.jpg"
                                    )
                                },
                            },
                        }
                    ]
                }
            ),
        )
    )
    requested_urls: list[str] = []

    def request(request, **_kwargs):
        requested_urls.append(request.full_url)
        return next(responses)

    monkeypatch.setattr(cover_module, "urlopen", request)

    results = CoverSearchService().search_google_books(
        title="Wizard Squared",
        author="K. E. Mills",
    )

    assert len(requested_urls) == 2
    assert "inauthor" in requested_urls[0]
    assert "inauthor" not in requested_urls[1]
    assert results[0].title == "Wizard Squared"
    assert results[0].provider_name == "Google Books"


def test_google_books_uses_optional_api_key(monkeypatch) -> None:
    requested_urls: list[str] = []

    def request(request, **_kwargs):
        requested_urls.append(request.full_url)
        return _Response({"totalItems": 0})

    monkeypatch.setattr(cover_module, "urlopen", request)

    CoverSearchService().search_google_books(
        title="Wizard Squared",
        api_key="protected-key",
    )

    assert requested_urls
    assert all("key=protected-key" in url for url in requested_urls)


def test_google_books_explains_incompatible_key_restrictions(
    monkeypatch,
) -> None:
    payload = json.dumps(
        {
            "error": {
                "message": "Requests from referer <empty> are blocked.",
                "errors": [{"reason": "forbidden"}],
            }
        }
    ).encode("utf-8")

    def reject(request, **_kwargs):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            BytesIO(payload),
        )

    monkeypatch.setattr(cover_module, "urlopen", reject)

    try:
        CoverSearchService().search_google_books(
            title="Quiller's Run",
            author="Adam Hall",
            api_key="temporary-test-key",
        )
    except cover_module.CoverSearchError as error:
        assert "website-referrer restriction" in str(error)
    else:
        raise AssertionError("A rejected Google key was reported as working")


def test_open_library_prefers_isbn_13_for_later_cover_plugins() -> None:
    candidate = MetadataStudioService._map_candidate(
        {
            "key": "/works/OL-WIZARD",
            "title": "Wizard Squared",
            "author_name": ["K. E. Mills"],
            "isbn": ["1841497290", "9781841497297"],
        },
        wanted_title="Wizard Squared",
        wanted_author="K. E. Mills",
        wanted_isbn="",
    )

    assert candidate is not None
    assert candidate.isbn == "9781841497297"


def test_open_library_maps_explicit_series_volume() -> None:
    candidate = MetadataStudioService._map_candidate(
        {
            "key": "/works/OL-INCA-GOLD",
            "title": "Inca Gold",
            "author_name": ["Clive Cussler"],
            "series": ["Dirk Pitt Series Volume 12"],
        },
        wanted_title="Inca Gold",
        wanted_author="Clive Cussler",
        wanted_isbn="",
    )

    assert candidate is not None
    assert candidate.title == "Inca Gold"
    assert candidate.series == "Dirk Pitt Series"
    assert candidate.series_number == "12"


def test_open_library_exact_isbn_fills_series_and_cover_from_edition(
    tmp_path,
    monkeypatch,
) -> None:
    responses = iter(
        (
            {
                "docs": [
                    {
                        "key": "/works/OL-GALILEO",
                        "title": "1634: The Galileo Affair",
                        "author_name": ["Eric Flint", "Andrew Dennis"],
                        "isbn": ["0743488156", "9780743488150"],
                        "publisher": ["Baen Books"],
                    }
                ]
            },
            {
                "title": "1634: The Galileo Affair",
                "series": ["Ring of Fire"],
                "covers": [479126],
                "isbn_10": ["0743488156"],
            },
        )
    )
    requested_urls: list[str] = []

    def fake_urlopen(request, **_kwargs):
        requested_urls.append(request.full_url)
        return _Response(next(responses))

    monkeypatch.setattr(metadata_module, "urlopen", fake_urlopen)
    service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
    )

    results = service.search_candidates(
        title="1634: The Galileo Affair",
        author="Eric Flint",
        isbn="0743488156",
    )

    assert len(results) == 1
    assert results[0].series == "Ring of Fire"
    assert results[0].cover_id == 479126
    assert results[0].confidence == 100
    assert requested_urls[1].endswith("/isbn/0743488156.json")


def test_open_library_converts_lone_isbn_10_for_later_cover_plugins() -> None:
    candidate = MetadataStudioService._map_candidate(
        {
            "key": "/works/OL-WIZARD",
            "title": "Wizard Squared",
            "author_name": ["K. E. Mills"],
            "isbn": ["1841497290"],
        },
        wanted_title="Wizard Squared",
        wanted_author="K. E. Mills",
        wanted_isbn="",
    )

    assert candidate is not None
    assert candidate.isbn == "9781841497297"


def test_legacy_metadata_cache_is_refreshed(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "metadata-cache.json"
    cache_path.write_text(
        json.dumps(
            {
                '["wizard squared","k. e. mills",""]': {
                    "stored_at": "2099-01-01T00:00:00+00:00",
                    "candidates": [],
                }
            }
        ),
        encoding="utf-8",
    )
    requests: list[str] = []

    def request(request, **_kwargs):
        requests.append(request.full_url)
        return _Response(
            {
                "docs": [
                    {
                        "key": "/works/OL-WIZARD",
                        "title": "Wizard Squared",
                        "author_name": ["K. E. Mills"],
                        "isbn": ["1841497290"],
                    }
                ]
            }
        )

    monkeypatch.setattr(metadata_module, "urlopen", request)
    service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=cache_path,
    )

    results = service.search_candidates(
        title="Wizard Squared",
        author="K. E. Mills",
    )

    assert len(requests) == 1
    assert results[0].isbn == "9781841497297"


def test_current_empty_metadata_cache_is_retried(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "metadata-cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "_schema_version": metadata_module.METADATA_CACHE_SCHEMA_VERSION,
                '["the secret of the haunted mirror","m. v. carey",""]': {
                    "stored_at": "2099-01-01T00:00:00+00:00",
                    "candidates": [],
                },
            }
        ),
        encoding="utf-8",
    )
    requests: list[str] = []

    def request(request, **_kwargs):
        requests.append(request.full_url)
        return _Response(
            {
                "docs": [
                    {
                        "key": "/works/OL-HAUNTED-MIRROR",
                        "title": "The Secret of the Haunted Mirror",
                        "author_name": ["M. V. Carey"],
                        "cover_i": 7402428,
                        "first_publish_year": 1974,
                    }
                ]
            }
        )

    monkeypatch.setattr(metadata_module, "urlopen", request)
    service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=cache_path,
    )

    results = service.search_candidates(
        title="The Secret of the Haunted Mirror",
        author="M. V. Carey",
    )

    assert len(requests) == 1
    assert results[0].title == "The Secret of the Haunted Mirror"
    assert results[0].cover_id == 7402428


def test_empty_memory_metadata_cache_is_retried(tmp_path, monkeypatch) -> None:
    requests: list[str] = []

    def request(request, **_kwargs):
        requests.append(request.full_url)
        return _Response(
            {
                "docs": [
                    {
                        "key": "/works/OL-HAUNTED-MIRROR",
                        "title": "The Secret of the Haunted Mirror",
                        "author_name": ["M. V. Carey"],
                        "cover_i": 7402428,
                    }
                ]
            }
        )

    monkeypatch.setattr(metadata_module, "urlopen", request)
    service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
    )
    key = ("the secret of the haunted mirror", "m. v. carey", "")
    service._lookup_cache[key] = ()

    results = service.search_candidates(
        title="The Secret of the Haunted Mirror",
        author="M. V. Carey",
    )

    assert len(requests) == 1
    assert results[0].cover_id == 7402428


def test_metadata_studio_maps_direct_cover_without_calibre(tmp_path) -> None:
    direct = DirectCoverResult(
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
        publisher="HarperCollins",
        language="en",
        published_date="1937",
        cover_url="https://books.google.com/cover.jpg",
        source_url="https://books.google.com/books?id=volume-1",
        provider_name="Google Books",
        confidence=100,
        confidence_reason="Exact ISBN match",
        series="Middle-earth",
        series_number="1",
    )
    cover_service = CoverSearchService()
    cover_service.search_google_books = lambda **_kwargs: (direct,)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
        cover_search_service=cover_service,
    )

    candidates = studio.search_cover_candidates(
        source_id="google_books",
        title="The Hobbit",
        isbn="9780261103344",
    )

    assert len(candidates) == 1
    assert candidates[0].provider_name == "Google Books"
    assert candidates[0].cover_url == direct.cover_url
    assert candidates[0].series == "Middle-earth"
    assert candidates[0].series_number == "1"


def test_cover_search_retries_title_when_exact_edition_has_no_cover(
    tmp_path,
) -> None:
    calls: list[str] = []
    unrelated_edition = DirectCoverResult(
        title="The Nervous Witch",
        author="Unknown",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_url="https://comicvine.gamespot.com/nervous-witch.jpg",
        source_url="https://comicvine.gamespot.com/nervous-witch",
        provider_name="Comic Vine",
        confidence=60,
        confidence_reason="Possible title match",
    )
    alternate_edition = DirectCoverResult(
        title="The Mystery of the Nervous Lion",
        author="Nick West",
        isbn="9780394823089",
        publisher="Random House",
        language="en",
        published_date="1971",
        cover_url="https://books.google.com/nervous-lion.jpg",
        source_url="https://books.google.com/books?id=nervous-lion",
        provider_name="Google Books",
        confidence=100,
        confidence_reason="Exact title and author match",
    )
    cover_service = CoverSearchService()

    def search_google_books(**kwargs):
        calls.append(str(kwargs.get("isbn") or ""))
        return (
            (unrelated_edition,)
            if kwargs.get("isbn")
            else (alternate_edition,)
        )

    cover_service.search_google_books = search_google_books
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
        cover_search_service=cover_service,
    )

    candidates = studio.search_cover_candidates(
        source_id="google_books",
        title="The Mystery of the Nervous Lion",
        author="Nick West",
        isbn="9780394923086",
    )

    assert calls == ["9780394923086", ""]
    assert len(candidates) == 1
    assert candidates[0].cover_url == alternate_edition.cover_url


def test_cover_search_retries_exact_title_without_conflicting_author(
    tmp_path,
) -> None:
    calls: list[str] = []
    underlying_author_edition = DirectCoverResult(
        title="The Mystery of the Nervous Lion",
        author="Kin Platt",
        isbn="9780001600164",
        publisher="Random House",
        language="en",
        published_date="1971",
        cover_url="https://covers.openlibrary.org/nervous-lion.jpg",
        source_url="https://openlibrary.org/works/nervous-lion",
        provider_name="Open Library",
        confidence=90,
        confidence_reason="Exact title match",
    )
    cover_service = CoverSearchService()

    def search_google_books(**kwargs):
        calls.append(str(kwargs.get("author") or ""))
        return () if kwargs.get("author") else (underlying_author_edition,)

    cover_service.search_google_books = search_google_books
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
        cover_search_service=cover_service,
    )

    candidates = studio.search_cover_candidates(
        source_id="google_books",
        title="The Mystery of the Nervous Lion",
        author="Nick West",
    )

    assert calls == ["Nick West", ""]
    assert len(candidates) == 1
    assert candidates[0].cover_url == underlying_author_edition.cover_url


def test_cover_preview_is_cached_separately_from_selected_cover(
    tmp_path,
    monkeypatch,
) -> None:
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
        "QVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    class ImageResponse:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit=None):
            return image_bytes

    monkeypatch.setattr(
        metadata_module,
        "urlopen",
        lambda *_args, **_kwargs: ImageResponse(),
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db")
    )
    candidate = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9780316035439",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="wizard",
        confidence=90,
        confidence_reason="Exact title and author match",
        provider_name="Google Books",
        remote_cover_url="https://books.google.com/wizard.png",
    )

    preview = studio.download_cover_preview(candidate, book_id=7)
    selected = studio.download_cover(candidate, book_id=7)

    assert preview.parent.name == "cover-previews"
    assert selected.parent.name == "covers"
    assert preview.read_bytes() == image_bytes
    assert selected.read_bytes() == image_bytes


def test_lookup_worker_downloads_a_cover_preview_without_selecting_it(
    tmp_path,
) -> None:
    candidate = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="wizard",
        confidence=90,
        confidence_reason="Exact title and author match",
        provider_name="Google Books",
        remote_cover_url="https://books.google.com/wizard.jpg",
    )
    preview_path = tmp_path / "wizard-preview.jpg"

    class Service:
        def download_cover_preview(self, wanted, *, book_id):
            assert wanted == candidate
            assert book_id == 7
            return preview_path

    received_covers = []
    worker = MetadataLookupWorker(
        Service(),
        cover_candidate=candidate,
        book_id=7,
        preview_cover=True,
    )
    worker.cover_ready.connect(received_covers.append)

    worker.run()

    assert received_covers == [str(preview_path)]
