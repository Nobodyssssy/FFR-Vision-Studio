
import tempfile
import unittest
from pathlib import Path

import build_receipt


class BuildReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.source = root / "unit.json"
        self.output = root / "mod.pak"
        self.receipt = root / "build-receipt.json"

        self.source.write_text('{"unit":"Rain"}')
        self.output.write_bytes(b"verified mod")

        self.inputs = {"unit": self.source}
        self.outputs = {"pak": self.output}

    def save(self):
        build_receipt.record(
            self.receipt, self.inputs, self.outputs
        )

    def check(self):
        return build_receipt.reusable(
            self.receipt, self.inputs, self.outputs
        )

    def test_unchanged_build_is_reusable(self):
        self.save()
        self.assertTrue(self.check())

    def test_changed_source_requires_rebuild(self):
        self.save()
        self.source.write_text('{"unit":"Sephiroth"}')
        self.assertFalse(self.check())

    def test_corrupted_package_requires_rebuild(self):
        self.save()
        self.output.write_bytes(b"corrupted mod")
        self.assertFalse(self.check())

    def test_missing_package_requires_rebuild(self):
        self.save()
        self.output.unlink()
        self.assertFalse(self.check())

    def test_missing_or_invalid_receipt_requires_rebuild(self):
        self.assertFalse(self.check())
        self.receipt.write_text("invalid json")
        self.assertFalse(self.check())


if __name__ == "__main__":
    unittest.main()
