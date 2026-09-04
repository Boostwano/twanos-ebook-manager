# Twano R4 RC6.4 Milestones Brief

**Release:** Twano R4 RC6.4 — Responsive Home and Smart Search  
**Status:** Accepted

## Purpose

This brief divides the RC6.4 change specification into reviewable delivery
milestones. The detailed requirements remain in
[`RC6.4-Change-Specification.md`](RC6.4-Change-Specification.md), and the
long-term package sequence remains in
[`Twano-Master-Delivery-Roadmap.md`](Twano-Master-Delivery-Roadmap.md).

## Milestone 1 — Responsive shell and Home

- Scale sidebar branding, navigation, and protection status within clamped
  desktop limits.
- Keep normal desktop sizes free from sidebar scrolling.
- Scale Home card typography, icons, actions, padding, and spacing.
- Use real font metrics for every supported hero greeting.
- Preserve explicit page-ID navigation and the RC6.3 design system.

## Milestone 2 — Smart search and actionable metadata

- Keep Home search suggestions in a floating overlay.
- Support keyboard navigation and dismissal.
- Route submitted searches to a dedicated Search Results page.
- Reset transient Home search state whenever Home is reopened.
- Route metadata warnings to a filtered, data-backed Review Queue.
- Continue to use shared Reading settings when opening books.

## Milestone 3 — Hero banner completion

- Display all seven bundled 2048×682 banner images.
- Provide a fixed selected-banner mode.
- Provide a rotate-on-startup mode that chooses once per application launch.
- Validate the selected banner and mode before use.
- Migrate legacy `off`, `favourite`, `random`, `daily`, `weekly`, and
  `seasonal` mode values to the two supported RC6.4 modes.
- Fall back to the default image, then another available image, then the
  painted safe scene when assets are unavailable.
- Preserve responsive text, contrast, and greeting-height behaviour.

## Milestone 4 — Validation and release gate

- Compile all Python source.
- Run focused preference, banner-service, and PySide6 UI tests.
- Run the complete pytest suite.
- Render representative Home layouts at 1280×720 and 1920×1080.
- Complete the Windows UI and native reader checklist.
- Validate the release ZIP only after the Windows checklist is accepted.

## Automated acceptance criteria

- All seven configured banner assets resolve.
- Invalid names use `The Grand Library`.
- Legacy rotation values persist as `fixed` or `startup`.
- Startup rotation remains stable while the application is open.
- Missing artwork never prevents Home from rendering.
- Search, navigation, responsive, scan, service, and database regression tests
  continue to pass.

## Windows acceptance checklist

- Open Settings > Home and select each of the seven banners.
- Save each selection and confirm Home displays the corresponding image.
- Select Fixed banner, restart Twano, and confirm the selected image remains.
- Select Rotate on startup, restart Twano twice, and confirm one image is used
  consistently during each launch.
- Check Home at 1280×720, 1366×768, 1600×900, 1920×1080, and 2560×1440.
- Confirm all greeting text is readable and unclipped.
- Confirm search suggestions float without moving Home cards.
- Confirm Search Results and Review Queue routing.
- Confirm all four Reading modes with installed Windows applications.

RC6.5 must not begin until this checklist is accepted or any exceptions are
recorded explicitly.
