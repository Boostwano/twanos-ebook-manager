# Twano R4 RC6.4 Test Report

**Package:** Responsive Home and Smart Search  
**Date:** 28 July 2026  
**Automated result:** Passed  
**Windows acceptance:** Passed
**Package validation:** Passed

## Environment

- Windows
- Python 3.14.6
- pytest 9.1.1
- PySide6 6.11.1
- Qt offscreen platform for automated widget and render checks

## Baseline

Before the banner-completion changes:

```text
python -m pytest -v
46 passed
```

## Compilation

Command:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Result:

```text
Passed
```

## Focused banner and UI tests

Command:

```text
.\.venv\Scripts\python.exe -m pytest -v tests\test_banner_service.py tests\test_rc6_4_ui.py
```

Result:

```text
15 passed
0 failed
0 skipped
```

Coverage includes:

- legacy preference migration
- invalid preference fallback
- fixed selection
- all seven bundled assets
- once-per-launch rotation
- missing-asset fallback layers
- painted fallback rendering
- Settings banner modes
- responsive sidebar and Home geometry
- greeting height
- floating suggestions
- Search Results routing and Home reset
- metadata Review Queue routing

## Complete regression suite

Command:

```text
.\.venv\Scripts\python.exe -m pytest -v
```

Result:

```text
55 passed in 2.36s
0 failed
0 skipped
0 warnings
```

## Visual render checks

`DashboardPage` was rendered with the real Grand Library artwork at:

- 1280×720
- 1920×1080

The renders confirm that the artwork fills the fixed hero, the left text
backdrop remains present, and Home geometry does not shift. The offscreen Qt
platform did not reproduce normal Windows font glyphs reliably, so font
appearance and clipping are not marked as manually accepted.

## Windows acceptance

The user confirmed the updated application was working correctly on Windows
on 28 July 2026 after following the requested RC6.4 checks.

- [x] Select and visually confirm all seven banners.
- [x] Confirm Fixed banner survives restart.
- [x] Confirm Rotate on startup remains stable during a launch and can change
      between launches.
- [x] Confirm Home at 1280×720, 1366×768, 1600×900, 1920×1080, and
      2560×1440.
- [x] Confirm every greeting is readable and unclipped.
- [x] Confirm floating search and Review Queue routing.
- [x] Confirm Windows default, custom reader, ask-every-time, and containing
      folder Reading modes.
- [x] Launch and validate the final ZIP from its packaged location.

## Package validation

- Constructed the package from the accepted workspace.
- Excluded Git metadata, virtual environments, caches, compiled Python,
  temporary test data, and nested ZIP files.
- Confirmed the entry point, launcher, requirements, release evidence, and all
  seven banner assets are present.
- Opened and read every compressed entry successfully.
- Extracted the archive into a clean validation directory.
- Smoke-launched the extracted source with the pinned project environment.
- Confirmed Home opened and loaded its packaged banner artwork.

The final SHA-256 checksum is stored beside the ZIP in `C:\Twano\Builds`.
RC6.4 satisfies its automated, Windows, and package acceptance gates.
