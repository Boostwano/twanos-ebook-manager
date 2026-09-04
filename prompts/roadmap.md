# Engineering Prompt Roadmap

> **Delivery authority:** Release work follows
> [`docs/Twano-Master-Delivery-Roadmap.md`](../docs/Twano-Master-Delivery-Roadmap.md).
> R4 Beta 1 is accepted. R4 Beta 2 reliability, provider, multi-folder,
> accessibility, and publication hardening is in development. Automated and
> clean-package validation pass; guided native Beta 2 acceptance remains.
> This table is retained only as historical engineering planning.

This is the execution-oriented roadmap. Detailed briefs live in [`milestones/`](milestones/); the reader-facing summary is in [`docs/roadmap.md`](../docs/roadmap.md).

| Milestone | Scope | Status |
| --- | --- | --- |
| 1 | Stabilisation | Completed |
| 2 | Service layer | Completed |
| 3 | Metadata provider framework | Completed |
| 4 | Open Library integration | Completed |
| 5 | Google Books integration | Planned |
| 6 | Metadata review queue | Planned |
| 7 | Duplicate detection | Planned |
| 8 | Rename and organise | Planned |
| 9 | Plugin framework | Planned |
| 10 | Packaging and Windows installer | Planned |

Milestone 2 is completed because the repository contains the service implementations, explicit UI dependencies, and service tests. Milestone 3 is completed because the local provider engine is integrated. Milestone 4 is completed because opt-in, cached Open Library enrichment is integrated through the provider manager with conservative matching and mocked network tests.
