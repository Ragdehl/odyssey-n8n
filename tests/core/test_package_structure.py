"""Structural tests for the initial Odyssey Core package boundary."""

import unittest

import odyssey_core
from odyssey_core import storage


class OdysseyCorePackageTests(unittest.TestCase):
    """Verify the application core and its known storage boundary are importable."""

    def test_core_and_storage_packages_import_from_repository(self) -> None:
        """Expose the bootstrapped core and storage namespaces without domain behavior."""
        self.assertEqual(odyssey_core.__package__, "odyssey_core")
        self.assertEqual(storage.__package__, "odyssey_core.storage")


if __name__ == "__main__":
    unittest.main()
