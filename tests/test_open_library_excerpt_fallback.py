"""Low-confidence EPUB identification can use Open Library first sentences."""

from __future__ import annotations

import json

from database.database import DatabaseManager
from services.metadata_studio_service import MetadataStudioService


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


def test_open_library_excerpt_requires_strong_first_sentence_match(
    monkeypatch,
    tmp_path,
) -> None:
    opening = (
        "The spaceship resumed humming around Sweeney without his noticing "
        "the change. When Captain Meikiejon's voice finally came again."
    )
    payload = {
        "docs": [
            {
                "key": "/works/OL1W",
                "title": "The Seedling Stars",
                "author_name": ["James Blish"],
                "first_sentence": [opening],
                "cover_i": 123,
            },
            {
                "key": "/works/OL2W",
                "title": "An Unrelated Book",
                "author_name": ["James Blish"],
                "first_sentence": [
                    "This completely different sentence is long enough but "
                    "does not occur in the supplied opening passage."
                ],
            },
        ]
    }
    monkeypatch.setattr(
        "services.metadata_studio_service.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
    )

    matches = studio.search_open_library_excerpt(
        excerpt=opening + " Sweeney remained still.",
        author="James Blish",
    )

    assert len(matches) == 1
    assert matches[0].title == "The Seedling Stars"
    assert matches[0].confidence == 95
    assert matches[0].cover_url.endswith("/123-L.jpg?default=false")


def test_wikipedia_resolves_short_story_to_containing_collection(
    monkeypatch,
    tmp_path,
) -> None:
    payload = {
        "query": {
            "search": [
                {
                    "title": "The Seedling Stars",
                    "snippet": (
                        "James Blish called the process pantropy. "
                        "<span class='searchmatch'>Seeding Program</span> "
                        "was published in 1956."
                    ),
                }
            ]
        }
    }
    monkeypatch.setattr(
        "services.metadata_studio_service.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
    )

    assert studio.resolve_wikipedia_containing_work(
        title="Seeding Program",
        author="James Blish",
    ) == "The Seedling Stars"


def test_wikipedia_rejects_result_without_title_and_author_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    payload = {
        "query": {
            "search": [
                {
                    "title": "Unrelated Seed Collection",
                    "snippet": "A general article about a seeding program.",
                }
            ]
        }
    }
    monkeypatch.setattr(
        "services.metadata_studio_service.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    studio = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db"),
        cache_path=tmp_path / "metadata-cache.json",
    )

    assert studio.resolve_wikipedia_containing_work(
        title="Seeding Program",
        author="James Blish",
    ) == ""
