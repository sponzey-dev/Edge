import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import tarfile
import unittest
from pathlib import Path
from typing import Optional
import test_candidate_archive as candidate_fixture


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "tools" / "release" / "validate_promotion_evidence.py"
TAG = "v0.1.0"
COMMIT = "a" * 40
IMAGE = f"ghcr.io/sponzey-lab/sponzey-edge:{TAG}@sha256:{'b' * 64}"
SOURCE_COMMANDS = {
    "format": ["cargo", "fmt", "--check"],
    "clippy": ["cargo", "clippy", "--workspace", "--all-targets", "--", "-D", "warnings"],
    "workspace_tests": ["cargo", "test", "--workspace", "--", "--test-threads=1"],
    "mutation": ["cargo", "run", "-p", "edge-core", "--example", "http_framing_mutation_fuzz", "--", "1000"],
    "architecture": ["python3", "tools/release/check_architecture.py", "--workspace", "."],
    "source_index": ["python3", "tools/release/check_source_indexes.py", "--workspace", "."],
    "dependency_audit": ["cargo", "audit"],
}
SUPPORT_HTTP_OBSERVATIONS = {
    "authenticated": {"unauthenticated_status": 401, "authenticated_status": 200},
    "csrf_enforced": {"missing_csrf_status": 403, "authenticated_status": 200},
}
FORWARDING_DIGEST = hashlib.sha256(b"sponzey-release-fixture\n").hexdigest()
DEPLOYMENT_OBSERVATIONS = {
    "forwarding": {"status_code": 200, "body_sha256": FORWARDING_DIGEST},
    "admin_loopback": {"listen_address": "127.0.0.1", "remote_probe": "connection_refused"},
    "preservation": {stage: {key: "d" * 64 for key in ("config", "certificate", "audit_prefix", "data")}
                     for stage in ("before", "after_upgrade", "after_rollback")},
    "upgrade": {"state": "committed", "previous_sha256": "1" * 64, "candidate_sha256": "2" * 64,
                "observed_sha256": "2" * 64, "candidate_image": IMAGE},
    "forced_rollback": {"state": "rolled_back", "previous_sha256": "1" * 64, "candidate_sha256": "2" * 64,
                        "observed_sha256": "1" * 64, "candidate_image": IMAGE},
    "restart": {"command_exit": 0, "ready_status": 200, "before_id": "instance-a", "after_id": "instance-b"},
    "sigterm": {"signal_exit": 0, "post_stop_state": "inactive", "start_exit": 0, "ready_status": 200},
    "cleanup": {"test_services_remaining": 0, "test_listeners_remaining": 0, "test_paths_remaining": 0},
}


class ReleasePromotionContractTest(unittest.TestCase):
    def test_promotion_downloads_release_assets_before_candidate_verification(self) -> None:
        workflow = (ROOT / ".github/workflows/promote-release.yml").read_text()
        self.assertIn("Download candidate release assets", workflow)
        self.assertIn("gh release download", workflow)
        self.assertIn("--release-artifacts", workflow)
        self.assertLess(workflow.index("Download candidate release assets"), workflow.index("Validate promotion evidence"))
        self.assertLess(workflow.index("Validate promotion evidence"), workflow.index("Promote GitHub prerelease"))

    def evidence(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tag": TAG,
            "commit": COMMIT,
            "image": IMAGE,
            "source_quality": "passed",
            "support_bundle": "passed",
            "manual_or_private_pki_only": True,
            "certificate_automation_deferred": True,
            "matrix": [
                {"deployment": deployment, "platform": platform, "status": "passed"}
                for deployment in ("compose", "systemd")
                for platform in ("linux-amd64",)
            ],
        }

    def validate(self, evidence: dict[str, object], *, inspect_legacy: bool = False, inspect_v2: bool = True, require_tracked: bool = False, root: Optional[Path] = None, release_artifacts: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = (root or Path(directory)) / "promotion.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--evidence",
                    str(path),
                    "--tag",
                    TAG,
                    "--commit",
                    COMMIT,
                    "--image",
                    IMAGE,
                    *(["--inspect-legacy"] if inspect_legacy else []),
                    *(["--inspect-v2"] if evidence.get("schema_version") == 2 and inspect_v2 else []),
                    *(["--require-tracked"] if require_tracked else []),
                    *(["--release-artifacts", str(release_artifacts)] if release_artifacts else []),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_rejects_status_only_legacy_evidence_for_promotion(self) -> None:
        result = self.validate(self.evidence())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROMOTION_LEGACY_NOT_ELIGIBLE", result.stderr)

    def test_inspects_legacy_evidence_without_promotion_eligibility(self) -> None:
        result = self.validate(self.evidence(), inspect_legacy=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"matrix_cells":2', result.stdout)
        self.assertIn('"promotion_eligible":false', result.stdout)

    def v2_evidence(self, root: Path) -> dict[str, object]:
        candidate = {"tag": TAG, "commit": COMMIT, "image": IMAGE}
        records = {}

        def write(relative: str, value: object) -> dict[str, str]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}

        archive_data = io.BytesIO()
        with tarfile.open(fileobj=archive_data, mode="w") as archive:
            for name, raw in (("version.manifest", b"version=fixture\n"), ("logs/product.log", b"fixture log\n"), ("manifest.txt", b"format=sponzey-support-v1\nartifacts=2\nredaction=passed\n")):
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
        raw_archive = archive_data.getvalue()
        (root / "bundle.tar").write_bytes(raw_archive)
        archive_digest = hashlib.sha256(raw_archive).hexdigest()
        bundle_original = {
            "archive": {"path": "bundle.tar", "sha256": archive_digest},
            "response": write("bundle-response.json", {"archive_id": archive_digest, "digest_sha256": archive_digest,
                              "collected_artifacts": ["version_manifest", "bounded_product_log"], "omitted_artifacts": [], "total_bytes": len(b"version=fixture\n") + len(b"fixture log\n")}),
            "log_observation": {"collected_at_unix": 100000, "modified_at_unix": 99000,
                                "sha256": hashlib.sha256(b"fixture log\n").hexdigest()},
        }
        symlink_data = io.BytesIO()
        with tarfile.open(fileobj=symlink_data, mode="w") as archive:
            for name, raw in (("logs/product.log", b"fixture log\n"), ("manifest.txt", b"format=sponzey-support-v1\nartifacts=1\nredaction=passed\n")):
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
        symlink_raw = symlink_data.getvalue()
        (root / "symlink-bundle.tar").write_bytes(symlink_raw)
        symlink_digest = hashlib.sha256(symlink_raw).hexdigest()
        symlink_original = {
            "source_type": "symlink", "target_artifact": "version_manifest",
            "archive": {"path": "symlink-bundle.tar", "sha256": symlink_digest},
            "response": write("symlink-response.json", {"archive_id": symlink_digest, "digest_sha256": symlink_digest,
                              "collected_artifacts": ["bounded_product_log"], "omitted_artifacts": ["version_manifest"], "total_bytes": len(b"fixture log\n")}),
            "log_observation": dict(bundle_original["log_observation"]),
        }

        def receipt(kind: str, checks: dict[str, object]) -> dict[str, object]:
            observations = {}
            for name, value in checks.items():
                actual = ({"command": SOURCE_COMMANDS[name], "source_commit": COMMIT, "exit_code": value, "stdout": "", "stderr": ""}
                          if kind == "source_quality" else
                          SUPPORT_HTTP_OBSERVATIONS[name] if kind == "support_bundle" and name in SUPPORT_HTTP_OBSERVATIONS
                          else bundle_original if kind == "support_bundle" and name == "allowlist_and_bounds"
                          else symlink_original if kind == "support_bundle" and name == "unsafe_paths_rejected"
                          else {"archive_sha256": archive_digest} if kind == "support_bundle" and name == "sensitive_content_excluded"
                          else {"os": "linux", "arch": "x86_64", "runtime": "systemd" if kind == "systemd" else "docker-compose",
                                "candidate_commit": COMMIT, "candidate_image": IMAGE, "observed_sha256": "2" * 64,
                                "command_exit": 0, "ready_status": 200} if kind in ("compose", "systemd") and name == "install"
                          else DEPLOYMENT_OBSERVATIONS[name] if kind in ("compose", "systemd") and name in DEPLOYMENT_OBSERVATIONS
                          else {"observation": name, "result": value})
                output = write(f"outputs/{kind}-{name}.json", actual)
                observations[name] = {"value": value, "output": output}
            trace = write(f"traces/{kind}.json", {"schema_version": 1, "kind": kind, "candidate": candidate, "observations": observations})
            return {"schema_version": 1, "kind": kind, "candidate": candidate, "checks": checks, "trace": trace}

        records["source_quality"] = write("source-quality.json", receipt("source_quality", {
            "format": 0, "clippy": 0, "workspace_tests": 0, "mutation": 0,
            "architecture": 0, "source_index": 0, "dependency_audit": 0,
        }))
        records["support_bundle"] = write("support.json", receipt("support_bundle", {
            "authenticated": True, "csrf_enforced": True, "allowlist_and_bounds": True,
            "sensitive_content_excluded": True, "unsafe_paths_rejected": True,
        }))
        for deployment in ("compose", "systemd"):
            records[deployment] = write(f"{deployment}.json", receipt(deployment, {
                "install": True, "forwarding": True, "admin_loopback": True,
                "restart": True, "sigterm": True, "upgrade": True,
                "forced_rollback": True, "preservation": True, "cleanup": True,
            }))

        # Raw performance fixtures use the same k6 metrics and host identity as
        # the production collector. Summaries are generated by that collector's
        # existing functions, not by an independent copy of its arithmetic.
        generator = ROOT / "tests" / "release_contract" / "promotion_performance_fixture.mjs"
        generated = subprocess.run(["node", str(generator), str(root), COMMIT, IMAGE], capture_output=True, text=True, check=True)
        for name, files in json.loads(generated.stdout).items():
            records[name] = {}
            for relative in files:
                raw = (root / relative).read_bytes()
                records[name][Path(relative).name] = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}
        return {
            "schema_version": 2, **candidate, "manual_or_private_pki_only": True,
            "certificate_automation_deferred": True, "records": records,
        }

    def test_accepts_raw_bound_v2_and_rejects_missing_or_changed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            result = self.validate(evidence, root=root)
            self.assertEqual(result.returncode, 0)
            self.assertIn('"promotion_eligible":false', result.stdout)
            self.assertIn('"evidence_contract_valid":false', result.stdout)
            path = root / "source-quality.json"
            path.write_text("{}", encoding="utf-8")
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)
            path.unlink()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_source_quality_requires_command_result_instead_of_boolean_echo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            self.assertEqual(self.validate(evidence, root=root).returncode, 0)
            receipt_ref = evidence["records"]["source_quality"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            output_ref = trace["observations"]["format"]["output"]
            output_path = root / output_ref["path"]
            def rewrite(ref: dict[str, str], path: Path, data: object) -> None:
                raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
                path.write_bytes(raw)
                ref["sha256"] = hashlib.sha256(raw).hexdigest()

            valid = {"command": SOURCE_COMMANDS["format"], "source_commit": COMMIT,
                     "exit_code": 0, "stdout": "", "stderr": ""}
            for output in ({"observation": "format", "result": 0},
                           {**valid, "exit_code": 1},
                           {**valid, "command": ["true"]},
                           {**valid, "source_commit": "c" * 40},
                           {**valid, "stdout": "password=fixture-secret"}):
                rewrite(output_ref, output_path, output)
                rewrite(trace_ref, trace_path, trace)
                rewrite(receipt_ref, receipt_path, receipt)
                result = self.validate(evidence, root=root)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("fixture-secret", result.stdout + result.stderr)

    def test_v2_cannot_authorize_promotion_without_independent_originals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            result = self.validate(evidence, root=root, inspect_v2=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PROMOTION_ORIGINALS_UNVERIFIED", result.stderr)

    def test_support_auth_checks_http_status_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            self.assertEqual(self.validate(evidence, root=root).returncode, 0)
            receipt_ref = evidence["records"]["support_bundle"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            output_ref = trace["observations"]["csrf_enforced"]["output"]
            output_path = root / output_ref["path"]
            for output in ({"observation": "csrf_enforced", "result": True},
                           {"missing_csrf_status": 200, "authenticated_status": 200}):
                for ref, path, value in ((output_ref, output_path, output), (trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                    path.write_bytes(raw)
                    ref["sha256"] = hashlib.sha256(raw).hexdigest()
                self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_symlink_omission_is_supported_by_separate_archive_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            result = self.validate(evidence, root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_ref = evidence["records"]["support_bundle"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            output_ref = trace["observations"]["unsafe_paths_rejected"]["output"]
            output_path = root / output_ref["path"]
            output = json.loads(output_path.read_text())
            response_ref = output["response"]
            response_path = root / response_ref["path"]
            response = json.loads(response_path.read_text())
            response["omitted_artifacts"] = []
            for ref, path, value in ((response_ref, response_path, response), (output_ref, output_path, output), (trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                path.write_bytes(raw)
                ref["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_support_archive_requires_actual_safe_archive_and_matching_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            self.assertEqual(self.validate(evidence, root=root).returncode, 0)
            receipt_ref = evidence["records"]["support_bundle"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            output_ref = trace["observations"]["allowlist_and_bounds"]["output"]
            output_path = root / output_ref["path"]
            output = json.loads(output_path.read_text())
            # A changed archive must still fail even if all the reference digests are updated.
            response_ref = output["response"]
            response_path = root / response_ref["path"]
            response = json.loads(response_path.read_text())
            for name, payload, symlink in (("version.manifest", b"", True), ("secrets.env", b"safe", False), ("version.manifest", b"password=fixture-secret", False)):
                bad = io.BytesIO()
                with tarfile.open(fileobj=bad, mode="w") as archive:
                    member = tarfile.TarInfo(name)
                    if symlink:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "../../secret"
                        archive.addfile(member)
                    else:
                        member.size = len(payload)
                        archive.addfile(member, io.BytesIO(payload))
                    manifest = b"format=sponzey-support-v1\nartifacts=1\nredaction=passed\n"
                    member = tarfile.TarInfo("manifest.txt")
                    member.size = len(manifest)
                    archive.addfile(member, io.BytesIO(manifest))
                archive_raw = bad.getvalue()
                (root / output["archive"]["path"]).write_bytes(archive_raw)
                digest = hashlib.sha256(archive_raw).hexdigest()
                output["archive"]["sha256"] = digest
                response["archive_id"] = response["digest_sha256"] = digest
                response["total_bytes"] = len(payload)
                for ref, path, value in ((response_ref, response_path, response), (output_ref, output_path, output), (trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                    path.write_bytes(raw)
                    ref["sha256"] = hashlib.sha256(raw).hexdigest()
                result = self.validate(evidence, root=root)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("fixture-secret", result.stdout + result.stderr)

    def test_support_archive_log_age_is_bound_to_archived_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            self.assertEqual(self.validate(evidence, root=root).returncode, 0)
            receipt_ref = evidence["records"]["support_bundle"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            output_ref = trace["observations"]["allowlist_and_bounds"]["output"]
            output_path = root / output_ref["path"]
            output = json.loads(output_path.read_text())
            for update in ({"collected_at_unix": 100000, "modified_at_unix": 1, "sha256": hashlib.sha256(b"fixture log\n").hexdigest()},
                           {"collected_at_unix": 100000, "modified_at_unix": 99000, "sha256": "0" * 64}):
                output["log_observation"] = update
                for ref, path, value in ((output_ref, output_path, output), (trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                    path.write_bytes(raw)
                    ref["sha256"] = hashlib.sha256(raw).hexdigest()
                self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_deployment_forwarding_and_admin_use_observed_values(self) -> None:
        for deployment, check, bad in (
            ("compose", "forwarding", {"status_code": 200, "body_sha256": "0" * 64}),
            ("systemd", "admin_loopback", {"listen_address": "0.0.0.0", "remote_probe": "connection_refused"}),
            ("systemd", "preservation", {stage: {key: ("e" if stage == "after_rollback" else "d") * 64 for key in ("config", "certificate", "audit_prefix", "data")}
                                         for stage in ("before", "after_upgrade", "after_rollback")}),
            ("compose", "forced_rollback", {**DEPLOYMENT_OBSERVATIONS["forced_rollback"], "observed_sha256": "2" * 64}),
            ("compose", "forced_rollback", {**DEPLOYMENT_OBSERVATIONS["forced_rollback"], "previous_sha256": "3" * 64, "observed_sha256": "3" * 64}),
            ("systemd", "upgrade", {**DEPLOYMENT_OBSERVATIONS["upgrade"], "candidate_image": IMAGE.replace("b" * 64, "c" * 64)}),
            ("systemd", "restart", {**DEPLOYMENT_OBSERVATIONS["restart"], "after_id": "instance-a"}),
            ("compose", "cleanup", {**DEPLOYMENT_OBSERVATIONS["cleanup"], "test_listeners_remaining": 1}),
        ):
            with self.subTest(deployment=deployment), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                evidence = self.v2_evidence(root)
                self.assertEqual(self.validate(evidence, root=root).returncode, 0)
                receipt_ref = evidence["records"][deployment]  # type: ignore[index]
                receipt_path = root / receipt_ref["path"]
                receipt = json.loads(receipt_path.read_text())
                trace_ref = receipt["trace"]
                trace_path = root / trace_ref["path"]
                trace = json.loads(trace_path.read_text())
                output_ref = trace["observations"][check]["output"]
                output_path = root / output_ref["path"]
                for ref, path, value in ((output_ref, output_path, bad), (trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                    path.write_bytes(raw)
                    ref["sha256"] = hashlib.sha256(raw).hexdigest()
                self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_systemd_observation_matches_verified_release_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            assets = root / "release-assets"
            assets.mkdir()
            binary_digest = candidate_fixture.CandidateArchiveTest().make_assets(assets)
            self.assertNotEqual(self.validate(evidence, root=root, release_artifacts=assets).returncode, 0)
            receipt_ref = evidence["records"]["systemd"]  # type: ignore[index]
            receipt_path = root / receipt_ref["path"]
            receipt = json.loads(receipt_path.read_text())
            trace_ref = receipt["trace"]
            trace_path = root / trace_ref["path"]
            trace = json.loads(trace_path.read_text())
            for name in ("install", "upgrade", "forced_rollback"):
                ref = trace["observations"][name]["output"]
                path = root / ref["path"]
                value = json.loads(path.read_text())
                if name == "install": value["observed_sha256"] = binary_digest
                else:
                    value["candidate_sha256"] = binary_digest
                    if name == "upgrade": value["observed_sha256"] = binary_digest
                raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                path.write_bytes(raw)
                ref["sha256"] = hashlib.sha256(raw).hexdigest()
            for ref, path, value in ((trace_ref, trace_path, trace), (receipt_ref, receipt_path, receipt)):
                raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                path.write_bytes(raw)
                ref["sha256"] = hashlib.sha256(raw).hexdigest()
            result = self.validate(evidence, root=root, release_artifacts=assets)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"promotion_eligible":false', result.stdout)
            self.assertIn('"archive_binding_verified":true', result.stdout)
            self.assertIn('"evidence_contract_valid":true', result.stdout)

    def test_approved_legacy_reference_without_config_hash_is_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            result = self.validate(evidence, root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            ref = evidence["records"]["c8_reference"]["metadata.json"]  # type: ignore[index]
            path = root / ref["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["source_tree"] = "d" * 40
            raw = json.dumps(value).encode()
            path.write_bytes(raw)
            ref["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_mixed_identity_and_missing_performance_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            reference = evidence["records"]["compose"]  # type: ignore[index]
            path = root / reference["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["candidate"]["commit"] = "c" * 40
            raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            reference["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)
            evidence = self.v2_evidence(root)
            del evidence["records"]["c8_candidate"]["baseline-3.json"]  # type: ignore[index]
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_tampered_raw_metrics_even_with_updated_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            reference = evidence["records"]["c8_candidate"]["baseline-1.json"]  # type: ignore[index]
            path = root / reference["path"]
            raw_value = json.loads(path.read_text(encoding="utf-8"))
            raw_value["metrics"]["http_reqs"]["rate"] = 1
            raw = json.dumps(raw_value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            reference["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_missing_original_operational_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            trace_ref = json.loads((root / "compose.json").read_text(encoding="utf-8"))["trace"]
            trace = json.loads((root / trace_ref["path"]).read_text(encoding="utf-8"))
            (root / trace["observations"]["forced_rollback"]["output"]["path"]).unlink()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_recomputes_c8_and_rejects_regression_with_consistent_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            files = evidence["records"]["c8_candidate"]  # type: ignore[index]

            def replace(name: str, value: object) -> None:
                ref = files[name]
                raw = json.dumps(value, separators=(",", ":")).encode()
                (root / ref["path"]).write_bytes(raw)
                ref["sha256"] = hashlib.sha256(raw).hexdigest()

            for index in range(1, 4):
                name = f"baseline-{index}.json"
                value = json.loads((root / files[name]["path"]).read_text(encoding="utf-8"))
                value["metrics"]["http_reqs"]["rate"] = 94
                replace(name, value)
            summary = json.loads((root / files["summary.json"]["path"]).read_text(encoding="utf-8"))
            for run in summary["runs"]:
                run["rps"] = 94
            summary["baseline_comparison"]["rps"] = {"min": 94, "median": 94, "max": 94}
            replace("summary.json", summary)
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_unapproved_reference_and_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            ref = evidence["records"]["c8_reference"]["metadata.json"]  # type: ignore[index]
            path = root / ref["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["source_commit"] = "d" * 40
            raw = json.dumps(value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            ref["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)
            evidence = self.v2_evidence(root)
            evidence["records"]["source_quality"]["path"] = "../source-quality.json"  # type: ignore[index]
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_mixed_candidate_source_trees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            reference = evidence["records"]["soak"]["metadata.json"]  # type: ignore[index]
            path = root / reference["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["source_tree"] = "a" * 40
            raw = json.dumps(value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            reference["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_sensitive_fields_in_original_performance_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            reference = evidence["records"]["soak"]["metadata.json"]  # type: ignore[index]
            path = root / reference["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["authorization"] = "Bearer example-sensitive-value"
            raw = json.dumps(value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            reference["sha256"] = hashlib.sha256(raw).hexdigest()
            result = self.validate(evidence, root=root)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("example-sensitive-value", result.stderr)

    def test_rejects_hardlinked_originals_reused_for_distinct_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            compose = json.loads((root / "traces/compose.json").read_text(encoding="utf-8"))
            systemd = json.loads((root / "traces/systemd.json").read_text(encoding="utf-8"))
            first = root / compose["observations"]["restart"]["output"]["path"]
            second = root / systemd["observations"]["restart"]["output"]["path"]
            self.assertEqual(first.read_bytes(), second.read_bytes())
            second.unlink()
            os.link(first, second)
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_rejects_symlink_and_unproven_candidate_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            reference = evidence["records"]["c8_candidate"]["metadata.json"]  # type: ignore[index]
            path = root / reference["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            del value["candidate_image"]
            raw = json.dumps(value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            reference["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)
            evidence = self.v2_evidence(root)
            source = root / "source-quality.json"
            target = root / "source-copy.json"
            target.write_bytes(source.read_bytes())
            source.unlink()
            source.symlink_to(target)
            self.assertNotEqual(self.validate(evidence, root=root).returncode, 0)

    def test_promotion_requires_every_original_to_be_committed_and_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "promotion.json").write_text(json.dumps(evidence), encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            self.assertEqual(self.validate(evidence, root=root, require_tracked=True).returncode, 0)
            result = self.validate(evidence, root=root, require_tracked=True, inspect_v2=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PROMOTION_ORIGINALS_UNVERIFIED", result.stderr)
            record = evidence["records"]["source_quality"]  # type: ignore[index]
            path = root / record["path"]
            raw = path.read_bytes() + b" "
            path.write_bytes(raw)
            record["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(self.validate(evidence, root=root, require_tracked=True).returncode, 0)

    def test_rejects_symlinked_promotion_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.v2_evidence(root)
            (root / "original.json").write_text(json.dumps(evidence), encoding="utf-8")
            (root / "promotion.json").symlink_to(root / "original.json")
            result = subprocess.run([
                sys.executable, str(VALIDATOR), "--evidence", str(root / "promotion.json"),
                "--tag", TAG, "--commit", COMMIT, "--image", IMAGE, "--inspect-v2",
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_matrix_cell(self) -> None:
        evidence = self.evidence()
        evidence["matrix"] = evidence["matrix"][:-1]  # type: ignore[index]
        result = self.validate(evidence)
        self.assertIn("PROMOTION_MATRIX_INCOMPLETE", result.stderr)

    def test_rejects_unsupported_arm64_matrix_cell(self) -> None:
        evidence = self.evidence()
        evidence["matrix"].append(  # type: ignore[union-attr]
            {"deployment": "compose", "platform": "linux-arm64", "status": "passed"}
        )
        result = self.validate(evidence)
        self.assertIn("PROMOTION_MATRIX_INCOMPLETE", result.stderr)

    def test_rejects_identity_or_certificate_scope_drift(self) -> None:
        evidence = self.evidence()
        evidence["image"] = f"ghcr.io/sponzey-lab/sponzey-edge:{TAG}"
        result = self.validate(evidence)
        self.assertIn("PROMOTION_IDENTITY_MISMATCH", result.stderr)

        evidence = self.evidence()
        evidence["certificate_automation_deferred"] = False
        result = self.validate(evidence)
        self.assertIn("PROMOTION_SCOPE_INVALID", result.stderr)

    def test_workflows_create_only_a_prerelease_until_manual_promotion(self) -> None:
        candidate = (ROOT / ".github/workflows/build-binaries.yml").read_text(encoding="utf-8")
        promotion = (ROOT / ".github/workflows/promote-release.yml").read_text(encoding="utf-8")
        self.assertIn("Create GitHub prerelease candidate", candidate)
        self.assertIn("prerelease: true", candidate)
        self.assertNotIn("Create GitHub Release", candidate)
        self.assertIn("workflow_dispatch", promotion)
        self.assertIn("validate_promotion_evidence.py", promotion)
        self.assertIn("--require-tracked", promotion)
        self.assertIn("actions/setup-node@", promotion)
        self.assertIn("PROMOTION_EVIDENCE_PATH:", promotion)
        self.assertNotIn('"${{ inputs.evidence_path }}"', promotion)
        self.assertIn("gh release edit", promotion)

    def test_release_docs_describe_tracked_evidence_promotion(self) -> None:
        release_gate = (ROOT / "docs/release-gate.md").read_text(encoding="utf-8")
        template = (ROOT / "docs/release-evidence-template.md").read_text(encoding="utf-8")
        self.assertIn("promote-release.yml", release_gate)
        self.assertIn("promotion.json", template)
        self.assertIn("certificate_automation_deferred", template)
        self.assertIn("Official support is Linux `amd64` only", release_gate)
        self.assertIn("Linux amd64 only", template)


if __name__ == "__main__":
    unittest.main()
