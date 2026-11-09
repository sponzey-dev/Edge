#!/usr/bin/env python3
"""Fail closed unless clean-host evidence matches one immutable candidate."""

import argparse
import hashlib
import io
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
import validate_candidate_archive as candidate_archive


SEMVER = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^ghcr\.io/sponzey-lab/sponzey-edge:v[0-9]+\.[0-9]+\.[0-9]+@sha256:[0-9a-f]{64}$")
MATRIX = {
    ("compose", "linux-amd64"),
    ("systemd", "linux-amd64"),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_SUPPORT_ARCHIVE_BYTES = MAX_EVIDENCE_BYTES + 64 * 1024
SENSITIVE_KEYS = {
    "authorization", "proxy_authorization", "cookie", "set_cookie", "password", "passphrase",
    "private_key", "private_key_pem", "client_secret", "access_token", "session_token",
    "csrf_token", "request_body", "response_body", "query_string", "headers", "pem",
}
SENSITIVE_TEXT = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----|\bBearer\s+\S+|https?://[^\s?]+\?"
    r"|\b(?:password|passphrase|client_secret|access_token|session_token|csrf_token|authorization|cookie)\s*[:=]\s*[^\s]+",
    re.IGNORECASE,
)
PERFORMANCE_FILES = {
    "c8_reference": {"metadata.json", "state.json", "summary.json", "edge-resource-samples.json", "baseline-1.json", "baseline-2.json", "baseline-3.json"},
    "c8_candidate": {"metadata.json", "state.json", "summary.json", "edge-resource-samples.json", "baseline-1.json", "baseline-2.json", "baseline-3.json"},
    "soak": {"metadata.json", "state.json", "summary.json", "edge-resource-samples.json", "soak-1.json"},
}
RECEIPT_CHECKS = {
    "source_quality": {"format", "clippy", "workspace_tests", "mutation", "architecture", "source_index", "dependency_audit"},
    "support_bundle": {"authenticated", "csrf_enforced", "allowlist_and_bounds", "sensitive_content_excluded", "unsafe_paths_rejected"},
    "compose": {"install", "forwarding", "admin_loopback", "restart", "sigterm", "upgrade", "forced_rollback", "preservation", "cleanup"},
    "systemd": {"install", "forwarding", "admin_loopback", "restart", "sigterm", "upgrade", "forced_rollback", "preservation", "cleanup"},
}
SOURCE_COMMANDS = {
    "format": ["cargo", "fmt", "--check"],
    "clippy": ["cargo", "clippy", "--workspace", "--all-targets", "--", "-D", "warnings"],
    "workspace_tests": ["cargo", "test", "--workspace", "--", "--test-threads=1"],
    "mutation": ["cargo", "run", "-p", "edge-core", "--example", "http_framing_mutation_fuzz", "--", "1000"],
    "architecture": ["python3", "tools/release/check_architecture.py", "--workspace", "."],
    "source_index": ["python3", "tools/release/check_source_indexes.py", "--workspace", "."],
    "dependency_audit": ["cargo", "audit"],
}
SUPPORT_HTTP_STATUSES = {
    "authenticated": {"unauthenticated_status": 401, "authenticated_status": 200},
    "csrf_enforced": {"missing_csrf_status": 403, "authenticated_status": 200},
}
FORWARDING_DIGEST = hashlib.sha256(b"sponzey-release-fixture\n").hexdigest()
SUPPORT_MEMBERS = {
    "version.manifest": "version_manifest", "config/masked.toml": "masked_config",
    "logs/product.log": "bounded_product_log", "health.json": "health_summary",
    "resource.json": "resource_summary", "audit-summary.json": "audit_summary",
}


class PromotionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise PromotionError(code, message)


def decode_json(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> object:
        raise ValueError("non-finite JSON number")

    def check_sensitive(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower().replace("-", "_") in SENSITIVE_KEYS:
                    fail("PROMOTION_EVIDENCE_SENSITIVE", "evidence contains a prohibited field")
                check_sensitive(child)
        elif isinstance(value, list):
            for child in value:
                check_sensitive(child)
        elif isinstance(value, str) and SENSITIVE_TEXT.search(value):
            fail("PROMOTION_EVIDENCE_SENSITIVE", "evidence contains prohibited content")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
        check_sensitive(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        fail("PROMOTION_EVIDENCE_INVALID", "evidence JSON is invalid")


def read_index(path: Path) -> object:
    try:
        if stat.S_ISLNK(path.lstat().st_mode):
            fail("PROMOTION_EVIDENCE_INVALID", "evidence index symlinks are forbidden")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_EVIDENCE_BYTES:
                fail("PROMOTION_EVIDENCE_INVALID", "evidence index is not a bounded regular file")
            raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    except (OSError, ValueError):
        fail("PROMOTION_EVIDENCE_INVALID", "evidence index cannot be read safely")
    if len(raw) > MAX_EVIDENCE_BYTES:
        fail("PROMOTION_EVIDENCE_INVALID", "evidence index is too large")
    return decode_json(raw)


def read_reference(root: Path, reference: object, used: set[str], inodes: set[tuple[int, int]], *, limit: int = MAX_EVIDENCE_BYTES) -> tuple[Path, bytes]:
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        fail("PROMOTION_EVIDENCE_INVALID", "artifact reference must contain only path and sha256")
    name, digest = reference["path"], reference["sha256"]
    if not isinstance(name, str) or not name or "\\" in name or name.startswith("/"):
        fail("PROMOTION_EVIDENCE_INVALID", "artifact path is invalid")
    parts = name.split("/")
    if any(part in ("", ".", "..") or part.endswith(".partial") for part in parts) or name in used:
        fail("PROMOTION_EVIDENCE_INVALID", "artifact path is unsafe or duplicated")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        fail("PROMOTION_EVIDENCE_INVALID", "artifact digest is invalid")
    current = root
    try:
        for part in parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                fail("PROMOTION_EVIDENCE_INVALID", "artifact symlinks are forbidden")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(current, flags)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                fail("PROMOTION_EVIDENCE_INVALID", "artifact is not a bounded regular file")
            identity = (info.st_dev, info.st_ino)
            if identity in inodes:
                fail("PROMOTION_EVIDENCE_INVALID", "artifact aliases another original")
            raw = handle.read(limit + 1)
    except (OSError, ValueError):
        fail("PROMOTION_EVIDENCE_INVALID", "artifact cannot be read safely")
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != digest:
        fail("PROMOTION_EVIDENCE_INVALID", "artifact digest does not match")
    used.add(name)
    inodes.add(identity)
    return current, raw


def require_committed(index: Path, root: Path, used: set[str]) -> None:
    try:
        repository = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        repo = Path(repository).resolve()
        paths = [str(path.resolve().relative_to(repo)) for path in [index, *(root / name for name in sorted(used))]]
        prefix = ["git", "--literal-pathspecs", "-C", str(repo)]
        subprocess.run([*prefix, "ls-files", "--error-unmatch", "--", *paths], capture_output=True, timeout=10, check=True)
        subprocess.run([*prefix, "diff", "--quiet", "HEAD", "--", *paths], capture_output=True, timeout=10, check=True)
    except (OSError, ValueError, subprocess.SubprocessError):
        fail("PROMOTION_EVIDENCE_UNTRACKED", "all evidence must be committed and unchanged")


def validate_support_archive(root: Path, output: object, used: set[str], inodes: set[tuple[int, int]]) -> tuple[dict[str, object], set[str]]:
    if not isinstance(output, dict) or set(output) != {"archive", "response", "log_observation"}:
        fail("PROMOTION_EVIDENCE_INVALID", "support archive references are incomplete")
    _, raw = read_reference(root, output["archive"], used, inodes, limit=MAX_SUPPORT_ARCHIVE_BYTES)
    _, response_raw = read_reference(root, output["response"], used, inodes)
    response = decode_json(response_raw)
    digest = hashlib.sha256(raw).hexdigest()
    if (not isinstance(response, dict) or set(response) != {"archive_id", "digest_sha256", "collected_artifacts", "omitted_artifacts", "total_bytes"}
        or response["archive_id"] != digest or response["digest_sha256"] != digest
        or not isinstance(response["collected_artifacts"], list) or not isinstance(response["omitted_artifacts"], list)
        or any(not isinstance(item, str) for item in response["collected_artifacts"])
        or any(not isinstance(item, str) for item in response["omitted_artifacts"])
        or type(response["total_bytes"]) is not int):
        fail("PROMOTION_EVIDENCE_INVALID", "support receipt is invalid")
    contents: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                if (member.name not in set(SUPPORT_MEMBERS) | {"manifest.txt"} or member.name in contents
                    or not member.isfile() or member.size > MAX_EVIDENCE_BYTES):
                    fail("PROMOTION_EVIDENCE_INVALID", "support archive member is unsafe")
                stream = archive.extractfile(member)
                if stream is None:
                    fail("PROMOTION_EVIDENCE_INVALID", "support archive member cannot be read")
                contents[member.name] = stream.read(MAX_EVIDENCE_BYTES + 1)
    except (tarfile.TarError, OSError, ValueError):
        fail("PROMOTION_EVIDENCE_INVALID", "support archive is malformed")
    members = set(contents) - {"manifest.txt"}
    total = sum(len(contents[name]) for name in members)
    manifest = f"format=sponzey-support-v1\nartifacts={len(members)}\nredaction=passed\n".encode()
    if (contents.get("manifest.txt") != manifest or total > MAX_EVIDENCE_BYTES
        or response["total_bytes"] != total
        or sorted(response["collected_artifacts"]) != sorted(SUPPORT_MEMBERS[name] for name in members)):
        fail("PROMOTION_EVIDENCE_INVALID", "support archive and receipt do not match")
    log = output["log_observation"]
    if ("logs/product.log" not in contents or not isinstance(log, dict)
        or set(log) != {"collected_at_unix", "modified_at_unix", "sha256"}
        or type(log["collected_at_unix"]) is not int or type(log["modified_at_unix"]) is not int
        or log["modified_at_unix"] < 0 or not 0 <= log["collected_at_unix"] - log["modified_at_unix"] <= 86400
        or log["sha256"] != hashlib.sha256(contents["logs/product.log"]).hexdigest()):
        fail("PROMOTION_EVIDENCE_INVALID", "support log age observation is invalid")
    for content in contents.values():
        text = content.decode("utf-8", errors="replace")
        if SENSITIVE_TEXT.search(text) or any(needle in text.lower() for needle in ("authorization:", "cookie:", "set-cookie:", "password=", "secret=")):
            fail("PROMOTION_EVIDENCE_SENSITIVE", "support archive contains prohibited content")
    return response, members


def validate_v2(evidence: dict[str, object], index: Path, tag: str, commit: str, image: str, *, require_tracked: bool, binary_sha256: str = "") -> dict[str, object]:
    root = index.parent.resolve()
    expected_keys = {"schema_version", "tag", "commit", "image", "manual_or_private_pki_only", "certificate_automation_deferred", "records"}
    if set(evidence) != expected_keys:
        fail("PROMOTION_EVIDENCE_INVALID", "unexpected or missing evidence fields")
    if evidence.get("manual_or_private_pki_only") is not True or evidence.get("certificate_automation_deferred") is not True:
        fail("PROMOTION_SCOPE_INVALID", "certificate automation remains deferred")
    records = evidence.get("records")
    if not isinstance(records, dict) or set(records) != set(RECEIPT_CHECKS) | set(PERFORMANCE_FILES):
        fail("PROMOTION_EVIDENCE_INCOMPLETE", "required evidence records are missing or unexpected")
    candidate = {"tag": tag, "commit": commit, "image": image}
    used: set[str] = set()
    inodes: set[tuple[int, int]] = set()
    for kind, required_checks in RECEIPT_CHECKS.items():
        _, raw = read_reference(root, records[kind], used, inodes)
        receipt = decode_json(raw)
        if not isinstance(receipt, dict) or set(receipt) != {"schema_version", "kind", "candidate", "checks", "trace"}:
            fail("PROMOTION_EVIDENCE_INVALID", "receipt schema is invalid")
        if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1 or receipt["kind"] != kind or receipt["candidate"] != candidate:
            fail("PROMOTION_IDENTITY_MISMATCH", "receipt identity or kind does not match")
        checks = receipt["checks"]
        if not isinstance(checks, dict) or set(checks) != required_checks:
            fail("PROMOTION_EVIDENCE_INCOMPLETE", "receipt checks are incomplete")
        for value in checks.values():
            valid = type(value) is int and value == 0 if kind == "source_quality" else value is True
            if not valid:
                fail("PROMOTION_EVIDENCE_INCOMPLETE", "receipt contains a failing check")
        _, trace_raw = read_reference(root, receipt["trace"], used, inodes)
        trace = decode_json(trace_raw)
        if not isinstance(trace, dict) or set(trace) != {"schema_version", "kind", "candidate", "observations"}:
            fail("PROMOTION_EVIDENCE_INVALID", "observation trace schema is invalid")
        if type(trace["schema_version"]) is not int or trace["schema_version"] != 1 or trace["kind"] != kind or trace["candidate"] != candidate:
            fail("PROMOTION_IDENTITY_MISMATCH", "observation trace identity does not match")
        observations = trace["observations"]
        if not isinstance(observations, dict) or set(observations) != required_checks:
            fail("PROMOTION_EVIDENCE_INCOMPLETE", "original observations are incomplete")
        lifecycle: dict[str, dict[str, object]] = {}
        support_digests: dict[str, str] = {}
        for name, expected in checks.items():
            observation = observations[name]
            if not isinstance(observation, dict) or set(observation) != {"value", "output"}:
                fail("PROMOTION_EVIDENCE_INVALID", "original observation is invalid")
            if type(observation["value"]) is not type(expected) or observation["value"] != expected:
                fail("PROMOTION_EVIDENCE_INVALID", "original observation differs from receipt")
            _, output_raw = read_reference(root, observation["output"], used, inodes)
            output = decode_json(output_raw)
            if kind == "source_quality":
                if (not isinstance(output, dict)
                    or set(output) != {"command", "source_commit", "exit_code", "stdout", "stderr"}
                    or output["command"] != SOURCE_COMMANDS[name]
                    or output["source_commit"] != commit
                    or type(output["exit_code"]) is not int or output["exit_code"] != 0
                    or not isinstance(output["stdout"], str) or not isinstance(output["stderr"], str)):
                    fail("PROMOTION_EVIDENCE_INVALID", "source command output is invalid or failed")
            elif kind == "support_bundle" and name in SUPPORT_HTTP_STATUSES:
                expected_statuses = SUPPORT_HTTP_STATUSES[name]
                if (not isinstance(output, dict) or set(output) != set(expected_statuses)
                    or any(type(output[key]) is not int or output[key] != status for key, status in expected_statuses.items())):
                    fail("PROMOTION_EVIDENCE_INVALID", "support authentication observations are invalid")
            elif kind == "support_bundle" and name == "allowlist_and_bounds":
                validate_support_archive(root, output, used, inodes)
                support_digests["archive"] = output["archive"]["sha256"]
            elif kind == "support_bundle" and name == "sensitive_content_excluded":
                if (not isinstance(output, dict) or set(output) != {"archive_sha256"}
                    or not isinstance(output["archive_sha256"], str) or SHA256.fullmatch(output["archive_sha256"]) is None):
                    fail("PROMOTION_EVIDENCE_INVALID", "support scan identity is invalid")
                support_digests["scan"] = output["archive_sha256"]
            elif kind == "support_bundle" and name == "unsafe_paths_rejected":
                if (not isinstance(output, dict) or set(output) != {"source_type", "target_artifact", "archive", "response", "log_observation"}
                    or output["source_type"] != "symlink" or output["target_artifact"] != "version_manifest"):
                    fail("PROMOTION_EVIDENCE_INVALID", "unsafe source observation is invalid")
                archive_output = {key: output[key] for key in ("archive", "response", "log_observation")}
                response, members = validate_support_archive(root, archive_output, used, inodes)
                if "version.manifest" in members or "version_manifest" not in response["omitted_artifacts"]:
                    fail("PROMOTION_EVIDENCE_INVALID", "unsafe source was not omitted")
            elif kind in ("compose", "systemd") and name == "forwarding":
                if (not isinstance(output, dict) or set(output) != {"status_code", "body_sha256"}
                    or type(output["status_code"]) is not int or output["status_code"] != 200
                    or output["body_sha256"] != FORWARDING_DIGEST):
                    fail("PROMOTION_EVIDENCE_INVALID", "forwarding observation is invalid")
            elif kind in ("compose", "systemd") and name == "admin_loopback":
                if (not isinstance(output, dict) or set(output) != {"listen_address", "remote_probe"}
                    or not isinstance(output["listen_address"], str) or output["remote_probe"] != "connection_refused"):
                    fail("PROMOTION_EVIDENCE_INVALID", "admin listener observation is invalid")
                try:
                    if not ipaddress.ip_address(output["listen_address"]).is_loopback:
                        fail("PROMOTION_EVIDENCE_INVALID", "admin listener is not loopback")
                except ValueError:
                    fail("PROMOTION_EVIDENCE_INVALID", "admin listener address is invalid")
            elif kind in ("compose", "systemd") and name == "preservation":
                keys = {"config", "certificate", "audit_prefix", "data"}
                if (not isinstance(output, dict) or set(output) != {"before", "after_upgrade", "after_rollback"}
                    or not isinstance(output["before"], dict) or set(output["before"]) != keys
                    or output["before"] != output["after_upgrade"] or output["before"] != output["after_rollback"]
                    or any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in output["before"].values())):
                    fail("PROMOTION_EVIDENCE_INVALID", "preservation digest observations are invalid")
            elif kind in ("compose", "systemd") and name in ("upgrade", "forced_rollback"):
                fields = {"state", "previous_sha256", "candidate_sha256", "observed_sha256", "candidate_image"}
                if (not isinstance(output, dict) or set(output) != fields or output["candidate_image"] != image
                    or output["state"] != ("committed" if name == "upgrade" else "rolled_back")
                    or any(not isinstance(output[key], str) or SHA256.fullmatch(output[key]) is None
                           for key in ("previous_sha256", "candidate_sha256", "observed_sha256"))
                    or output["previous_sha256"] == output["candidate_sha256"]
                    or output["observed_sha256"] != output["candidate_sha256" if name == "upgrade" else "previous_sha256"]):
                    fail("PROMOTION_EVIDENCE_INVALID", "upgrade or rollback observation is invalid")
                lifecycle[name] = output
            elif kind in ("compose", "systemd") and name == "install":
                fields = {"os", "arch", "runtime", "candidate_commit", "candidate_image", "observed_sha256", "command_exit", "ready_status"}
                if (not isinstance(output, dict) or set(output) != fields
                    or output["os"] != "linux" or output["arch"] != "x86_64"
                    or output["runtime"] != ("systemd" if kind == "systemd" else "docker-compose")
                    or output["candidate_commit"] != commit or output["candidate_image"] != image
                    or not isinstance(output["observed_sha256"], str) or SHA256.fullmatch(output["observed_sha256"]) is None
                    or type(output["command_exit"]) is not int or output["command_exit"] != 0
                    or type(output["ready_status"]) is not int or output["ready_status"] != 200):
                    fail("PROMOTION_EVIDENCE_INVALID", "installation observation is invalid")
                lifecycle[name] = output
            elif kind in ("compose", "systemd") and name == "restart":
                if (not isinstance(output, dict) or set(output) != {"command_exit", "ready_status", "before_id", "after_id"}
                    or type(output["command_exit"]) is not int or output["command_exit"] != 0
                    or type(output["ready_status"]) is not int or output["ready_status"] != 200
                    or any(not isinstance(output[key], str) or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", output[key]) is None for key in ("before_id", "after_id"))
                    or output["before_id"] == output["after_id"]):
                    fail("PROMOTION_EVIDENCE_INVALID", "restart observation is invalid")
            elif kind in ("compose", "systemd") and name == "sigterm":
                if (not isinstance(output, dict) or set(output) != {"signal_exit", "post_stop_state", "start_exit", "ready_status"}
                    or type(output["signal_exit"]) is not int or output["signal_exit"] != 0
                    or output["post_stop_state"] != "inactive"
                    or type(output["start_exit"]) is not int or output["start_exit"] != 0
                    or type(output["ready_status"]) is not int or output["ready_status"] != 200):
                    fail("PROMOTION_EVIDENCE_INVALID", "SIGTERM observation is invalid")
            elif kind in ("compose", "systemd") and name == "cleanup":
                keys = {"test_services_remaining", "test_listeners_remaining", "test_paths_remaining"}
                if (not isinstance(output, dict) or set(output) != keys
                    or any(type(output[key]) is not int or output[key] != 0 for key in keys)):
                    fail("PROMOTION_EVIDENCE_INVALID", "cleanup observation is invalid")
            else:
                if not isinstance(output, dict) or set(output) != {"observation", "result"} or output["observation"] != name:
                    fail("PROMOTION_EVIDENCE_INVALID", "original output schema is invalid")
                if type(output["result"]) is not type(expected) or output["result"] != expected:
                    fail("PROMOTION_EVIDENCE_INVALID", "original output differs from receipt")
        if kind in ("compose", "systemd"):
            if any(lifecycle["upgrade"][key] != lifecycle["forced_rollback"][key] for key in ("previous_sha256", "candidate_sha256")):
                fail("PROMOTION_IDENTITY_MISMATCH", "upgrade and rollback identities differ")
            if lifecycle["install"]["observed_sha256"] != lifecycle["upgrade"]["candidate_sha256"]:
                fail("PROMOTION_IDENTITY_MISMATCH", "installed and upgraded candidates differ")
            if kind == "systemd" and binary_sha256 and lifecycle["install"]["observed_sha256"] != binary_sha256:
                fail("PROMOTION_IDENTITY_MISMATCH", "systemd executable differs from candidate archive")
        if kind == "support_bundle" and support_digests.get("scan") != support_digests.get("archive"):
            fail("PROMOTION_IDENTITY_MISMATCH", "support scan and archive identities differ")
    try:
        with tempfile.TemporaryDirectory(prefix="edge-promotion-check-") as temporary:
            directories = []
            for kind, required_files in PERFORMANCE_FILES.items():
                group = records[kind]
                if not isinstance(group, dict) or set(group) != required_files:
                    fail("PROMOTION_EVIDENCE_INCOMPLETE", "performance originals are incomplete")
                parents: set[Path] = set()
                staging = Path(temporary) / kind
                staging.mkdir()
                for name in sorted(required_files):
                    path, raw = read_reference(root, group[name], used, inodes)
                    if path.name != name:
                        fail("PROMOTION_EVIDENCE_INVALID", "performance filename does not match its role")
                    decode_json(raw)
                    parents.add(path.parent)
                    (staging / name).write_bytes(raw)
                if len(parents) != 1:
                    fail("PROMOTION_EVIDENCE_INVALID", "performance files must share their profile directory")
                directories.append(str(staging))
            if require_tracked:
                require_committed(index, root, used)
            result = subprocess.run(
                ["node", str(Path(__file__).with_name("validate_promotion_performance.mjs")), *directories, commit, image],
                capture_output=True, timeout=30, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        fail("PROMOTION_PERFORMANCE_INVALID", "independent performance validation could not run")
    if result.returncode != 0:
        fail("PROMOTION_PERFORMANCE_INVALID", "independent performance validation failed")
    return {"matrix_cells": 2, "tag": tag, "promotion_eligible": True}


def validate(
    evidence_path: Path, tag: str, commit: str, image: str, *, inspect_legacy: bool = False, inspect_v2: bool = False, require_tracked: bool = False, release_artifacts: Path = None
) -> dict[str, object]:
    if SEMVER.fullmatch(tag) is None or COMMIT.fullmatch(commit) is None or IMAGE.fullmatch(image) is None:
        fail("PROMOTION_ARGUMENT_INVALID", "expected candidate identity is invalid")
    evidence = read_index(evidence_path)
    if not isinstance(evidence, dict) or type(evidence.get("schema_version")) is not int or evidence.get("schema_version") not in (1, 2):
        fail("PROMOTION_EVIDENCE_INVALID", "unsupported evidence schema_version")
    if any(evidence.get(key) != expected for key, expected in (("tag", tag), ("commit", commit), ("image", image))):
        fail("PROMOTION_IDENTITY_MISMATCH", "evidence must match the candidate tag, commit, and immutable image")
    if not image.startswith(f"ghcr.io/sponzey-lab/sponzey-edge:{tag}@sha256:"):
        fail("PROMOTION_IDENTITY_MISMATCH", "image tag does not match candidate tag")
    if evidence["schema_version"] == 2:
        if inspect_legacy:
            fail("PROMOTION_EVIDENCE_INVALID", "legacy inspection requires schema v1")
        binary_sha256 = ""
        if release_artifacts is not None:
            try:
                binary_sha256 = candidate_archive.validate(release_artifacts, tag, commit, image)["binary_sha256"]
            except (OSError, ValueError, StopIteration, tarfile.TarError, candidate_archive.release.ManifestError):
                fail("PROMOTION_ARCHIVE_INVALID", "candidate release assets are invalid")
        result = validate_v2(evidence, evidence_path, tag, commit, image, require_tracked=require_tracked, binary_sha256=binary_sha256)
        result["archive_binding_verified"] = bool(binary_sha256)
        result["evidence_contract_valid"] = bool(binary_sha256)
        if not inspect_v2:
            fail("PROMOTION_ORIGINALS_UNVERIFIED", "operational and source results lack independent original verification")
        result["promotion_eligible"] = False
        return result
    if inspect_v2:
        fail("PROMOTION_EVIDENCE_INVALID", "v2 inspection requires schema v2")
    if evidence.get("source_quality") != "passed" or evidence.get("support_bundle") != "passed":
        fail("PROMOTION_EVIDENCE_INCOMPLETE", "source quality and support bundle evidence must pass")
    if evidence.get("manual_or_private_pki_only") is not True or evidence.get("certificate_automation_deferred") is not True:
        fail("PROMOTION_SCOPE_INVALID", "promotion must retain manual/private PKI scope and deferred automation")
    matrix = evidence.get("matrix")
    cells: set[tuple[str, str]] = set()
    if not isinstance(matrix, list):
        fail("PROMOTION_MATRIX_INCOMPLETE", "matrix must contain the required clean-host cells")
    for item in matrix:
        if not isinstance(item, dict) or item.get("status") != "passed":
            fail("PROMOTION_MATRIX_INCOMPLETE", "every matrix cell must be a passed object")
        deployment, platform = item.get("deployment"), item.get("platform")
        if not isinstance(deployment, str) or not isinstance(platform, str):
            fail("PROMOTION_MATRIX_INCOMPLETE", "matrix cell identity is invalid")
        cells.add((deployment, platform))
    if cells != MATRIX or len(matrix) != len(MATRIX):
        fail("PROMOTION_MATRIX_INCOMPLETE", "matrix must contain each supported Compose/systemd Linux amd64 cell once")
    if not inspect_legacy:
        fail("PROMOTION_LEGACY_NOT_ELIGIBLE", "status-only evidence cannot authorize promotion")
    return {"matrix_cells": len(cells), "tag": tag, "promotion_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--inspect-legacy", action="store_true", help="inspect legacy evidence without authorizing promotion")
    parser.add_argument("--inspect-v2", action="store_true", help="inspect v2 evidence without authorizing promotion")
    parser.add_argument("--require-tracked", action="store_true", help="require committed, unchanged evidence originals")
    parser.add_argument("--release-artifacts", type=Path, help="inspect local published-candidate release assets")
    arguments = parser.parse_args()
    try:
        result = validate(arguments.evidence, arguments.tag, arguments.commit, arguments.image, inspect_legacy=arguments.inspect_legacy, inspect_v2=arguments.inspect_v2, require_tracked=arguments.require_tracked, release_artifacts=arguments.release_artifacts)
    except PromotionError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
