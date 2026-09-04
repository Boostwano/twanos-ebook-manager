# Twano's eBook Manager

## Project

Twano's eBook Manager is a Python and PySide6 desktop application for scanning, cataloguing, searching, and managing ebook files.

## Architecture

The intended dependency direction is:

```text
UI -> Services -> Database -> SQLite
```

Background scanning uses Qt workers and QThreads.

## Working rules

Before making changes:

- Read the repository and relevant documentation.
- Understand the current implementation.
- Keep changes limited to the requested milestone.
- Modify the minimum number of files necessary.
- Preserve existing behaviour unless the task explicitly changes it.

Never commit, push, merge, delete branches, or rewrite Git history unless explicitly instructed.

## UI and services

- UI classes manage widgets, signals, navigation, and presentation.
- Services contain application and business orchestration.
- UI classes must not contain raw SQL.
- Services must not depend on PySide6 widgets.
- Avoid circular imports and hidden global state.

## Database and threading

- Database modules own SQL, connections, transactions, and persistence.
- SQLite connections must be created, used, and closed in the same thread.
- Never share SQLite connection objects between GUI and worker threads.
- Long-running work must not run on the GUI thread.
- Do not introduce blocking QThread waits on the GUI thread.
- Preserve safe worker cleanup and repeated scan support.

## Code quality

Prefer:

- small focused functions
- descriptive names
- explicit dependencies
- useful type hints
- straightforward implementations

Avoid:

- giant classes
- unnecessary frameworks
- duplicated code
- speculative abstractions
- commented-out code
- unrelated refactors

## Testing

Before finishing any code task, run:

```text
python -m pytest -v
```

Report:

- command executed
- passed and failed test counts
- skipped tests
- unresolved failures

## Documentation

Update documentation when architecture, behaviour, setup, or workflows change.

Keep these aligned where relevant:

- README.md
- ARCHITECTURE.md
- CONTRIBUTING.md
- docs/
- prompts/roadmap.md
