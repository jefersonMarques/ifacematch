# Signed release workflow

## Prerequisites

Ubuntu or WSL with Git, Go, Python 3, Make and Tar, plus access to the four component repositories. For release signing, the authorized operator also needs the existing Ed25519 distribution authority stored privately in `~/.config/ifacematch/distribution/`. Never copy signing private keys into Git repositories or customer servers.

The release adapter implemented at this stage targets **0.1.11**, a Console-only correction from the signed 0.1.10 baseline. The signed 0.1.10 archive must match SHA-256:

`e6d0e991694c471c79e4d2e6d02f641b5144ec48d3f4bb9900b4eaca1ba5373e`

## Local commands

```bash
cd /opt/iFaceMatch/ifacematch
make doctor
make bootstrap
make test
make build
make release-base
make release VERSION=0.1.11
make release-verify VERSION=0.1.11
```

By default, `make release-base` and `make release` automatically locate the signed 0.1.10 archive in the coordinator release directory, local workspace releases, an operator release pointer (`~/.config/ifacematch/release-0.1.10.path`) or matching local signing directories. All candidates are checked against the pinned SHA-256. No archive is downloaded from an untrusted location. If no valid archive exists, the command exits without making a release; you can register its directory in the pointer file once or use `BASE_ARCHIVE=/absolute/path/to/archive.tar.gz` as a one-time override.

The `build` target creates **unsigned development binaries** under `dist/build/`; they are not production deliverables. The `release` target invokes the Admin candidate builder pinned by the lockfile, performs Console tests and signed baseline checks, signs a complete new release and enforces that the only changed components are Console binary and its provenance.

Signed packages are placed under `dist/releases/0.1.11/` and are excluded from Git. No license record, database or VPS is touched by these local commands.

## Publication and deployment

`make publish` and `make deploy` are **fail-closed** until an independently reviewed production adapter is integrated and tested. These targets only verify the local signed package and refuse remote mutations. Do not interpret a successful build as a published release.

The detailed candidate pilot upgrade and rollback instructions live in the private Admin repository on the pinned branch, under `docs/RELEASE_0_1_11_CONSOLE_LOGIN_HOTFIX.md`. The current generic server upgrade intentionally rejects Console-only changes; do not force it or edit signed release files in place.

Operational release publication, HTTPS setup, signed manifest verification, smoke tests and rollback evidence remain mandatory before changing production.
