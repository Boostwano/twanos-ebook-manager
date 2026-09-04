"""Persistent user preferences for Twano."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QSettings


DEFAULT_BANNER_NAME = "The Grand Library"
BANNER_NAMES = (
    DEFAULT_BANNER_NAME,
    "Reading Nook",
    "Modern Library",
    "Candlelit Study",
    "Rainy Afternoon",
    "Woodland Library",
    "Infinite Library",
    "By the light of a warm Fire",
)


class ProtectionMode(StrEnum):
    STANDARD = "standard"
    READ_ONLY = "read_only"


class GreetingStyle(StrEnum):
    DYNAMIC = "dynamic"
    SIMPLE = "simple"
    MINIMAL = "minimal"


class BannerRotation(StrEnum):
    FIXED = "fixed"
    STARTUP = "startup"


class ReaderMode(StrEnum):
    WINDOWS_DEFAULT = "windows_default"
    CUSTOM = "custom"
    ASK = "ask"
    FOLDER = "folder"


class LibraryViewMode(StrEnum):
    GRID = "grid"
    LIST = "list"


class LibraryDensity(StrEnum):
    COMPACT = "compact"
    COMFORTABLE = "comfortable"
    SPACIOUS = "spacious"


class LibrarySortField(StrEnum):
    TITLE = "title"
    AUTHOR = "author"
    SERIES = "series"
    DATE_ADDED = "date_added"
    FILE_MODIFIED = "file_modified"
    FORMAT = "format"
    METADATA_QUALITY = "metadata_quality"


class LibrarySortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


@dataclass(frozen=True)
class HomePreferences:
    protection_mode: ProtectionMode = ProtectionMode.STANDARD
    greeting_style: GreetingStyle = GreetingStyle.DYNAMIC
    show_today_insight: bool = True
    show_seasonal_messages: bool = True
    show_reading_quotes: bool = False
    banner_name: str = DEFAULT_BANNER_NAME
    banner_rotation: BannerRotation = BannerRotation.FIXED


@dataclass(frozen=True)
class ReadingPreferences:
    reader_mode: ReaderMode = ReaderMode.WINDOWS_DEFAULT
    epub_reader: str = ""
    pdf_reader: str = ""
    mobi_reader: str = ""
    comic_reader: str = ""


@dataclass(frozen=True)
class LibraryPreferences:
    view_mode: LibraryViewMode = LibraryViewMode.GRID
    density: LibraryDensity = LibraryDensity.COMFORTABLE
    sort_field: LibrarySortField = LibrarySortField.TITLE
    sort_direction: LibrarySortDirection = (
        LibrarySortDirection.ASCENDING
    )
    details_visible: bool = True


@dataclass(frozen=True)
class ProtectionPreferences:
    """User-controlled database backup policy."""

    backup_folder: str = ""
    retention_days: int = 0


@dataclass(frozen=True)
class OrganizationPreferences:
    """Where correctly identified and deleted books are physically moved."""

    destination_folder: str = ""
    destination_prompt_shown: bool = False


@dataclass(frozen=True)
class MetadataPreferences:
    """Privacy-relevant provider controls."""

    open_library_enabled: bool = True
    cache_days: int = 30
    auto_lookup_next: bool = False
    confirm_reviewed_apply: bool = True


@dataclass(frozen=True)
class AccessibilityPreferences:
    """Application-wide readability and motion preferences."""

    text_scale_percent: int = 100
    reduced_motion: bool = False
    high_contrast_focus: bool = True


@dataclass(frozen=True)
class GeneralPreferences:
    """Small set of everyday application behaviours."""

    check_updates_on_startup: bool = False
    show_first_run_guide: bool = True


def normalise_banner_name(value: object) -> str:
    """Return a supported banner name, including legacy aliases."""
    text = str(value).strip()
    normalised = _normalise_label(text)
    aliases = {
        _normalise_label(name): name
        for name in BANNER_NAMES
    }
    aliases["grand library"] = DEFAULT_BANNER_NAME
    return aliases.get(normalised, DEFAULT_BANNER_NAME)


def normalise_banner_rotation(value: object) -> BannerRotation:
    """Map legacy rotation settings to the two supported RC6.4 modes."""
    normalised = (
        str(value)
        .strip()
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
    )
    if normalised in {
        BannerRotation.STARTUP.value,
        "rotate_on_startup",
        "random",
        "daily",
        "weekly",
        "seasonal",
    }:
        return BannerRotation.STARTUP
    return BannerRotation.FIXED


class PreferencesStore:
    """Load, validate, migrate, and save application preferences."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def load_home_preferences(self) -> HomePreferences:
        raw_banner_name = self._settings.value(
            "home/banner_name",
            DEFAULT_BANNER_NAME,
        )
        raw_banner_rotation = self._settings.value(
            "home/banner_rotation",
            BannerRotation.FIXED.value,
        )
        banner_name = normalise_banner_name(raw_banner_name)
        banner_rotation = normalise_banner_rotation(raw_banner_rotation)
        self._migrate_banner_preferences(
            raw_banner_name,
            raw_banner_rotation,
            banner_name,
            banner_rotation,
        )

        return HomePreferences(
            protection_mode=self._enum_value(
                ProtectionMode,
                self._settings.value(
                    "protection/mode",
                    ProtectionMode.STANDARD.value,
                ),
                ProtectionMode.STANDARD,
            ),
            greeting_style=self._enum_value(
                GreetingStyle,
                self._settings.value(
                    "home/greeting_style",
                    GreetingStyle.DYNAMIC.value,
                ),
                GreetingStyle.DYNAMIC,
            ),
            show_today_insight=self._bool_value(
                "home/show_today_insight",
                True,
            ),
            show_seasonal_messages=self._bool_value(
                "home/show_seasonal_messages",
                True,
            ),
            show_reading_quotes=self._bool_value(
                "home/show_reading_quotes",
                False,
            ),
            banner_name=banner_name,
            banner_rotation=banner_rotation,
        )

    def load_reading_preferences(self) -> ReadingPreferences:
        return ReadingPreferences(
            reader_mode=self._enum_value(
                ReaderMode,
                self._settings.value(
                    "reading/mode",
                    ReaderMode.WINDOWS_DEFAULT.value,
                ),
                ReaderMode.WINDOWS_DEFAULT,
            ),
            epub_reader=str(
                self._settings.value("reading/epub_reader", "")
            ),
            pdf_reader=str(
                self._settings.value("reading/pdf_reader", "")
            ),
            mobi_reader=str(
                self._settings.value("reading/mobi_reader", "")
            ),
            comic_reader=str(
                self._settings.value("reading/comic_reader", "")
            ),
        )

    def load_library_preferences(self) -> LibraryPreferences:
        """Load validated Library presentation and sort preferences."""
        raw_view_mode = self._settings.value(
            "library/view_mode",
            LibraryViewMode.GRID.value,
        )
        raw_density = self._settings.value(
            "library/density",
            LibraryDensity.COMFORTABLE.value,
        )
        raw_sort_field = self._settings.value(
            "library/sort_field",
            LibrarySortField.TITLE.value,
        )
        raw_sort_direction = self._settings.value(
            "library/sort_direction",
            LibrarySortDirection.ASCENDING.value,
        )
        preferences = LibraryPreferences(
            view_mode=self._enum_value(
                LibraryViewMode,
                raw_view_mode,
                LibraryViewMode.GRID,
            ),
            density=self._enum_value(
                LibraryDensity,
                raw_density,
                LibraryDensity.COMFORTABLE,
            ),
            sort_field=self._enum_value(
                LibrarySortField,
                raw_sort_field,
                LibrarySortField.TITLE,
            ),
            sort_direction=self._enum_value(
                LibrarySortDirection,
                raw_sort_direction,
                LibrarySortDirection.ASCENDING,
            ),
            details_visible=self._bool_value(
                "library/details_visible",
                True,
            ),
        )
        self._migrate_library_preferences(
            raw_view_mode,
            raw_density,
            raw_sort_field,
            raw_sort_direction,
            preferences,
        )
        return preferences

    def load_protection_preferences(self) -> ProtectionPreferences:
        """Load backup settings and repair unsafe legacy values."""
        raw_folder = self._settings.value(
            "protection/backup_folder",
            "",
        )
        raw_retention = self._settings.value(
            "protection/retention_days",
            0,
        )
        backup_folder = self._absolute_folder_or_empty(raw_folder)
        retention_days = self._retention_days(raw_retention)
        if (
            str(raw_folder).strip() != backup_folder
            or str(raw_retention).strip() != str(retention_days)
        ):
            self._settings.setValue(
                "protection/backup_folder",
                backup_folder,
            )
            self._settings.setValue(
                "protection/retention_days",
                retention_days,
            )
            self._settings.sync()
        return ProtectionPreferences(
            backup_folder=backup_folder,
            retention_days=retention_days,
        )

    def load_organization_preferences(self) -> OrganizationPreferences:
        """Load the destination folder and repair unsafe legacy values."""
        raw_folder = self._settings.value(
            "organization/destination_folder",
            "",
        )
        destination_folder = self._absolute_folder_or_empty(raw_folder)
        if str(raw_folder).strip() != destination_folder:
            self._settings.setValue(
                "organization/destination_folder",
                destination_folder,
            )
            self._settings.sync()
        return OrganizationPreferences(
            destination_folder=destination_folder,
            destination_prompt_shown=self._bool_value(
                "organization/destination_prompt_shown",
                False,
            ),
        )

    def load_metadata_preferences(self) -> MetadataPreferences:
        raw_cache_days = self._settings.value("metadata/cache_days", 30)
        try:
            cache_days = int(raw_cache_days)
        except (TypeError, ValueError):
            cache_days = 30
        if not 0 <= cache_days <= 365:
            cache_days = 30
        return MetadataPreferences(
            open_library_enabled=self._bool_value(
                "metadata/open_library_enabled",
                True,
            ),
            cache_days=cache_days,
            auto_lookup_next=self._bool_value(
                "metadata/auto_lookup_next",
                False,
            ),
            confirm_reviewed_apply=self._bool_value(
                "metadata/confirm_reviewed_apply",
                True,
            ),
        )

    def load_accessibility_preferences(
        self,
    ) -> AccessibilityPreferences:
        raw_scale = self._settings.value(
            "accessibility/text_scale_percent",
            100,
        )
        try:
            scale = int(raw_scale)
        except (TypeError, ValueError):
            scale = 100
        if scale not in {90, 100, 110, 125, 150}:
            scale = 100
        return AccessibilityPreferences(
            text_scale_percent=scale,
            reduced_motion=self._bool_value(
                "accessibility/reduced_motion",
                False,
            ),
            high_contrast_focus=self._bool_value(
                "accessibility/high_contrast_focus",
                True,
            ),
        )

    def load_general_preferences(self) -> GeneralPreferences:
        return GeneralPreferences(
            check_updates_on_startup=self._bool_value(
                "general/check_updates_on_startup",
                False,
            ),
            show_first_run_guide=self._bool_value(
                "general/show_first_run_guide",
                True,
            ),
        )

    def save_home_preferences(
        self,
        preferences: HomePreferences,
    ) -> None:
        banner_name = normalise_banner_name(preferences.banner_name)
        banner_rotation = normalise_banner_rotation(
            preferences.banner_rotation
        )
        self._settings.setValue(
            "protection/mode",
            ProtectionMode(preferences.protection_mode).value,
        )
        self._settings.setValue(
            "home/greeting_style",
            GreetingStyle(preferences.greeting_style).value,
        )
        self._settings.setValue(
            "home/show_today_insight",
            preferences.show_today_insight,
        )
        self._settings.setValue(
            "home/show_seasonal_messages",
            preferences.show_seasonal_messages,
        )
        self._settings.setValue(
            "home/show_reading_quotes",
            preferences.show_reading_quotes,
        )
        self._settings.setValue("home/banner_name", banner_name)
        self._settings.setValue(
            "home/banner_rotation",
            banner_rotation.value,
        )

    def save_reading_preferences(
        self,
        preferences: ReadingPreferences,
    ) -> None:
        self._settings.setValue(
            "reading/mode",
            ReaderMode(preferences.reader_mode).value,
        )
        self._settings.setValue(
            "reading/epub_reader",
            preferences.epub_reader,
        )
        self._settings.setValue(
            "reading/pdf_reader",
            preferences.pdf_reader,
        )
        self._settings.setValue(
            "reading/mobi_reader",
            preferences.mobi_reader,
        )
        self._settings.setValue(
            "reading/comic_reader",
            preferences.comic_reader,
        )

    def save_library_preferences(
        self,
        preferences: LibraryPreferences,
    ) -> None:
        """Persist validated Library presentation and sort preferences."""
        self._settings.setValue(
            "library/view_mode",
            LibraryViewMode(preferences.view_mode).value,
        )
        self._settings.setValue(
            "library/density",
            LibraryDensity(preferences.density).value,
        )
        self._settings.setValue(
            "library/sort_field",
            LibrarySortField(preferences.sort_field).value,
        )
        self._settings.setValue(
            "library/sort_direction",
            LibrarySortDirection(
                preferences.sort_direction
            ).value,
        )
        self._settings.setValue(
            "library/details_visible",
            preferences.details_visible,
        )

    def save_protection_preferences(
        self,
        preferences: ProtectionPreferences,
    ) -> None:
        """Persist a validated database backup policy."""
        backup_folder = self._absolute_folder_or_empty(
            preferences.backup_folder
        )
        if str(preferences.backup_folder).strip() and not backup_folder:
            raise ValueError("Backup folder must be an absolute path.")
        try:
            requested_retention = int(preferences.retention_days)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Backup retention must be between 0 and 36500 days."
            ) from error
        retention_days = self._retention_days(requested_retention)
        if retention_days != requested_retention:
            raise ValueError(
                "Backup retention must be between 0 and 36500 days."
            )
        self._settings.setValue(
            "protection/backup_folder",
            backup_folder,
        )
        self._settings.setValue(
            "protection/retention_days",
            retention_days,
        )

    def save_organization_preferences(
        self,
        preferences: OrganizationPreferences,
    ) -> None:
        """Persist a validated destination folder for organised books."""
        destination_folder = self._absolute_folder_or_empty(
            preferences.destination_folder
        )
        if (
            str(preferences.destination_folder).strip()
            and not destination_folder
        ):
            raise ValueError("Destination folder must be an absolute path.")
        self._settings.setValue(
            "organization/destination_folder",
            destination_folder,
        )
        self._settings.setValue(
            "organization/destination_prompt_shown",
            bool(preferences.destination_prompt_shown),
        )

    def save_metadata_preferences(
        self,
        preferences: MetadataPreferences,
    ) -> None:
        cache_days = int(preferences.cache_days)
        if not 0 <= cache_days <= 365:
            raise ValueError(
                "Metadata cache retention must be between 0 and 365 days."
            )
        self._settings.setValue(
            "metadata/open_library_enabled",
            bool(preferences.open_library_enabled),
        )
        self._settings.setValue("metadata/cache_days", cache_days)
        self._settings.setValue(
            "metadata/auto_lookup_next",
            bool(preferences.auto_lookup_next),
        )
        self._settings.setValue(
            "metadata/confirm_reviewed_apply",
            bool(preferences.confirm_reviewed_apply),
        )

    def save_accessibility_preferences(
        self,
        preferences: AccessibilityPreferences,
    ) -> None:
        scale = int(preferences.text_scale_percent)
        if scale not in {90, 100, 110, 125, 150}:
            raise ValueError("Choose one of the supported text sizes.")
        self._settings.setValue(
            "accessibility/text_scale_percent",
            scale,
        )
        self._settings.setValue(
            "accessibility/reduced_motion",
            bool(preferences.reduced_motion),
        )
        self._settings.setValue(
            "accessibility/high_contrast_focus",
            bool(preferences.high_contrast_focus),
        )

    def save_general_preferences(
        self,
        preferences: GeneralPreferences,
    ) -> None:
        self._settings.setValue(
            "general/check_updates_on_startup",
            bool(preferences.check_updates_on_startup),
        )
        self._settings.setValue(
            "general/show_first_run_guide",
            bool(preferences.show_first_run_guide),
        )

    def set_protection_mode(self, mode: ProtectionMode) -> None:
        self._settings.setValue(
            "protection/mode",
            ProtectionMode(mode).value,
        )

    def sync(self) -> None:
        self._settings.sync()

    def _bool_value(self, key: str, default: bool) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _absolute_folder_or_empty(value: object) -> str:
        text = str(value).strip()
        if not text:
            return ""
        path = Path(text).expanduser()
        if not path.is_absolute():
            return ""
        return str(path)

    @staticmethod
    def _retention_days(value: object) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError):
            return 0
        if not 0 <= days <= 36500:
            return 0
        return days

    def _migrate_banner_preferences(
        self,
        raw_name: object,
        raw_rotation: object,
        banner_name: str,
        banner_rotation: BannerRotation,
    ) -> None:
        changed = False
        if str(raw_name) != banner_name:
            self._settings.setValue("home/banner_name", banner_name)
            changed = True
        if str(raw_rotation) != banner_rotation.value:
            self._settings.setValue(
                "home/banner_rotation",
                banner_rotation.value,
            )
            changed = True
        if changed:
            self._settings.sync()

    def _migrate_library_preferences(
        self,
        raw_view_mode: object,
        raw_density: object,
        raw_sort_field: object,
        raw_sort_direction: object,
        preferences: LibraryPreferences,
    ) -> None:
        values = {
            "library/view_mode": preferences.view_mode.value,
            "library/density": preferences.density.value,
            "library/sort_field": preferences.sort_field.value,
            "library/sort_direction": preferences.sort_direction.value,
        }
        raw_values = {
            "library/view_mode": raw_view_mode,
            "library/density": raw_density,
            "library/sort_field": raw_sort_field,
            "library/sort_direction": raw_sort_direction,
        }
        changed = False
        for key, value in values.items():
            if str(raw_values[key]) != value:
                self._settings.setValue(key, value)
                changed = True
        if changed:
            self._settings.sync()

    @staticmethod
    def _enum_value(
        enum_type: type["_PreferenceEnum"],
        value: object,
        default: "_PreferenceEnum",
    ) -> "_PreferenceEnum":
        try:
            return enum_type(str(value))
        except ValueError:
            return default


_PreferenceEnum = TypeVar("_PreferenceEnum", bound=StrEnum)


def _normalise_label(value: str) -> str:
    return " ".join(
        value.replace("_", " ").replace("-", " ").split()
    ).casefold()
