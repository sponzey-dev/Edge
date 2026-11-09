import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/release/validate_candidate_archive.py"
TAG = "v0.1.0"
COMMIT = "a" * 40
IMAGE = f"ghcr.io/sponzey-lab/sponzey-edge:{TAG}@sha256:{'b' * 64}"


class CandidateArchiveTest(unittest.TestCase):
    def make_assets(self, root: Path, *, duplicate: bool = False, symlink: bool = False) -> str:
        entries, checksums = [], []
        for platform in ("linux-amd64", "linux-arm64"):
            name = f"edge-proxy-{platform}.tar.gz"
            with tarfile.open(root / name, "w:gz") as archive:
                for _ in range(2 if duplicate and platform == "linux-amd64" else 1):
                    member = tarfile.TarInfo("edge-proxy")
                    if symlink and platform == "linux-amd64":
                        member.type = tarfile.SYMTYPE
                        member.linkname = "elsewhere"
                        archive.addfile(member)
                    else:
                        data = f"binary-{platform}".encode()
                        member.size = len(data)
                        archive.addfile(member, io.BytesIO(data))
            sbom = f"edge-proxy-{platform}.spdx.json"
            (root / sbom).write_text('{"spdxVersion":"SPDX-2.3"}')
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            entries.append({"platform": platform, "archive": name, "sbom": sbom, "sha256": digest})
            for filename in (name, sbom):
                checksums.append(f"{hashlib.sha256((root / filename).read_bytes()).hexdigest()}  {filename}\n")
        (root / "SHA256SUMS").write_text("".join(checksums))
        (root / "release-manifest.json").write_text(json.dumps({"schema_version": 1, "tag": TAG, "commit": COMMIT, "image": IMAGE, "artifacts": entries}))
        return hashlib.sha256(b"binary-linux-amd64").hexdigest()

    def run_tool(self, root: Path, commit: str = COMMIT) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(TOOL), "--artifacts", str(root), "--tag", TAG,
                               "--commit", commit, "--image", IMAGE], text=True, capture_output=True)

    def test_binds_verified_archive_binary_to_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self.make_assets(root)
            result = self.run_tool(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["binary_sha256"], expected)
            self.assertNotEqual(self.run_tool(root, "c" * 40).returncode, 0)
            (root / "edge-proxy-linux-amd64.tar.gz").write_bytes(b"tampered")
            self.assertNotEqual(self.run_tool(root).returncode, 0)

    def test_rejects_ambiguous_or_linked_binary(self) -> None:
        for kwargs in ({"duplicate": True}, {"symlink": True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_assets(root, **kwargs)
                self.assertNotEqual(self.run_tool(root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
