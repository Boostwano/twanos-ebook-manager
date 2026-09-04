"""Approved native providers and API-key setup must work without Calibre."""

from __future__ import annotations

import json
import zipfile
from threading import Barrier

from PySide6.QtWidgets import QApplication

from database.database import DatabaseManager
from services.cover_search_service import (
    CoverSearchError,
    CoverSearchService,
    DirectCoverResult,
)
from services.integration_service import IntegrationService
from services.metadata_studio_service import (
    MetadataCandidate,
    MetadataLookupError,
    MetadataStudioService,
)
from services.plugin_credential_service import PluginCredentialStore
from services.plugin_service import PluginService
import services.metadata_studio_service as studio_module
from services.remote_metadata_provider_service import (
    RemoteMetadataResult,
    RemoteMetadataProviderService,
)
import services.remote_metadata_provider_service as provider_module
from ui.plugin_page import PluginPage


class _MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save(self, plugin_id: str, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter an API key before choosing Save.")
        self.values[plugin_id] = cleaned

    def load(self, plugin_id: str) -> str:
        return self.values.get(plugin_id, "")

    def has(self, plugin_id: str) -> bool:
        return bool(self.load(plugin_id))

    def entry_exists(self, plugin_id: str) -> bool:
        return plugin_id in self.values

    def delete(self, plugin_id: str) -> None:
        self.values.pop(plugin_id, None)


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _HtmlHeaders:
    @staticmethod
    def get_content_charset() -> str:
        return "utf-8"


class _HtmlResponse:
    status = 200
    headers = _HtmlHeaders()

    def __init__(self, page: str) -> None:
        self.page = page

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, *_args) -> bytes:
        return self.page.encode("utf-8")


def _plugin_service(tmp_path) -> PluginService:
    return PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
        credential_store=_MemoryCredentials(),
    )


def _disable_default_lookup_plugins(service: PluginService) -> None:
    """Keep exact-provider tests independent of the built-in default set."""
    for plugin in service.list_plugins():
        if plugin.installed and plugin.enabled and (
            "metadata_provider" in plugin.capabilities
            or "cover_provider" in plugin.capabilities
        ):
            service.set_enabled(plugin.plugin_id, False)


def test_api_key_plugin_requires_setup_before_enable(tmp_path) -> None:
    service = _plugin_service(tmp_path)

    installed = service.install_builtin("hardcover_metadata")

    assert installed.status == "Setup required"
    assert not installed.api_key_configured
    try:
        service.set_enabled("hardcover_metadata", True)
    except ValueError as error:
        assert "Configure an API key" in str(error)
    else:
        raise AssertionError("Provider was enabled without an API key")

    configured = service.set_api_key(
        "hardcover_metadata",
        "secret-token",
    )
    assert configured.api_key_configured
    active = service.set_enabled("hardcover_metadata", True)
    assert active.status == "Active"
    assert service.get_api_key("hardcover_metadata") == "secret-token"

    cleared = service.clear_api_key("hardcover_metadata")
    assert cleared.status == "Setup required"
    assert not cleared.enabled
    assert not cleared.api_key_configured


def test_plugin_page_explains_api_key_setup_state(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    service = _plugin_service(tmp_path)
    page = PluginPage(service, IntegrationService())
    row = next(
        index
        for index, plugin in enumerate(page.plugins)
        if plugin.plugin_id == "comic_vine_metadata"
    )
    page.plugin_table.selectRow(row)
    application.processEvents()

    page.install_button.click()
    application.processEvents()

    assert page.plugin_table.item(row, 4).text() == "Setup required"
    assert page.api_key_button.isEnabled()
    assert not page.enable_button.isEnabled()
    assert "Configure API Key" in page.status_label.text()


def test_plugin_table_shows_api_key_state_without_exposing_key(tmp_path) -> None:
    _application = QApplication.instance() or QApplication([])
    service = _plugin_service(tmp_path)
    service.install_builtin("google_books_covers")
    service.set_api_key("google_books_covers", "private-google-key")
    service.install_builtin("hardcover_metadata")
    page = PluginPage(service, IntegrationService())
    rows = {
        plugin.plugin_id: row
        for row, plugin in enumerate(page.plugins)
    }

    assert page.plugin_table.horizontalHeaderItem(2).text() == "Version"
    assert page.plugin_table.item(rows["google_books_covers"], 2).text() == "1.0"
    assert page.plugin_table.horizontalHeaderItem(5).text() == "API Key"
    assert (
        page.plugin_table.item(rows["google_books_covers"], 5).text()
        == "API Key Added"
    )
    assert (
        page.plugin_table.item(rows["hardcover_metadata"], 5).text()
        == "Not Added"
    )
    assert (
        page.plugin_table.item(rows["open_library_metadata"], 5).text()
        == "None Required"
    )
    visible_table_text = " ".join(
        page.plugin_table.item(row, column).text()
        for row in range(page.plugin_table.rowCount())
        for column in range(page.plugin_table.columnCount())
    )
    assert "private-google-key" not in visible_table_text


def test_provider_health_is_persisted_and_explained_on_plugins_page(
    tmp_path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    service = _plugin_service(tmp_path)
    service.install_builtin("amazon_metadata")
    service.set_enabled("amazon_metadata", True)
    service.report_provider_health(
        "amazon_metadata",
        "layout_changed",
        "Expected result cards were absent.",
    )

    reloaded = _plugin_service(tmp_path)
    plugin = next(
        value
        for value in reloaded.list_plugins()
        if value.plugin_id == "amazon_metadata"
    )
    assert plugin.status == "Active — provider update needed"
    assert plugin.provider_health == "layout_changed"
    page = PluginPage(reloaded, IntegrationService())
    row = next(
        index
        for index, value in enumerate(page.plugins)
        if value.plugin_id == "amazon_metadata"
    )
    assert page.plugin_table.horizontalHeaderItem(6).text() == "Provider Check"
    assert page.plugin_table.item(row, 6).text() == "Provider Update Needed"
    page.plugin_table.selectRow(row)
    assert "Expected result cards were absent" in page.status_label.text()
    page.close()


def test_amazon_public_provider_maps_a_cover_without_an_api_key(
    monkeypatch,
) -> None:
    page = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B000TEST">
        <h2><a href="/dp/B000TEST"><span>X-Country</span></a></h2>
        <span>by</span><a>Robert Reed</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/example._SX300_.jpg">
      </div>
    </body></html>
    """
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(page),
    )

    results = RemoteMetadataProviderService().search_amazon(
        title="X-Country",
        author="Robert Reed",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Amazon AU"
    assert results[0].confidence == 90
    assert results[0].cover_url.endswith("/example.jpg")


def test_amazon_searches_english_marketplaces_au_first(monkeypatch) -> None:
    seen_urls: list[str] = []

    def response_for(request, *_args, **_kwargs):
        seen_urls.append(request.full_url)
        host = request.host
        marker = host.replace(".", "-")
        page = f"""
        <html><body>
          <div data-component-type="s-search-result" data-asin="B000TEST">
            <h2><a href="/dp/B000TEST"><span>X-Country</span></a></h2>
            <span>by</span><a>Robert Reed</a>
            <img class="s-image"
                 src="https://m.media-amazon.com/images/I/{marker}.jpg">
          </div>
        </body></html>
        """
        return _HtmlResponse(page)

    monkeypatch.setattr(provider_module, "urlopen", response_for)

    results = RemoteMetadataProviderService().search_amazon(
        title="X-Country",
        author="Robert Reed",
    )

    assert [value.split("/", 3)[2] for value in seen_urls] == [
        "www.amazon.com.au",
        "www.amazon.com",
        "www.amazon.co.uk",
        "www.amazon.ca",
    ]
    assert [result.provider_name for result in results] == [
        "Amazon AU",
        "Amazon US",
        "Amazon UK",
        "Amazon CA",
    ]
    assert results[0].source_url.startswith("https://www.amazon.com.au/")
    assert results[2].source_url.startswith("https://www.amazon.co.uk/")


def test_amazon_keeps_searching_when_one_marketplace_is_blocked(
    monkeypatch,
) -> None:
    service = RemoteMetadataProviderService()
    seen_providers: list[str] = []
    us_page = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B000TEST">
        <h2><a href="/dp/B000TEST"><span>X-Country</span></a></h2>
        <span>by</span><a>Robert Reed</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/us-cover.jpg">
      </div>
    </body></html>
    """

    def read_marketplace(request, *, provider_name):
        del request
        seen_providers.append(provider_name)
        if provider_name == "Amazon AU":
            raise provider_module.RemoteProviderError(
                "Amazon AU blocked the request.",
                health_status="blocked",
            )
        if provider_name == "Amazon US":
            return us_page
        return "<html><body>No results for this search</body></html>"

    monkeypatch.setattr(service, "_read_public_page", read_marketplace)

    results = service.search_amazon(
        title="X-Country",
        author="Robert Reed",
    )

    assert seen_providers == [
        "Amazon AU",
        "Amazon US",
        "Amazon UK",
        "Amazon CA",
    ]
    assert len(results) == 1
    assert results[0].provider_name == "Amazon US"


def test_amazon_title_exposes_series_and_reading_order(monkeypatch) -> None:
    page = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B01MQFHCT1">
        <h2><a href="/dp/B01MQFHCT1"><span>
          Inca Gold (Dirk Pitt Adventures Book 12)
        </span></a></h2>
        <span>by</span><a>Clive Cussler</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/inca._SX300_.jpg">
      </div>
    </body></html>
    """
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(page),
    )

    results = RemoteMetadataProviderService().search_amazon(
        title="Inca Gold",
        author="Clive Cussler",
    )

    assert len(results) == 1
    assert results[0].title == "Inca Gold"
    assert results[0].series == "Dirk Pitt Adventures"
    assert results[0].series_number == "12"


def test_amazon_current_card_layout_maps_title_author_and_series(monkeypatch) -> None:
    page = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B01MQFHCT1">
        <a class="s-link-style" href="/Inca-Gold/dp/B01MQFHCT1">
          <h2 aria-label="Inca Gold (Dirk Pitt Adventures)">
            <span>Inca Gold (Dirk Pitt Adventures)</span>
          </h2>
        </a>
        <a href="/dp/SERIES"><span>
          Book 12 of 28: A Dirk Pitt Adventure
        </span></a>
        <span>by </span><a>Clive Cussler</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/inca._SX300_.jpg">
      </div>
      <div data-component-type="s-search-result" data-asin="B000OTHER">
        <a href="/Treasure/dp/B000OTHER">
          <h2 aria-label="Treasure of Khan"><span>Treasure of Khan</span></h2>
        </a>
        <span>by </span><a>Clive Cussler</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/other._SX300_.jpg">
      </div>
    </body></html>
    """
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(page),
    )

    results = RemoteMetadataProviderService().search_amazon(
        title="Inca Gold",
        author="Clive Cussler",
    )

    assert len(results) == 1
    assert results[0].title == "Inca Gold"
    assert results[0].author == "Clive Cussler"
    assert results[0].series == "Dirk Pitt Adventures"
    assert results[0].series_number == "12"


_GOODREADS_SEARCH_PAGE = """
<html><body>
<table class="tableList">
<tr itemscope itemtype="http://schema.org/Book">
<td width="5%"><a href="/book/show/500744.The_Mystery_of_Death_Trap_Mine">
<img class="bookCover" src="https://example/cover-thumb.jpg"/></a></td>
<td width="100%">
<a class="bookTitle" itemprop="url"
   href="/book/show/500744.The_Mystery_of_Death_Trap_Mine?from_search=true">
<span itemprop='name' role='heading' aria-level='4'>The Mystery of Death
Trap Mine (Alfred Hitchcock and The Three Investigators, #24)</span>
</a>
<span class='by'>by</span>
<span itemprop='author' itemscope='' itemtype='http://schema.org/Person'>
<div class='authorName__container'>
<a class="authorName" itemprop="url" href="/author/show/1.M_V_Carey">
<span itemprop="name">M.V. Carey</span></a>
</div>
</span>
</td>
</tr>
</table>
</body></html>
"""


def _goodreads_book_page(*, with_unrelated_book_node: bool = False) -> str:
    apollo_state = {
        "ROOT_QUERY": {"__typename": "Query"},
        "Book:kca://book/amzn1.gr.book.v1.primary": {
            "__typename": "Book",
            "legacyId": "500744",
            "title": "The Mystery of Death Trap Mine",
            "description": "The Investigators untangle <b>a mine</b>.",
            "imageUrl": "http://images.example/cover.jpg",
            "primaryContributorEdge": {
                "node": {"__ref": "Contributor:kca://author/v1.carey"}
            },
            "bookSeries": [
                {
                    "userPosition": "24",
                    "series": {"__ref": "Series:kca://series/v1.investigators"},
                }
            ],
            "details": {
                "isbn13": "9780394833217",
                "isbn": "039483321X",
                "publisher": "Random House Books for Young Readers",
                "publicationTime": 211359600000,
                "language": {"name": "English"},
            },
            "work": {"__ref": "Work:kca://work/v1.primary"},
        },
        "Series:kca://series/v1.investigators": {
            "__typename": "Series",
            "title": "Alfred Hitchcock and The Three Investigators",
        },
        "Contributor:kca://author/v1.carey": {
            "__typename": "Contributor",
            "name": "M.V. Carey",
        },
        "Work:kca://work/v1.primary": {
            "__typename": "Work",
            "stats": {"averageRating": 3.73, "ratingsCount": 1142},
        },
    }
    if with_unrelated_book_node:
        # A "similar books" node the same page also embeds -- must not be
        # mistaken for the page's own book just because it appears later.
        apollo_state["Book:kca://book/amzn1.gr.book.v1.unrelated"] = {
            "__typename": "Book",
            "legacyId": "999999",
            "title": "Some Unrelated Similar Book",
        }
    payload = {"props": {"pageProps": {"apolloState": apollo_state}}}
    return (
        "<html><head>"
        f'<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}</script>"
        "</head><body>Goodreads book page</body></html>"
    )


def test_goodreads_provider_reads_structured_series_and_rating(
    monkeypatch,
) -> None:
    def response_for(request, *_args, **_kwargs):
        if "/search" in request.full_url:
            return _HtmlResponse(_GOODREADS_SEARCH_PAGE)
        return _HtmlResponse(_goodreads_book_page())

    monkeypatch.setattr(provider_module, "urlopen", response_for)

    results = RemoteMetadataProviderService().search_goodreads(
        title="The Mystery of Death Trap Mine",
        author="M. V. Carey",
    )

    assert len(results) == 1
    result = results[0]
    assert result.title == "The Mystery of Death Trap Mine"
    assert result.author == "M.V. Carey"
    assert result.series == "Alfred Hitchcock and The Three Investigators"
    assert result.series_number == "24"
    assert result.isbn == "9780394833217"
    assert result.publisher == "Random House Books for Young Readers"
    assert result.language == "English"
    assert result.provider_rating == 3.73
    assert result.rating_count == 1142
    assert result.provider_name == "Goodreads"
    assert result.confidence == 90


def test_goodreads_provider_picks_the_pages_own_book_not_a_related_one(
    monkeypatch,
) -> None:
    def response_for(request, *_args, **_kwargs):
        if "/search" in request.full_url:
            return _HtmlResponse(_GOODREADS_SEARCH_PAGE)
        return _HtmlResponse(
            _goodreads_book_page(with_unrelated_book_node=True)
        )

    monkeypatch.setattr(provider_module, "urlopen", response_for)

    results = RemoteMetadataProviderService().search_goodreads(
        title="The Mystery of Death Trap Mine",
        author="M. V. Carey",
    )

    assert len(results) == 1
    assert results[0].title == "The Mystery of Death Trap Mine"
    assert results[0].series == "Alfred Hitchcock and The Three Investigators"


def test_goodreads_provider_raises_blocked_error_on_a_captcha_page(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(
            "<html>Sorry, we just need to make sure you're not a robot. "
            "CAPTCHA</html>"
        ),
    )

    try:
        RemoteMetadataProviderService().search_goodreads(
            title="The Mystery of Death Trap Mine",
            author="M. V. Carey",
        )
    except provider_module.RemoteProviderError as error:
        assert error.health_status == "blocked"
    else:
        raise AssertionError("Expected a blocked RemoteProviderError")


def test_goodreads_provider_returns_no_results_when_search_finds_nothing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(
            "<html><body>No results found</body></html>"
        ),
    )

    results = RemoteMetadataProviderService().search_goodreads(
        title="Zzqxnonexistentbooktitle123",
        author="Nobody",
    )

    assert results == ()


def test_goodreads_metadata_is_not_installed_or_enabled_by_default(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)

    record = next(
        value
        for value in plugins.list_plugins()
        if value.plugin_id == "goodreads_metadata"
    )

    assert record.installed is False
    assert record.enabled is False
    assert "Terms of Service" in record.description


def test_public_provider_distinguishes_blocking_from_no_results(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(
            "<html>Sorry, we just need to make sure you're not a robot. CAPTCHA</html>"
        ),
    )

    try:
        RemoteMetadataProviderService().search_amazon(
            title="X-Country",
            author="Robert Reed",
        )
    except Exception as error:
        assert getattr(error, "health_status", "") == "blocked"
        assert "blocked" in str(error).casefold()
    else:
        raise AssertionError("A bot-check page was treated as book results")


def test_google_books_accepts_optional_key_without_requiring_it(tmp_path) -> None:
    service = _plugin_service(tmp_path)
    installed = service.install_builtin("google_books_covers")

    active = service.set_enabled("google_books_covers", True)
    assert active.enabled
    assert active.optional_api_key

    configured = service.set_api_key(
        "google_books_covers",
        "google-key",
    )
    assert configured.enabled
    assert configured.api_key_configured
    assert service.get_api_key("google_books_covers") == "google-key"
    cleared = service.clear_api_key("google_books_covers")
    assert cleared.enabled
    assert not cleared.api_key_configured


def test_expanded_provider_catalog_has_accurate_key_requirements(
    tmp_path,
) -> None:
    plugins = {
        plugin.plugin_id: plugin
        for plugin in _plugin_service(tmp_path).list_plugins()
    }

    assert not plugins["gutenberg_metadata"].requires_api_key
    assert not plugins["harvard_librarycloud_metadata"].requires_api_key
    assert not plugins["crossref_metadata"].requires_api_key
    assert plugins["big_book_metadata"].requires_api_key
    assert plugins["openweb_ninja_metadata"].requires_api_key


def test_gutenberg_maps_summary_and_cover(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "results": [
                    {
                        "id": 1342,
                        "title": "Pride and Prejudice",
                        "authors": [{"name": "Austen, Jane"}],
                        "summaries": ["A novel of manners."],
                        "languages": ["en"],
                        "formats": {
                            "image/jpeg": (
                                "https://www.gutenberg.org/cache/epub/"
                                "1342/pg1342.cover.medium.jpg"
                            )
                        },
                    }
                ]
            }
        ),
    )

    results = RemoteMetadataProviderService().search_gutenberg(
        title="Pride and Prejudice",
        author="Austen, Jane",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Project Gutenberg"
    assert results[0].description == "A novel of manners."
    assert results[0].cover_url.endswith("pg1342.cover.medium.jpg")


def test_harvard_librarycloud_maps_open_dc_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "items": [
                    {
                        "title": ["Example Book"],
                        "creator": ["Example, Alice"],
                        "identifier": [
                            "ISBN 9781234567897",
                            "https://id.lib.harvard.edu/example",
                        ],
                        "publisher": ["Example Press"],
                        "date": ["2020"],
                        "description": ["A catalogue description."],
                    }
                ]
            }
        ),
    )

    results = (
        RemoteMetadataProviderService().search_harvard_librarycloud(
            isbn="9781234567897"
        )
    )

    assert len(results) == 1
    assert results[0].provider_name == "Harvard LibraryCloud"
    assert results[0].isbn == "9781234567897"
    assert results[0].publisher == "Example Press"
    assert results[0].description == "A catalogue description."


def test_crossref_maps_academic_book_metadata_without_cover(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "message": {
                    "items": [
                        {
                            "type": "book",
                            "title": ["Research Methods"],
                            "author": [
                                {"given": "Alice", "family": "Example"}
                            ],
                            "ISBN": ["9781234567897"],
                            "publisher": "Academic Press",
                            "published-print": {
                                "date-parts": [[2021, 4, 2]]
                            },
                            "abstract": "<jats:p>Study guide.</jats:p>",
                            "DOI": "10.1234/example",
                        }
                    ]
                }
            }
        ),
    )

    results = RemoteMetadataProviderService().search_crossref(
        title="Research Methods",
        author="Alice Example",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Crossref"
    assert results[0].published_date == "2021-4-2"
    assert results[0].description == "Study guide."
    assert not results[0].cover_url


def test_big_book_uses_protected_header_and_detail_metadata(
    monkeypatch,
) -> None:
    captured_headers = []

    def request(request, **_kwargs):
        captured_headers.append(request.get_header("X-api-key"))
        if "search-books" in request.full_url:
            return _Response(
                {
                    "books": [
                        [
                            {
                                "id": 42,
                                "title": "Example Book",
                                "image": "https://covers.example/42.jpg",
                                "authors": [{"name": "Alice Example"}],
                            }
                        ]
                    ]
                }
            )
        return _Response(
            {
                "id": 42,
                "title": "Example Book",
                "image": "https://covers.example/42.jpg",
                "authors": [{"name": "Alice Example"}],
                "identifiers": {"isbn_13": "9781234567897"},
                "publish_date": 2020,
                "description": "A detailed description.",
            }
        )

    monkeypatch.setattr(provider_module, "urlopen", request)

    results = RemoteMetadataProviderService().search_big_book(
        api_key="big-book-secret",
        title="Example Book",
        author="Alice Example",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Big Book API"
    assert results[0].description == "A detailed description."
    assert captured_headers == ["big-book-secret", "big-book-secret"]
    assert all(
        "big-book-secret" not in url
        for url in (
            "https://api.bigbookapi.com/search-books",
            "https://api.bigbookapi.com/42",
        )
    )


def test_openweb_ninja_maps_only_returned_book_data(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "results": [
                    {
                        "id": "volume-1",
                        "title": "Example Book",
                        "book_authors": [{"name": "Alice Example"}],
                        "publication_year": 2022,
                        "image_url": "https://books.example/cover.jpg",
                        "view_url": "https://books.example/volume-1",
                    }
                ]
            }
        ),
    )

    results = RemoteMetadataProviderService().search_openweb_ninja(
        api_key="openweb-secret",
        title="Example Book",
        author="Alice Example",
    )

    assert len(results) == 1
    assert results[0].provider_name == "OpenWeb Ninja"
    assert results[0].cover_url == "https://books.example/cover.jpg"


def test_windows_credential_store_verifies_saved_key_round_trip(tmp_path) -> None:
    store = PluginCredentialStore(tmp_path / "credentials.json")

    store.save("google_books_covers", "temporary-test-key")

    assert store.entry_exists("google_books_covers")
    assert not store.is_unreadable("google_books_covers")
    assert store.load("google_books_covers") == "temporary-test-key"


def test_plugin_reports_saved_key_that_windows_cannot_unlock(tmp_path) -> None:
    credentials = _MemoryCredentials()
    service = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
        credential_store=credentials,
    )
    service.install_builtin("google_books_covers")
    service.set_enabled("google_books_covers", True)
    credentials.values["google_books_covers"] = "unreadable-placeholder"
    credentials.load = lambda _plugin_id: ""

    google = next(
        plugin
        for plugin in service.list_plugins()
        if plugin.plugin_id == "google_books_covers"
    )

    assert google.enabled
    assert google.api_key_unreadable
    assert google.status == "Active — key needs re-entry"


def test_hardcover_provider_maps_metadata_and_cover(monkeypatch) -> None:
    responses = iter(
        (
            _Response({"data": {"search": {"ids": ["42"]}}}),
            _Response(
                {
                    "data": {
                        "books": [
                            {
                                "id": 42,
                                "title": "The Hobbit",
                                "slug": "the-hobbit",
                                "description": "<p>A journey.</p>",
                                "cached_featured_series": {
                                    "position": 1,
                                    "series": {"name": "Middle-earth"},
                                },
                                "editions": [
                                    {
                                        "title": "The Hobbit",
                                        "isbn_13": "9780261103344",
                                        "isbn_10": "",
                                        "cached_contributors": [
                                            {
                                                "contribution": "Author",
                                                "author": {
                                                    "name": "J. R. R. Tolkien"
                                                },
                                            }
                                        ],
                                        "cached_image": {
                                            "url": "https://images.example/cover.jpg"
                                        },
                                        "release_date": "1937-09-21",
                                        "language": {"code3": "eng"},
                                        "publisher": {
                                            "name": "George Allen & Unwin"
                                        },
                                        "users_count": 100,
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
        )
    )
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: next(responses),
    )

    results = RemoteMetadataProviderService().search_hardcover(
        api_key="token",
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Hardcover"
    assert results[0].confidence == 100
    assert results[0].series == "Middle-earth"
    assert results[0].description == "A journey."
    assert results[0].cover_url.endswith("cover.jpg")


def test_hardcover_provider_treats_null_search_ids_as_no_results(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {"data": {"search": {"ids": None}}}
        ),
    )

    results = RemoteMetadataProviderService().search_hardcover(
        api_key="token",
        title="The Mystery of the Trail of Terror",
        author="M. V. Carey",
    )

    assert results == ()


def test_comic_vine_provider_maps_volume_and_cover(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "status_code": 1,
                "error": "OK",
                "results": [
                    {
                        "id": 1,
                        "name": "Saga",
                        "publisher": {"name": "Image"},
                        "start_year": "2012",
                        "image": {
                            "original_url": "https://images.example/saga.jpg"
                        },
                        "site_detail_url": (
                            "https://comicvine.gamespot.com/saga/4050-"
                        ),
                        "description": "<p>Space opera.</p>",
                    }
                ],
            }
        ),
    )

    results = RemoteMetadataProviderService().search_comic_vine(
        api_key="comic-key",
        title="Saga",
    )

    assert len(results) == 1
    assert results[0].provider_name == "Comic Vine"
    assert results[0].confidence == 90
    assert results[0].publisher == "Image"
    assert results[0].description == "Space opera."


def test_comic_vine_finds_exact_issue_after_matching_volume(
    monkeypatch,
) -> None:
    requested_urls: list[str] = []
    responses = iter(
        (
            _Response(
                {
                    "status_code": 1,
                    "error": "OK",
                    "results": [
                        {
                            "id": 77,
                            "name": "The Phantom",
                            "publisher": {"name": "Frew Publications"},
                            "start_year": "1948",
                        },
                        {
                            "id": 88,
                            "name": "The Phantom",
                            "publisher": {"name": "Moonstone"},
                            "start_year": "2003",
                        },
                    ],
                }
            ),
            _Response(
                {
                    "status_code": 1,
                    "error": "OK",
                    "results": [
                        {
                            "id": 1048,
                            "name": "The Search for Byron",
                            "issue_number": "1048",
                            "volume": {"id": 77, "name": "The Phantom"},
                            "image": {
                                "original_url": (
                                    "https://images.example/phantom-1048.jpg"
                                )
                            },
                            "site_detail_url": (
                                "https://comicvine.gamespot.com/the-phantom-1048/"
                            ),
                            "description": "<p>An exact issue.</p>",
                            "cover_date": "1993-01-01",
                            "person_credits": [
                                {"name": "Example Writer", "role": "writer"}
                            ],
                        }
                    ],
                }
            ),
        )
    )

    def urlopen(request, **_kwargs):
        requested_urls.append(request.full_url)
        return next(responses)

    monkeypatch.setattr(provider_module, "urlopen", urlopen)
    results = RemoteMetadataProviderService().search_comic_vine(
        api_key="comic-key",
        title="The Phantom",
        issue_number="1048",
        publisher="Frew Publications",
    )

    assert len(results) == 1
    assert results[0].title == "The Phantom #1048: The Search for Byron"
    assert results[0].series == "The Phantom"
    assert results[0].series_number == "1048"
    assert results[0].publisher == "Frew Publications"
    assert results[0].author == "Example Writer"
    assert results[0].description == "An exact issue."
    assert results[0].cover_url.endswith("phantom-1048.jpg")
    assert results[0].confidence == 100
    assert len(requested_urls) == 2
    assert "volume%3A77%2Cissue_number%3A1048" in requested_urls[1]


def test_active_hardcover_plugin_feeds_simple_metadata_lookup(tmp_path) -> None:
    credentials = _MemoryCredentials()
    plugins = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
        credential_store=credentials,
    )
    plugins.install_builtin("hardcover_metadata")
    plugins.set_api_key("hardcover_metadata", "token")
    plugins.set_enabled("hardcover_metadata", True)

    remote = RemoteMetadataProviderService()
    remote.search_hardcover = lambda **_kwargs: ()
    remote.search_comic_vine = lambda **_kwargs: ()
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        remote_provider_service=remote,
    )

    assert studio.search_enabled_candidates(title="Example") == ()
    source_ids = {source.source_id for source in studio.cover_sources()}
    assert "hardcover" in source_ids
    assert "comic_vine" not in source_ids


def test_api_provider_search_updates_plugin_health(tmp_path) -> None:
    credentials = _MemoryCredentials()
    plugins = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
        credential_store=credentials,
    )
    for plugin_id in ("hardcover_metadata", "comic_vine_metadata"):
        plugins.install_builtin(plugin_id)
        plugins.set_api_key(plugin_id, f"{plugin_id}-key")
        plugins.set_enabled(plugin_id, True)

    remote = RemoteMetadataProviderService()
    remote.search_hardcover = lambda **_kwargs: ()
    remote.search_comic_vine = lambda **_kwargs: ()
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        remote_provider_service=remote,
    )

    studio._search_hardcover(title="Example", author="", isbn="")
    studio._search_comic_vine(title="Saga", author="", isbn="")

    health = {
        plugin.plugin_id: plugin.provider_health
        for plugin in plugins.list_plugins()
    }
    assert health["hardcover_metadata"] == "healthy"
    assert health["comic_vine_metadata"] == "healthy"


def test_active_google_books_uses_filename_for_metadata_lookup(tmp_path) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("google_books_covers")
    plugins.set_enabled("google_books_covers", True)
    captured: dict[str, str] = {}
    cover_service = CoverSearchService()

    def search_google_books(**kwargs):
        captured.update(kwargs)
        return (
            DirectCoverResult(
                title="Wizard Squared",
                author="K. E. Mills",
                isbn="9781841497273",
                publisher="Orbit",
                language="en",
                published_date="2010",
                cover_url="https://books.google.com/wizard-squared.jpg",
                source_url="https://books.google.com/books?id=wizard",
                provider_name="Google Books",
                confidence=90,
                confidence_reason="Exact title and author match",
            ),
        )

    cover_service.search_google_books = search_google_books
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="03 Wizard Squared",
        author="Mills, K.E.",
        file_name="Wizard Squared - K. E. Mills.epub",
        include_open_library=False,
    )

    assert captured == {
        "title": "Wizard Squared",
        "author": "K. E. Mills",
        "isbn": "",
        "api_key": "",
    }
    assert results[0].provider_name == "Google Books"
    assert results[0].title == "Wizard Squared"
    google_plugin = next(
        plugin
        for plugin in plugins.list_plugins()
        if plugin.plugin_id == "google_books_covers"
    )
    assert google_plugin.name == "Google Books Metadata & Covers"
    assert "metadata_provider" in google_plugin.capabilities


def test_combined_lookup_searches_every_active_cover_provider(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    for plugin_id in (
        "open_library_metadata",
        "google_books_covers",
        "hardcover_metadata",
        "comic_vine_metadata",
        "apple_books_metadata",
        "isbndb_metadata",
    ):
        plugins.install_builtin(plugin_id)
        if plugin_id in {
            "hardcover_metadata",
            "comic_vine_metadata",
            "isbndb_metadata",
        }:
            plugins.set_api_key(plugin_id, f"{plugin_id}-key")
        plugins.set_enabled(plugin_id, True)

    open_library = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9781841497297",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="open-wizard",
        confidence=90,
        confidence_reason="Exact title and author match",
        provider_name="Open Library",
    )

    def candidate(provider: str, cover_url: str) -> MetadataCandidate:
        return MetadataCandidate(
            title="Wizard Squared",
            author="K. E. Mills",
            isbn="9781841497297",
            publisher="Orbit",
            language="en",
            published_date="2010",
            cover_id=None,
            work_key=provider.casefold().replace(" ", "-"),
            confidence=100,
            confidence_reason="Exact ISBN match",
            provider_name=provider,
            remote_cover_url=cover_url,
        )

    calls: dict[str, dict[str, str]] = {}
    cover_service = CoverSearchService()

    def google_search(**kwargs):
        calls["Google Books"] = kwargs
        return (
            DirectCoverResult(
                title="Wizard Squared",
                author="K. E. Mills",
                isbn="9781841497297",
                publisher="Orbit",
                language="en",
                published_date="2010",
                cover_url="https://google.example/wizard.jpg",
                source_url="https://google.example/wizard",
                provider_name="Google Books",
                confidence=100,
                confidence_reason="Exact ISBN match",
            ),
        )

    cover_service.search_google_books = google_search

    def apple_search(**kwargs):
        calls["Apple Books"] = kwargs
        return (
            DirectCoverResult(
                title="Wizard Squared",
                author="K. E. Mills",
                isbn="",
                publisher="Orbit",
                language="en",
                published_date="2010",
                cover_url="https://apple.example/wizard.jpg",
                source_url="https://apple.example/wizard",
                provider_name="Apple Books",
                confidence=90,
                confidence_reason="Exact title and author match",
                description="Apple description",
            ),
        )

    def isbndb_search(**kwargs):
        calls["ISBNdb"] = kwargs
        return (
            DirectCoverResult(
                title="Wizard Squared",
                author="K. E. Mills",
                isbn="9781841497297",
                publisher="Orbit",
                language="en",
                published_date="2010",
                cover_url="https://isbndb.example/wizard.jpg",
                source_url="https://isbndb.example/wizard",
                provider_name="ISBNdb",
                confidence=100,
                confidence_reason="Exact ISBN match",
                description="ISBNdb description",
            ),
        )

    cover_service.search_apple_books = apple_search
    cover_service.search_isbndb = isbndb_search
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )
    studio.search_candidates = lambda **_kwargs: (open_library,)

    def hardcover_search(**kwargs):
        calls["Hardcover"] = kwargs
        return (candidate("Hardcover", "https://hardcover.example/wizard.jpg"),)

    def comic_vine_search(**kwargs):
        calls["Comic Vine"] = kwargs
        return (candidate("Comic Vine", "https://comic.example/wizard.jpg"),)

    studio._search_hardcover = hardcover_search
    studio._search_comic_vine = comic_vine_search

    results = studio.search_enabled_candidates(
        title="03 Wizard Squared",
        author="Mills, K.E.",
        file_name="Wizard Squared - K. E. Mills.epub",
    )

    assert set(calls) == {
        "Google Books",
        "Hardcover",
        "Apple Books",
        "ISBNdb",
    }
    expected_terms = {
        "title": "Wizard Squared",
        "author": "K. E. Mills",
        "isbn": "9781841497297",
    }
    assert calls["Google Books"] == {
        **expected_terms,
        "api_key": "",
    }
    assert calls["Apple Books"] == expected_terms
    assert calls["ISBNdb"] == {
        **expected_terms,
        "api_key": "isbndb_metadata-key",
    }
    assert calls["Hardcover"] == expected_terms
    assert {
        result.provider_name for result in results if result.cover_url
    } == {
        "Google Books",
        "Hardcover",
        "Apple Books",
        "ISBNdb",
    }
    assert studio.last_search_report.searched_providers == (
        "Open Library",
        "Google Books",
        "Apple Books",
        "ISBNdb",
        "Hardcover",
        "Wikipedia Series Resolver",
        "Wikidata Series Resolver",
    )
    assert studio.last_search_report.cover_providers == (
        "Google Books",
        "Apple Books",
        "ISBNdb",
        "Hardcover",
    )
    apple_result = next(
        result for result in results
        if result.provider_name == "Apple Books"
    )
    assert apple_result.isbn == "9781841497297"
    assert apple_result.description == "ISBNdb description"


def test_discovered_isbn_enriches_series_from_open_library(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    for plugin_id in (
        "open_library_metadata",
        "harvard_librarycloud_metadata",
    ):
        plugins.install_builtin(plugin_id)
        plugins.set_enabled(plugin_id, True)

    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    open_library_calls: list[str] = []

    def open_library_search(**kwargs):
        requested_isbn = kwargs["isbn"]
        open_library_calls.append(requested_isbn)
        if not requested_isbn:
            return ()
        return (
            MetadataCandidate(
                title="1634: The Galileo Affair",
                author="Eric Flint, Andrew Dennis",
                isbn="0743488156",
                publisher="Baen Books",
                language="eng",
                published_date="2004",
                cover_id=479126,
                work_key="OL3681694M",
                confidence=100,
                confidence_reason="Exact ISBN match",
                provider_name="Open Library",
                series="Ring of Fire",
            ),
        )

    studio.search_candidates = open_library_search
    studio._open_library_isbn_edition = lambda _isbn: {
        "series": ["Ring of Fire"],
    }
    studio._wikipedia_series_hint = lambda **_kwargs: ("1632", "3")
    studio._search_remote_provider = lambda **_kwargs: (
        MetadataCandidate(
            title="1634: The Galileo Affair",
            author="Eric Flint, Andrew Dennis",
            isbn="0743488156",
            publisher="Baen Books",
            language="eng",
            published_date="2004",
            cover_id=None,
            work_key="harvard-galileo",
            confidence=100,
            confidence_reason="Exact title and author match",
            provider_name="Harvard LibraryCloud",
        ),
    )

    results = studio.search_enabled_candidates(
        title="1634 The Galileo Affair",
        author="Eric Flint, Andrew Dennis",
        file_name="1634-The Galileo Affair - Eric Flint.epub",
    )

    harvard = next(
        result
        for result in results
        if result.provider_name == "Harvard LibraryCloud"
    )
    assert open_library_calls == ["", "0743488156"]
    assert harvard.series == "Ring of Fire"
    assert harvard.series_number == "3"


def test_wikipedia_series_hint_reads_explicit_numbered_public_result(
    tmp_path,
    monkeypatch,
) -> None:
    payload = {
        "query": {
            "pages": {
                "123": {
                    "title": "1634: The Galileo Affair",
                    "extract": (
                        "1634: The Galileo Affair is the fourth book and "
                        "third novel published in the 1632 series."
                    ),
                }
            }
        }
    }
    requested_urls: list[str] = []

    def response_for(request, *_args, **_kwargs):
        requested_urls.append(request.full_url)
        return _Response(payload)

    monkeypatch.setattr(studio_module, "urlopen", response_for)
    studio = MetadataStudioService(DatabaseManager(tmp_path / "library.db"))

    result = studio._wikipedia_series_hint(
        title="1634: The Galileo Affair",
        author="Eric Flint, Andrew Dennis",
    )

    assert result == ("1632", "3")
    assert requested_urls
    assert requested_urls[0].startswith("https://en.wikipedia.org/w/api.php?")


def test_wikidata_series_hint_reads_structured_series_claim(
    tmp_path,
    monkeypatch,
) -> None:
    search_payload = {
        "search": [
            {"id": "Q123", "label": "The Mystery of Death Trap Mine"}
        ]
    }
    claims_payload = {
        "entities": {
            "Q123": {
                "claims": {
                    "P31": [
                        {"mainsnak": {"datavalue": {"value": {"id": "Q571"}}}}
                    ],
                    "P179": [
                        {
                            "mainsnak": {
                                "datavalue": {"value": {"id": "Q999"}}
                            },
                            "qualifiers": {
                                "P1545": [
                                    {"datavalue": {"value": "24"}}
                                ]
                            },
                        }
                    ],
                }
            }
        }
    }
    label_payload = {
        "entities": {
            "Q999": {"labels": {"en": {"value": "The Three Investigators"}}}
        }
    }
    responses = iter(
        (
            _Response(search_payload),
            _Response(claims_payload),
            _Response(label_payload),
        )
    )
    monkeypatch.setattr(
        studio_module,
        "urlopen",
        lambda *_args, **_kwargs: next(responses),
    )
    studio = MetadataStudioService(DatabaseManager(tmp_path / "library.db"))

    result = studio._wikidata_series_hint(
        title="The Mystery of Death Trap Mine",
        author="M. V. Carey",
    )

    assert result == ("The Three Investigators", "24")


def test_wikidata_series_hint_rejects_a_non_book_item(
    tmp_path,
    monkeypatch,
) -> None:
    search_payload = {
        "search": [{"id": "Q1", "label": "Death Trap Mine"}]
    }
    claims_payload = {
        "entities": {
            "Q1": {
                "claims": {
                    "P31": [
                        {"mainsnak": {"datavalue": {"value": {"id": "Q515"}}}}
                    ]
                }
            }
        }
    }
    responses = iter((_Response(search_payload), _Response(claims_payload)))
    monkeypatch.setattr(
        studio_module,
        "urlopen",
        lambda *_args, **_kwargs: next(responses),
    )
    studio = MetadataStudioService(DatabaseManager(tmp_path / "library.db"))

    result = studio._wikidata_series_hint(
        title="Death Trap Mine",
        author="M. V. Carey",
    )

    assert result == ("", "")


def test_serpapi_series_hint_reads_parenthetical_result(
    tmp_path,
    monkeypatch,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("serpapi_book_resolver")
    plugins.set_api_key("serpapi_book_resolver", "test-key")
    plugins.set_enabled("serpapi_book_resolver", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    payload = {
        "organic_results": [
            {
                "title": "M.V. Carey",
                "snippet": (
                    "The Mystery of Death Trap Mine (1976) by M.V. Carey. "
                    "463 people #24 currently reading."
                ),
            },
            {
                "title": (
                    "The Mystery of Death Trap Mine (The Three "
                    "Investigators No. 24) by Mary V. Carey."
                ),
                "snippet": "ISBN 13: 9780394844497",
            },
        ]
    }
    monkeypatch.setattr(
        studio_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    result = studio._serpapi_series_hint(
        title="The Mystery of Death Trap Mine",
        author="M. V. Carey",
    )

    assert result == ("The Three Investigators", "24")


def test_serpapi_series_hint_strips_redundant_trailing_series_word(
    tmp_path,
    monkeypatch,
) -> None:
    """A "(Name series, #N)" snippet must not fold "series" into the name.

    Otherwise this one book organises into its own "Name series" folder
    instead of joining every other volume's shared "Name" series folder.
    """
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("serpapi_book_resolver")
    plugins.set_api_key("serpapi_book_resolver", "test-key")
    plugins.set_enabled("serpapi_book_resolver", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    payload = {
        "organic_results": [
            {
                "title": (
                    "The Mystery of Death Trap Mine (Alfred Hitchcock and "
                    "the Three Investigators series #24) by Mary V. Carey."
                ),
                "snippet": "ISBN 13: 9780394844497",
            },
        ]
    }
    monkeypatch.setattr(
        studio_module,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    result = studio._serpapi_series_hint(
        title="The Mystery of Death Trap Mine",
        author="M. V. Carey",
    )

    assert result == ("Alfred Hitchcock and the Three Investigators", "24")


def test_exact_isbn_edition_enriches_differently_formatted_provider_record(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    for plugin_id in (
        "open_library_metadata",
        "harvard_librarycloud_metadata",
    ):
        plugins.install_builtin(plugin_id)
        plugins.set_enabled(plugin_id, True)

    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    studio.search_candidates = lambda **_kwargs: ()
    studio._open_library_isbn_edition = lambda _isbn: {
        "series": ["Ring of Fire"],
    }
    studio._search_remote_provider = lambda **_kwargs: (
        MetadataCandidate(
            title="1634: the Galileo affair",
            author="Flint, Eric",
            isbn="0743488156",
            publisher="Baen Books",
            language="eng",
            published_date="2004",
            cover_id=None,
            work_key="harvard-galileo",
            confidence=100,
            confidence_reason="Exact title and author match",
            provider_name="Harvard LibraryCloud",
        ),
    )

    results = studio.search_enabled_candidates(
        title="1634 The Galileo Affair",
        author="Eric Flint, Andrew Dennis",
        isbn="0743488156",
        file_name="1634-The Galileo Affair - Eric Flint.epub",
    )

    harvard = next(
        result
        for result in results
        if result.provider_name == "Harvard LibraryCloud"
    )
    assert harvard.series == "Ring of Fire"


def test_combined_lookup_searches_all_newly_enabled_providers(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    provider_settings = (
        ("gutenberg_metadata", False),
        ("harvard_librarycloud_metadata", False),
        ("crossref_metadata", False),
        ("big_book_metadata", True),
        ("openweb_ninja_metadata", True),
    )
    for plugin_id, needs_key in provider_settings:
        plugins.install_builtin(plugin_id)
        if needs_key:
            plugins.set_api_key(plugin_id, f"{plugin_id}-key")
        plugins.set_enabled(plugin_id, True)

    remote = RemoteMetadataProviderService()
    calls: dict[str, dict[str, str]] = {}

    def search(provider_name):
        def run(**kwargs):
            calls[provider_name] = kwargs
            return (
                RemoteMetadataResult(
                    title="Example Book",
                    author="Alice Example",
                    provider_name=provider_name,
                    confidence=90,
                    confidence_reason="Exact title and author match",
                ),
            )

        return run

    remote.search_gutenberg = search("Project Gutenberg")
    remote.search_harvard_librarycloud = search("Harvard LibraryCloud")
    remote.search_crossref = search("Crossref")
    remote.search_big_book = search("Big Book API")
    remote.search_openweb_ninja = search("OpenWeb Ninja")
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        remote_provider_service=remote,
    )

    results = studio.search_enabled_candidates(
        title="Example Book",
        author="Alice Example",
        include_open_library=False,
    )

    assert {result.provider_name for result in results} == set(calls)
    assert studio.last_search_report.searched_providers == (
        "Project Gutenberg",
        "Harvard LibraryCloud",
        "Crossref",
        "Big Book API",
        "OpenWeb Ninja",
    )
    assert calls["Big Book API"]["api_key"] == "big_book_metadata-key"
    assert (
        calls["OpenWeb Ninja"]["api_key"]
        == "openweb_ninja_metadata-key"
    )
    assert "api_key" not in calls["Project Gutenberg"]


def test_combined_lookup_runs_independent_providers_concurrently(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    for plugin_id in (
        "google_books_covers",
        "apple_books_metadata",
        "hardcover_metadata",
    ):
        plugins.install_builtin(plugin_id)
        if plugin_id == "hardcover_metadata":
            plugins.set_api_key(plugin_id, "hardcover-key")
        plugins.set_enabled(plugin_id, True)

    all_started = Barrier(3, timeout=2)

    def wait_for_other_providers(**_kwargs):
        all_started.wait()
        return ()

    cover_service = CoverSearchService()
    cover_service.search_google_books = wait_for_other_providers
    cover_service.search_apple_books = wait_for_other_providers
    remote = RemoteMetadataProviderService()
    remote.search_hardcover = wait_for_other_providers
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
        remote_provider_service=remote,
    )

    assert studio.search_enabled_candidates(
        title="Example Book",
        author="Alice Example",
        include_open_library=False,
    ) == ()
    assert studio.last_search_report.searched_providers == (
        "Google Books",
        "Apple Books",
        "Hardcover",
    )


def test_metadata_search_continues_when_one_provider_returns_none(tmp_path) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    for plugin_id in ("google_books_covers", "apple_books_metadata"):
        plugins.install_builtin(plugin_id)
        plugins.set_enabled(plugin_id, True)

    cover_service = CoverSearchService()
    cover_service.search_google_books = lambda **_kwargs: None
    cover_service.search_apple_books = lambda **_kwargs: (
        DirectCoverResult(
            title="The Secret of the Haunted Mirror",
            author="M. V. Carey",
            isbn="9780394843349",
            publisher="Random House",
            language="en",
            published_date="1974",
            cover_url="https://books.apple.example/haunted-mirror.jpg",
            source_url="https://books.apple.example/haunted-mirror",
            provider_name="Apple Books",
            confidence=100,
            confidence_reason="Exact title and author match",
        ),
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="The Secret of the Haunted Mirror",
        author="M. V. Carey",
        include_open_library=False,
    )

    assert len(results) == 1
    assert results[0].provider_name == "Apple Books"
    assert results[0].title == "The Secret of the Haunted Mirror"
    assert studio.last_search_report.searched_providers == (
        "Google Books",
        "Apple Books",
    )


def test_partial_provider_outage_does_not_discard_completed_empty_search(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    for plugin_id in ("google_books_covers", "apple_books_metadata"):
        plugins.install_builtin(plugin_id)
        plugins.set_enabled(plugin_id, True)

    cover_service = CoverSearchService()
    cover_service.search_google_books = lambda **_kwargs: (_ for _ in ()).throw(
        CoverSearchError("Google Books rejected the request (HTTP 503).")
    )
    cover_service.search_apple_books = lambda **_kwargs: ()
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="The Secret of the Haunted Mirrror",
        author="M. V. Carey",
        include_open_library=False,
    )

    assert results == ()
    assert studio.last_search_report.searched_providers == (
        "Google Books",
        "Apple Books",
    )
    assert studio.last_search_report.failed_providers == ("Google Books",)
    assert studio.last_search_report.failure_details == (
        "Google Books rejected the request (HTTP 503).",
    )


def test_metadata_search_can_use_only_the_selected_active_provider(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    for plugin_id in ("google_books_covers", "comic_vine_metadata"):
        plugins.install_builtin(plugin_id)
        plugins.set_api_key(plugin_id, f"{plugin_id}-key")
        plugins.set_enabled(plugin_id, True)

    cover_service = CoverSearchService()
    cover_service.search_google_books = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("Google Books must not run for a Comic Vine-only search")
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )
    comic_candidate = MetadataCandidate(
        title="Example Comic",
        author="Example Creator",
        isbn="",
        publisher="Example Publisher",
        language="en",
        published_date="2026",
        cover_id=None,
        work_key="comic-vine-example",
        confidence=95,
        confidence_reason="Exact title match",
        provider_name="Comic Vine",
        remote_cover_url="https://comic.example/cover.jpg",
    )
    comic_calls: dict[str, str] = {}

    def comic_search(**kwargs):
        comic_calls.update(kwargs)
        return (comic_candidate,)

    studio._search_comic_vine = comic_search

    results = studio.search_enabled_candidates(
        title="(Frew) Phantom 1048",
        author="Unknown",
        file_name="(Frew) Phantom 1048.cbr",
        provider_plugin_id="comic_vine_metadata",
    )

    assert results == (comic_candidate,)
    assert studio.last_search_report.searched_providers == ("Comic Vine",)
    assert studio.last_search_report.cover_providers == ("Comic Vine",)
    assert comic_calls == {
        "title": "The Phantom",
        "author": "",
        "isbn": "",
        "issue_number": "1048",
        "publisher": "Frew Publications",
    }


def test_automatic_cover_search_skips_comic_vine_for_non_comic_files(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    for plugin_id in ("google_books_covers", "comic_vine_metadata"):
        plugins.install_builtin(plugin_id)
        if plugin_id == "comic_vine_metadata":
            plugins.set_api_key(plugin_id, "comic-vine-key")
        plugins.set_enabled(plugin_id, True)

    cover_service = CoverSearchService()
    google_calls: list[dict[str, str]] = []

    def google_search(**kwargs):
        google_calls.append(kwargs)
        return ()

    cover_service.search_google_books = google_search
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )
    studio._search_comic_vine = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("Comic Vine must not run for a non-comic cover search")
    )

    results = studio.search_cover_candidates(
        source_id="automatic",
        title="Wizard Squared",
        author="K. E. Mills",
        file_name="Wizard Squared - K. E. Mills.epub",
    )

    assert results == ()
    assert google_calls


def test_combined_lookup_retries_cover_search_with_corrected_metadata(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("hardcover_metadata")
    plugins.set_api_key("hardcover_metadata", "test-hardcover-key")
    plugins.set_enabled("hardcover_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    metadata_match = MetadataCandidate(
        title="Seeding Program",
        author="James Blish",
        isbn="9780000000001",
        publisher="Example Press",
        language="en",
        published_date="1970",
        cover_id=None,
        work_key="hardcover-seeding-program",
        confidence=95,
        confidence_reason="Exact title and author match",
        provider_name="Hardcover",
    )
    cover_match = MetadataCandidate(
        title="Seeding Program",
        author="James Blish",
        isbn="9780000000001",
        publisher="Example Press",
        language="en",
        published_date="1970",
        cover_id=None,
        work_key="hardcover-seeding-program-cover",
        confidence=95,
        confidence_reason="Exact title and author match",
        provider_name="Hardcover",
        remote_cover_url="https://hardcover.example/seeding-program.jpg",
    )
    calls: list[dict[str, str]] = []

    def hardcover_search(**kwargs):
        calls.append(kwargs)
        if kwargs["title"] == metadata_match.title:
            return (cover_match,)
        return (metadata_match,)

    studio._search_hardcover = hardcover_search

    results = studio.search_enabled_candidates(
        title="01 Unhelpful Catalogue Title",
        author="James Blish",
        file_name="01 - Unhelpful Catalogue Title - James Blish.epub",
        include_open_library=False,
        provider_plugin_id="hardcover_metadata",
    )

    assert len(calls) == 2
    assert calls[0]["title"] == "Unhelpful Catalogue Title"
    assert calls[1]["title"] == "Seeding Program"
    assert any(candidate.cover_url for candidate in results)
    assert studio.last_search_report.cover_providers == ("Hardcover",)


def test_weak_results_trigger_bounded_epub_opening_text_lookup(tmp_path) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("google_books_covers")
    plugins.set_enabled("google_books_covers", True)
    cover_service = CoverSearchService()
    weak = DirectCoverResult(
        title="Oneness vs The 1%: Shattering Illusions, Seeding Freedom",
        author="Vandana Shiva",
        isbn="9781780265131",
        publisher="Example",
        language="en",
        published_date="2018",
        cover_url="",
        source_url="",
        provider_name="Google Books",
        confidence=60,
        confidence_reason="Possible title or author match",
    )
    identified = DirectCoverResult(
        title="The Seedling Stars",
        author="James Blish",
        isbn="9780671831130",
        publisher="Example",
        language="en",
        published_date="1957",
        cover_url="https://books.example/seedling-stars.jpg",
        source_url="https://books.example/seedling-stars",
        provider_name="Google Books",
        confidence=90,
        confidence_reason="Opening text and author match",
    )
    cover_service.search_google_books = lambda **_kwargs: (weak,)
    excerpt_calls: list[dict[str, str]] = []

    def excerpt_search(**kwargs):
        excerpt_calls.append(kwargs)
        return (identified,)

    cover_service.search_google_books_excerpt = excerpt_search
    epub_path = tmp_path / "01 - Seeding Program - James Blish.epub"
    container = """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
    </container>"""
    package = """<package xmlns="http://www.idpf.org/2007/opf">
      <manifest><item id="chapter" href="chapter.xhtml"/></manifest>
      <spine><itemref idref="chapter"/></spine>
    </package>"""
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr(
            "OEBPS/chapter.xhtml",
            "<p>The spaceship resumed humming around Sweeney without his "
            "noticing the change. When the captain spoke again, he listened.</p>",
        )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="1 Seeding Program",
        author="James Blish",
        isbn="6766468014821",
        file_name=str(epub_path),
        include_open_library=False,
        provider_plugin_id="google_books_covers",
    )

    assert len(excerpt_calls) == 1
    assert excerpt_calls[0]["author"] == "James Blish"
    assert excerpt_calls[0]["excerpt"].startswith(
        "The spaceship resumed humming"
    )
    assert [result.title for result in results] == ["The Seedling Stars"]
    assert results[0].cover_url.endswith("seedling-stars.jpg")


def test_weak_lookup_retries_bounded_mystery_secret_title_alias(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("google_books_covers")
    plugins.set_enabled("google_books_covers", True)
    cover_service = CoverSearchService()
    calls: list[str] = []
    corrected = DirectCoverResult(
        title="The Secret of the Crooked Cat",
        author="William Arden",
        isbn="9780394811888",
        publisher="Random House",
        language="en",
        published_date="1970",
        cover_url="https://books.example/crooked-cat.jpg",
        source_url="https://books.example/crooked-cat",
        provider_name="Google Books",
        confidence=90,
        confidence_reason="Exact title and author match",
        series="Alfred Hitchcock and The Three Investigators",
        series_number="13",
    )

    def google_search(**kwargs):
        calls.append(kwargs["title"])
        if kwargs["title"] == corrected.title:
            return (corrected,)
        return ()

    cover_service.search_google_books = google_search
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="13 The Mystery of the Crooked Cat",
        author="William Arden",
        file_name="13 - The Mystery of the Crooked Cat.epub",
        include_open_library=False,
    )

    assert calls == [
        "The Mystery of the Crooked Cat",
        "The Secret of the Crooked Cat",
    ]
    assert results[0].title == "The Secret of the Crooked Cat"
    assert results[0].author == "William Arden"
    assert results[0].cover_url == corrected.cover_url
    assert results[0].series_number == "13"


def test_weak_lookup_retries_missing_possessive_apostrophe(tmp_path) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("google_books_covers")
    plugins.set_enabled("google_books_covers", True)
    cover_service = CoverSearchService()
    calls: list[str] = []
    corrected = DirectCoverResult(
        title="The Mystery of the Dead Man's Riddle",
        author="William Arden",
        isbn="9780394830469",
        publisher="Random House",
        language="en",
        published_date="1974",
        cover_url="https://books.example/dead-mans-riddle.jpg",
        source_url="https://books.example/dead-mans-riddle",
        provider_name="Google Books",
        confidence=90,
        confidence_reason="Exact title and author match",
        series="Alfred Hitchcock and The Three Investigators",
        series_number="22",
    )

    def google_search(**kwargs):
        calls.append(kwargs["title"])
        if kwargs["title"] == corrected.title:
            return (corrected,)
        return ()

    cover_service.search_google_books = google_search
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
        cover_search_service=cover_service,
    )

    results = studio.search_enabled_candidates(
        title="22 The Mystery of the Dead Mans Riddle",
        author="William Arden",
        file_name="22 - The Mystery of the Dead Mans Riddle.epub",
        include_open_library=False,
    )

    assert "The Mystery of the Dead Man's Riddle" in calls
    assert results[0].title == corrected.title
    assert results[0].series_number == "22"


def test_exact_alternate_title_accepts_catalogue_pen_name_difference(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("open_library_metadata")
    plugins.set_enabled("open_library_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    calls: list[str] = []
    open_library_match = MetadataCandidate(
        title="The Secret of the Crooked Cat",
        author="Robert Arthur, Dennis Lynds",
        isbn="9780394811888",
        publisher="Random House",
        language="eng",
        published_date="1970",
        cover_id=6889628,
        work_key="OL4104515M",
        confidence=75,
        confidence_reason="Exact title match",
    )

    def open_library_search(**kwargs):
        calls.append(kwargs["title"])
        if kwargs["title"] == open_library_match.title:
            return (open_library_match,)
        return ()

    studio.search_candidates = open_library_search
    # The rescued match above carries an ISBN but no series, so the
    # post-fallback series-enrichment pass (a separate, deliberate concern
    # from this test) would otherwise reach for these live network sources.
    studio._open_library_isbn_edition = lambda _isbn: None
    studio._wikipedia_series_hint = lambda **_kwargs: ("", "")
    studio._wikidata_series_hint = lambda **_kwargs: ("", "")

    results = studio.search_enabled_candidates(
        title="13 The Mystery of the Crooked Cat",
        author="William Arden",
        file_name="13 - The Mystery of the Crooked Cat.epub",
    )

    assert calls == [
        "The Mystery of the Crooked Cat",
        "The Mystery of the Crooked Cat",
        "The Secret of the Crooked Cat",
        "The Mystery of the Crooked Cat",
    ]
    assert results[0].title == "The Secret of the Crooked Cat"
    assert results[0].author == "William Arden"
    assert results[0].isbn == "9780394811888"
    assert results[0].cover_url.endswith("/6889628-L.jpg?default=false")


def test_exact_title_retry_accepts_underlying_writer_difference(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("open_library_metadata")
    plugins.set_enabled("open_library_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    authors: list[str] = []
    underlying_writer_match = MetadataCandidate(
        title="The Mystery of the Nervous Lion",
        author="Kin Platt",
        isbn="9780394923086",
        publisher="Random House",
        language="eng",
        published_date="1971",
        cover_id=12770781,
        work_key="OL-NERVOUS-LION",
        confidence=75,
        confidence_reason="Exact title match",
    )

    def open_library_search(**kwargs):
        authors.append(kwargs["author"])
        if kwargs["author"]:
            return ()
        return (underlying_writer_match,)

    studio.search_candidates = open_library_search

    results = studio.search_enabled_candidates(
        title="16 The Mystery of the Nervous Lion",
        author="Nick West",
        file_name="16 - The Mystery of the Nervous Lion - Nick West.epub",
    )

    assert authors[:2] == ["Nick West", ""]
    assert results[0].title == "The Mystery of the Nervous Lion"
    assert results[0].author == "Nick West"
    assert results[0].isbn == "9780394923086"
    assert results[0].confidence >= 85
    assert results[0].cover_url.endswith("/12770781-L.jpg?default=false")


def test_irrelevant_medium_result_does_not_block_alternate_title_retry(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("open_library_metadata")
    plugins.set_enabled("open_library_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    irrelevant = MetadataCandidate(
        title="The Crooked House Mystery",
        author="Another Author",
        isbn="",
        publisher="",
        language="eng",
        published_date="",
        cover_id=None,
        work_key="OL-WRONG",
        confidence=70,
        confidence_reason="Partial words",
    )
    corrected = MetadataCandidate(
        title="The Secret of the Crooked Cat",
        author="Robert Arthur, Dennis Lynds",
        isbn="9780394811888",
        publisher="Random House",
        language="eng",
        published_date="1970",
        cover_id=6889628,
        work_key="OL4104515M",
        confidence=75,
        confidence_reason="Exact title match",
    )

    def open_library_search(**kwargs):
        if kwargs["title"] == corrected.title:
            return (corrected,)
        return (irrelevant,)

    studio.search_candidates = open_library_search

    results = studio.search_enabled_candidates(
        title="The Mystery of the Crooked Cat",
        author="William Arden",
        file_name="13 - The Mystery of the Crooked Cat.epub",
    )

    assert [result.title for result in results] == [corrected.title]
    assert results[0].author == "William Arden"


def test_check_provider_connection_reports_healthy_on_success(
    tmp_path, monkeypatch,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    plugins.install_builtin("amazon_metadata")
    plugins.set_enabled("amazon_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    page = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B000TEST">
        <h2><a href="/dp/B000TEST"><span>Pride and Prejudice</span></a></h2>
        <span>by</span><a>Jane Austen</a>
        <img class="s-image"
             src="https://m.media-amazon.com/images/I/example._SX300_.jpg">
      </div>
    </body></html>
    """
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(page),
    )

    status, message = studio.check_provider_connection("amazon_metadata")

    assert status == "healthy"
    assert "responded" in message
    refreshed = next(
        record
        for record in plugins.list_plugins()
        if record.plugin_id == "amazon_metadata"
    )
    assert refreshed.provider_health == "healthy"


def test_check_provider_connection_reports_failure_status(
    tmp_path, monkeypatch,
) -> None:
    plugins = _plugin_service(tmp_path)
    _disable_default_lookup_plugins(plugins)
    plugins.install_builtin("amazon_metadata")
    plugins.set_enabled("amazon_metadata", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )
    monkeypatch.setattr(
        provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _HtmlResponse(
            "<html>Sorry, we just need to make sure you're not a robot. "
            "CAPTCHA</html>"
        ),
    )

    status, message = studio.check_provider_connection("amazon_metadata")

    assert status == "blocked"
    refreshed = next(
        record
        for record in plugins.list_plugins()
        if record.plugin_id == "amazon_metadata"
    )
    assert refreshed.provider_health == "blocked"
    assert refreshed.provider_health_message == message


def test_check_provider_connection_requires_the_plugin_to_be_enabled(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("amazon_metadata")
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )

    try:
        studio.check_provider_connection("amazon_metadata")
    except MetadataLookupError as error:
        assert "Enable this plugin" in str(error)
    else:
        raise AssertionError("Expected a MetadataLookupError")


def test_check_provider_connection_rejects_identification_only_plugins(
    tmp_path,
) -> None:
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("serpapi_book_resolver")
    plugins.set_api_key("serpapi_book_resolver", "test-key")
    plugins.set_enabled("serpapi_book_resolver", True)
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=plugins,
    )

    try:
        studio.check_provider_connection("serpapi_book_resolver")
    except MetadataLookupError as error:
        assert "does not offer" in str(error)
    else:
        raise AssertionError("Expected a MetadataLookupError")


def test_check_provider_connection_rejects_an_unknown_plugin(
    tmp_path,
) -> None:
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        plugin_service=_plugin_service(tmp_path),
    )

    try:
        studio.check_provider_connection("not_a_real_plugin")
    except MetadataLookupError as error:
        assert "Unknown plugin" in str(error)
    else:
        raise AssertionError("Expected a MetadataLookupError")
