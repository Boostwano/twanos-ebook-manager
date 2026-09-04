# Milestone 3: Metadata Engine v1

**Status: Completed**

## Goal

Introduce a provider-based metadata framework without changing current EPUB metadata behaviour or adding external integrations.

## Background

Local extraction reads embedded EPUB package metadata. The framework must separate provider-neutral results, provider selection, and local extraction so future providers can be added without changing scanner logic.

## Completed State

The repository contains `MetadataResult`, `MetadataProvider`, `ProviderManager`, `LocalMetadataProvider`, and provider-aware scan orchestration. Focused metadata tests and the complete regression suite pass.

## Requirements

- Create a UI-independent `MetadataResult` model.
- Create an abstract `MetadataProvider` interface.
- Create a `ProviderManager`.
- Create a `LocalMetadataProvider` wrapping existing local extraction.
- Make scanner or metadata orchestration use `ProviderManager`.
- Register only the local provider by default.
- Support confidence values on provider results.
- Allow future providers without modifying scanner logic.
- Preserve current EPUB metadata behaviour.
- Add unit tests.
- Run the complete test suite.

## Acceptance Criteria

- Provider code imports without PySide6.
- Confidence is represented consistently and validated.
- Provider execution and selection are deterministic.
- The default manager contains only the local provider.
- Local EPUB fields and statuses remain compatible.
- Scanner logic depends on the manager, not a concrete provider.
- Unit tests and the complete suite pass.

## Tests

- Model immutability and confidence bounds.
- Registration and duplicate-name handling.
- Highest-confidence selection.
- Local adapter field and status preservation.
- Default local-only registration.
- Scan and service integration.
- `python -m pytest -v`

## Manual Verification

- Scan a valid EPUB and confirm embedded metadata is persisted.
- Scan supported non-EPUB files and confirm existing unsupported behaviour.
- Confirm the application starts and Library displays scanned records.

## Deliverables

- Provider-neutral model and interface.
- Provider manager and local adapter.
- Provider-aware metadata and scan orchestration.
- Unit tests and updated metadata documentation.

## Migration or Compatibility Risks

- Status changes could affect dashboard health and Library filters.
- Wrong-thread database creation could regress scan safety.
- Confidence ties must preserve deterministic precedence.

## Out of Scope

- Open Library
- Google Books
- ISBNdb
- networking
- cover downloading
- duplicate detection
- file renaming
- file organisation
- plugins
- unrelated UI redesigns
