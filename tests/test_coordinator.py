import json
import tempfile
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("coordinator", ROOT / "scripts/coordinator.py")
coordinator = module_from_spec(SPEC)
SPEC.loader.exec_module(coordinator)


class LockfileTests(unittest.TestCase):
    def test_known_lockfile_is_valid(self):
        data = coordinator.read_lock()
        self.assertEqual(set(data), set(coordinator.REPOSITORY_NAMES))
        self.assertEqual(data["console"]["sha"], "e20a4197e74c7fea13d2ab0b1784e665d6f60377")

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


if __name__ == "__main__":
    unittest.main()
