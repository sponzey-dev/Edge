import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "release" / "resolve_image_config_digest.py"
sys.path.insert(0, str(ROOT / "tools" / "release"))
from resolve_image_config_digest import (  # noqa: E402
    ImageIdentityError,
    linux_amd64_manifest_digest,
    platform_config_digest,
)


class OciImageIdentityContractTest(unittest.TestCase):
    def test_selects_linux_amd64_manifest_and_skips_other_platforms_and_attestations(self) -> None:
        index = {
            "manifests": [
                {"digest": f"sha256:{'a' * 64}", "platform": {"os": "linux", "architecture": "arm64"}},
                {"digest": f"sha256:{'b' * 64}", "platform": {"os": "unknown", "architecture": "unknown"}},
                {"digest": f"sha256:{'c' * 64}", "platform": {"os": "linux", "architecture": "amd64"}},
            ]
        }

        self.assertEqual(linux_amd64_manifest_digest(index), f"sha256:{'c' * 64}")

    def test_rejects_missing_or_ambiguous_linux_amd64_manifest(self) -> None:
        with self.assertRaisesRegex(ImageIdentityError, "linux/amd64 manifest is missing"):
            linux_amd64_manifest_digest({"manifests": []})
        with self.assertRaisesRegex(ImageIdentityError, "exactly one linux/amd64 manifest"):
            linux_amd64_manifest_digest(
                {
                    "manifests": [
                        {"digest": f"sha256:{'a' * 64}", "platform": {"os": "linux", "architecture": "amd64"}},
                        {"digest": f"sha256:{'b' * 64}", "platform": {"os": "linux", "architecture": "amd64"}},
                    ]
                }
            )

    def test_reads_config_digest_from_selected_platform_manifest(self) -> None:
        manifest = {"config": {"digest": f"sha256:{'d' * 64}"}}

        self.assertEqual(platform_config_digest(manifest), f"sha256:{'d' * 64}")

    def test_cli_reads_oci_documents_from_standard_input(self) -> None:
        manifest_digest = f"sha256:{'c' * 64}"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "amd64-manifest"],
            input=json.dumps(
                {
                    "manifests": [
                        {"digest": manifest_digest, "platform": {"os": "linux", "architecture": "amd64"}}
                    ]
                }
            ),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), manifest_digest)

    def test_rejects_malformed_oci_identity_documents(self) -> None:
        for document in ({}, {"manifests": "invalid"}, {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}):
            with self.subTest(document=document), self.assertRaises(ImageIdentityError):
                linux_amd64_manifest_digest(document)
        for document in ({}, {"config": {}}, {"config": {"digest": "sha256:bad"}}):
            with self.subTest(document=document), self.assertRaises(ImageIdentityError):
                platform_config_digest(document)


if __name__ == "__main__":
    unittest.main()
