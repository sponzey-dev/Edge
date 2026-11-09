#!/usr/bin/env python3
"""Bind an immutable release manifest and Linux archive to its executable bytes."""

import argparse
import hashlib
import json
import os
import stat
import sys
import tarfile
import tempfile
from pathlib import Path

import validate_release_manifest as release

MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_BINARY_BYTES = 128 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def snapshot(source: Path, target: Path) -> None:
    try:
        if stat.S_ISLNK(source.lstat().st_mode):
            raise ValueError("symlink")
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream, target.open("xb") as destination:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ASSET_BYTES:
                raise ValueError("asset bound")
            copied = 0
            while True:
                chunk = stream.read(min(1024 * 1024, MAX_ASSET_BYTES + 1 - copied))
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_ASSET_BYTES:
                    raise ValueError("asset grew")
                destination.write(chunk)
    except (OSError, ValueError) as error:
        raise ValueError("candidate asset cannot be snapshotted safely") from error


def validate(artifacts: Path, tag: str, commit: str, image: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="edge-candidate-") as tmp:
        staged = Path(tmp)
        snapshot(artifacts / "release-manifest.json", staged / "release-manifest.json")
        manifest = release.read_json(staged / "release-manifest.json", "RELEASE_MANIFEST_INVALID")
        if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in (("tag", tag), ("commit", commit), ("image", image))):
            raise ValueError("candidate identity differs")
        entries = manifest.get("artifacts")
        if not isinstance(entries, list):
            raise ValueError("artifact entries invalid")
        names = {"SHA256SUMS"}
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("artifact entry invalid")
            for field in ("archive", "sbom"):
                name = release.safe_name(item.get(field), field)
                if name in names or name == "release-manifest.json":
                    raise ValueError("duplicate artifact name")
                names.add(name)
        for name in sorted(names):
            snapshot(artifacts / name, staged / name)
        release.validate(staged / "release-manifest.json", staged)
        amd64 = next(item for item in entries if item.get("platform") == "linux-amd64")
        digest = hashlib.sha256()
        with tarfile.open(staged / amd64["archive"], mode="r:gz") as archive:
            binaries = []
            total = 0
            for member in archive:
                total += member.size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("candidate archive exceeds expanded bound")
                if member.name in ("edge-proxy", "./edge-proxy"):
                    binaries.append(member)
            if len(binaries) != 1 or not binaries[0].isfile() or not 0 < binaries[0].size <= MAX_BINARY_BYTES:
                raise ValueError("candidate binary is absent, ambiguous, or unsafe")
            stream = archive.extractfile(binaries[0])
            if stream is None:
                raise ValueError("candidate binary is unavailable")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"tag": tag, "commit": commit, "image": image, "binary_sha256": digest.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        result = validate(args.artifacts, args.tag, args.commit, args.image)
    except (OSError, ValueError, StopIteration, tarfile.TarError, release.ManifestError):
        print("CANDIDATE_ARCHIVE_INVALID", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
