# Publish Twano to a Private GitHub Repository

Do not use `git add .` for the first publication. Twano keeps local build
archives, downloaded plugin research, and runtime test data beside the source;
the repository audit must exclude them.

## One-time account preparation

1. Create the GitHub account and enable two-factor authentication.
2. Save recovery codes outside the development computer.
3. In GitHub email settings, enable email privacy and copy the GitHub-provided
   `noreply` address.
4. Configure that address locally before creating the publication commit.
5. Create or publish `twano-ebook-manager` as a **private** repository.

Do not place a GitHub token, provider API key, signing key, or password in this
folder.

## Pre-publication checks

From the project root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe tools\check_github_readiness.py
git status --short
```

All three validation commands must pass. Review every line of `git status`.

## Explicit first staging

Only after the checks pass:

```powershell
git add -- `
  .gitattributes .github .gitignore AGENTS.md ARCHITECTURE.md CHANGELOG.md `
  CONTRIBUTING.md LICENSE.md PROJECT_HANDOVER.md README.md ROADMAP.md `
  SECURITY.md START_HERE.txt THIRD_PARTY_NOTICES.md UPLOAD_TO_GITHUB.md `
  launcher.bat packaging prompts pytest.ini requirements-build.txt `
  requirements.txt src tests tools design docs

git diff --cached --name-only
git diff --cached --check
```

Confirm the staged list contains no:

- `.env`, database, credential, log, cache, or test-runtime file;
- ebook file;
- root release ZIP;
- `zip/` Calibre-plugin research archive;
- private signing key;
- real provider API key.

Stop and unstage the affected file if anything unexpected appears.

## First publication

Committing and pushing are deliberate release-management actions. Perform them
only after the staged-file review is approved:

```powershell
git commit -m "Prepare Twano R4 Beta 2 private source repository"
git push -u origin main
```

Create releases as drafts, attach only a package that passed clean-extraction
validation, and publish the draft only after testing that exact asset.
