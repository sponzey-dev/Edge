#!/usr/bin/env python3
"""Resolve the linux/amd64 OCI image config digest from registry manifests."""

import argparse
import json
import re
import sys
from typing import Any


DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImageIdentityError(ValueError):
    pass


def linux_amd64_manifest_digest(index: Any) -> str:
    if not isinstance(index, dict) or not isinstance(index.get("manifests"), list):
        raise ImageIdentityError("OCI image index must contain a manifests list")

    matches = []
    for descriptor in index["manifests"]:
        if not isinstance(descriptor, dict):
            continue
        platform = descriptor.get("platform")
        if (
            isinstance(platform, dict)
            and platform.get("os") == "linux"
            and platform.get("architecture") == "amd64"
        ):
            matches.append(descriptor)

    if not matches:
        raise ImageIdentityError("linux/amd64 manifest is missing from the OCI image index")
    if len(matches) != 1:
        raise ImageIdentityError("OCI image index must contain exactly one linux/amd64 manifest")

    digest = matches[0].get("digest")
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        raise ImageIdentityError("linux/amd64 manifest digest is malformed")
    return digest


def platform_config_digest(manifest: Any) -> str:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("config"), dict):
        raise ImageIdentityError("OCI platform manifest must contain a config descriptor")

    digest = manifest["config"].get("digest")
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        raise ImageIdentityError("OCI platform config digest is malformed")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("amd64-manifest", "config"))
    arguments = parser.parse_args()

    try:
        document = json.load(sys.stdin)
        digest = (
            linux_amd64_manifest_digest(document)
            if arguments.mode == "amd64-manifest"
            else platform_config_digest(document)
        )
    except (json.JSONDecodeError, ImageIdentityError) as error:
        print(f"OCI_IMAGE_IDENTITY_INVALID: {error}", file=sys.stderr)
        return 2

    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
