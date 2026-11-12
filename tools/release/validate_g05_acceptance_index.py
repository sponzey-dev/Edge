#!/usr/bin/env python3
"""Fail-closed structural and digest inspection for a G05 acceptance index."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


CRITERIA = tuple(f"G05-A0{number}" for number in range(1, 9))
CANDIDATE_FIELDS = {
    "tag",
    "commit",
    "oci_index_digest",
    "linux_amd64_config_digest",
}
INDEX_FIELDS = {"schema_version", "goal", "candidate", "criteria"}
CRITERION_FIELDS = {"id", "status", "evidence"}
EVIDENCE_FIELDS = {"path", "sha256"}
RECORD_FIELDS = {
    "schema_version",
    "criterion_id",
    "candidate",
    "expected",
    "actual",
    "decision",
}
MAX_INDEX_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024
MAX_OBSERVATION_TEXT = 4096


class IndexErrorCode(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IndexErrorCode("G05_INDEX_JSON_DUPLICATE_KEY", "JSON objects must not contain duplicate keys")
        result[key] = value
    return result


def parse_json(data: bytes, code: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except IndexErrorCode:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IndexErrorCode(code, "input must be valid UTF-8 JSON") from error


def require_object(value: Any, fields: set[str], code: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise IndexErrorCode(code, f"{label} has an invalid shape")
    return value


def safe_relative_path(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "evidence path must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "evidence path must stay below the evidence root")
    return path.parts


def read_beneath(root: Path, parts: tuple[str, ...], max_bytes: int) -> bytes:
    """Open each component relative to an anchored root fd, refusing symlinks."""
    if not parts:
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "file path is empty")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory or os.open not in getattr(os, "supports_dir_fd", set()):
        raise IndexErrorCode("G05_INDEX_PLATFORM_UNSUPPORTED", "safe relative file access is unavailable on this platform")

    root_fd = os.open(root, os.O_RDONLY | directory | nofollow)
    current_fd = root_fd
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current_fd)
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "evidence references must be regular files")
            if file_stat.st_size > max_bytes:
                raise IndexErrorCode("G05_INDEX_FILE_TOO_LARGE", "an index or observation exceeds its size bound")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(file_fd, min(65536, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise IndexErrorCode("G05_INDEX_FILE_TOO_LARGE", "an index or observation exceeds its size bound")
            return b"".join(chunks)
        finally:
            os.close(file_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "symlink paths are not accepted") from error
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "a referenced file is missing or cannot be opened safely") from error
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def validate_candidate(value: Any) -> dict[str, str]:
    candidate = require_object(value, CANDIDATE_FIELDS, "G05_INDEX_CANDIDATE_INVALID", "candidate")
    if not isinstance(candidate["tag"], str) or not re.fullmatch(
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", candidate["tag"]
    ):
        raise IndexErrorCode("G05_INDEX_CANDIDATE_INVALID", "candidate tag must be an exact v-prefixed SemVer release tag")
    if not isinstance(candidate["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]):
        raise IndexErrorCode("G05_INDEX_CANDIDATE_INVALID", "candidate commit must be a full lowercase Git SHA")
    for field in ("oci_index_digest", "linux_amd64_config_digest"):
        if not isinstance(candidate[field], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate[field]):
            raise IndexErrorCode("G05_INDEX_CANDIDATE_INVALID", f"{field} must be a lowercase SHA-256 digest")
    return candidate


def validate_index(root: Path, index_parts: tuple[str, ...]) -> dict[str, Any]:
    index_data = read_beneath(root, index_parts, MAX_INDEX_BYTES)
    index = require_object(
        parse_json(index_data, "G05_INDEX_JSON_INVALID"),
        INDEX_FIELDS,
        "G05_INDEX_SHAPE_INVALID",
        "index",
    )
    if type(index["schema_version"]) is not int or index["schema_version"] != 1 or index["goal"] != "G05":
        raise IndexErrorCode("G05_INDEX_SHAPE_INVALID", "index must use schema version 1 and goal G05")
    candidate = validate_candidate(index["candidate"])

    criteria = index["criteria"]
    if not isinstance(criteria, list):
        raise IndexErrorCode("G05_INDEX_CRITERIA_INCOMPLETE", "criteria must contain each required G05 acceptance criterion")
    by_id: dict[str, dict[str, Any]] = {}
    for raw_criterion in criteria:
        criterion = require_object(raw_criterion, CRITERION_FIELDS, "G05_INDEX_SHAPE_INVALID", "criterion")
        criterion_id = criterion["id"]
        if not isinstance(criterion_id, str) or criterion_id not in CRITERIA or criterion_id in by_id:
            raise IndexErrorCode("G05_INDEX_CRITERIA_INCOMPLETE", "criteria must contain each required G05 acceptance criterion exactly once")
        by_id[criterion_id] = criterion
    if set(by_id) != set(CRITERIA):
        raise IndexErrorCode("G05_INDEX_CRITERIA_INCOMPLETE", "criteria must contain each required G05 acceptance criterion exactly once")

    seen_evidence: set[str] = set()
    for criterion_id in CRITERIA:
        criterion = by_id[criterion_id]
        if criterion["status"] != "PASS":
            raise IndexErrorCode("G05_INDEX_CRITERION_NOT_PASS", f"{criterion_id} is not marked PASS")
        evidence = criterion["evidence"]
        if not isinstance(evidence, list) or len(evidence) != 1:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_MISSING", f"{criterion_id} must reference exactly one observation")
        reference = require_object(evidence[0], EVIDENCE_FIELDS, "G05_INDEX_SHAPE_INVALID", "evidence reference")
        parts = safe_relative_path(reference["path"])
        relative_name = "/".join(parts)
        if relative_name in seen_evidence:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_DUPLICATE", "an observation file cannot be reused for multiple criteria")
        seen_evidence.add(relative_name)
        expected_digest = reference["sha256"]
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise IndexErrorCode("G05_INDEX_EVIDENCE_DIGEST_INVALID", "evidence SHA-256 must be lowercase hex")
        record_data = read_beneath(root, parts, MAX_RECORD_BYTES)
        if hashlib.sha256(record_data).hexdigest() != expected_digest:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_DIGEST_MISMATCH", f"{criterion_id} observation digest does not match")
        record = require_object(
            parse_json(record_data, "G05_INDEX_EVIDENCE_JSON_INVALID"),
            RECORD_FIELDS,
            "G05_INDEX_EVIDENCE_SHAPE_INVALID",
            "observation",
        )
        if type(record["schema_version"]) is not int or record["schema_version"] != 1 or record["criterion_id"] != criterion_id:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_SHAPE_INVALID", f"{criterion_id} observation identity is invalid")
        if record["candidate"] != candidate:
            raise IndexErrorCode("G05_INDEX_CANDIDATE_MISMATCH", f"{criterion_id} observation belongs to another candidate")
        for field in ("expected", "actual"):
            value = record[field]
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_OBSERVATION_TEXT:
                raise IndexErrorCode("G05_INDEX_EVIDENCE_SHAPE_INVALID", f"{criterion_id} {field} observation is missing or out of bounds")
        if record["decision"] != "PASS":
            raise IndexErrorCode("G05_INDEX_CRITERION_NOT_PASS", f"{criterion_id} observation decision is not PASS")

    return {
        "goal": "G05",
        "candidate": candidate,
        "criteria_passed": len(CRITERIA),
        "evidence_files_verified": len(seen_evidence),
        "index_digest": hashlib.sha256(index_data).hexdigest(),
        "index_valid": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--index", required=True, help="index path, absolute beneath evidence root or relative to it")
    return parser.parse_args()


def index_parts(root_argument: Path, value: str) -> tuple[str, ...]:
    supplied = Path(value)
    if ".." in supplied.parts:
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "index path must not traverse parent directories")
    if supplied.is_absolute():
        lexical_root = Path(os.path.abspath(root_argument))
        lexical_index = Path(os.path.abspath(supplied))
        try:
            relative = lexical_index.relative_to(lexical_root)
        except ValueError as error:
            raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "index must be beneath the evidence root") from error
    else:
        relative = supplied
    parts = tuple(relative.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "index must be a safe relative path beneath the evidence root")
    return parts


def main() -> int:
    args = parse_args()
    try:
        root = args.evidence_root.resolve(strict=True)
        if not root.is_dir():
            raise IndexErrorCode("G05_INDEX_EVIDENCE_UNSAFE_PATH", "evidence root must be a directory")
        result = validate_index(root, index_parts(args.evidence_root, args.index))
    except IndexErrorCode as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 1
    except OSError:
        print("G05_INDEX_EVIDENCE_UNSAFE_PATH: evidence root is missing or cannot be opened safely", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
