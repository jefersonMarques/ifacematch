#!/usr/bin/env python3
"""Publish verified, immutable-by-policy iFaceMatch releases to GitHub."""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "jefersonMarques/ifacematch"
APPROVED_SHA256 = {
    "0.1.11": "4a44480bc5fe340ae1c26405284599560325807ac88c8c0daab8a645df10dc32"
}


class PublicationError(Exception):
    pass


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifacts(version, archive, checksums, updater, notes):
    if version not in APPROVED_SHA256:
        raise PublicationError(f"Unapproved release version: {version}")
    expected_archive = f"ifacematch-{version}-ubuntu-amd64.tar.gz"
    expected = {
        "archive": (archive, expected_archive),
        "checksums": (checksums, "SHA256SUMS"),
        "updater": (updater, "ifacematch-update.sh"),
        "notes": (notes, f"{version}.md"),
    }
    for label, (path, basename) in expected.items():
        if path.name != basename or not path.is_file() or path.is_symlink():
            raise PublicationError(f"Missing or unsafe {label}: {path}")

    expected_digest = APPROVED_SHA256[version]
    if checksum(archive) != expected_digest:
        raise PublicationError("Signed archive SHA-256 does not match the approved release")
    if checksums.read_text(encoding="utf-8") != f"{expected_digest}  {expected_archive}\n":
        raise PublicationError("SHA256SUMS must exactly match the approved archive")
    source = updater.read_text(encoding="utf-8")
    if f"expected_archive_sha256={expected_digest}" not in source:
        raise PublicationError("Updater does not pin the approved archive SHA-256")
    if f"release_version={version}" not in source:
        raise PublicationError("Updater version differs from the release")

    return {
        expected_archive: expected_digest,
        "SHA256SUMS": checksum(checksums),
        "ifacematch-update.sh": checksum(updater),
    }


def command(arguments, check=True, quiet=False, cwd=None):
    result = subprocess.run(
        [str(value) for value in arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        raise PublicationError(f"{arguments[0]} failed: {message}")
    if not quiet and result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    return result


def assert_absent(resource):
    result = command(
        ["gh", "api", f"repos/{REPOSITORY}/{resource}"],
        check=False,
        quiet=True,
    )
    if result.returncode == 0:
        raise PublicationError(f"Release or tag already exists: {resource}")
    if not re.search(r"\b404\b|not found", result.stderr, re.IGNORECASE):
        raise PublicationError(
            "Cannot confirm release/tag absence; refusing publication: "
            + (result.stderr.strip() or "GitHub API unavailable")
        )


def preflight_github():
    if shutil.which("gh") is None:
        raise PublicationError("GitHub CLI missing; install gh and run gh auth login")
    command(["gh", "auth", "status"], quiet=True)
    visibility = command(
        ["gh", "api", f"repos/{REPOSITORY}", "--jq", ".visibility"],
        quiet=True,
    ).stdout.strip()
    if visibility != "public":
        raise PublicationError("Distribution repository must be public for anonymous downloads")

    local_head = command(
        ["git", "rev-parse", "HEAD"], quiet=True, cwd=ROOT
    ).stdout.strip()
    remote_head = command(
        ["gh", "api", f"repos/{REPOSITORY}/branches/main", "--jq", ".commit.sha"],
        quiet=True,
    ).stdout.strip()
    if local_head != remote_head:
        raise PublicationError("Coordinator is not at origin main; run git pull --ff-only")
    changes = command(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        quiet=True, cwd=ROOT
    ).stdout.strip()
    if changes:
        raise PublicationError("Coordinator has uncommitted tracked changes")
    return local_head


def verify_published_assets(version, expected_checksums):
    tag = f"v{version}"
    with tempfile.TemporaryDirectory(prefix="ifacematch-published-") as folder:
        directory = Path(folder)
        patterns = sorted(expected_checksums)
        arguments = [
            "gh", "release", "download", tag,
            "--repo", REPOSITORY,
            "--dir", directory,
        ]
        for pattern in patterns:
            arguments.extend(["--pattern", pattern])
        command(arguments, quiet=True)
        for name, digest in expected_checksums.items():
            asset = directory / name
            if not asset.is_file() or checksum(asset) != digest:
                raise PublicationError(
                    f"Published GitHub asset differs from local verified file: {name}"
                )
    print(f"[PASS] All GitHub Release assets downloaded and SHA-256 verified: {tag}")


def publish(version):
    archive_dir = ROOT / "dist" / "releases" / version
    archive = archive_dir / f"ifacematch-{version}-ubuntu-amd64.tar.gz"
    checksums = archive_dir / "SHA256SUMS"
    updater = ROOT / "scripts" / "ifacematch-update.sh"
    notes = ROOT / "release-notes" / f"{version}.md"
    expected_checksums = validate_artifacts(
        version, archive, checksums, updater, notes
    )
    head = preflight_github()
    tag = f"v{version}"
    assert_absent(f"releases/tags/{tag}")
    assert_absent(f"git/ref/tags/{tag}")

    print(f"[PUBLISH] Publishing {tag} at {head}", flush=True)
    command(
        [
            "gh", "release", "create", tag,
            archive, checksums, f"{updater}#ifacematch-update.sh",
            "--repo", REPOSITORY,
            "--target", head,
            "--title", f"iFaceMatch {version}",
            "--notes-file", notes,
        ],
    )
    print(
        "[PUBLISHED] GitHub Release created. "
        "If post-publication verification fails, do not overwrite it.",
        flush=True,
    )
    verify_published_assets(version, expected_checksums)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    options = parser.parse_args()
    try:
        publish(options.version)
    except (PublicationError, OSError, ValueError, UnicodeError) as error:
        print(f"[BLOCK] {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
