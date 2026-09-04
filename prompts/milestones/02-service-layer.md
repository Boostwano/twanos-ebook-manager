# Milestone 2: Service Layer

**Status: Completed**

## Goal

Move application and database orchestration out of UI pages into UI-independent services with explicit dependencies.

## Confirmed Current State

- `LibraryService` owns Library query orchestration and returns presentation-neutral records.
- `DashboardService` builds an immutable dashboard snapshot.
- `MetadataService` provides metadata extraction orchestration.
- `ScanService` coordinates discovery, persistence, and metadata processing.
- The main window, UI pages, and scan worker use explicit service dependencies or factories.
- Raw SQL is confined to `DatabaseManager`; UI pages do not orchestrate database calls.
- Scan services are created inside the worker thread, preserving SQLite connection ownership.
- `tests/test_services.py` covers service behaviour, with scan lifecycle tests covering worker integration.

## Requirements Record

- Preserve scanning behaviour and thread safety.
- Keep services independent of PySide6 widgets.
- Keep persistence details in the database layer.
- Prefer explicit constructor dependencies and factories.
- Test service boundaries with isolated fakes or temporary databases.

## Acceptance Record

The required services, dependency boundaries, scan-thread integration, and service tests are present in the current checkout. Milestone 2 is therefore completed.

## Related

- [Architecture](../../docs/architecture.md)
- [Database](../../docs/database.md)
