# Contributing

Read the repository and relevant documentation before changing it. Keep work limited to the requested milestone, preserve existing behaviour unless a task explicitly changes it, and avoid unrelated refactors.

The dependency direction is UI -> services -> database -> SQLite. UI classes own widgets and presentation; services own orchestration; database modules own SQL and transactions. Background work belongs in Qt workers, and every SQLite connection must be opened, used, and closed in the same thread.

Use the applicable brief under [`prompts/`](prompts/), or start from [`prompts/templates/`](prompts/templates/). Architectural detail is in [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`docs/architecture.md`](docs/architecture.md). Repository-specific agent rules are in [`AGENTS.md`](AGENTS.md).

For code changes, run:

```text
python -m compileall -q src tests tools
python -m pytest -v
python tools/check_github_readiness.py
```

Report the command, pass/fail/skip counts, and unresolved failures. Update documentation when architecture, behaviour, setup, or workflows change. Do not commit, push, merge, delete branches, or rewrite history unless explicitly instructed.

Never commit real API keys, user libraries, ebook files, databases, logs,
backups, local release archives, downloaded Calibre plugins, or signing keys.
Use synthetic test fixtures and redact screenshots and diagnostics.

Twano is currently proprietary. Contributions may be accepted only with the
repository owner's approval and remain subject to `LICENSE.md`. Do not copy
third-party plugin or website code into Twano without a documented compatible
licence and provenance review.
