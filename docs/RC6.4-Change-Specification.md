# Twano R4 RC6.4 — Responsive Home and Smart Search

## Source package

Continue from:

`Twano-R4-RC6.3-Twano-Design-System.zip`

Do not rename the existing ZIP. Inspect and genuinely modify the source, run available tests, and produce:

`Twano-R4-RC6.4-Responsive-Home-and-Smart-Search.zip`

---

## Product direction

Twano is a digital librarian rather than simply an ebook manager.

Core principles:

- Beginner friendly
- Safe by design
- Preview before changes
- Automatic backups
- Unlimited Undo
- Calm, professional single-window interface
- Dark theme
- Beautiful rather than corporate
- Home is welcoming rather than statistics-heavy
- Every warning must provide a direct path to resolve it

Preserve the approved visual direction:

- Large blue open-book logo
- Large **TWANO** title
- **eBook Manager** subtitle
- Dark navy and blue colour palette
- Large coloured icons
- Larger readable typography
- Strong visual hierarchy
- Square or only subtly rounded hero banner
- Premium desktop application appearance

---

# Required changes

## 1. Responsive sidebar

### Current problem

The left navigation becomes vertically scrollable when the application window is resized.

### Required behaviour

The sidebar should resize its contents to fit normal supported desktop sizes rather than showing a visible scrollbar.

Dynamically scale:

- Logo
- TWANO title
- eBook Manager subtitle
- Navigation icons
- Navigation text
- Navigation item heights
- Vertical padding
- Section spacing
- Protection Mode panel

Keep:

- Branding at the top
- Protection Mode panel at the bottom
- All navigation entries accessible
- Existing navigation groups and divider

Use scrolling only as an emergency fallback for exceptionally small windows.

Navigation entries:

### Main group

- Home
- Library
- Scan
- Metadata
- Review Queue
- Analytics
- Library Health
- Plugins
- Settings

### Secondary group

- User Guide
- What's New
- About

---

## 2. Responsive dashboard cards

The cards currently resize, but their text and icons remain almost fixed.

Scale the following according to both available width and height:

- Card headings
- Card heading icons
- Summary icons
- Summary values and labels
- Recent Activity text
- Quick Action icons
- Quick Action labels
- Buttons
- Card padding
- Row heights
- Element spacing
- Status or insight banner text and icons

Use clamped minimum and maximum sizes.

Expected behaviour:

```text
Small window   -> compact but readable
1920 × 1080    -> normal Twano sizing
Large/4K       -> larger text, icons and spacing

Do not allow uncontrolled scaling, clipping, overlapping or unnecessary scrollbars.

3. Fix clipped hero greeting

The bottom of Good evening is clipped at both maximised and resized window sizes.

Required fix:

Remove insufficient fixed label heights.
Use the rendered font metrics or natural size hint.
Add safe top and bottom padding.
Recalculate minimum height after responsive font changes.
Ensure all letters render fully.
Preserve the current alignment and spacing.
Test every possible greeting, not only “Good evening”.
4. Actionable metadata insight

Replace the passive message:

3 books could benefit from better metadata.

With an actionable insight such as:

3 books need metadata improvements
Review Now

The message or Review Now action must be clickable.

Clicking it must open the existing Review Queue, filtered to books requiring metadata attention.

The filtered results should identify:

Book title
Author
Format
Cover when available
Missing or weak metadata fields
A direct action to review or fix metadata

Metadata problems may include:

Missing title
Unknown author
Missing ISBN
Missing publisher
Missing cover
Missing series
Missing description
Inconsistent metadata

Design rule:

Every warning should provide a direct path to review or resolve it.

5. Remove inline Home search results

Search results must no longer expand inside the Home page layout.

The current behaviour pushes the dashboard cards down and makes the page look messy.

The Home layout must remain stationary while search suggestions are displayed.

6. Floating search suggestions

When typing in the Home search field, show a compact floating panel below the field.

Requirements:

Float above dashboard content.
Do not participate in the Home page layout.
Show the best 3–5 results.
Have a fixed maximum height.
Do not push cards downward.
Close when:
Escape is pressed
The user clicks elsewhere
The field is cleared
The user navigates away

Each suggestion should contain:

Small cover thumbnail
Title
Author
Format

Include this final option:

View all results for “search term”

Keyboard behaviour:

Down Arrow: select next result
Up Arrow: select previous result
Enter: open selected result
Enter with nothing selected: open full Search Results
Escape: close the suggestions
7. Dedicated Search Results page

Create a first-class Search Results page.

It should open when the user:

Presses Enter in the Home search field
Clicks Find a Book
Clicks View all results
Selects Search from navigation, should a navigation entry be added

Page header example:

Search Results
14 results for "dal"

Keep the query populated on this page so the user can refine it.

Each result should include:

Cover
Title
Author
Series when available
Format
Metadata status
Filename or library location
Open Book
View in Library or View Details

Provide room for filters such as:

Format
Author
Series
Metadata status
Library location

At minimum, implement the page and filter structure so it can be expanded later.

Opening a book must respect the existing Reading settings:

Windows default application
Custom reader
Ask every time
Open containing folder
8. Clear search when returning Home

Whenever the user returns to Home:

Clear the Home search field.
Close the suggestion panel.
Clear any selected suggestion.
Remove focus from the search field.
Restore the default dashboard presentation.

Do not restore the previous Home query.

The dedicated Search Results page may retain the query while the user remains on that page.

9. Preserve RC6.3 styling

Do not regress:

Twano open-book branding
Large TWANO title
eBook Manager subtitle
Coloured navigation icons
Large typography
Dark navy theme
Selected navigation styling
Protection Mode panel
Square hero design
Library Summary card
Recent Activity card
Quick Actions card
Smart insight or status area
Architecture

Create or improve reusable components where practical:

BrandHeader
ResponsiveSidebar
NavigationButton
ResponsiveCard
SmartInsight
SearchField
SearchSuggestionPopup
SearchResultItem
SearchResultsPage
Responsive typography helpers
Responsive icon-sizing helpers

Avoid putting all behaviour into one large Home widget.

Use explicit page IDs so adding Search or visual dividers cannot break navigation:

home
library
search
scan
metadata
review_queue
analytics
library_health
plugins
settings
user_guide
whats_new
about

Responsive calculations should be clamped:

value = clamp(minimum, calculated_value, maximum)

Use the actual application content area and consider both width and height.

Automated testing

Run all existing tests.

Add tests where practical for:

Search matching
Search page routing
Metadata-filter routing
Home search reset
Explicit page IDs
Responsive scaling clamps
Empty searches
No-result searches

Add or update PySide6 interface tests for:

Sidebar scrollbar normally hidden
Navigation options visible at common sizes
Hero greeting not clipped
Search suggestions not moving dashboard cards
Search popup open and close behaviour
Enter opening Search Results
Review Now opening filtered Review Queue
Returning Home clearing search
Card typography scaling
Text and icons not overlapping

Test these window sizes where possible:

1280 × 720
1366 × 768
1600 × 900
1920 × 1080
2560 × 1440

Never claim PySide6 tests passed unless they were actually executed.

Manual Windows testing

Verify:

Maximise Twano.
Resize it to approximately 1280 × 720.
Confirm the sidebar does not normally display a scrollbar.
Confirm every navigation option remains accessible.
Confirm TWANO and eBook Manager remain readable.
Confirm card fonts and icons grow when maximised.
Confirm they become compact but readable in smaller windows.
Confirm Good evening is fully visible.
Type in the Home search field.
Confirm suggestions float above the cards.
Confirm the Home cards do not move.
Press Escape and confirm suggestions close.
Press Enter and confirm Search Results opens.
Return Home and confirm the search field is empty.
Click Review Now.
Confirm Review Queue opens with metadata issues filtered.
Confirm books still open using the configured Reading settings.
Documentation

Update:

Application version
CHANGELOG.md
README.md
ROADMAP.md
PROJECT_HANDOVER.md
Relevant architecture documentation

Release name:

Twano R4 RC6.4 — Responsive Home and Smart Search

Packaging validation

Before creating the ZIP:

Compile all Python files.
Run available automated tests.
Check ZIP integrity.
Confirm the application entry point exists.
Confirm all required assets are included.
Exclude caches, temporary files and test output.
Instructions for the new chat

Use the attached RC6.3 ZIP as the source code.

Implement every requirement in this document and build:

Twano R4 RC6.4 — Responsive Home and Smart Search

Act as a collaborative software architect named Atlas. Challenge decisions when there is a stronger implementation, but preserve the agreed visual direction and user experience.

Inspect the source before modifying it. Do not fabricate successful tests. Produce a genuine updated ZIP and report:

Files changed
Features implemented
Tests passed
Tests that could not be run
Manual Windows checks required
 ​:contentReference[oaicite:0]{index=0}​