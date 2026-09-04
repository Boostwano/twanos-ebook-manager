"""Welcome-panel text selection independent of Qt widgets."""

from dataclasses import dataclass
from datetime import datetime

from preferences import GreetingStyle, HomePreferences
from services.dashboard_service import DashboardData


@dataclass(frozen=True)
class WelcomeContent:
    greeting: str
    summary: str
    insight: str


class WelcomeService:
    """Choose calm, neutral welcome text once per application launch."""

    def __init__(self, started_at: datetime | None = None) -> None:
        self._started_at = started_at or datetime.now()

    def build(self, data: DashboardData, preferences: HomePreferences) -> WelcomeContent:
        greeting = self._greeting(preferences.greeting_style)
        summary = self._summary(data, preferences.greeting_style)
        insight = self._insight(data) if preferences.show_today_insight else ""
        return WelcomeContent(greeting=greeting, summary=summary, insight=insight)

    def _greeting(self, style: GreetingStyle) -> str:
        if style is GreetingStyle.MINIMAL:
            return "Welcome back."
        hour = self._started_at.hour
        if hour < 12:
            return "Good morning."
        if hour < 18:
            return "Good afternoon."
        return "Good evening."

    @staticmethod
    def _summary(data: DashboardData, style: GreetingStyle) -> str:
        if style is GreetingStyle.MINIMAL:
            return "Your library is ready."
        if data.total_books == 0:
            return "Your library is ready for its first scan."
        location_word = "location" if data.library_count == 1 else "locations"
        return (
            f"Your library contains {data.total_books:,} books across "
            f"{data.library_count:,} {location_word}."
        )

    @staticmethod
    def _insight(data: DashboardData) -> str:
        if data.total_books == 0:
            return "Start with Scan to discover and catalogue your books."
        if data.missing_books:
            noun = "file" if data.missing_books == 1 else "files"
            return f"{data.missing_books:,} missing {noun} need attention."
        if data.needs_metadata:
            noun = "book" if data.needs_metadata == 1 else "books"
            return (
                f"{data.needs_metadata:,} {noun} need metadata "
                "improvements."
            )
        if data.metadata_health >= 90:
            return "Your library metadata is in excellent condition."
        return "Library Health can help identify the next useful improvements."
