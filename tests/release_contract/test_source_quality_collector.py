import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import test_release_promotion as promotion_fixture

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/release"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("source_collector", TOOLS / "collect_source_quality.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
COMMIT = "a" * 40
IMAGE = f"ghcr.io/sponzey-lab/sponzey-edge:v0.1.0@sha256:{'b' * 64}"


class SourceQualityCollectorTest(unittest.TestCase):
    def runner(self, *, dirty=False, failing="", secret=False):
        def run(command, cwd):
            if command[:2] == ["git", "status"]:
                return subprocess.CompletedProcess(command, 0, " M x\n" if dirty else "", "")
            if command[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(command, 0, COMMIT + "\n", "")
            return subprocess.CompletedProcess(command, 1 if command[0] == failing else 0,
                                               "password=fixture-secret" if secret else "ok\n", "")
        return run

    def test_writes_bound_originals_only_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = MODULE.collect(root, root / "source-evidence", "v0.1.0", COMMIT, IMAGE, self.runner())
            receipt = json.loads((root / "source-evidence" / result["path"]).read_text())
            self.assertEqual(receipt["candidate"]["commit"], COMMIT)
            self.assertEqual(set(receipt["checks"]), set(MODULE.SOURCE_COMMANDS))
            trace = json.loads((root / "source-evidence" / receipt["trace"]["path"]).read_text())
            original = json.loads((root / "source-evidence" / trace["observations"]["format"]["output"]["path"]).read_text())
            self.assertEqual(original["command"], ["cargo", "fmt", "--check"])
            self.assertEqual(original["stdout"], "ok\n")
            with self.assertRaises(ValueError):
                MODULE.collect(root, root / "source-evidence", "v0.1.0", COMMIT, IMAGE, self.runner())

    def test_dirty_failing_and_sensitive_runs_do_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, runner in enumerate((self.runner(dirty=True), self.runner(failing="cargo"), self.runner(secret=True))):
                output = root / f"evidence-{index}"
                with self.assertRaises(ValueError):
                    MODULE.collect(root, output, "v0.1.0", COMMIT, IMAGE, runner)
                self.assertFalse(output.exists())

    def test_real_subprocess_capture_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = MODULE.run_bounded([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"], root)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "out\n", "err\n"))
            with self.assertRaises(ValueError):
                MODULE.run_bounded([sys.executable, "-c", "print('x' * (1024 * 1024 + 1))"], root)

    def test_source_change_during_commands_prevents_publication(self):
        calls = 0
        base = self.runner()
        def changed(command, cwd):
            nonlocal calls
            if command[:2] == ["git", "status"]:
                calls += 1
                if calls == 2:
                    return subprocess.CompletedProcess(command, 0, " M changed\n", "")
            return base(command, cwd)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                MODULE.collect(root, root / "evidence", "v0.1.0", COMMIT, IMAGE, changed)
            self.assertFalse((root / "evidence").exists())

    def test_wrong_candidate_revision_is_rejected_before_quality_commands(self):
        commands = []
        def wrong_revision(command, cwd):
            commands.append(command)
            if command[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(command, 0, "c" * 40 + "\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                MODULE.collect(root, root / "evidence", "v0.1.0", COMMIT, IMAGE, wrong_revision)
            self.assertFalse((root / "evidence").exists())
            self.assertTrue(all(command[0] == "git" for command in commands))

    def test_collected_source_receipt_is_consumed_by_v2_inspector(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "evidence"
            reference = MODULE.collect(workspace, root, "v0.1.0", COMMIT, IMAGE, self.runner())
            original = (root / reference["path"]).read_bytes()
            fixture = promotion_fixture.ReleasePromotionContractTest()
            index = fixture.v2_evidence(root)
            (root / reference["path"]).write_bytes(original)
            index["records"]["source_quality"] = reference
            result = fixture.validate(index, root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"promotion_eligible":false', result.stdout)


if __name__ == "__main__":
    unittest.main()
