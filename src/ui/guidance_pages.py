"""Current in-application guidance, release notes, and support details."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import APP_VERSION, RELEASE_NAME
from ui.branding import BRAND_TAGLINE
from database.database import APP_DATA_FOLDER, DEFAULT_DATABASE_PATH


def _topic(
    title: str,
    introduction: str,
    steps: tuple[str, ...],
    notes: tuple[str, ...] = (),
) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 16, 20, 16)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    copy = QLabel(introduction)
    copy.setObjectName("sectionDescription")
    copy.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(copy)
    for index, step in enumerate(steps, start=1):
        label = QLabel(f"{index}.  {step}")
        label.setObjectName("guideStep")
        label.setWordWrap(True)
        layout.addWidget(label)
    for note in notes:
        note_label = QLabel(note)
        note_label.setObjectName("sectionDescription")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
    layout.addStretch()
    return page


class UserGuidePage(QWidget):
    """Concise guide kept in lockstep with the visible application."""

    def __init__(self) -> None:
        super().__init__()
        title = QLabel("User Guide")
        title.setObjectName("pageTitle")
        description = QLabel(
            "Choose the task you want to complete. Each guide uses the same "
            "names and buttons shown in Twano."
        )
        description.setObjectName("pageDescription")
        self.tabs = QTabWidget()
        self.tabs.addTab(
            _topic(
                "Welcome to Twano",
                "New to managing an ebook library with software like this? "
                "Start here — a few plain-language explanations of what "
                "Twano actually does, before the step-by-step guides below.",
                (),
                (
                    "A “watched library” (or “source”) is "
                    "just a folder on your computer, a network drive, or an "
                    "external drive that you tell Twano to keep an eye on. "
                    "Twano never watches anything until you add it.",
                    "“Scanning” means Twano looks through that "
                    "folder and notes which ebook files are there. Scanning "
                    "never changes, moves, or deletes a file by itself — "
                    "it only builds a preview of what it found. You choose "
                    "whether to apply that preview.",
                    "“Metadata” is just the details about a book: "
                    "its title, author, series, description, and cover "
                    "image. Some of this is already stored inside the "
                    "ebook file itself; Twano can also look online (only "
                    "when you ask it to) to fill in anything missing or fix "
                    "anything wrong.",
                    "“Organising” means renaming and moving a file "
                    "into a tidy Author or Series folder once Twano is "
                    "confident it has the right details. Nothing is ever "
                    "organised automatically without your review — you "
                    "always see and approve the change first.",
                    "A “plugin” is simply one source Twano can "
                    "check for book details or covers (for example, Open "
                    "Library or Google Books). You choose which ones are "
                    "active; some need a free account and key from that "
                    "service, most do not.",
                    "Twano keeps a safety net running in the background: a "
                    "verified backup of your catalogue is made before any "
                    "change that could be hard to reverse, and most actions "
                    "can be undone. Look for the safety card at the bottom "
                    "of the navigation bar at any time.",
                    "If something ever looks wrong, the Diagnostic Report "
                    "button (also at the bottom of the navigation bar) "
                    "saves a text file describing your setup that you can "
                    "pass along when asking for help — see the Getting "
                    "Help tab.",
                ),
            ),
            "Welcome",
        )
        self.tabs.addTab(
            _topic(
                "Start a New Library",
                "Scanning is read-only until you approve the preview.",
                (
                    "Open Scan and choose Add Library Location.",
                    "Choose a local, mapped-drive, UNC, NAS, or Calibre folder.",
                    "Select Preview Scan and review the counts.",
                    "Select Apply Preview. Twano creates a verified backup first.",
                ),
                (
                    "In plain terms: step 3 just shows you what Twano "
                    "found, without touching anything. Step 4 is the only "
                    "point where your catalogue actually changes, and even "
                    "then, your ebook files themselves are never edited — "
                    "only Twano's own record of them.",
                ),
            ),
            "Getting Started",
        )
        self.tabs.addTab(
            _topic(
                "Browse and Open Books",
                "Library keeps browsing actions separate from changes.",
                (
                    "Use Search and filters to narrow the bookshelf.",
                    "Select a cover or row to open Details.",
                    "Open Book uses your Reading setting; Open Folder selects the file.",
                    "Metadata and Review Issues open the matching guided workflow.",
                    "Open Manual Review Folder opens files moved aside from Metadata.",
                ),
                (
                    "Browsing here never changes a file — it only reads "
                    "what Twano already knows. Nothing you click on this "
                    "page can accidentally move, rename, or delete an "
                    "ebook.",
                ),
            ),
            "Library",
        )
        self.tabs.addTab(
            _topic(
                "Find Metadata & Covers",
                "Online lookup runs only when you request it.",
                (
                    "Open Metadata and select a book.",
                    "Choose Find Metadata & Covers. One search uses every active direct provider and does not open websites.",
                    "Twano uses a clear Title - Author or Author - Title filename when embedded details are messy.",
                      "Series details are read from Open Library, Google Books, Hardcover, Amazon and a few other sources when they return a clear series name and reading number.",
                      "Choosing a result with a usable title and author automatically selects safe file organisation. Standalone books go into the author folder; series books from every author go into one shared -=Series=- folder in reading order. Optional Series group fields keep universes and their sub-series together.",
                      "The first found cover is shown automatically; choose another to preview it, then select Use Cover.",
                    "Choose a result, then untick any field you do not want.",
                    "Choose Apply Reviewed Changes; a verified backup is created first.",
                    "Previews expire after 30 minutes. If one expires, Twano creates a fresh preview and asks you to review it before applying.",
                    "Optionally search the next attention book after Apply, or choose Prepare Review Queue to perform cancellable read-only searches in advance.",
                    "Use Next Prepared to review queued suggestions. Every book still requires manual Preview and Apply.",
                    "If the file is not a valid book or no useful result exists, choose Move to Manual Review to set it aside, or Delete Book to move it into a -=deleted=- folder and stop Twano checking it. Either way the file is only moved, never erased — you can always bring it back by moving it out again.",
                ),
                (
                    "New to this page? “Applying” a match means "
                    "Twano updates its own record for that book (title, "
                    "author, cover, and so on) and, if you left file "
                    "organisation ticked, renames and moves the file into "
                    "a tidy folder. The ebook's actual content is never "
                    "changed — only its filename, location, and the "
                    "details Twano stores about it.",
                    "By default, each watched library organises its own "
                    "books into its own Author/-=Series=- folders. If you'd "
                    "rather every organised (and deleted) book land in one "
                    "single folder instead, set that up once in Settings → "
                    "File Organisation.",
                ),
            ),
            "Metadata",
        )
        self.tabs.addTab(
            _topic(
                "Keep the Library Healthy",
                "Every warning has a direct action.",
                (
                    "Open Library Health and review the explainable score.",
                    "Choose the action on a health card to open the right tool.",
                    "Review possible duplicates; byte-identical files and EPUBs differing only by recognised Apple catalogue metadata are clearly labelled as exact copies.",
                    "Quarantine only confirmed exact copies and restore them if needed.",
                ),
                (
                    "A book can show as “missing” if its file was "
                    "moved or deleted outside Twano (for example, moved by "
                    "hand in Windows Explorer). This is not destructive on "
                    "Twano's side — the catalogue entry and its details "
                    "stay intact. If you moved the file into your "
                    "configured destination folder yourself, re-saving "
                    "that folder path in Settings → File Organisation "
                    "checks for it and clears the missing flag "
                    "automatically.",
                ),
            ),
            "Health",
        )
        self.tabs.addTab(
            _topic(
                "Backups, Restore and Undo",
                "Select the safety card at the bottom of the navigation bar.",
                (
                    "Create and verify a catalogue backup at any time.",
                    "Review Activity & Undo to understand every protected operation.",
                    "Use Undo where a full inverse is available.",
                    "Use Restore for a whole-catalogue recovery; ebook files are untouched.",
                ),
                (
                    "A “backup” here means a snapshot of Twano's "
                    "own catalogue database — the record of your books, "
                    "their details, and where they are — not the ebook "
                    "files themselves. Restoring one puts that record back "
                    "to an earlier point without touching any file on "
                    "disk.",
                ),
            ),
            "Safety",
        )
        self.tabs.addTab(
            _topic(
                "Plugins, Calibre and Network Libraries",
                "Twano accepts only approved plugin sources.",
                (
                    "Open Plugins and tick one or more approved providers.",
                    "Choose Install Selected to install all eligible checked providers.",
                    "For a provider that needs a key, choose Configure API Key and follow its guide.",
                    "Choose Enable Selected; Active providers join Metadata search.",
                    "Use Calibre & Network Libraries to detect Calibre.",
                    "Offline NAS locations stay unavailable instead of marking books deleted.",
                ),
                (
                    "You do not need to enable every plugin. Open Library "
                    "alone covers most books with no setup at all; the "
                    "others are optional extras for when a particular book "
                    "is hard to find. A provider that needs a key usually "
                    "means creating a free account on that service's own "
                    "website first — Configure API Key explains exactly "
                    "what to paste in.",
                ),
            ),
            "Integrations",
        )
        self.tabs.addTab(
            _topic(
                "Getting Help",
                "If something looks wrong, start here before asking for "
                "help elsewhere.",
                (
                    "Try the guide tab above that matches what you were "
                    "doing — most unexpected results (a missing book, an "
                    "odd match, a stuck plugin) are explained in plain "
                    "terms there.",
                    "If that doesn't explain it, select Diagnostic Report "
                    "at the bottom of the navigation bar.",
                    "Choose where to save the file when prompted, then "
                    "attach that file when you describe the problem.",
                ),
                (
                    "The Diagnostic Report is a plain text file listing "
                    "your Twano version, a summary of your library and "
                    "watched folders, which plugins are active, and recent "
                    "activity — it is built to leave out your Windows "
                    "account name, real folder names, book titles, and any "
                    "API keys, replacing folder paths with generic labels "
                    "like [WATCHED_SOURCE_1] instead. Nothing is sent "
                    "anywhere automatically; you choose where it is saved "
                    "and whether to share it.",
                ),
            ),
            "Getting Help",
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.tabs, 1)


class WhatsNewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("What's New")
        title.setObjectName("pageTitle")
        description = QLabel(
            f"{APP_VERSION} — {RELEASE_NAME}"
        )
        description.setObjectName("pageDescription")
        panel = QFrame()
        panel.setObjectName("guidancePanel")
        panel_layout = QVBoxLayout(panel)
        for heading, copy in (
            (
                "Metadata & Cover Art",
                "One filename-aware search finds both book details and covers "
                "from every active direct provider, including library, "
                "public-domain, academic, community and commercial sources. "
                "Structured series names and reading order are retained from "
                "Open Library, Google Books, Hardcover and Amazon results. "
                "Invalid files can be moved into a scan-excluded manual "
                "review folder before continuing with the next book.",
            ),
            (
                "Duplicate Review & Library Health",
                "Explainable duplicate evidence, recoverable quarantine, and "
                "health cards that take you directly to the right tool.",
            ),
            (
                "Calibre, Network Libraries & Approved Plugins",
                "Documented Calibre launch support, offline NAS protection, "
                "a controlled provider catalogue, and protected API-key setup.",
            ),
            (
                "Simpler Twano",
                "A calmer navigation bar, larger original-style branding, "
                "and a quiet application status strip along the bottom.",
            ),
        ):
            heading_label = QLabel(heading)
            heading_label.setObjectName("sectionTitle")
            copy_label = QLabel(copy)
            copy_label.setObjectName("sectionDescription")
            copy_label.setWordWrap(True)
            panel_layout.addWidget(heading_label)
            panel_layout.addWidget(copy_label)
        panel_layout.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(panel, 1)


class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        title = QLabel("About Twano")
        title.setObjectName("pageTitle")
        description = QLabel(BRAND_TAGLINE)
        description.setObjectName("pageDescription")

        panel = QFrame()
        panel.setObjectName("guidancePanel")
        form = QFormLayout(panel)
        form.setContentsMargins(24, 20, 24, 20)
        form.addRow("Version", QLabel(APP_VERSION))
        form.addRow("Release", QLabel(RELEASE_NAME))
        form.addRow("Catalogue", QLabel(str(DEFAULT_DATABASE_PATH)))
        form.addRow("User data", QLabel(str(APP_DATA_FOLDER)))
        form.addRow(
            "Privacy",
            QLabel(
                "Book details leave this computer only after a manual "
                "metadata or cover lookup."
            ),
        )
        source_button = QPushButton("Open Library API Information")
        source_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://openlibrary.org/developers/api")
            )
        )
        folder_button = QPushButton("Open Twano Data Folder")
        folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(APP_DATA_FOLDER)))
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(folder_button)
        actions.addWidget(source_button)
        actions.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(panel)
        layout.addLayout(actions)
        layout.addStretch()
