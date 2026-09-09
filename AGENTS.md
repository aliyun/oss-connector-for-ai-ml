# Repository Agent Instructions

## Secret-safety gate

- Never add real access keys, secret keys, session tokens, signed credentials, private keys, or other secrets to source, tests, documentation, fixtures, logs, or commit messages.
- On a new checkout, run `./scripts/install-hooks.sh` before committing or pushing.
- The installer must not overwrite an existing developer hook. If it reports a conflict, preserve the existing hook and follow the integration instructions printed by the installer.
- Before creating a commit, stage only the intended files and run `./scripts/check-secrets.sh staged`. The installed `pre-commit` hook runs the same check automatically.
- Do not bypass Git hooks with `--no-verify`, environment changes, alternate hook paths, or equivalent workarounds.
- Allow the installed `pre-push` hook to scan every outgoing commit before any push. If it fails, stop and resolve the finding before pushing.
- Do not weaken `.gitleaks.toml`, add broad allowlists, or mark a finding as safe merely to make a scan pass. Any exception must be narrow and must be verified as public, deterministic test data rather than a usable credential.
- Do not commit files under `.git/hooks/` or a local `gitleaks` binary. Commit the shared files under `scripts/` and `.gitleaks.toml` instead.
