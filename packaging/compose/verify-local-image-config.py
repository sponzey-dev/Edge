#!/usr/bin/env python3
"""Verify a local Docker tag by hashing its exported image config blob."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import PurePosixPath

DOCKER = "/usr/bin/docker"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_LAYOUT_BYTES = 64 * 1024
MAX_CONFIG_BYTES = 16 * 1024 * 1024


def read_member(archive: tarfile.TarFile, member: tarfile.TarInfo, maximum: int) -> bytes:
    if not member.isfile() or member.size > maximum:
        raise ValueError("Docker image archive member is invalid")
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError("Docker image archive member is unreadable")
    content = stream.read(maximum + 1)
    if len(content) != member.size:
        raise ValueError("Docker image archive member is truncated")
    return content


def exported_config_digest(image: str, expected_tag: str, expected_config_digest: str) -> str:
    process = subprocess.Popen(
        [DOCKER, "image", "save", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        if process.stdout is None:
            raise ValueError("Docker image export stream is unavailable")
        legacy_manifest_count = 0
        legacy_config_name = None
        legacy_config_count = 0
        legacy_config_digest = None
        oci_index_count = 0
        oci_index = None
        oci_layout_count = 0
        oci_layout_version = None
        oci_manifests = {}
        oci_config_count = 0
        oci_config_digest = None
        oci_config_size = None
        expected_config_hex = expected_config_digest.removeprefix("sha256:")
        expected_config_blob = "blobs/sha256/" + expected_config_hex
        legacy_expected_tag = None

        with tarfile.open(fileobj=process.stdout, mode="r|*") as archive:
            while True:
                member = archive.next()
                if member is None:
                    break
                if member.name == "manifest.json":
                    legacy_manifest_count += 1
                    if legacy_manifest_count != 1:
                        raise ValueError("Docker image archive has duplicate manifests")
                    manifest_bytes = read_member(archive, member, MAX_MANIFEST_BYTES)
                    images = json.loads(manifest_bytes)
                    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
                        raise ValueError("Docker image archive must contain one image")
                    image_entry = images[0]
                    repo_tags = image_entry.get("RepoTags")
                    if not isinstance(repo_tags, list) or expected_tag not in repo_tags:
                        raise ValueError("Docker image archive tag mismatch")
                    config_name = image_entry.get("Config")
                    config_path = PurePosixPath(config_name) if isinstance(config_name, str) else None
                    if (
                        config_path is None
                        or config_path.is_absolute()
                        or ".." in config_path.parts
                        or not config_path.parts
                    ):
                        raise ValueError("Docker image config path is invalid")
                    legacy_expected_tag = config_path.as_posix()
                elif member.name == "index.json":
                    oci_index_count += 1
                    if oci_index_count != 1:
                        raise ValueError("OCI archive has duplicate indexes")
                    index_bytes = read_member(archive, member, MAX_MANIFEST_BYTES)
                    oci_index = json.loads(index_bytes)
                elif member.name == "oci-layout":
                    oci_layout_count += 1
                    if oci_layout_count != 1:
                        raise ValueError("OCI archive has duplicate layout markers")
                    layout_bytes = read_member(archive, member, MAX_LAYOUT_BYTES)
                    layout = json.loads(layout_bytes)
                    if not isinstance(layout, dict):
                        raise ValueError("OCI layout marker is invalid")
                    oci_layout_version = layout.get("imageLayoutVersion")
                elif member.name == expected_config_blob:
                    oci_config_count += 1
                    if oci_config_count != 1:
                        raise ValueError("OCI archive has duplicate config blobs")
                    config_bytes = read_member(archive, member, MAX_CONFIG_BYTES)
                    oci_config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
                    oci_config_size = member.size
                    if legacy_expected_tag == member.name:
                        legacy_config_count += 1
                        if legacy_config_count != 1:
                            raise ValueError("Docker image archive has duplicate configs")
                        legacy_config_digest = oci_config_digest
                elif legacy_expected_tag is not None and member.name == legacy_expected_tag:
                    legacy_config_count += 1
                    if legacy_config_count != 1:
                        raise ValueError("Docker image archive has duplicate configs")
                    config_bytes = read_member(archive, member, MAX_CONFIG_BYTES)
                    legacy_config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
                elif member.name.startswith("blobs/sha256/") and member.isfile() and member.size <= MAX_MANIFEST_BYTES:
                    blob_name = member.name.rsplit("/", 1)[-1]
                    if re.fullmatch(r"[0-9a-f]{64}", blob_name) is None:
                        raise ValueError("OCI archive blob path is invalid")
                    blob_bytes = read_member(archive, member, MAX_MANIFEST_BYTES)
                    if blob_bytes.startswith(b"{"):
                        try:
                            blob = json.loads(blob_bytes)
                        except json.JSONDecodeError:
                            blob = None
                        if isinstance(blob, dict) and "config" in blob and "layers" in blob:
                            blob_digest = "sha256:" + hashlib.sha256(blob_bytes).hexdigest()
                            if blob_digest != "sha256:" + blob_name:
                                raise ValueError("OCI manifest blob digest mismatch")
                            oci_manifests[blob_digest] = (blob, member.size)

        if oci_index_count or oci_layout_count:
            if legacy_manifest_count and legacy_expected_tag != expected_config_blob:
                raise ValueError("OCI Docker manifest config path does not match the expected blob")
            if (
                oci_index_count != 1
                or oci_layout_count != 1
                or oci_layout_version != "1.0.0"
                or not isinstance(oci_index, dict)
                or oci_index.get("schemaVersion") != 2
                or not isinstance(oci_index.get("manifests"), list)
                or oci_config_count != 1
                or oci_config_digest is None
            ):
                raise ValueError("OCI archive layout is incomplete")
            expected_tag_name = expected_tag.rsplit(":", 1)[-1]
            matching_descriptors = []
            for descriptor in oci_index["manifests"]:
                if not isinstance(descriptor, dict):
                    continue
                annotations = descriptor.get("annotations")
                ref_name = annotations.get("org.opencontainers.image.ref.name") if isinstance(annotations, dict) else None
                if ref_name in (expected_tag, expected_tag_name):
                    matching_descriptors.append(descriptor)
            if len(matching_descriptors) != 1:
                raise ValueError("OCI archive tag is missing or ambiguous")
            descriptor = matching_descriptors[0]
            manifest_digest = descriptor.get("digest")
            if not isinstance(manifest_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest) is None:
                raise ValueError("OCI archive manifest digest is invalid")
            manifest_entry = oci_manifests.get(manifest_digest)
            if manifest_entry is None or manifest_entry[1] != descriptor.get("size"):
                raise ValueError("OCI archive manifest is missing or mismatched")
            image_manifest = manifest_entry[0]
            config_descriptor = image_manifest.get("config")
            if (
                not isinstance(config_descriptor, dict)
                or config_descriptor.get("digest") != expected_config_digest
                or config_descriptor.get("size") != oci_config_size
            ):
                raise ValueError("OCI manifest config identity mismatch")
            config_digest = oci_config_digest
        elif legacy_manifest_count:
            if legacy_config_count != 1 or legacy_config_digest is None:
                raise ValueError("Docker image archive layout is incomplete")
            config_digest = legacy_config_digest
        else:
            raise ValueError("Docker image archive layout is not supported")

        if process.wait() != 0:
            raise ValueError("Docker image export failed")
        return config_digest
    except (OSError, tarfile.TarError, UnicodeError, json.JSONDecodeError, ValueError):
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("expected_tag")
    parser.add_argument("expected_config_digest")
    arguments = parser.parse_args()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", arguments.expected_config_digest) is None:
        print("image config digest is invalid", file=sys.stderr)
        return 2
    try:
        actual = exported_config_digest(
            arguments.image,
            arguments.expected_tag,
            arguments.expected_config_digest,
        )
    except (OSError, tarfile.TarError, UnicodeError, json.JSONDecodeError, ValueError):
        print("cannot verify local Docker image config", file=sys.stderr)
        return 2
    if actual != arguments.expected_config_digest:
        print("image config digest mismatch", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
