import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "release" / "validate_g05_acceptance_index.py"
CRITERIA = [f"G05-A0{number}" for number in range(1, 9)]
CANDIDATE = {
    "tag": "v0.1.18",
    "commit": "a" * 40,
    "oci_index_digest": "sha256:" + "b" * 64,
    "linux_amd64_config_digest": "sha256:" + "c" * 64,
}


class G05AcceptanceIndexContractTest(unittest.TestCase):
    def write_valid_index(self, root: Path) -> Path:
        criteria = []
        for criterion_id in CRITERIA:
            record = {
                "schema_version": 1,
                "criterion_id": criterion_id,
                "candidate": CANDIDATE,
                "expected": f"{criterion_id} evidence matches the candidate",
                "actual": f"{criterion_id} observation verified",
                "decision": "PASS",
            }
            relative = Path("evidence") / f"{criterion_id.lower()}.json"
            evidence_file = root / relative
            evidence_file.parent.mkdir(parents=True, exist_ok=True)
            evidence_file.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
            digest = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
            criteria.append({
                "id": criterion_id,
                "status": "PASS",
                "evidence": [{"path": relative.as_posix(), "sha256": digest}],
            })

        index = root / "g05-acceptance-index.json"
        index.write_text(json.dumps({
            "schema_version": 1,
            "goal": "G05",
            "candidate": CANDIDATE,
            "criteria": criteria,
        }, sort_keys=True), encoding="utf-8")
        return index

    def run_inspector(self, root: Path, index: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), "--evidence-root", str(root), "--index", str(index)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

    def test_accepts_complete_candidate_bound_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)

            result = self.run_inspector(root, index)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["criteria_passed"], 8)

    def test_rejects_a_missing_acceptance_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            document = json.loads(index.read_text(encoding="utf-8"))
            document["criteria"] = document["criteria"][:-1]
            index.write_text(json.dumps(document), encoding="utf-8")

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_CRITERIA_INCOMPLETE", result.stderr)

    def test_rejects_tampered_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            evidence = root / "evidence" / "g05-a04.json"
            evidence.write_text("{}", encoding="utf-8")

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_EVIDENCE_DIGEST_MISMATCH", result.stderr)

    def test_rejects_evidence_bound_to_a_different_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            evidence = root / "evidence" / "g05-a06.json"
            record = json.loads(evidence.read_text(encoding="utf-8"))
            record["candidate"]["tag"] = "v0.1.17"
            evidence.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
            document = json.loads(index.read_text(encoding="utf-8"))
            for criterion in document["criteria"]:
                if criterion["id"] == "G05-A06":
                    criterion["evidence"][0]["sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
            index.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_CANDIDATE_MISMATCH", result.stderr)

    def test_rejects_non_pass_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            document = json.loads(index.read_text(encoding="utf-8"))
            document["criteria"][0]["status"] = "FAIL"
            index.write_text(json.dumps(document), encoding="utf-8")

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_CRITERION_NOT_PASS", result.stderr)

    def test_rejects_evidence_symlinks_and_paths_outside_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            evidence = root / "evidence" / "g05-a01.json"
            outside = root.parent / f"{root.name}-outside.json"
            outside.write_text(evidence.read_text(encoding="utf-8"), encoding="utf-8")
            evidence.unlink()
            evidence.symlink_to(outside)

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_EVIDENCE_UNSAFE_PATH", result.stderr)
            outside.unlink()

    def test_rejects_a_symlinked_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            linked_index = root / "linked-index.json"
            linked_index.symlink_to(index)

            result = self.run_inspector(root, linked_index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_EVIDENCE_UNSAFE_PATH", result.stderr)

    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = self.write_valid_index(root)
            index.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")

            result = self.run_inspector(root, index)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("G05_INDEX_JSON_DUPLICATE_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()
