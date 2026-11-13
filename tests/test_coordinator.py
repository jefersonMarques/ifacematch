import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("coordinator", ROOT / "scripts/coordinator.py")
coordinator = module_from_spec(SPEC)
SPEC.loader.exec_module(coordinator)


class LockfileTests(unittest.TestCase):
    def test_known_lockfile_is_valid(self):
        data = coordinator.read_lock()
        self.assertEqual(set(data), set(coordinator.REPOSITORY_NAMES))
        self.assertEqual(data["console"]["sha"], "6b9b0fdc18b94b1e722cdce18517026019943692")
        self.assertEqual(data["server"]["sha"], "41b62aa5743dfb2c68205e41e87a413f5bb2b8b7")
        self.assertEqual(data["admin"]["sha"], "9c6aad579a89175fe3f1f1ee5840eff1973d6b37")

    def test_rejects_unexpected_repository(self):
        self.assert_invalid({"repository": "example/console"})

    def test_rejects_invalid_sha(self):
        self.assert_invalid({"sha": "../../latest"})

    def test_rejects_unsafe_ref(self):
        self.assert_invalid({"ref": "feature/../unsafe"})

    def assert_invalid(self, replacement):
        data = json.loads(coordinator.LOCK_PATH.read_text(encoding="utf-8"))
        data["repositories"]["console"].update(replacement)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(coordinator.CoordinatorError):
                coordinator.read_lock(path)


class RemoteTests(unittest.TestCase):
    def test_accepts_ssh_and_https(self):
        original = coordinator.os.environ.get("GIT_PROTOCOL")
        try:
            for protocol, expected in (
                ("ssh", "git@github.com:jefersonMarques/ifacematch-console.git"),
                ("https", "https://github.com/jefersonMarques/ifacematch-console.git"),
            ):
                coordinator.os.environ["GIT_PROTOCOL"] = protocol
                self.assertEqual(
                    coordinator.remote_url("jefersonMarques/ifacematch-console"),
                    expected,
                )
        finally:
            if original is None:
                coordinator.os.environ.pop("GIT_PROTOCOL", None)
            else:
                coordinator.os.environ["GIT_PROTOCOL"] = original

    def test_rejects_unknown_protocol(self):
        original = coordinator.os.environ.get("GIT_PROTOCOL")
        try:
            coordinator.os.environ["GIT_PROTOCOL"] = "local"
            with self.assertRaises(coordinator.CoordinatorError):
                coordinator.remote_url("jefersonMarques/ifacematch-console")
        finally:
            if original is None:
                coordinator.os.environ.pop("GIT_PROTOCOL", None)
            else:
                coordinator.os.environ["GIT_PROTOCOL"] = original



class BaseArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home"
        self.root = Path(temporary.name) / "coordinator"
        self.workspace = Path(temporary.name) / "workspace"
        for directory in (self.home, self.root, self.workspace):
            directory.mkdir()
        self.payload = b"signed-test-archive-fixture"
        self.pin = hashlib.sha256(self.payload).hexdigest()

    def resolve(self, chosen=""):
        with patch.object(coordinator, "BASE_SHA256", self.pin):
            return coordinator.resolve_base_archive(
                chosen, home=self.home, root=self.root, workspace=self.workspace,
            )

    def create_archive(self, destination, payload=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload if payload is None else payload)
        return destination

    def test_finds_archive_in_coordinator_release_directory(self):
        expected = self.create_archive(
            self.root / "dist/releases/0.1.10" / coordinator.BASE_ARCHIVE_NAME
        )
        self.assertEqual(self.resolve(), expected)

    def test_finds_archive_through_operator_release_pointer(self):
        archive = self.create_archive(
            self.home / "ifacematch-signing-0.1.10-test" / coordinator.BASE_ARCHIVE_NAME
        )
        pointer = self.home / ".config/ifacematch/release-0.1.10.path"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(str(archive.parent) + "\n", encoding="utf-8")
        self.assertEqual(self.resolve(), archive)

    def test_finds_archive_in_local_signing_directory(self):
        expected = self.create_archive(
            self.home / "ifacematch-signing-0.1.10-test" / coordinator.BASE_ARCHIVE_NAME
        )
        self.assertEqual(self.resolve(), expected)

    def test_skips_mismatched_archive_if_valid_copy_exists(self):
        self.create_archive(
            self.root / "dist/releases/0.1.10" / coordinator.BASE_ARCHIVE_NAME,
            b"bad-artifact",
        )
        expected = self.create_archive(
            self.home / "ifacematch-signed-0.1.10-test" / coordinator.BASE_ARCHIVE_NAME
        )
        self.assertEqual(self.resolve(), expected)

    def test_manual_override_is_still_supported(self):
        expected = self.create_archive(
            self.workspace / "archives" / coordinator.BASE_ARCHIVE_NAME
        )
        self.assertEqual(self.resolve(str(expected)), expected)

    def test_rejects_archive_with_wrong_sha256(self):
        invalid = self.create_archive(
            self.workspace / "archives" / coordinator.BASE_ARCHIVE_NAME,
            b"incorrect-archive",
        )
        with self.assertRaisesRegex(coordinator.CoordinatorError, "SHA-256"):
            self.resolve(str(invalid))

    def test_missing_archive_has_actionable_error(self):
        with self.assertRaisesRegex(coordinator.CoordinatorError, "release-0.1.10.path"):
            self.resolve()

    def test_refuses_relative_release_pointer(self):
        pointer = self.home / ".config/ifacematch/release-0.1.10.path"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("./relative/path", encoding="utf-8")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "absolute path"):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
