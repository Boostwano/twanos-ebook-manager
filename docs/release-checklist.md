# Release Checklist

- [ ] Working tree reviewed; every change belongs to the release.
- [ ] Complete `python -m pytest -v` suite passes.
- [ ] Application starts.
- [ ] Dashboard loads.
- [ ] Library loads before scanning.
- [ ] Library loads after scanning.
- [ ] Search and filters work.
- [ ] Scan completes.
- [ ] A second scan works without restarting.
- [ ] Cancellation restores controls.
- [ ] Application exits without `QThread` warnings.
- [ ] Version is updated in every applicable location.
- [ ] Documentation is updated.
- [ ] Changelog or release notes are updated where applicable.
- [ ] Installer is tested when packaging exists.
- [ ] Git tag is created only after explicit approval.
