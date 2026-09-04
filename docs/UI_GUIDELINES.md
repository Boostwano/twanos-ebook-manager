# UI Guidelines

## Responsive page layout

- Top-level application pages must fit inside Twano's supported 900 x 600
  minimum window without a page-level scrollbar.
- Reflow fields and actions, use tabs to separate distinct tasks, and let data
  tables or long-detail viewers scroll internally when their content requires
  it.
- Give editable fields the expanding space in a row. Omit secondary table
  columns at compact widths when the same facts remain available in Details.
- Prefer a short heading and one concise orientation sentence. Move extended
  explanations into tooltips, guides, or context shown only when needed.
- New pages must be checked at both 900 x 600 and a normal restored desktop
  size before their milestone is accepted.

## Home

- Keep the banner hero compact enough for the three-card dashboard to remain
  visible at the minimum window size.
- Preserve one Library Summary card, one Recent Activity card, and one Quick
  Links card. Put contextual guidance inside a card instead of adding another
  full-width dashboard section.
- Keep Find a Book immediately below the hero and use an overlay for live
  suggestions so results never push the cards down.

## Action colours

Colour may distinguish adjacent commands when a uniform neutral button group
could be mistaken for one selected action and several inactive actions.

- Keep the text label as the primary meaning; colour is supporting information.
- Use a consistent colour for the same action wherever it appears.
- Preserve white text contrast of at least 4.5:1 on enabled action backgrounds.
- Provide distinct hover and pressed states.
- Every enabled push button must visibly depress when pressed. Use the shared
  two-pixel down-and-right content movement with an inset/darker state, keeping
  total padding unchanged so the surrounding layout does not jump.
- Use the shared subdued disabled style only when an action is unavailable.
- Do not use an enabled action colour to imply a persistent selection state.

## Protection Centre

- State exactly what has been verified: a creation-time manifest is not a
  substitute for running Verify Backup again.
- Use `Verified`, `Changed`, `Invalid`, `Unverified`, and `Missing` as
  evidence states rather than vague success or failure colouring.
- Keep routine recovery language concrete: **Restore Backup**, **Review Old
  Backups**, and **Cancel**. Do not require users to understand manifests,
  basis tokens, staged files, or audit transitions.
- Restore uses one plain-language confirmation explaining that Twano checks
  the selected backup and automatically makes a safety copy first.
- Old-backup review shows the exact count and total size before confirmation
  and states which changed, recent, unverified, or unrelated files stay.
- Keep detailed plan and recovery evidence in Activity & Undo; it must support
  diagnosis without becoming a prerequisite for routine Restore or cleanup.
- Resize settings and action rows with the page; stack them only below the
  supported application width.
- Cancellation text must explain that Twano stops at the next safe boundary.

## Change plans and history

- Always separate intended database changes from intended file changes.
- Show affected books, risk, reversibility, warnings, and current status before
  an approval control.
- Label approval-only states explicitly when Apply is not available.
- Never use `Approved` as a synonym for `Applied`.
- Preserve cancelled and failed plans in history; they are safety evidence.
- Reports must repeat that planned/approved intent does not prove execution.
- Separate plan preview and operation history into task tabs. Omit secondary
  compact table columns before horizontal scrolling is needed.
- Keep Preview, Approve, Apply, Preview Undo, and Cancel as visibly distinct
  actions. Approval must never imply execution.
- Enable Apply only for an approved allowlisted plan in Standard mode. Enable
  Preview Undo only when persisted inverse data and current state prove it is
  still safe.

## Scan Apply

- Preserve the selected-source **Preview Scan → Apply Preview** flow and the
  combined **Preview All Watched Folders → Apply All Previews** flow. Combined
  work processes sources sequentially and retains a separate verified backup
  and Undo history record for each source. The common
  protection plan and approval are internal implementation details.
- Use one confirmation that says Twano rechecks candidates, creates a safety
  backup automatically, updates the catalogue, and never changes ebook files.
- In Read-Only mode, disable Apply and point directly to the Protection Mode
  setting.
- Keep New, Changed, Missing, Unchanged, Unreadable, and Safely skipped counts
  in Scan History. Do not duplicate those columns in Activity & Undo.
- Label recovery as **No one-click Undo; safety backup available**. Do not
  imply that restoring the whole catalogue is a narrow per-scan Undo.
