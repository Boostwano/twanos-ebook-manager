## What changed

Describe the user-visible or internal change.

## Safety

- [ ] No real API keys, credentials, personal library data, databases, ebook
      files, local build ZIPs, or downloaded plugin archives are included.
- [ ] Long-running work remains outside the GUI thread.
- [ ] SQLite connections are created, used, and closed in the same thread.
- [ ] Ebook files are unchanged unless the reviewed feature explicitly and
      safely performs a file operation.

## Validation

- [ ] `python -m compileall -q src tests tools`
- [ ] `python -m pytest -v`
- [ ] `python tools/check_github_readiness.py`
- [ ] Documentation and the user guide are updated where relevant.
