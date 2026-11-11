# iFaceMatch — Coordinator Architecture

The coordinator is not a monorepo or a replacement for the signed customer updater.

| Component | Responsibility |
| --- | --- |
| ifacematch-server | Biometric API, CLI and native biometric runtime |
| ifacematch-console | Customer Hosted operator console |
| ifacematch-admin | Central, licensing and signed release engineering |
| ifacematch-site | Portal, installer and developer-facing resources |
| ifacematch | Repository pins, local orchestration, tests and commercial release workflow |

`versions.lock.json` records **commit SHAs**, never moving branch aliases. Every `test` and `build` command archives those commits into temporary workspaces and does not alter the developer's working trees.

`bootstrap` clones missing repositories and fetches the pinned references into existing clones without resetting branches. A manual change to the lockfile requires review of all four commit SHAs.

The coordinator repository is currently public. Commit references and orchestration scripts are public metadata; private repositories, binaries, data, SSH keys, signing keys and licenses remain outside this repository.

Commercial artifacts may be built locally only when the authorized distribution signing material is available. Signed customer installation verification is enforced by the existing iFaceMatch CLI and release packager.
