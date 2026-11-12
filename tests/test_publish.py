import hashlib
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("release_publisher", ROOT / "scripts/publish.py")
publisher = module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.archive = root / "ifacematch-0.1.11-ubuntu-amd64.tar.gz"
        self.checksums = root / "SHA256SUMS"
        self.updater = root / "ifacematch-update.sh"
        self.notes = root / "0.1.11.md"

        self.archive.write_bytes(b"fixture-release")
        self.digest = hashlib.sha256(b"fixture-release").hexdigest()
        self.checksums.write_text(
            f"{self.digest}  {self.archive.name}\n", encoding="utf-8"
        )
        self.updater.write_text(
            "#!/usr/bin/env bash\n"
            "release_version=0.1.11\n"
            f"expected_archive_sha256={self.digest}\n",
            encoding="utf-8",
        )
        self.notes.write_text("# Release 0.1.11\n", encoding="utf-8")

    def check(self):
        with patch.dict(publisher.APPROVED_SHA256, {"0.1.11": self.digest}):
            return publisher.validate_artifacts(
                "0.1.11",
                self.archive,
                self.checksums,
                self.updater,
                self.notes,
            )

    def test_valid_verified_artifacts(self):
        result = self.check()
        self.assertEqual(result[self.archive.name], self.digest)
        self.assertIn("ifacematch-update.sh", result)

    def test_rejects_corrupted_archive(self):
        self.archive.write_bytes(b"modified-release")
        with self.assertRaisesRegex(publisher.PublicationError, "SHA-256"):
            self.check()

    def test_rejects_changed_checksums_file(self):
        self.checksums.write_text(f"{self.digest} *{self.archive.name}\n")
        with self.assertRaisesRegex(publisher.PublicationError, "SHA256SUMS"):
            self.check()

    def test_rejects_unpinned_updater(self):
        self.updater.write_text("release_version=0.1.11\n")
        with self.assertRaisesRegex(publisher.PublicationError, "does not pin"):
            self.check()

    def test_rejects_unsupported_version(self):
        with self.assertRaisesRegex(publisher.PublicationError, "Unapproved"):
            publisher.validate_artifacts(
                "0.1.12",
                self.archive,
                self.checksums,
                self.updater,
                self.notes,
            )

    def test_rejects_symlink_asset(self):
        linked = self.updater.with_name("temporary-updater")
        linked.write_text(self.updater.read_text())
        self.updater.unlink()
        self.updater.symlink_to(linked)
        with self.assertRaisesRegex(publisher.PublicationError, "unsafe updater"):
            self.check()


if __name__ == "__main__":
    unittest.main()
