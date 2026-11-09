import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DependencyAdvisoryContractTest(unittest.TestCase):
    def test_crypto_bigint_resolution_meets_rustsec_2026_0387_minimum(self) -> None:
        lockfile = (ROOT / "Cargo.lock").read_text(encoding="utf-8")
        matches = re.findall(r'name = "crypto-bigint"\nversion = "([0-9]+)\.([0-9]+)\.([0-9]+)"', lockfile)
        for match in matches:
            self.assertGreaterEqual(tuple(map(int, match)), (0, 7, 6))

    def test_rustls_direct_dependencies_reject_vulnerable_minimum(self) -> None:
        for relative in ("crates/edge-adapters/Cargo.toml", "apps/edge-proxy/Cargo.toml", "tests/memory-harness/Cargo.toml"):
            with self.subTest(manifest=relative):
                manifest = (ROOT / relative).read_text(encoding="utf-8")
                match = re.search(r'^rustls\s*=\s*\{\s*version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', manifest, re.MULTILINE)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertGreaterEqual(tuple(map(int, match.groups())), (0, 23, 46))

    def test_h2_lockfile_resolution_meets_rustsec_2026_0258_minimum(self) -> None:
        lockfile = (ROOT / "Cargo.lock").read_text(encoding="utf-8")
        match = re.search(
            r'name = "h2"\nversion = "([0-9]+)\.([0-9]+)\.([0-9]+)"', lockfile
        )
        self.assertIsNotNone(match, "Cargo.lock must contain the resolved h2 package")
        assert match is not None
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version, (0, 4, 16), "RUSTSEC-2026-0258 requires h2 >= 0.4.16")


if __name__ == "__main__":
    unittest.main()
