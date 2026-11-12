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

**Publication is implemented for the signed pilot 0.1.11.** The distribution operator runs:

```bash
cd /opt/iFaceMatch/ifacematch
git pull --ff-only
gh auth status || gh auth login
make publish VERSION=0.1.11
```

The publish command verifies the signed archive against local Ed25519 trust, checks its pinned SHA-256 and the updater script, then creates a new `v0.1.11` GitHub Release with exactly three assets: the archive, `SHA256SUMS`, and `ifacematch-update.sh`. It checks that the source repository is public and at the current `main` commit, rejects existing releases/tags, and downloads published files to verify their checksums. Never upload private signing keys, client licenses or secrets.

**Pilot deployment is a separate privileged operation** on the customer VPS (`srv855672`):

```bash
curl --fail --location --silent --show-error \
  --output /root/ifacematch-update.sh \
  https://github.com/jefersonMarques/ifacematch/releases/download/v0.1.11/ifacematch-update.sh
bash -n /root/ifacematch-update.sh
bash /root/ifacematch-update.sh --check
```

After confirming an external snapshot/backup and an appropriate maintenance window, run `bash /root/ifacematch-update.sh 0.1.11` as root. The updater downloads and caches the pinned archive, validates its SHA-256 and uses the installed iFaceMatch CLI to verify the Ed25519 signed release, stage it under a new version and switch only the Console unit with rollback on failed post-update checks. The `--check` mode may write the local cache but does not restart services. Do not use this pilot-specific script on other servers.

`make deploy` is still blocked until a general multi-version component updater is independently tested. Publishing is **not** deploying.

The detailed candidate pilot upgrade and rollback instructions live in the private Admin repository on the pinned branch, under `docs/RELEASE_0_1_11_CONSOLE_LOGIN_HOTFIX.md`. The current generic server upgrade intentionally rejects Console-only changes; do not force it or edit signed release files in place.

Operational release publication, HTTPS setup, signed manifest verification, smoke tests and rollback evidence remain mandatory before changing production.
