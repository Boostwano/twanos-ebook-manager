# Security Policy

## Supported versions

Only the latest published Twano Beta or production release receives security
fixes. Development snapshots and older test packages are unsupported.

## Reporting a vulnerability

Do not post API keys, book-library details, personal data, exploit details, or
unpatched vulnerabilities in a public issue.

While the source repository is private, report a suspected vulnerability
directly to the repository owner. After GitHub publication, use the
repository's private security-advisory feature.

Include:

- the affected Twano version;
- clear reproduction steps using expendable test data;
- the expected and observed behaviour;
- whether catalogue or ebook files may be affected;
- logs with credentials, usernames, book titles, and local paths removed.

Twano will acknowledge the report, assess severity, prepare and validate a
fix, and publish an advisory when users have a safe update path.

## Secrets

Provider API keys belong only in Twano's Windows-protected credential store.
Never place real keys in source files, tests, screenshots, issue reports,
workflow files, release notes, or GitHub Actions variables intended for public
output.
