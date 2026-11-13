#!/usr/bin/env python3
"""Coordinates reproducible iFaceMatch source builds and signed releases."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
LOCK_PATH = ROOT / "versions.lock.json"
REPOSITORY_NAMES = ("server", "console", "admin", "site")
SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
REF_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]*$")
SIGNED_RELEASE_PATTERN = re.compile(r"^0\.[0-9]+\.[0-9]+$")
TRUST_PATH = Path.home() / ".config/ifacematch/distribution/distribution.public"
TRUST_KEY_ID = "ifm_distribution_prod_v1"
BASE_VERSION = "0.1.10"
BASE_SHA256 = "e6d0e991694c471c79e4d2e6d02f641b5144ec48d3f4bb9900b4eaca1ba5373e"
BASE_ARCHIVE_NAME = f"ifacematch-{BASE_VERSION}-ubuntu-amd64.tar.gz"


class CoordinatorError(Exception):
    pass


def execute(arguments, cwd=None, quiet=False):
    result = subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        stdout=subprocess.DEVNULL if quiet else None,
        check=False,
    )
    if result.returncode != 0:
        raise CoordinatorError(
            f"Command failed with exit code {result.returncode}: {arguments[0]}"
        )


def capture(arguments, cwd=None):
    result = subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoordinatorError(f"Command failed: {arguments[0]} {arguments[1]}")
    return result.stdout.strip()


def read_lock(path=LOCK_PATH):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schemaVersion") != 1:
        raise CoordinatorError("Unsupported lockfile schema")
    repositories = document.get("repositories")
    if not isinstance(repositories, dict) or set(repositories) != set(REPOSITORY_NAMES):
        raise CoordinatorError("Lockfile must include exactly four repositories")
    for name in REPOSITORY_NAMES:
        item = repositories[name]
        if item.get("repository") != f"jefersonMarques/ifacematch-{name}":
            raise CoordinatorError(f"Unexpected GitHub repository for {name}")
        if not SHA_PATTERN.fullmatch(item.get("sha", "")):
            raise CoordinatorError(f"Invalid commit SHA for {name}")
        reference = item.get("ref", "")
        if not REF_PATTERN.fullmatch(reference) or ".." in reference or "//" in reference:
            raise CoordinatorError(f"Invalid branch reference for {name}")
        if item.get("module") not in (".", "services/api", None):
            raise CoordinatorError(f"Invalid Go module for {name}")
    return repositories


def remote_url(repository):
    protocol = os.environ.get("GIT_PROTOCOL", "ssh").strip().lower()
    if protocol == "ssh":
        return f"git@github.com:{repository}.git"
    if protocol == "https":
        return f"https://github.com/{repository}.git"
    raise CoordinatorError("GIT_PROTOCOL must be either ssh or https")


def repository_path(name):
    return WORKSPACE / f"ifacematch-{name}"


def verified_git_repository(name, config):
    location = repository_path(name)
    if not location.is_dir():
        raise CoordinatorError(f"{location} is missing; run make bootstrap")
    remote = capture(["git", "-C", location, "remote", "get-url", "origin"])
    allowed = {
        f"git@github.com:{config['repository']}.git",
        f"https://github.com/{config['repository']}.git",
        f"https://github.com/{config['repository']}",
        f"ssh://git@github.com/{config['repository']}.git",
    }
    if remote not in allowed:
        raise CoordinatorError(f"Unexpected origin configured for {name}")
    try:
        capture(["git", "-C", location, "cat-file", "-e", f"{config['sha']}^{{commit}}"])
    except CoordinatorError as error:
        raise CoordinatorError(
            f"Pinned commit missing in {name}; run make bootstrap"
        ) from error
    return location


def bootstrap(repositories):
    for name, config in repositories.items():
        location = repository_path(name)
        if not location.exists():
            print(f"[CLONE] {name}", flush=True)
            execute(["git", "clone", "--no-checkout", remote_url(config["repository"]), location])
            execute(["git", "-C", location, "fetch", "--no-tags", "origin", f"refs/heads/{config['ref']}"], quiet=True)
            execute(["git", "-C", location, "checkout", "--detach", config["sha"]])
        else:
            verified_git_remote(name, config)
            print(f"[FETCH] {name} (working tree unchanged)", flush=True)
            execute(["git", "-C", location, "fetch", "--no-tags", "origin", f"refs/heads/{config['ref']}"])
        verified_git_repository(name, config)
    print("[PASS] All pinned commits available. Existing working trees preserved.")


def verified_git_remote(name, config):
    location = repository_path(name)
    if not location.is_dir():
        raise CoordinatorError(f"Repository path is not a directory: {location}")
    remote = capture(["git", "-C", location, "remote", "get-url", "origin"])
    expected = config["repository"]
    if remote not in {
        f"git@github.com:{expected}.git",
        f"https://github.com/{expected}.git",
        f"https://github.com/{expected}",
        f"ssh://git@github.com/{expected}.git",
    }:
        raise CoordinatorError(f"{name} origin does not match {expected}")


def extract_snapshot(name, config, destination):
    location = verified_git_repository(name, config)
    destination.mkdir(mode=0o700, parents=True)
    producer = subprocess.Popen(
        ["git", "-C", str(location), "archive", "--format=tar", config["sha"]],
        stdout=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=producer.stdout, mode="r|") as archive:
            for member in archive:
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise CoordinatorError(f"Unsafe archive path in {name}")
                if not member.isfile() and not member.isdir():
                    raise CoordinatorError(f"Unsupported archive entry in {name}")
                if member.isdir():
                    (destination / path).mkdir(parents=True, exist_ok=True)
                    continue
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise CoordinatorError(f"Unreadable archive member in {name}")
                with target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(member.mode & 0o777)
    finally:
        if producer.stdout is not None:
            producer.stdout.close()
        exit_code = producer.wait()
    if exit_code != 0:
        raise CoordinatorError(f"Cannot archive pinned revision of {name}")


@contextmanager
def snapshots(repositories, names=REPOSITORY_NAMES):
    with tempfile.TemporaryDirectory(prefix="ifacematch-source-") as directory:
        root = Path(directory)
        for name in names:
            extract_snapshot(name, repositories[name], root / f"ifacematch-{name}")
        yield root


def doctor(repositories):
    for tool in ("git", "go", "python3", "tar", "bash", "make"):
        found = shutil.which(tool)
        print(f"[{'OK' if found else 'MISSING'}] {tool}")
    for name, config in repositories.items():
        location = repository_path(name)
        if not location.exists():
            print(f"[MISSING] {name}: run make bootstrap")
            continue
        try:
            verified_git_repository(name, config)
            actual = capture(["git", "-C", location, "rev-parse", "HEAD"])
            suffix = "" if actual == config["sha"] else " (checkout differs; pinned snapshot used)"
            print(f"[OK] {name}: {config['sha'][:12]}{suffix}")
        except CoordinatorError as error:
            print(f"[CHECK] {name}: {error}")
    print(f"[{'AVAILABLE' if TRUST_PATH.is_file() else 'NOT CONFIGURED'}] Local distribution public key")


def test(repositories):
    with snapshots(repositories) as root:
        for name in ("server", "console", "admin"):
            config = repositories[name]
            module = root / f"ifacematch-{name}" / config["module"]
            print(f"[TEST] {name}", flush=True)
            execute(["go", "test", "./..."], cwd=module)
            execute(["go", "vet", "./..."], cwd=module)
        print("[TEST] Admin signed release staging", flush=True)
        execute(
            [
                "python3", "-m", "unittest", "discover",
                "-s", root / "ifacematch-admin" / "scripts",
                "-p", "test_build_signed_console_upgrade_0_1_14.py",
                "-v",
            ]
        )
        site = root / "ifacematch-site"
        for path in sorted(site.rglob("*.sh")):
            execute(["bash", "-n", path], quiet=True)
        for path in sorted((site / "portal").glob("*.js")):
            if shutil.which("node"):
                execute(["node", "--check", path], quiet=True)
        print("[PASS] Component tests and syntax checks completed.")


def build(repositories):
    build_root = ROOT / "dist" / "build"
    if build_root.exists():
        raise CoordinatorError(
            f"{build_root} already exists. Preserve or move the prior build before retrying"
        )
    build_root.mkdir(parents=True)
    try:
        with snapshots(repositories, ("server", "console", "admin")) as root:
            targets = (
                ("server", "services/api", "./cmd/server", "ifacematch-server"),
                ("server", "services/api", "./cmd/ifacematchctl", "ifacematchctl"),
                ("console", ".", "./cmd/console", "ifacematch-console"),
                ("admin", ".", "./cmd/releasecheck", "releasecheck"),
                ("admin", ".", "./cmd/releasepack", "releasepack"),
                ("admin", ".", "./cmd/releasebundle", "releasebundle"),
            )
            for name, module, package, filename in targets:
                source = root / f"ifacematch-{name}" / module
                print(f"[BUILD] {name}: {filename}", flush=True)
                execute(["go", "build", "-trimpath", "-o", build_root / filename, package], cwd=source)
        print(f"[PASS] Unsigned development binaries at {build_root}")
        print("[NOTE] These are not production-signed packages.")
    except Exception:
        shutil.rmtree(build_root)
        raise


def verify_base_archive(source):
    if not source.is_absolute() or not source.is_file() or source.is_symlink():
        raise CoordinatorError("Source archive must be an existing absolute regular file")
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != BASE_SHA256:
        raise CoordinatorError(f"Base archive SHA-256 does not match the pinned {BASE_VERSION} release")


def base_archive_candidates(home, workspace, root):
    yield root / "dist" / "releases" / BASE_VERSION / BASE_ARCHIVE_NAME
    yield workspace / "releases" / BASE_VERSION / BASE_ARCHIVE_NAME
    yield home / ".config" / "ifacematch" / "releases" / BASE_VERSION / BASE_ARCHIVE_NAME

    pointer = home / ".config" / "ifacematch" / f"release-{BASE_VERSION}.path"
    if pointer.exists() or pointer.is_symlink():
        if pointer.is_symlink() or not pointer.is_file():
            raise CoordinatorError(f"Release pointer must be a regular file: {pointer}")
        location = Path(pointer.read_text(encoding="utf-8").strip()).expanduser()
        if not location.is_absolute():
            raise CoordinatorError(f"Release pointer must contain an absolute path: {pointer}")
        yield location / BASE_ARCHIVE_NAME if location.is_dir() else location

    for directory in sorted(home.glob(f"*{BASE_VERSION}*")):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for subdirectory in ("", "release", "signed", "output"):
            yield directory / subdirectory / BASE_ARCHIVE_NAME


def resolve_base_archive(chosen="", *, home=None, workspace=None, root=None):
    if chosen:
        archive = Path(chosen).expanduser()
        verify_base_archive(archive)
        return archive

    home = home if home is not None else Path.home()
    workspace = workspace if workspace is not None else WORKSPACE
    root = root if root is not None else ROOT
    inspected = set()
    rejected = []

    for archive in base_archive_candidates(home, workspace, root):
        if archive in inspected:
            continue
        inspected.add(archive)
        if not archive.exists() and not archive.is_symlink():
            continue
        try:
            verify_base_archive(archive)
        except (CoordinatorError, OSError) as error:
            rejected.append(f"{archive}: {error}")
            continue
        return archive

    if rejected:
        raise CoordinatorError(
            f"No valid signed {BASE_VERSION} archive was found. "
            f"Rejected candidates: {'; '.join(rejected)}"
        )
    raise CoordinatorError(
        f"Signed {BASE_VERSION} archive not found in the configured local release "
        "locations. Register its directory in "
        f"~/.config/ifacematch/release-{BASE_VERSION}.path, "
        "or use BASE_ARCHIVE=/absolute/path for this build."
    )


def make_release(repositories, version, base_archive):
    if version != "0.1.14":
        raise CoordinatorError("The only implemented and reviewed release adapter is 0.1.14")
    source = resolve_base_archive(base_archive)
    print(f"[BASE] Verified signed {BASE_VERSION} archive: {source}", flush=True)
    destination = ROOT / "dist" / "releases" / version
    if destination.exists():
        raise CoordinatorError("Release output already exists; never overwrite signed builds")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ifacematch-release-") as directory:
        stage = Path(directory)
        for name in ("admin", "console", "server"):
            config = repositories[name]
            location = stage / f"ifacematch-{name}"
            execute([
                "git", "clone", "--no-checkout", "--single-branch",
                "--branch", config["ref"], remote_url(config["repository"]), location
            ], quiet=True)
            execute(["git", "-C", location, "checkout", "--detach", config["sha"]], quiet=True)
        builder = stage / "ifacematch-admin/scripts/build-signed-console-upgrade-0.1.14.sh"
        execute(["bash", builder, stage, source, destination])
    print(f"[PASS] Release created: {destination}")


def show_release_base(chosen):
    source = resolve_base_archive(chosen)
    print(f"[PASS] Verified signed {BASE_VERSION} base: {source}")


def release_archive(version, chosen):
    if not SIGNED_RELEASE_PATTERN.fullmatch(version):
        raise CoordinatorError("VERSION must be a stable semver")
    path = (
        Path(chosen).expanduser()
        if chosen else
        ROOT / "dist" / "releases" / version / f"ifacematch-{version}-ubuntu-amd64.tar.gz"
    )
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise CoordinatorError(f"Signed archive missing: {path}")
    return path


def verify_release(repositories, version, archive_argument):
    archive = release_archive(version, archive_argument)
    if not TRUST_PATH.is_file() or TRUST_PATH.is_symlink():
        raise CoordinatorError("Distribution public key is missing from the signing workstation")
    if archive.parent.joinpath("SHA256SUMS").is_file():
        execute(["sha256sum", "--check", "SHA256SUMS"], cwd=archive.parent)
    with snapshots(repositories, ("admin",)) as root:
        admin = root / "ifacematch-admin"
        execute([
            "go", "run", "./cmd/releasecheck",
            "--archive", archive,
            "--trust", TRUST_PATH,
            "--key-id", TRUST_KEY_ID,
            "--expected-version", version,
        ], cwd=admin)
    print(f"[PASS] Signed release verified: {archive}")
    return archive


def publish_release(repositories, version, archive_argument):
    archive = verify_release(repositories, version, archive_argument)
    expected = ROOT / "dist" / "releases" / version
    if archive.parent != expected:
        raise CoordinatorError(
            "Publishing requires the standard verified release directory"
        )
    execute(
        ["python3", ROOT / "scripts" / "publish.py", "--version", version]
    )


def restricted_remote_action(repositories, command, version, archive_argument):
    archive = verify_release(repositories, version, archive_argument)
    print(f"[PLAN] {command} {version}: {archive}")
    raise CoordinatorError(
        f"'{command}' is intentionally blocked: no reviewed production adapter "
        "has been integrated into this coordinator. No remote changes were made."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "help", "doctor", "bootstrap", "test", "build",
            "release", "release-base", "release-verify", "publish", "deploy",
        ),
    )
    parser.add_argument("--version", default="0.1.14")
    parser.add_argument("--base-archive", default="")
    parser.add_argument("--archive", default="")
    options = parser.parse_args()
    if options.command == "help":
        print(
            "make doctor | make bootstrap | make test | make build\n"
            "make release-base                 (find and verify signed 0.1.10)\n"
            "make release VERSION=0.1.14       (auto-discover signed 0.1.10)\n"
            "make release-verify VERSION=0.1.14\n"
            "make publish VERSION=0.1.14       (upload verified GitHub Release)\n"
            "make deploy VERSION=0.1.14   (blocked until approved integration)\n"
            "Use GIT_PROTOCOL=https for GitHub HTTPS instead of SSH."
        )
        return
    repositories = read_lock()
    actions = {
        "doctor": lambda: doctor(repositories),
        "bootstrap": lambda: bootstrap(repositories),
        "test": lambda: test(repositories),
        "build": lambda: build(repositories),
        "release": lambda: make_release(
            repositories, options.version, options.base_archive,
        ),
        "release-base": lambda: show_release_base(options.base_archive),
        "release-verify": lambda: verify_release(
            repositories, options.version, options.archive,
        ),
        "publish": lambda: publish_release(
            repositories, options.version, options.archive,
        ),
        "deploy": lambda: restricted_remote_action(
            repositories, "deploy", options.version, options.archive,
        ),
    }
    actions[options.command]()


if __name__ == "__main__":
    try:
        main()
    except (CoordinatorError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"[BLOCK] {error}", file=sys.stderr)
        raise SystemExit(1) from None
